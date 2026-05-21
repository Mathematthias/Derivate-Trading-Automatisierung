# Tier C - US-Universum (NASDAQ-100)
# Stand: 2026-05-13 (neu angelegt im Rahmen Variante-A-Split: US-Werte aus
#                    Tier B ausgegliedert, weil Tier-B-Runs mit ~308 Symbolen
#                    zu unrobust waren — siehe MIGRATION_NOTES)
# Quellen: finanzen.net NASDAQ-100 24-29.04.2026, Yahoo-Verifikation 30.04.2026
#
# Universumsgroesse: ~96 Symbole (NASDAQ-100 minus China-ADRs PDD/JD).
#
# Schedule-Empfehlung: Mo-Fr 14:30 + 21:30 CEST in cron-job.org
#                      (vor US-Open bzw. nach US-Close).
#
# Erweiterung-TODO (frühestens Mitte Juni 2026, nur wenn Tier C stabil läuft):
#   S&P 100 ex-NDX: ~40 weitere US-Werte (JPM, BAC, JNJ, PFE, LLY, XOM, CVX,
#   CAT, HON, RTX, ...) — schließt Old-Economy-Lücke (Banken, Pharma,
#   Industrie, Energie). Alle KO-handelbar bei SB+. Würde Tier C auf ~136
#   Symbole wachsen lassen — noch unter der 200er-Robustheitsschwelle.
#
# Ethik-Filter: keine Defense-Pure-Plays im NASDAQ-100 (LMT/NOC/RTX/GD
#               sind alle in S&P-500 ex-NDX, also bei künftiger Erweiterung
#               via ethik_excluded ausnehmen).
# China-ADR-Filter: PDD und JD ausgenommen (Delisting/VIE-Risiko, dünne KO-Cov.).
#
# Konfidenz-Tags:
#   [H] high   - Standard-Mapping, Pipeline sollte Daten finden
#   [M] medium - Ticker plausibel, beim ersten Pull verifizieren
#   [L] low    - unsicher, manuelle Pruefung empfohlen

categories:

  nasdaq_100:
    Adobe: "ADBE"  # [H]
    Airbnb: "ABNB"  # [H]
    Align_Technology: "ALGN"  # [H]
    Alphabet_A: "GOOGL"  # [H]
    Alphabet_C: "GOOG"  # [H]
    Amazon: "AMZN"  # [H]
    AMD: "AMD"  # [H]
    American_Electric_Power: "AEP"  # [H]
    Amgen: "AMGN"  # [H]
    Analog_Devices: "ADI"  # [H]
    Apple: "AAPL"  # [H]
    Applied_Materials: "AMAT"  # [H]
    AppLovin: "APP"  # [H]
    Arm: "ARM"  # [H]
    ASML_NDX: "ASML"  # [H] ADR auf NASDAQ, EuroStoxx-Hauptlisting
    Atlassian: "TEAM"  # [H]
    Autodesk: "ADSK"  # [H]
    Automatic_Data_Processing: "ADP"  # [H]
    Axon: "AXON"  # [H]
    Baker_Hughes: "BKR"  # [H]
    Biogen: "BIIB"  # [H]
    Booking: "BKNG"  # [H]
    Broadcom: "AVGO"  # [H]
    Cadence_Design: "CDNS"  # [H]
    Charter_A: "CHTR"  # [H]
    Cintas: "CTAS"  # [H]
    Cisco: "CSCO"  # [H]
    Cognizant: "CTSH"  # [H]
    Comcast: "CMCSA"  # [H]
    Constellation_Energy: "CEG"  # [H]
    Copart: "CPRT"  # [H]
    CoStar_Group: "CSGP"  # [H]
    Costco: "COST"  # [H]
    CrowdStrike: "CRWD"  # [H]
    CSX: "CSX"  # [H]
    Datadog: "DDOG"  # [H]
    DexCom: "DXCM"  # [H]
    Diamondback_Energy: "FANG"  # [H]
    Dollar_Tree: "DLTR"  # [H]
    eBay: "EBAY"  # [H]
    Electronic_Arts: "EA"  # [H]
    Enphase_Energy: "ENPH"  # [H]
    Exelon: "EXC"  # [H]
    Fastenal: "FAST"  # [H]
    Fiserv: "FISV"  # [H] yfinance-Quirk bei NYSE-Ticker FI seit Listing-Wechsel 06/2023; Yahoo behält FISV als Alias
    Fortinet: "FTNT"  # [H]
    Gilead: "GILD"  # [H]
    GlobalFoundries: "GFS"  # [H]
    Honeywell: "HON"  # [H]
    IDEXX: "IDXX"  # [H]
    Intel: "INTC"  # [H]
    Intuit: "INTU"  # [H]
    Intuitive_Surgical: "ISRG"  # [H]
    Keurig_Dr_Pepper: "KDP"  # [H]
    KLA: "KLAC"  # [H]
    Kraft_Heinz: "KHC"  # [H]
    Lam_Research: "LRCX"  # [H]
    Linde: "LIN"  # [H] IE-ISIN, NYSE-listed seit DAX-Austritt 2023
    Lululemon: "LULU"  # [H]
    Marriott: "MAR"  # [H]
    Marvell: "MRVL"  # [H]
    MercadoLibre: "MELI"  # [H]
    Meta: "META"  # [H]
    Microchip_Technology: "MCHP"  # [H]
    Micron: "MU"  # [H]
    Microsoft: "MSFT"  # [H]
    Mondelez: "MDLZ"  # [H]
    Monster_Beverage: "MNST"  # [H]
    Netflix: "NFLX"  # [H]
    NVIDIA: "NVDA"  # [H]
    NXP_Semiconductors: "NXPI"  # [H]
    OReilly_Automotive: "ORLY"  # [H]
    Old_Dominion_Freight: "ODFL"  # [H]
    ON_Semiconductor: "ON"  # [H]
    Paccar: "PCAR"  # [H]
    Palantir: "PLTR"  # [H]
    Palo_Alto_Networks: "PANW"  # [H]
    Paychex: "PAYX"  # [H]
    PayPal: "PYPL"  # [H]
    PepsiCo: "PEP"  # [H]
    Qualcomm: "QCOM"  # [H]
    Regeneron: "REGN"  # [H]
    Ross_Stores: "ROST"  # [H]
    Starbucks: "SBUX"  # [H]
    Strategy: "MSTR"  # [H] ex MicroStrategy
    Synopsys: "SNPS"  # [H]
    Tesla: "TSLA"  # [H]
    T_Mobile_US: "TMUS"  # [H]
    Verisk: "VRSK"  # [H]
    Vertex_Pharmaceuticals: "VRTX"  # [H]
    Walmart: "WMT"  # [L] NYSE-Listing, NDX-100-Aufnahme verifizieren beim Pipeline-Pull
    Warner_Bros_Discovery: "WBD"  # [H]
    Workday: "WDAY"  # [H]
    Xcel_Energy: "XEL"  # [H]
    Zoom: "ZM"  # [H]
    Zscaler: "ZS"  # [H]
