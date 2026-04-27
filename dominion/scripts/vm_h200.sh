#!/bin/bash
# ================================================================
# DOMINION — 8 × H200 141GB  |  1-hour max intelligence run
# $84.81/hr  |  ~$85 total
#
# USAGE:
#   bash vm_h200.sh 2>&1 | tee run.log
#
# AFTER IT FINISHES:
#   gcloud compute scp $(hostname):~/dominion/models/hydra/scalping/best.pt .
#   gcloud compute scp $(hostname):~/dominion/models/hydra/scalping/swa_best.pt .
#   gcloud compute instances stop $(hostname) --zone=YOUR_ZONE
# ================================================================

set -e
T0=$(date +%s)
REPO="https://github.com/MatinDeevv/BlackmarkDominion"
WORK="$HOME/dominion"
CKPT="$WORK/models/hydra/scalping/best.pt"
DATA="$WORK/data/processed/dataset"

ts()  { date '+%H:%M:%S'; }
min() { echo $(( ( $(date +%s) - T0 ) / 60 )); }

echo "╔══════════════════════════════════════════════════╗"
echo "║  DOMINION  ·  8 × H200 141GB  ·  $(ts)       ║"
echo "╠══════════════════════════════════════════════════╣"
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader
echo "╚══════════════════════════════════════════════════╝"

# ── 1. CLONE ──────────────────────────────────────────────────
echo; echo "[$(ts)] [1/4] Clone..."
if [ -d "$WORK" ]; then
    cd "$WORK" && git pull -q
else
    git clone -q "$REPO" "$WORK"
fi
cd "$WORK"

# ── 2. INSTALL ────────────────────────────────────────────────
echo "[$(ts)] [2/4] Install (CUDA 12.1 + H200)..."
pip install -q --upgrade pip
pip install -q torch torchvision \
    --index-url https://download.pytorch.org/whl/cu121
pip install -q flash-attn --no-build-isolation 2>/dev/null \
    || echo "  flash-attn skipped"
pip install -q yfinance polars pyarrow structlog typer tqdm psutil 'numpy<2.0'
pip install -q -e ".[ml,dev]" 2>/dev/null || pip install -q -r requirements.txt

echo "  Install done at $(min) min"

# ── 3. DATA + DATASET ─────────────────────────────────────────
echo "[$(ts)] [3/4] Download + Build dataset..."
mkdir -p data/processed "$DATA"

python3 - <<'PYEOF'
import yfinance as yf, polars as pl, numpy as np
from pathlib import Path
import json

out = Path("data/processed")
dst = Path("data/processed/dataset")
dst.mkdir(parents=True, exist_ok=True)

# XAUUSD
print("  XAUUSD...")
for iv in ["5m","1h"]:
    df = yf.download("GC=F", start="2019-01-01", interval=iv,
                     progress=False, auto_adjust=True)
    if not df.empty:
        print(f"  Got {len(df):,} bars at {iv}")
        break
df = df[["Open","High","Low","Close","Volume"]].copy()
df.columns = ["open","high","low","close","volume"]
df.index = df.index.tz_convert("UTC") if df.index.tz else df.index.tz_localize("UTC")
df["time_ms"] = df.index.astype("int64")//1_000_000
df = df.dropna().reset_index(drop=True)
bars = pl.from_pandas(df)
print(f"  XAUUSD: {len(bars):,} bars | {df.index[0].date()} → {df.index[-1].date()}")

# Cross-asset
for name,sym in [("DXY","DX-Y.NYB"),("SILVER","SI=F"),("VIX","^VIX"),("US10Y","^TNX")]:
    try:
        ca = yf.download(sym, start="2019-01-01", interval="5m",
                         progress=False, auto_adjust=True)
        if ca.empty: raise ValueError
        ca = ca[["Close"]]; ca.columns = ["close"]
        ca.index = ca.index.tz_convert("UTC") if ca.index.tz else ca.index.tz_localize("UTC")
        ca["time_ms"] = ca.index.astype("int64")//1_000_000
        pl.from_pandas(ca.reset_index(drop=True)).write_parquet(out/f"{name}.parquet")
        print(f"  {name}: {len(ca):,} bars")
    except: print(f"  {name}: skipped")

# Features
close=bars["close"]; high=bars["high"]; low=bars["low"]
vol=bars["volume"].cast(pl.Float64)
bars = bars.with_columns([
    ((close-low)/(high-low+1e-10)).alias("bar_pos"),
    ((close-close.shift(1))/(close.shift(1)+1e-10)).alias("ret_1"),
    ((close-close.shift(3))/(close.shift(3)+1e-10)).alias("ret_3"),
    ((close-close.shift(6))/(close.shift(6)+1e-10)).alias("ret_6"),
    ((close-close.shift(12))/(close.shift(12)+1e-10)).alias("ret_12"),
    ((close-close.shift(24))/(close.shift(24)+1e-10)).alias("ret_24"),
    (high-low).alias("range"),
    (high-low).rolling_mean(5).alias("atr_5"),
    (high-low).rolling_mean(14).alias("atr_14"),
    (high-low).rolling_mean(50).alias("atr_50"),
    close.ewm_mean(span=5).alias("ema_5"),
    close.ewm_mean(span=8).alias("ema_8"),
    close.ewm_mean(span=13).alias("ema_13"),
    close.ewm_mean(span=21).alias("ema_21"),
    close.ewm_mean(span=34).alias("ema_34"),
    close.ewm_mean(span=55).alias("ema_55"),
    close.ewm_mean(span=89).alias("ema_89"),
    close.rolling_mean(20).alias("sma_20"),
    close.rolling_std(20).alias("std_20"),
    vol.alias("volume"),
    (vol/(vol.rolling_mean(5)+1e-10)).alias("vol_r5"),
    (vol/(vol.rolling_mean(20)+1e-10)).alias("vol_r20"),
    ((close-close.shift(48))/(close.shift(48)+1e-10)).alias("mom_4h"),
    ((close-close.shift(288))/(close.shift(288)+1e-10)).alias("mom_1d"),
])
bars = bars.with_columns([
    ((pl.col("ema_5")-pl.col("ema_13"))/(pl.col("atr_14")+1e-10)).alias("x_5_13"),
    ((pl.col("ema_8")-pl.col("ema_21"))/(pl.col("atr_14")+1e-10)).alias("x_8_21"),
    ((pl.col("ema_13")-pl.col("ema_34"))/(pl.col("atr_14")+1e-10)).alias("x_13_34"),
    ((pl.col("ema_21")-pl.col("ema_55"))/(pl.col("atr_14")+1e-10)).alias("x_21_55"),
    ((pl.col("ema_34")-pl.col("ema_89"))/(pl.col("atr_14")+1e-10)).alias("x_34_89"),
    ((2*pl.col("std_20"))/(pl.col("sma_20")+1e-10)*100).alias("bb_width"),
    ((close-(pl.col("sma_20")-pl.col("std_20")))/(2*pl.col("std_20")+1e-10)).alias("bb_pos"),
    ((close-pl.col("sma_20"))/(pl.col("atr_14")+1e-10)).alias("dist_sma20"),
    ((close-pl.col("ema_55"))/(pl.col("atr_14")+1e-10)).alias("dist_ema55"),
])
d=close.diff(1)
g=d.map_elements(lambda x:max(x,0.),return_dtype=pl.Float64)
l=d.map_elements(lambda x:max(-x,0.),return_dtype=pl.Float64)
rsi=100.-100./(1.+g.ewm_mean(span=14)/(l.ewm_mean(span=14)+1e-10))
bars=bars.with_columns([
    rsi.alias("rsi_14"),
    ((rsi-rsi.rolling_min(14))/(rsi.rolling_max(14)-rsi.rolling_min(14)+1e-10)).alias("stoch_rsi"),
])
bars=bars.with_columns([
    (pl.col("time_ms")*1000).cast(pl.Datetime("us","UTC")).alias("ts")
])
bars=bars.with_columns([
    pl.col("ts").dt.hour().alias("hour"),
    pl.col("ts").dt.weekday().alias("dow"),
])
bars=bars.with_columns([
    (pl.col("hour")/24.).alias("hour_norm"),
    (pl.col("dow")/7.).alias("dow_norm"),
])

for name in ["DXY","SILVER","VIX","US10Y"]:
    p=out/f"{name}.parquet"
    if not p.exists(): continue
    ca=pl.read_parquet(p).sort("time_ms"); c=ca["close"]
    ca=ca.with_columns([
        ((c-c.shift(1))/(c.shift(1)+1e-10)).alias(f"{name.lower()}_r1"),
        ((c-c.shift(5))/(c.shift(5)+1e-10)).alias(f"{name.lower()}_r5"),
        ((c-c.rolling_mean(50))/(c.rolling_std(50)+1e-10)).alias(f"{name.lower()}_z"),
    ]).select(["time_ms",f"{name.lower()}_r1",f"{name.lower()}_r5",f"{name.lower()}_z"])
    bars=bars.join_asof(ca,on="time_ms",strategy="backward")
    print(f"  {name} joined")

# Labels
cn=bars["close"].to_numpy(); at=bars["atr_14"].to_numpy(); n=len(cn)
def tb(c,a,h,tp=0.8,sl=0.8):
    y=np.ones(n,dtype=np.int64)
    for i in range(n-h):
        av=max(float(a[i]),1e-10); T,S=c[i]+tp*av,c[i]-sl*av
        for j in range(i+1,min(i+h+1,n)):
            if c[j]>=T: y[i]=2; break
            if c[j]<=S: y[i]=0; break
    return y
print("  Labels...")
y5=tb(cn,at,1); y15=tb(cn,at,3); y30=tb(cn,at,6)
bars=bars.with_columns([pl.Series("y5",y5),pl.Series("y15",y15),pl.Series("y30",y30)])

excl={"time_ms","open","high","low","close","volume","ts","y5","y15","y30","hour","dow"}
cont=[c for c in bars.columns if c not in excl
      and bars[c].dtype in (pl.Float64,pl.Float32,pl.Int64,pl.Int32)]
X=bars.select(cont).to_numpy().astype(np.float32)
X=np.nan_to_num(X,0.,0.,0.)
hr=bars["hour"].to_numpy()
sess=np.where(hr<8,0,np.where(hr<12,1,np.where(hr<16,2,np.where(hr<21,3,4)))).astype(np.int64).reshape(-1,1)

emb=120; te=int(n*0.70)-emb; ve=int(n*0.85)-emb
for sp,(s,e) in [("train",(0,te)),("val",(te+emb,ve)),("test",(ve+emb,n))]:
    np.savez_compressed(dst/f"{sp}.npz",
        X_cont=X[s:e],X_cat=sess[s:e],close=cn[s:e].astype(np.float32),
        y_label_5m=y5[s:e],y_label_15m=y15[s:e],y_label_60m=y30[s:e],
        feature_names=np.array(cont))
    print(f"  {sp}: {e-s:,} rows")

json.dump({"n_continuous_features":X.shape[1],"n_categorical_features":1,
           "continuous_feature_names":cont},
          open(dst/"metadata.json","w"))
print(f"\n  Done: {X.shape[1]} features | {n:,} bars")
PYEOF

echo "  Data done at $(min) min"

# ── 4. TRAIN ──────────────────────────────────────────────────
SETUP_MIN=$(min)
TRAIN_MIN=$(( 57 - SETUP_MIN ))
echo "[$(ts)] [4/4] Training — ${TRAIN_MIN} min budget"
echo "  8×H200 | BF16 | OneCycleLR | SWA@75% | batch=auto"
echo "  Estimated ~$(( TRAIN_MIN * 60 / 2 )) epochs"

torchrun \
    --nproc_per_node=8 \
    --master_port=29500 \
    scripts/train_smart.py \
    --data "$DATA" \
    --ckpt "$CKPT" \
    --minutes "$TRAIN_MIN" \
    --lr 3e-4 \
    --lookback 64 \
    --swa-start-pct 0.75

# ── RESULTS ───────────────────────────────────────────────────
echo
echo "╔══════════════════════════════════════════════════╗"
echo "║  COMPLETE  $(ts)  |  $(min) min total          ║"
python3 -c "
import torch; from pathlib import Path
d = Path('$CKPT').parent
for label, name in [('BEST','best.pt'),('SWA','swa_best.pt')]:
    p = d/name
    if p.exists():
        m = torch.load(p, map_location='cpu')
        print(f'║  {label}  ep={m[\"epoch\"]:4d}  '
              f'loss={m[\"val_loss\"]:.4f}  '
              f'acc={m.get(\"val_acc_5m\",0)*100:.1f}%  '
              f'{p.stat().st_size/1e6:.0f}MB  ║')
"
HOST=$(hostname)
echo "╠══════════════════════════════════════════════════╣"
echo "║  DOWNLOAD:                                       ║"
echo "║  gcloud compute scp $HOST:$CKPT .  ║"
echo "║  gcloud compute scp $HOST:$(dirname $CKPT)/swa_best.pt . ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  ⚠  STOP VM NOW (billing stops):                 ║"
echo "║  gcloud compute instances stop $HOST             ║"
echo "╚══════════════════════════════════════════════════╝"
