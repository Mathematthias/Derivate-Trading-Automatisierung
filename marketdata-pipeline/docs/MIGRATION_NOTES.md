# Migration Notes - Universe-Erweiterung

**Stand:** 2026-04-29

## Was diese Aenderung bewirkt

Erweiterung des Pipeline-Universums von ~63 Werten (Tier A: 12 + Tier B: 53)
auf insgesamt ~330 Werte durch Aufnahme aller deutschen Index-Komponenten
plus NASDAQ-100, EuroStoxx 50 (ex-DAX) und SMI 20.

## Neue Tier-B-Sektionen

| Sektion | Werte | Inhalt |
|---|---|---|
| `dax_komponenten` | 39 | DAX 40 minus Rheinmetall |
| `mdax_komponenten` | 50 | komplett |
| `sdax_komponenten` | 70 | komplett |
| `nasdaq_100` | 97 | minus PDD/JD/Karteileichen |
| `eurostoxx_ex_dax` | 32 | EuroStoxx 50 ohne DAX-Doubletten und ohne Rheinmetall |
| `smi_20` | 20 | komplett |

**Gesamt neu: 308 Werte** (vor Konflikt-Check mit bestehenden Sektionen)

## Was unveraendert bleibt

- **Tier A komplett** (Indizes/Rohstoffe/Krypto/Positionen + nebenwerte_de mit 12 Werten)
- **Bestehende Tier-B-Sektionen** (biotech_de, ma_hot_list, ai_quantum, nasdaq_growth, tecdax_kern)

## Doubletten-Strategie

Pro Wert genau ein Eintrag in den neuen Index-Sektionen. Wenn ein Wert
in mehreren Indizes ist (z.B. SAP in DAX + EuroStoxx + TecDAX), erscheint
er nur in der Sektion mit hoechster Prioritaet (DAX > MDAX > SDAX), in
den anderen Sektionen wird er ausgelassen, im YAML-Kommentar markiert.

**Doubletten zu Tier-A-nebenwerte_de:** Werte werden in den neuen Sektionen
trotzdem aufgenommen (mit Kommentar `auch tier_a/nebenwerte_de`), da die
Pipeline beim yfinance-Pull dedupliziert. Falls die Pipeline NICHT
dedupliziert, im Skript fixen oder Tier-A-Werte hier auslassen.

**Konflikte mit bestehenden Tier-B-Sektionen:** vorerst belassen.
- `tecdax_kern` (10) wird hinfaellig - alle 30 TecDAX-Werte sind in
  DAX/MDAX/SDAX/tier_a abgedeckt. Sektion kann geloescht werden.
- `nasdaq_growth` (21) wird hinfaellig - alle Werte sind in `nasdaq_100`.
  Sektion kann geloescht werden.
- `biotech_de` (11): 4 Werte (Bayer, Merck_KGaA, Sartorius, Qiagen) sind
  jetzt in `dax_komponenten`, 4 weitere (Evotec, HelloFresh, Eckert_Ziegler,
  Formycon) in `sdax_komponenten`. Verbleibend: BioNTech, Curevac, MorphoSys
  (delistet pruefen).
- `ma_hot_list` (6): alle 6 Werte sind jetzt in DAX/MDAX/SDAX. Sektion
  kann geloescht oder als Tag-Filter weiterverwendet werden.
- `ai_quantum` (5): keine Doubletten, bleibt unveraendert.

## Offene Punkte / Verifikationen (Stand nach DAX-Verify 29.04.2026)

Alle vier urspruenglich offenen Punkte sind durch finanzen.net DAX-Fetch
geklaert:

1. **Sartorius:** NICHT im DAX. Sartorius VZ (SRT3.DE / DE0007165631) ist
   im MDAX. Stamm-Aktie nicht relevant.

2. **Porsche AG vs. Porsche SE:** Nur Porsche Automobil Holding SE
   (PAH3.DE / DE000PAH0038) im DAX. Porsche AG operative (P911.DE) im MDAX.

3. **Fresenius Medical Care (FME.DE) im DAX** ergaenzt (urspruenglich
   nicht in der Wissensliste).

4. **Scout24 (G24.DE) im DAX** ergaenzt (war frueher MDAX, mittlerweile DAX).

5. **Walmart in NASDAQ-100:** finanzen.net fuehrt Walmart (WMT) im NDX-Fetch.
   WMT ist NYSE-listed. Nicht aufgeloest - beim ersten Pull verifizieren.

## L-Konfidenz-Werte (manuelle Pruefung)

- `S9I.DE` (Shelly, BG-ISIN, SDAX) - Frankfurt-Listing-Ticker unsicher
- `M8G.DE` (Verve_Group, SE-ISIN, SDAX) - Frankfurt-Listing-Ticker unsicher
- `AMRZ.SW` (Amrize, Holcim-Spinoff 2025, SMI) - Ticker verifizieren
- `WMT` (Walmart, NASDAQ-100) - NDX-Aufnahme unklar

## Refactoring-Empfehlung (optional, naechste Session)

Nach erfolgreichem ersten Pull mit dem neuen Universum:
1. `tecdax_kern` und `nasdaq_growth` aus tickers_tier_b.yaml entfernen
   (komplett von neuen Sektionen abgedeckt).
2. `biotech_de` reduzieren auf nicht-Index-Biotech (BioNTech, Curevac).
3. `ma_hot_list` aufloesen oder zu `m_a_tags`-Filter umbauen.

## Naechster manueller Refresh

Quartalsweise (immer nach Index-Reviews der Deutschen Boerse):
- Dezember: Annual Review SMI/EuroStoxx
- September: Quartals-Review DAX-Familie + Annual Review NASDAQ-100/EuroStoxx
- Maerz, Juni: Quartals-Review DAX-Familie

Workflow: pro Index `https://www.finanzen.net/index/<X>/werte` aufrufen,
Tabelle hierher pasten, Skript neu laufen lassen.
