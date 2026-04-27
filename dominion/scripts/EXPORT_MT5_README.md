"""
Quick reference: download MT5 data from all open brokers on this PC.

Scenarios:

1. DOWNLOAD ALL (default 365 days, common symbols/timeframes):
   python scripts/export_mt5_all_brokers.py --output data/raw

2. DOWNLOAD SPECIFIC SYMBOLS ONLY:
   python scripts/export_mt5_all_brokers.py \
       --symbols XAUUSD EURUSD GBPUSD \
       --output data/raw

3. DOWNLOAD SPECIFIC TIMEFRAMES ONLY:
   python scripts/export_mt5_all_brokers.py \
       --timeframes M1 M5 H1 D1 \
       --output data/raw

4. DOWNLOAD FULL HISTORY (2 years):
   python scripts/export_mt5_all_brokers.py \
       --days 730 \
       --output data/raw

5. DOWNLOAD EVERYTHING (all timeframes, 1 year):
   python scripts/export_mt5_all_brokers.py \
       --timeframes M1 M5 M15 M30 H1 H4 D1 W1 MN1 \
       --symbols XAUUSD EURUSD GBPUSD USDJPY AUDNZD EURJPY NZDUSD \
       --days 365 \
       --output data/raw

Output structure:
   data/raw/
   ├── broker=broker_name/
   │   ├── symbol=XAUUSD/
   │   │   ├── timeframe=M1/
   │   │   │   └── data.parquet
   │   │   ├── timeframe=H1/
   │   │   │   └── data.parquet
   │   │   └── timeframe=D1/
   │   │       └── data.parquet
   │   └── symbol=EURUSD/
   │       ├── timeframe=M1/
   │       │   └── data.parquet
   │       ...

Requirements:
   - MetaTrader5 must be installed and running on this PC
   - At least one MT5 account must be logged in
   - pip install MetaTrader5 polars pyarrow structlog

After download, use mt5pipe to import:
   python -m mt5pipe backfill \
       --raw-root data/raw \
       --output data/processed \
       --symbol XAUUSD \
       --timeframe H1
"""
