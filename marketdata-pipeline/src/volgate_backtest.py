#!/usr/bin/env python3
"""
volgate_backtest.py — Validierung des Volumen-Gates auf Breakout-Triggern.

FRAGE: Kostet das harte Vol-Gate (Breakout nur BEREIT wenn Vol >= Schwelle) Edge,
       oder filtert es echte Fake-Breakouts heraus?

METHODE:
  1. Iteriere ueber CANDIDATES-*.md ABEND-Files (Vol final, nach Marktschluss).
     -> WICHTIG: Morgen-Files (0931) taugen NICHT, dort ist Vol "noch offen" (Tagesvol
        nicht akkumuliert). Default-Filter: nur Files mit Zeitstempel >= 21:00.
  2. Pro File/Symbol/Trigger Flags extrahieren:
        is_breakout, preis_erfuellt, vol_final, vol_schwelle, vol_erfuellt
  3. Breakout-Signal = is_breakout AND preis_erfuellt AND vol_final is not None
        - GEBLOCKT  = vol_final <  schwelle  (das Gate haette geblockt)
        - DURCHGELASSEN (Kontrolle) = vol_final >= schwelle
  4. Kurs-Panel aus dem "Kurs X.XX"-Header jedes Symbols ueber alle Files (Datums-Index).
  5. Forward-Return je Signal nach +5/+10/+20 Handelstagen (naechster verfuegbarer
     Sample-Tag im Panel, Toleranz +-2 HT).
  6. Vergleich GEBLOCKT vs DURCHGELASSEN: Median/Mean-Return, Trefferquote (>0),
     richtungs-adjustiert (LONG: +ret, SHORT: -ret).

ENTSCHEIDUNGSREGEL:
  - Liegt der median forward-return der GEBLOCKTEN deutlich UEBER 0 (richtungs-adj.)
    UND nahe der DURCHGELASSENEN -> Gate kostet Edge -> lockern.
  - Liegen die GEBLOCKTEN im Schnitt <= 0 oder klar unter den DURCHGELASSENEN
    -> Gate verdient seinen Platz.

ERWEITERUNG 2026-09-18 — BAND-AUSWERTUNG (User-Entscheid, Punkt 4):
  Die geblockt/durchgelassen-Achse haengt an der Trigger-Schwelle, und die
  variiert (0,8 / 1,0 / 1,2). Das Band, um das es seit dem 2026-09-18 geht —
  1,0 bis 1,5, also der neue Daempfer-Bereich der Range-Buckets — war damit
  NICHT messbar: geblockt hiess immer "unter 0,8/1,0/1,2".
  Neu wird deshalb zusaetzlich nach ABSOLUTEM Vol-Band ausgewertet, unabhaengig
  von der Schwelle des jeweiligen Triggers. Zwei Konsequenzen:
    - Spalte `band` in der Detail-CSV, Roll-up `VOLGATE-BANDS-*.csv`.
    - `--include-gamechanger` erntet zusaetzlich die Range-Bucket-Kandidaten
      aus GAMECHANGER-HUNT-*.md (Spalte `source`). Diese Population ist der
      Universe-Scan, nicht die Watchlist — und erst SEIT dem Absenken des
      Bodens auf 1,0 enthaelt sie ueberhaupt Kandidaten im Band 1,0-1,5.
      Vor dem 2026-09-18 existieren diese Zeilen nirgends; die Messreihe
      beginnt also mit dem Deploy, nicht rueckwirkend.

EINSATZ:
  A) Lokal:  alle CANDIDATES-Abend-Files in einen Ordner legen, dann:
             python3 volgate_backtest.py /pfad/zu/files --horizons 5 10 20
  B) Pipeline (empfohhlen): als GitHub-Actions-Job, der die Files direkt aus dem
     Drive-Briefing-Folder liest (Auth ist dort vorhanden) und das Roll-up-CSV
     zurueckschreibt. Damit sammelt der laufende Betrieb die Daten automatisch weiter.
"""
import re, os, sys, glob, argparse, statistics, csv
from datetime import datetime

# ---------- Datei-Auswahl ----------
FNAME_RE = re.compile(r"CANDIDATES-(\d{4}-\d{2}-\d{2})-(\d{4})\.md$")

def pick_files(folder, evening_only=True, min_hhmm=2200):
    """Pro Handelstag genau ein File. Default: das spaeteste Abend-File (Vol final).

    min_hhmm=2200: nach hard_evaluation_utc_hour=20 UTC (=22 CEST) ist 'Vol unter
    Schwelle' hart ✗ (vorher ⏳/BEREIT*). Erst danach ist der Block final.
    """
    by_day = {}
    for p in glob.glob(os.path.join(folder, "CANDIDATES-*.md")):
        m = FNAME_RE.search(os.path.basename(p))
        if not m:
            continue
        day, hhmm = m.group(1), int(m.group(2))
        if evening_only and hhmm < min_hhmm:
            continue
        # spaetestes File des Tages gewinnt (Vol am vollstaendigsten)
        if day not in by_day or hhmm > by_day[day][1]:
            by_day[day] = (p, hhmm)
    return [by_day[d][0] for d in sorted(by_day)]

# ---------- Parsing eines Files ----------
ENTRY_RE = re.compile(r"^\s*-\s*\*\*(?P<tic>[^*]+)\*\*\s*\((?P<dir>LONG|SHORT)", re.M)
KURS_RE  = re.compile(r"Kurs\s+([\d.]+)")
# Vol final:  "Vol 0.86× < 1.00×"  oder  "Vol 1.02× ≥ 1.00×"
VOL_FINAL_RE = re.compile(r"Vol\s+([\d.]+)×\s*(<|≥|≤|>)\s*([\d.]+)×")
# Vol offen:  "⏳ Vol 0.05× (Schwelle 0.80×) — Tagesvolumen noch offen"
VOL_OPEN_RE  = re.compile(r"⏳\s*Vol\s+[\d.]+×\s*\(Schwelle")
# Breakout-Geometrie: Preis ueber/unter Range, im Gegensatz zu IN-ZONE (Pullback)
PREIS_UEBER_RE = re.compile(r"Preis\s+[\d.]+\s+(über|unter)\s+Range\s+\[[\d.–\-]+\]\s*\(([+\-][\d.]+)%\)")
PREIS_INZONE_RE= re.compile(r"Preis\s+[\d.]+\s+IN-ZONE")

def split_entries(text):
    """Zerlege das File in (ticker, direction, block_text) je Symbol."""
    out = []
    matches = list(ENTRY_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        out.append((m.group("tic").strip(), m.group("dir"), text[start:end]))
    return out

def split_triggers(block):
    """Zerlege einen Symbol-Block in [A]/[B]-Trigger-Abschnitte."""
    parts = re.split(r"\n\s*-\s*\[(A|B)\]", block)
    # parts[0] = Kopf (vor erstem Trigger); danach paarweise (label, body)
    trigs = []
    for j in range(1, len(parts), 2):
        label = parts[j]
        body = parts[j+1] if j+1 < len(parts) else ""
        trigs.append((label, body))
    return trigs

# Preis-Distanz mit Vorzeichen, egal ob "über/unter Range (..%)" oder ">= Y (..%)"
PREIS_PCT_RE = re.compile(r"Preis\s+[\d.]+\s+(?:über Range|unter Range|≥|≤|>|<)\s+[\[\d.]+[^\(]*\(([+\-][\d.]+)%\)")

def analyze_trigger(body, direction):
    """is_breakout, preis_erfuellt, vol_final, vol_schwelle, vol_erfuellt.

    Schluessel-Heuristik: NUR Breakout-Trigger haben ein Vol-Gate (Pullbacks nicht,
    Note #151). Ein finales Vol-Reading => Trigger ist ein Breakout.
    Richtungskopplung: LONG-Breakout ausgeloest wenn Preis >= Level (+%),
    SHORT-Breakout ausgeloest wenn Preis <= Level (-%). IN-ZONE ohne % = erreicht.
    """
    vol_final = vol_schwelle = vol_erfuellt = None
    if not VOL_OPEN_RE.search(body):
        mv = VOL_FINAL_RE.search(body)
        if mv:
            vol_final = float(mv.group(1)); op = mv.group(2); vol_schwelle = float(mv.group(3))
            vol_erfuellt = (op in ("≥", ">"))
    is_breakout = vol_final is not None     # Vol-Gate vorhanden => Breakout-Trigger
    preis_erfuellt = False
    if is_breakout:
        mp = PREIS_PCT_RE.search(body)
        if mp:
            pct = float(mp.group(1))
            preis_erfuellt = (pct >= 0) if direction == "LONG" else (pct <= 0)
        elif PREIS_INZONE_RE.search(body):
            preis_erfuellt = True           # in Breakout-Zone = Level erreicht
    return dict(is_breakout=is_breakout, preis_erfuellt=preis_erfuellt,
                vol_final=vol_final, vol_schwelle=vol_schwelle, vol_erfuellt=vol_erfuellt)

def parse_file(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = FNAME_RE.search(os.path.basename(path))
    day = m.group(1)
    prices = {}     # ticker -> kurs
    signals = []    # dicts
    for tic, direction, block in split_entries(text):
        km = KURS_RE.search(block)
        if km:
            prices[tic] = float(km.group(1))
        for label, body in split_triggers(block):
            a = analyze_trigger(body, direction)
            if a["is_breakout"] and a["preis_erfuellt"] and a["vol_final"] is not None:
                signals.append(dict(day=day, ticker=tic, direction=direction,
                                    label=label, **a))
    return day, prices, signals

# ---------- Vol-Baender (2026-09-18) ----------
# Grenzen bewusst an den beiden Schwellen ausgerichtet, die im Betrieb
# vorkommen: 1,0 (harter Boden) und 1,5 (Daempfer). Die Baender darunter sind
# feiner, weil dort die Backtest-Masse liegt.
VOL_BANDS = [
    ("<0.6",    0.0, 0.6),
    ("0.6-0.8", 0.6, 0.8),
    ("0.8-1.0", 0.8, 1.0),
    ("1.0-1.2", 1.0, 1.2),
    ("1.2-1.5", 1.2, 1.5),
    (">=1.5",   1.5, float("inf")),
]

def band_of(vol):
    """Absolutes Vol-Band, unabhaengig von der Trigger-Schwelle."""
    if vol is None:
        return None
    for label, lo, hi in VOL_BANDS:
        if lo <= vol < hi:
            return label
    return None

# GAMECHANGER-Range-Bullet, z.B.:
#   - TMUS: 166.45  20d-Low=166.35 (+0.06%)  Vol=1.7×  RSI=34  RRprox=2.94
# Achtung: Feldtrenner sind ZWEI Leerzeichen, das Mal-Zeichen ist U+00D7, und
# das Vorzeichen in der Klammer ist bei Short-Bullets nicht erzwungen
# (Format-Fallen aus Note #556).
GC_FNAME_RE = re.compile(r"GAMECHANGER-HUNT-(?:EU|US)-(\d{4}-\d{2}-\d{2})-(\d{4})\.md$")
GC_RANGE_RE = re.compile(
    r"^-\s*(?P<tic>[A-Z0-9.\-]+):\s*(?P<kurs>[\d.]+)\s+"
    r"20d-(?P<seite>High|Low)=(?P<lvl>[\d.]+)\s*\(([+\-]?[\d.]+)%\)\s+"
    r"Vol=(?P<vol>[\d.]+)\u00d7", re.M)

def parse_gamechanger_file(path):
    """Range-Bucket-Kandidaten aus einem GAMECHANGER-HUNT-File.

    Liefert (day, prices, signals). `geblockt` ist hier immer False — im File
    stehen nur Kandidaten, die das damals geltende Gate passiert haben. Der
    Erkenntniswert liegt im BAND, nicht in der Gate-Entscheidung.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = GC_FNAME_RE.search(os.path.basename(path))
    if not m:
        return None, {}, []
    day = m.group(1)
    prices, signals = {}, []
    for mm in GC_RANGE_RE.finditer(text):
        tic = mm.group("tic")
        kurs = float(mm.group("kurs"))
        vol = float(mm.group("vol"))
        direction = "LONG" if mm.group("seite") == "High" else "SHORT"
        prices[tic] = kurs
        signals.append(dict(day=day, ticker=tic, direction=direction, label="GC",
                            is_breakout=True, preis_erfuellt=True,
                            vol_final=vol, vol_schwelle=None, vol_erfuellt=True,
                            source="gamechanger"))
    return day, prices, signals

def pick_gc_files(folder, min_hhmm=1800):
    """Pro Tag und Tier das spaeteste GAMECHANGER-File (Vol am vollstaendigsten)."""
    best = {}
    for p in glob.glob(os.path.join(folder, "GAMECHANGER-HUNT-*.md")):
        base = os.path.basename(p)
        m = GC_FNAME_RE.search(base)
        if not m:
            continue
        tier = "EU" if "-EU-" in base else "US"
        day, hhmm = m.group(1), int(m.group(2))
        if hhmm < min_hhmm:
            continue
        key = (day, tier)
        if key not in best or hhmm > best[key][1]:
            best[key] = (p, hhmm)
    return [v[0] for v in best.values()]


# ---------- Backtest ----------
def trading_days_index(days):
    return {d: i for i, d in enumerate(sorted(days))}

def forward_return(panel, idx_by_day, ticker, day, horizon, tol=2):
    """Return nach 'horizon' Sample-Schritten (Toleranz tol)."""
    days = sorted(idx_by_day)
    i0 = idx_by_day[day]
    p0 = panel.get((ticker, day))
    if p0 is None:
        return None
    target = i0 + horizon
    for off in range(0, tol+1):
        for cand in (target+off, target-off):
            if 0 <= cand < len(days):
                d2 = days[cand]
                p1 = panel.get((ticker, d2))
                if p1 is not None:
                    return (p1 - p0) / p0
    return None

def run(folder, horizons, evening_only=True, include_gamechanger=False):
    files = pick_files(folder, evening_only=evening_only)
    gc_files = pick_gc_files(folder) if include_gamechanger else []
    if not files and not gc_files:
        print("Keine passenden Files gefunden. (Abend-Files noetig: HHMM>=2100)"); return
    panel = {}; all_days = set(); all_signals = []
    for p in files:
        day, prices, signals = parse_file(p)
        all_days.add(day)
        for t, pr in prices.items():
            panel[(t, day)] = pr
        for s in signals:
            s.setdefault("source", "watchlist")
        all_signals += signals
    for p in gc_files:
        day, prices, signals = parse_gamechanger_file(p)
        if day is None:
            continue
        all_days.add(day)
        for t, pr in prices.items():
            # Watchlist-Preis gewinnt: dieselbe Zahl, aber aus dem Kanal, der
            # den Panel-Index ohnehin traegt.
            panel.setdefault((t, day), pr)
        all_signals += signals
    idx = trading_days_index(all_days)

    def dir_adj(ret, direction):
        return ret if direction == "LONG" else -ret

    rows = []
    for s in all_signals:
        rec = dict(day=s["day"], ticker=s["ticker"], direction=s["direction"],
                   vol=s["vol_final"], schwelle=s["vol_schwelle"],
                   geblockt=(not s["vol_erfuellt"]),
                   band=band_of(s["vol_final"]),
                   source=s.get("source", "watchlist"))
        for h in horizons:
            r = forward_return(panel, idx, s["ticker"], s["day"], h)
            rec[f"ret{h}"] = None if r is None else round(dir_adj(r, s["direction"])*100, 2)
        rows.append(rec)

    # Aggregat
    def agg(group, h):
        vals = [r[f"ret{h}"] for r in group if r[f"ret{h}"] is not None]
        if not vals: return None
        return dict(n=len(vals), median=round(statistics.median(vals),2),
                    mean=round(statistics.mean(vals),2),
                    hit=round(100*sum(1 for v in vals if v>0)/len(vals),1))
    blocked = [r for r in rows if r["geblockt"]]
    passed  = [r for r in rows if not r["geblockt"]]
    print(f"\n=== Vol-Gate-Backtest  |  Files: {len(files)}  |  Signale: {len(rows)} "
          f"(geblockt {len(blocked)} / durchgelassen {len(passed)}) ===\n")
    print(f"{'Horizont':<10}{'Gruppe':<16}{'N':>4}{'Median%':>10}{'Mean%':>9}{'Trefferq.%':>12}")
    for h in horizons:
        for name, grp in (("GEBLOCKT", blocked), ("DURCHGELASSEN", passed)):
            a = agg(grp, h)
            if a:
                print(f"{h:<10}{name:<16}{a['n']:>4}{a['median']:>10}{a['mean']:>9}{a['hit']:>12}")
        print()

    # --- BAND-AUSWERTUNG (2026-09-18) ---------------------------------------
    # Unabhaengig von der Trigger-Schwelle, damit das Daempfer-Band 1,0-1,5
    # als eigene Gruppe sichtbar wird. Getrennt nach Richtung, weil genau dort
    # die Frage offen ist.
    print(f"\n=== Vol-BAENDER (absolut, schwellenunabhaengig) ===\n")
    band_rows = []
    for h in horizons:
        for richtung, sub in (("ALLE", rows),
                              ("LONG", [r for r in rows if r["direction"] == "LONG"]),
                              ("SHORT", [r for r in rows if r["direction"] == "SHORT"])):
            for label, _lo, _hi in VOL_BANDS:
                grp = [r for r in sub if r["band"] == label]
                a = agg(grp, h)
                if not a:
                    continue
                band_rows.append(dict(horizont=h, richtung=richtung, band=label,
                                      n=a["n"], median=a["median"],
                                      mean=a["mean"], trefferquote=a["hit"]))
    if band_rows:
        print(f"{'H':<4}{'Richtung':<10}{'Band':<10}{'N':>4}{'Median%':>10}"
              f"{'Mean%':>9}{'Trefferq.%':>12}")
        for b in band_rows:
            warn = "   (n<10)" if b["n"] < 10 else ""
            print(f"{b['horizont']:<4}{b['richtung']:<10}{b['band']:<10}{b['n']:>4}"
                  f"{b['median']:>10}{b['mean']:>9}{b['trefferquote']:>12}{warn}")
    else:
        print("  (keine Baender mit Folgerenditen)")
    print("\nHinweis: Das Band 1,0-1,5 ist auf der Universe-Scan-Seite erst ab dem"
          "\nDeploy vom 2026-09-18 besetzt — davor hat das Gate diese Kandidaten"
          "\ngar nicht erst erzeugt. Kleine n dort sind erwartet, kein Fehler.")

    # CSV
    band_csv = os.path.join(folder, "volgate_bands_result.csv")
    if band_rows:
        with open(band_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(band_rows[0].keys()))
            w.writeheader(); w.writerows(band_rows)
        print("Band-CSV:", band_csv)

    out_csv = os.path.join(folder, "volgate_backtest_result.csv")
    if rows:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print("Detail-CSV:", out_csv)
    return rows

# ---------- Drive-Modus (Pipeline) ----------
def load_from_drive(folder_id, tmpdir, min_hhmm=2200, since_iso=None,
                    name_contains='CANDIDATES-', fname_re=None):
    """Laedt pro Handelstag NUR das spaeteste Abend-File (Vol final) in tmpdir.

    Wichtig fuer Laufzeit: erst alle Namen+IDs listen (billig, ein API-Call/Seite),
    dann pro Tag genau ein File auswaehlen und NUR diese herunterladen. Ohne diese
    Vorauswahl wuerden alle ~15-20 Intraday-Snapshots/Tag geladen (Timeout-Gefahr).
    Auth identisch zu drive_writer.py (GDRIVE_SA_KEY als JSON-String)."""
    import json
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GDRIVE_SA_KEY"]),
        scopes=["https://www.googleapis.com/auth/drive"])
    svc = build("drive", "v3", credentials=creds)
    q = (f"'{folder_id}' in parents and name contains '{name_contains}' "
         f"and trashed = false")
    if since_iso:
        q += f" and modifiedTime > '{since_iso}'"
    # 1) listen (kein Download)
    entries = []; token = None
    while True:
        res = svc.files().list(q=q, pageSize=1000, fields="nextPageToken, files(id,name)",
                               pageToken=token,
                               supportsAllDrives=True,
                               includeItemsFromAllDrives=True,
                               corpora="allDrives").execute()
        entries += res.get("files", [])
        token = res.get("nextPageToken")
        if not token:
            break
    # 2) pro Tag das spaeteste Abend-File (HHMM >= min_hhmm)
    rx = fname_re or FNAME_RE
    best = {}
    for f in entries:
        m = rx.search(f["name"])
        if not m:
            continue
        day, hhmm = m.group(1), int(m.group(2))
        if hhmm < min_hhmm:
            continue
        # GAMECHANGER gibt es je Tag zweimal (EU/US) — beide behalten.
        tier = "EU" if "-EU-" in f["name"] else ("US" if "-US-" in f["name"] else "")
        key = (day, tier)
        if key not in best or hhmm > best[key][0]:
            best[key] = (hhmm, f["id"], f["name"])
    # 3) nur die ausgewaehlten herunterladen
    n = 0
    for day in sorted(best):
        _, fid, name = best[day]
        data = svc.files().get_media(fileId=fid).execute()
        with open(os.path.join(tmpdir, name), "wb") as out:
            out.write(data)
        n += 1
    print(f"[drive] {len(entries)} '{name_contains}' gelistet, "
          f"{n} Abend-Files (>= {min_hhmm}) geladen.")
    return svc

def upload_result(svc, folder_id, csv_path, prefix="VOLGATE-BACKTEST"):
    from googleapiclient.http import MediaFileUpload
    name = f"{prefix}-{datetime.utcnow():%Y-%m-%d}.csv"
    media = MediaFileUpload(csv_path, mimetype="text/csv")
    svc.files().create(body={"name": name, "parents": [folder_id]},
                       media_body=media, fields="id",
                       supportsAllDrives=True).execute()
    print(f"[drive] Ergebnis hochgeladen: {name}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=".",
                    help="lokaler Ordner mit CANDIDATES-*.md (source=local)")
    ap.add_argument("--source", choices=["local", "drive"], default="local")
    ap.add_argument("--folder-id", default="1_oQBr6KH7u6FDCAUIs1liTnEFjn-b_Ht",
                    help="Drive-Briefing-Folder-ID (source=drive)")
    ap.add_argument("--horizons", type=int, nargs="+", default=[5, 10, 20])
    ap.add_argument("--upload", action="store_true",
                    help="Ergebnis-CSV zurueck in den Drive-Folder schreiben")
    ap.add_argument("--weeks", type=int, default=12,
                    help="nur Files der letzten N Wochen laden (0 = ganze Historie). "
                         "Default 12 deckt ~6 Wochen Signale + 20-HT-Folgetiefe.")
    ap.add_argument("--include-morning", action="store_true",
                    help="auch Morgen-Files (NICHT empfohlen, Vol unvollstaendig)")
    ap.add_argument("--include-gamechanger", action="store_true",
                    help="zusaetzlich Range-Bucket-Kandidaten aus GAMECHANGER-HUNT-*.md "
                         "(Universe-Scan statt Watchlist; noetig fuer das Band 1,0-1,5)")
    args = ap.parse_args()

    if args.source == "drive":
        import tempfile
        from datetime import timedelta
        tmp = tempfile.mkdtemp(prefix="volgate_")
        min_hhmm = 0 if args.include_morning else 2200
        since_iso = None
        if args.weeks:
            since_iso = (datetime.utcnow() - timedelta(weeks=args.weeks)).strftime("%Y-%m-%dT00:00:00")
        svc = load_from_drive(args.folder_id, tmp, min_hhmm=min_hhmm, since_iso=since_iso)
        if args.include_gamechanger:
            load_from_drive(args.folder_id, tmp, min_hhmm=1800, since_iso=since_iso,
                            name_contains="GAMECHANGER-HUNT-", fname_re=GC_FNAME_RE)
        run(tmp, args.horizons, evening_only=not args.include_morning,
            include_gamechanger=args.include_gamechanger)
        if args.upload:
            res_csv = os.path.join(tmp, "volgate_backtest_result.csv")
            if os.path.exists(res_csv):
                upload_result(svc, args.folder_id, res_csv)
            band_csv = os.path.join(tmp, "volgate_bands_result.csv")
            if os.path.exists(band_csv):
                upload_result(svc, args.folder_id, band_csv, prefix="VOLGATE-BANDS")
    else:
        run(args.folder, args.horizons, evening_only=not args.include_morning,
            include_gamechanger=args.include_gamechanger)
