# tickers_tier_a.yaml — STATISCHES Kern-Universum
# Stand: 2026-04-25, V0.2 (Phase 0 Rebuild)
#
# WICHTIG — Architektur-Änderung gegenüber V0.1:
# Diese Datei enthält NUR Indizes, Rohstoffe, Krypto, Offene Positionen.
# Die WATCHLIST wird aus dem STATE-Doc geparsed (Single Source of Truth).
# Damit kann die Watchlist im Chat gepflegt werden, ohne Repo-Push.
#
# Wird gelesen von marketdata_sync.py.
# Sync-Frequenz: alle 30 Min Mo–Fr 08:00–22:00 CET, Sa 10:00.
#
# Phase 0b (später): DAX 40 + MDAX 50 + SDAX 70 + NASDAQ Top 100 als
# automatischer Import aus Wikipedia-Listen, ergänzt diese Datei.

# ============================================================
# INDIZES & VOLATILITÄT
# ============================================================
indizes:
  DAX:        "^GDAXI"
  MDAX:       "^MDAXI"
  SDAX:       "^SDAXI"
  TecDAX:     "^TECDAX"
  STOXX50E:   "^STOXX50E"
  SPX:        "^GSPC"
  NDX:        "^IXIC"
  DJI:        "^DJI"
  RUT:        "^RUT"
  Nikkei:     "^N225"
  HSI:        "^HSI"
  FTSE:       "^FTSE"
  VIX:        "^VIX"

# ============================================================
# ROHSTOFFE & FOREX
# ============================================================
rohstoffe_forex:
  Brent:      "BZ=F"
  WTI:        "CL=F"
  Gold:       "GC=F"
  Silber:     "SI=F"
  Kupfer:     "HG=F"
  NatGas:     "NG=F"
  EURUSD:     "EURUSD=X"
  USDJPY:     "USDJPY=X"
  EURGBP:     "EURGBP=X"

# ============================================================
# KRYPTO (Bison/Kraken-Referenz)
# ============================================================
krypto:
  BTC-EUR:    "BTC-EUR"
  ETH-EUR:    "ETH-EUR"
  SOL-EUR:    "SOL-EUR"
  BNB-EUR:    "BNB-EUR"
  BAT-EUR:    "BAT-EUR"      # ggf. dünn auf Yahoo, fallback BAT-USD beobachten

# ============================================================
# OFFENE POSITIONEN — Underlying-Ticker
# ============================================================
positionen:
  ATOSS:           "AOF.DE"     # Trade #53 KO Long, Underlying Entry 82,10€
  CTS_Eventim:     "EVD.DE"     # Trade #48 KO Long
  Xetra_Gold:      "4GLD.DE"    # Cross-Reference, nicht aktives Underlying
  Xtrackers_Gold:  "XAD5.DE"    # Trade #39 ETC Long, primäres Position-Underlying
  # JPM Sparplan-Rest: passiv, kein Tracking nötig
# ============================================================
# NEBENWERTE-COVERAGE — DE Mid/Small-Caps mit Hidden-Catalyst-Potenzial
# Stand: 2026-04-27, V0.3 — Coverage-Erweiterung nach CANCOM-Lücke
#
# Auswahl-Logik: Hohe News-Sensitivität, ausreichende Liquidität für KO-
# Zertifikate (Vol-Avg ≥ 1 Mio EUR/Tag), Sektor-Spread für Hidden-Catalyst-
# Treffer. Kein Rüstungs-Core (Ethik-Filter).
# ============================================================
nebenwerte_de:
  CANCOM:           "COK.DE"      # SDAX/TecDAX, IT-Services, Buyback-Story
  SFC_Energy:       "F3C.DE"      # Brennstoffzellen, Iran-Energie-Sensitiv
  SMA_Solar:        "S92.DE"      # Solar, Restrukturierung
  Energiekontor:    "EKT.DE"      # Wind-Projektierer, Sondervermögen-Profiteur
  PNE_AG:           "PNE3.DE"     # Wind, Morgan-Stanley-Spekulation
  Siltronic:        "WAF.DE"      # Halbleiter-Wafer, zyklischer Frühindikator
  KION_Group:       "KGX.DE"      # MDAX-Industrie, Korrelation Jungheinrich
  Evonik:           "EVK.DE"      # MDAX-Chemie, offene Order-Relevanz
  Siemens_Healthineers: "SHL.DE"  # DAX-Healthcare, defensiv
  HORNBACH_Holding: "HBH.DE"      # SDAX-Konsumindikator
  Stratec:          "SBS.DE"      # Diagnostik, hohe Insider-Aktivität
  Hensoldt:         "HAG.DE"      # MDAX-Defensivtech (kein Offensiv-Kerngeschäft, OK per Ethik 15.04.)
# ============================================================
# WATCHLIST — wird aus STATE-Doc geparsed (siehe state_parser.py)
# Diese Sektion ist HISTORISCH (V0.1) und wird vom Skript IGNORIERT.
# Bitte STATE-Doc als Single Source of Truth pflegen.
# ============================================================

# ============================================================
# ETHIK-AUSSCHLUSS — niemals in Output
# Pipeline filtert diese Symbole ZUSÄTZLICH zum STATE-Override
# ============================================================
ethik_excluded:
  - "RHM.DE"     # Rheinmetall — Offensiv-Rüstung Core
  - "BA.L"       # BAE Systems — dito
  # KNDS nicht börsennotiert
