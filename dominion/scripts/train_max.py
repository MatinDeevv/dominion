"""
MAXIMUM HARDWARE UTILIZATION TRAINER
-----------------------------------
Designed to saturate GPU/CPU/RAM on each training session.

Run:
    torchrun --nproc_per_node=NUM_GPUS scripts/train_max.py \
        --data data/processed/scalping_v2 \
        --checkpoint-dir models/hydra/scalping \
        --session-minutes 55

Resume is automatic via latest.pt.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import threading
import time
from pathlib import Path

import numpy as np
import structlog
import torch
import torch.distributed as dist
import torch.nn as nn
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, DistributedSampler

log = structlog.get_logger(__name__)


def configure_environment() -> None:
    """Max performance flags for CUDA, NCCL, OpenMP."""
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True
    torch.backends.cudnn.deterministic = False

    os.environ.setdefault("NCCL_ALGO", "Ring")
    os.environ.setdefault("NCCL_PROTO", "Simple")
    os.environ.setdefault("NCCL_MIN_NCHANNELS", "4")
    os.environ.setdefault("NCCL_NSOCKS_PERTHREAD", "4")
    os.environ.setdefault("NCCL_SOCKET_NTHREADS", "4")

    n_cpu = os.cpu_count() or 8
    os.environ.setdefault("OMP_NUM_THREADS", str(n_cpu))
    os.environ.setdefault("MKL_NUM_THREADS", str(n_cpu))
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(n_cpu))
    torch.set_num_threads(n_cpu)
    torch.set_num_interop_threads(max(1, n_cpu // 2))


configure_environment()


def setup_ddp() -> tuple[int, int, int]:
    dist.init_process_group(backend="nccl")
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    torch.cuda.set_device(local_rank)
    return rank, world_size, local_rank


def cleanup_ddp() -> None:
    if dist.is_available() and dist.is_initialized():
        dist.destroy_process_group()


def is_main(rank: int) -> bool:
    return rank == 0


class HardwareMonitor(threading.Thread):
    """Background thread that logs GPU/CPU/RAM utilization."""

    def __init__(self, rank: int, interval: int = 30):
        super().__init__(daemon=True)
        self.rank = rank
        self.interval = interval
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        if self.rank != 0:
            return
        try:
            import psutil
        except ImportError:
            return

        while not self._stop.wait(self.interval):
            try:
                cpu_pct = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory()
                ram_pct = ram.percent
                ram_gb = ram.used / 1e9

                gpu_lines = []
                n = torch.cuda.device_count()
                for i in range(n):
                    used = torch.cuda.memory_allocated(i) / 1e9
                    total = torch.cuda.get_device_properties(i).total_memory / 1e9
                    util = used / total * 100 if total > 0 else 0.0
                    gpu_lines.append(f"GPU{i}:{util:.0f}%({used:.1f}/{total:.0f}GB)")

                log.info(
                    "hardware_utilization",
                    cpu=f"{cpu_pct:.0f}%",
                    ram=f"{ram_pct:.0f}%({ram_gb:.1f}GB)",
                    gpus=" ".join(gpu_lines),
                )
            except Exception:
                pass


class PinnedDataset(torch.utils.data.Dataset):
    """Loads split tensors into pinned host RAM for async H2D copies."""

    def __init__(self, npz_path: Path, lookback: int = 64):
        data = np.load(npz_path, allow_pickle=True)

        self.X_cont = torch.from_numpy(data["X_cont"].astype(np.float32)).pin_memory()
        self.X_cat = torch.from_numpy(data["X_cat"].astype(np.int64)).pin_memory()
        self.y5 = torch.from_numpy(data["y_label_5m"].astype(np.int64)).pin_memory()
        self.y15 = torch.from_numpy(data["y_label_15m"].astype(np.int64)).pin_memory()

        if "y_label_60m" in data:
            y1h_key = "y_label_60m"
        elif "y_label_1h" in data:
            y1h_key = "y_label_1h"
        else:
            raise KeyError("Expected y_label_60m or y_label_1h in dataset")
        self.y30 = torch.from_numpy(data[y1h_key].astype(np.int64)).pin_memory()

        n = len(self.X_cont) - lookback
        if n <= 0:
            raise ValueError(f"Dataset too small for lookback={lookback}: rows={len(self.X_cont)}")
        self.indices = list(range(lookback, lookback + n))

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, idx: int):
        i = self.indices[idx]
        return self.X_cont[i], self.X_cat[i], self.y5[i], self.y15[i], self.y30[i]


class CUDAPrefetcher:
    """Prefetches next batch to GPU on a side stream."""

    def __init__(self, loader: DataLoader, device: torch.device):
        self.loader = loader
        self.device = device
        self.stream = torch.cuda.Stream(device)
        self._iter = None
        self._next = None

    def __iter__(self):
        self._iter = iter(self.loader)
        self._preload()
        return self

    def _preload(self):
        try:
            batch = next(self._iter)
        except StopIteration:
            self._next = None
            return

        with torch.cuda.stream(self.stream):
            self._next = tuple(t.to(self.device, non_blocking=True) for t in batch)

    def __next__(self):
        torch.cuda.current_stream(self.device).wait_stream(self.stream)
        batch = self._next
        if batch is None:
            raise StopIteration
        self._preload()
        return batch

    def __len__(self) -> int:
        return len(self.loader)


def find_max_batch_size(
    model: nn.Module,
    n_cont: int,
    n_cat: int,
    device: torch.device,
    starting_batch: int = 512,
    max_batch: int = 16384,
) -> int:
    """Binary search for largest batch size fitting VRAM."""
    dtype = torch.bfloat16

    def can_fit(bs: int) -> bool:
        try:
            torch.cuda.empty_cache()
            x = torch.randn(bs, n_cont, device=device, dtype=dtype)
            c = torch.zeros(bs, n_cat, device=device, dtype=torch.long)
            with torch.amp.autocast(device_type="cuda", dtype=dtype):
                out = model(x, c)
                loss = sum(v.mean() for v in out.values() if isinstance(v, torch.Tensor))
            loss.backward()
            model.zero_grad(set_to_none=True)
            torch.cuda.synchronize(device)
            torch.cuda.empty_cache()
            return True
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            model.zero_grad(set_to_none=True)
            return False

    log.info("finding_max_batch_size", starting=starting_batch)
    lo, hi = starting_batch, max_batch
    best = starting_batch

    if not can_fit(lo):
        lo = lo // 2
        if lo < 64 or not can_fit(lo):
            return 64

    while lo <= hi:
        mid = (lo + hi) // 2
        mid = (mid // 64) * 64
        if mid <= 0:
            break
        if can_fit(mid):
            best = mid
            lo = mid + 64
        else:
            hi = mid - 64

    safe = max(64, int(best * 0.85 // 64) * 64)
    log.info("batch_size_found", max_that_fits=best, using=safe)
    return safe


class ScalpingLoss(nn.Module):
    def __init__(self, gamma: float = 2.0, smoothing: float = 0.1):
        super().__init__()
        self.gamma = gamma
        self.ce = nn.CrossEntropyLoss(label_smoothing=smoothing, reduction="none")

    def focal(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce = self.ce(logits, targets)
        pt = torch.exp(-ce)
        return ((1.0 - pt) ** self.gamma * ce).mean()

    def forward(self, out: dict, y5: torch.Tensor, y15: torch.Tensor, y30: torch.Tensor) -> torch.Tensor:
        l5 = self.focal(out["logits_5m"], y5)
        l15 = self.focal(out["logits_15m"], y15)
        l30 = self.focal(out["logits_1h"], y30)
        moe = out.get("moe_balance_loss", torch.tensor(0.0, device=y5.device))
        return 0.45 * l5 + 0.35 * l15 + 0.20 * l30 + 0.01 * moe


def save(
    model,
    optimizer,
    scaler,
    scheduler,
    epoch: int,
    val_loss: float,
    val_acc: float,
    ckpt_dir: Path,
    is_best: bool,
    full: bool,
) -> None:
    raw = model.module if hasattr(model, "module") else model
    state = {
        "epoch": epoch,
        "val_loss": val_loss,
        "val_acc_5m": val_acc,
        "model_state": raw.state_dict(),
    }
    if full:
        state.update(
            {
                "optimizer_state": optimizer.state_dict(),
                "scaler_state": scaler.state_dict(),
                "scheduler_state": scheduler.state_dict() if scheduler else None,
            }
        )
        torch.save(state, ckpt_dir / f"epoch_{epoch:04d}.pt")

    torch.save(state, ckpt_dir / "latest.pt")
    if is_best:
        torch.save(state, ckpt_dir / "best.pt")
        log.info("best_saved", epoch=epoch, val_loss=round(val_loss, 4), val_acc_5m=round(val_acc * 100, 1))


def load(model, optimizer, scaler, scheduler, ckpt_dir: Path, device: torch.device) -> tuple[int, float, float]:
    p = ckpt_dir / "latest.pt"
    if not p.exists():
        return 0, float("inf"), 0.0
    ckpt = torch.load(p, map_location=device)
    raw = model.module if hasattr(model, "module") else model
    raw.load_state_dict(ckpt["model_state"])

    if "optimizer_state" in ckpt:
        try:
            optimizer.load_state_dict(ckpt["optimizer_state"])
        except Exception:
            pass
    if "scaler_state" in ckpt:
        try:
            scaler.load_state_dict(ckpt["scaler_state"])
        except Exception:
            pass
    if "scheduler_state" in ckpt and scheduler and ckpt["scheduler_state"]:
        try:
            scheduler.load_state_dict(ckpt["scheduler_state"])
        except Exception:
            pass

    epoch = ckpt.get("epoch", 0)
    val_loss = ckpt.get("val_loss", float("inf"))
    val_acc = ckpt.get("val_acc_5m", 0.0)
    log.info("resumed", epoch=epoch, val_loss=round(val_loss, 4))
    return epoch, val_loss, val_acc


def train_epoch(
    model,
    prefetcher,
    optimizer,
    loss_fn,
    scaler,
    grad_clip: float,
    accum_steps: int,
    dtype: torch.dtype,
) -> float:
    model.train()
    total_loss = 0.0
    n_batches = 0
    optimizer.zero_grad(set_to_none=True)

    for step, batch in enumerate(prefetcher):
        X_cont, X_cat, y5, y15, y30 = batch

        with torch.amp.autocast(device_type="cuda", dtype=dtype):
            out = model(X_cont, X_cat)
            loss = loss_fn(out, y5, y15, y30) / accum_steps

        scaler.scale(loss).backward()

        if (step + 1) % accum_steps == 0:
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)

        total_loss += loss.item() * accum_steps
        n_batches += 1

    return total_loss / max(n_batches, 1)


@torch.no_grad()
def val_epoch(model, prefetcher, loss_fn, dtype: torch.dtype) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch in prefetcher:
        X_cont, X_cat, y5, y15, y30 = batch
        with torch.amp.autocast(device_type="cuda", dtype=dtype):
            out = model(X_cont, X_cat)
            loss = loss_fn(out, y5, y15, y30)

        total_loss += loss.item()
        pred = out["logits_5m"].argmax(dim=1)
        correct += (pred == y5).sum().item()
        total += y5.size(0)

    acc = correct / max(total, 1)
    return total_loss / max(len(prefetcher), 1), acc


def main() -> None:
    parser = argparse.ArgumentParser("DOMINION Max Utilization Trainer")
    parser.add_argument("--data", required=True)
    parser.add_argument("--checkpoint-dir", default="models/hydra/scalping")
    parser.add_argument("--session-minutes", type=int, default=55)
    parser.add_argument("--batch-size", type=int, default=0, help="0 = auto-detect max that fits in VRAM")
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--lookback", type=int, default=64)
    parser.add_argument("--grad-accum", type=int, default=1)
    parser.add_argument("--grad-clip", type=float, default=1.0)
    parser.add_argument("--full-ckpt-every", type=int, default=5)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--compile", action="store_true", default=True, help="Use torch.compile (faster after warmup)")
    parser.add_argument("--no-compile", dest="compile", action="store_false")
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("train_max.py requires CUDA GPUs")

    rank, world_size, local_rank = setup_ddp()
    device = torch.device(f"cuda:{local_rank}")
    ckpt_dir = Path(args.checkpoint_dir)
    data_dir = Path(args.data)
    session_end = time.time() + args.session_minutes * 60

    monitor: HardwareMonitor | None = None
    if is_main(rank):
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        monitor = HardwareMonitor(rank, interval=30)
        monitor.start()

    cap = torch.cuda.get_device_capability(local_rank)
    dtype = torch.bfloat16 if cap >= (8, 0) else torch.float16

    if is_main(rank):
        try:
            import psutil

            ram_gb = round(psutil.virtual_memory().total / 1e9, 1)
        except Exception:
            ram_gb = "?"
        log.info(
            "hardware",
            gpus=world_size,
            device=str(device),
            dtype=str(dtype),
            cpu_cores=os.cpu_count(),
            ram_gb=ram_gb,
        )

    if is_main(rank):
        log.info("loading_dataset_into_ram")
    train_ds = PinnedDataset(data_dir / "train.npz", args.lookback)
    val_ds = PinnedDataset(data_dir / "val.npz", args.lookback)

    meta = json.loads((data_dir / "metadata.json").read_text())
    n_cont = int(meta["n_continuous_features"])
    n_cat = int(meta["n_categorical_features"])

    if is_main(rank):
        ram_used_gb = (
            train_ds.X_cont.element_size() * train_ds.X_cont.nelement()
            + val_ds.X_cont.element_size() * val_ds.X_cont.nelement()
        ) / 1e9
        log.info(
            "dataset_pinned",
            train_rows=len(train_ds),
            val_rows=len(val_ds),
            ram_used_gb=round(ram_used_gb, 2),
            n_cont=n_cont,
            n_cat=n_cat,
        )

    from aphelion.intelligence.hydra.cnn import CNNConfig
    from aphelion.intelligence.hydra.ensemble import EnsembleConfig, HydraGate
    from aphelion.intelligence.hydra.lstm import LSTMConfig
    from aphelion.intelligence.hydra.moe import MoEConfig
    from aphelion.intelligence.hydra.tcn import TCNConfig
    from aphelion.intelligence.hydra.tft import TFTConfig
    from aphelion.intelligence.hydra.transformer import TransformerConfig

    cfg = EnsembleConfig(
        tft_config=TFTConfig(
            n_continuous=n_cont,
            n_categorical=n_cat,
            hidden_dim=512,
            lstm_layers=4,
            attention_heads=8,
            lookback=args.lookback,
        ),
        lstm_config=LSTMConfig(
            n_continuous=n_cont,
            n_categorical=n_cat,
            hidden_size=512,
            num_layers=4,
            n_attention_heads=8,
        ),
        cnn_config=CNNConfig(
            n_continuous=n_cont,
            lookback=args.lookback,
            hidden_size=512,
            channels=(128, 256, 512, 512),
        ),
        moe_config=MoEConfig(
            n_continuous=n_cont,
            n_categorical=n_cat,
            hidden_size=512,
            expert_hidden_size=640,
            num_experts=8,
            top_k=2,
        ),
        tcn_config=TCNConfig(
            input_size=n_cont,
            hidden_size=512,
            num_channels=[128, 256, 512, 512, 512],
        ),
        transformer_config=TransformerConfig(
            input_size=n_cont,
            hidden_size=512,
            n_heads=8,
            n_layers=8,
            dim_feedforward=2048,
            max_seq_len=max(args.lookback, 512),
        ),
        gate_hidden_size=512,
        gate_n_heads=8,
        gate_n_interaction_layers=2,
        model_dropout=0.1,
        dropout=0.15,
    )

    model = HydraGate(cfg).to(device)

    if is_main(rank):
        n_params = sum(p.numel() for p in model.parameters())
        log.info("model_built", params=f"{n_params:,}")

    if args.batch_size == 0:
        if is_main(rank):
            batch_size = find_max_batch_size(model, n_cont, n_cat, device)
        else:
            batch_size = 512
        bs_t = torch.tensor([batch_size], device=device)
        dist.broadcast(bs_t, src=0)
        batch_size = int(bs_t.item())
    else:
        batch_size = args.batch_size

    if is_main(rank):
        log.info(
            "config",
            batch_per_gpu=batch_size,
            effective_batch=batch_size * world_size,
            grad_accum=args.grad_accum,
            real_effective=batch_size * world_size * args.grad_accum,
        )

    if args.compile:
        try:
            model = torch.compile(model, mode="max-autotune", dynamic=False, fullgraph=False)
            if is_main(rank):
                log.info("torch_compile_enabled")
        except Exception as e:
            if is_main(rank):
                log.warning("torch_compile_failed", error=str(e))

    model = DDP(
        model,
        device_ids=[local_rank],
        gradient_as_bucket_view=True,
        static_graph=True,
        find_unused_parameters=False,
    )

    try:
        raw = model.module
        sub_params = [
            p
            for n, p in raw.named_parameters()
            if not any(k in n for k in ("gate", "interaction", "master", "head"))
        ]
        gate_params = [
            p
            for n, p in raw.named_parameters()
            if any(k in n for k in ("gate", "interaction", "master", "head"))
        ]
        param_groups = [
            {"params": sub_params, "lr": args.lr * 0.5},
            {"params": gate_params, "lr": args.lr},
        ]
    except Exception:
        param_groups = model.parameters()

    optimizer = torch.optim.AdamW(param_groups, lr=args.lr, weight_decay=args.weight_decay, fused=True)
    scaler = torch.cuda.amp.GradScaler(enabled=(dtype == torch.float16))
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=[args.lr * 0.5, args.lr],
        steps_per_epoch=math.ceil(len(train_ds) / (batch_size * world_size)),
        epochs=1000,
        pct_start=0.05,
        anneal_strategy="cos",
        div_factor=10.0,
        final_div_factor=1000.0,
    )
    loss_fn = ScalpingLoss(gamma=2.0, smoothing=0.1).to(device)

    start_epoch, best_val_loss, best_val_acc = load(model, optimizer, scaler, scheduler, ckpt_dir, device)

    n_workers = max(1, os.cpu_count() or 4)
    train_sampler = DistributedSampler(train_ds, world_size, rank, shuffle=True)
    val_sampler = DistributedSampler(val_ds, world_size, rank, shuffle=False)

    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        sampler=train_sampler,
        num_workers=n_workers,
        pin_memory=False,
        persistent_workers=True,
        prefetch_factor=4,
        drop_last=True,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=batch_size * 2,
        sampler=val_sampler,
        num_workers=max(2, n_workers // 4),
        pin_memory=False,
        persistent_workers=True,
        prefetch_factor=2,
    )

    if is_main(rank):
        log.info(
            "training_start",
            resume_epoch=start_epoch,
            train_batches=len(train_loader),
            val_batches=len(val_loader),
            n_workers=n_workers,
            session_minutes=args.session_minutes,
        )

    patience_counter = 0
    epoch = start_epoch

    while time.time() < session_end:
        epoch += 1

        if session_end - time.time() < 180:
            if is_main(rank):
                log.info("session_ending_saving")
            break

        train_sampler.set_epoch(epoch)
        t0 = time.time()

        train_prefetch = CUDAPrefetcher(train_loader, device)
        val_prefetch = CUDAPrefetcher(val_loader, device)

        train_loss = train_epoch(
            model,
            train_prefetch,
            optimizer,
            loss_fn,
            scaler,
            args.grad_clip,
            args.grad_accum,
            dtype,
        )
        val_loss, val_acc = val_epoch(model, val_prefetch, loss_fn, dtype)

        scheduler.step()

        metrics = torch.tensor([train_loss, val_loss, val_acc], device=device)
        dist.all_reduce(metrics, op=dist.ReduceOp.AVG)
        train_loss, val_loss, val_acc = metrics.tolist()

        if is_main(rank):
            is_best = val_loss < best_val_loss - 1e-4
            if is_best:
                best_val_loss = val_loss
                best_val_acc = val_acc
                patience_counter = 0
            else:
                patience_counter += 1

            full_ckpt = epoch % args.full_ckpt_every == 0
            save(
                model,
                optimizer,
                scaler,
                scheduler,
                epoch,
                val_loss,
                val_acc,
                ckpt_dir,
                is_best=is_best,
                full=full_ckpt,
            )

            elapsed = time.time() - (session_end - args.session_minutes * 60)
            remaining = max(0.0, session_end - time.time())
            epoch_time = time.time() - t0

            log.info(
                "epoch",
                ep=epoch,
                tr_loss=round(train_loss, 4),
                vl_loss=round(val_loss, 4),
                acc_5m=f"{val_acc * 100:.1f}%",
                best=f"{best_val_loss:.4f}",
                t=f"{epoch_time:.0f}s",
                elapsed=f"{elapsed / 60:.1f}m",
                remaining=f"{remaining / 60:.1f}m",
                best_flag="*" if is_best else "",
            )

            if patience_counter >= args.patience:
                log.info("early_stop", patience=args.patience)
                break

    if is_main(rank):
        log.info(
            "session_done",
            epochs_this_session=epoch - start_epoch,
            total_epochs=epoch,
            best_val_loss=round(best_val_loss, 4),
            best_val_acc_5m=f"{best_val_acc * 100:.1f}%",
            model_file=str(ckpt_dir / "best.pt"),
        )

    if monitor is not None:
        monitor.stop()

    cleanup_ddp()


if __name__ == "__main__":
    main()
