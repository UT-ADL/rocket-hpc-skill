---
name: rocket-hpc
description: Run training jobs and other processing on the University of Tartu HPC Rocket cluster (Slurm, rocket.hpc.ut.ee / helios login nodes). Use whenever submitting, sizing, monitoring, cancelling or costing Slurm jobs there, staging data to node-local SSD, choosing GPU types (V100 / A100 / H200 / B200), or checking quota and spending.
---

# Working on the UT HPC Rocket cluster

Rocket is a shared, billed Slurm cluster. Every job costs the paying project money, and every idle GPU you hold
delays other researchers. Size jobs to what they actually use, prove ideas small before running them big, and watch
what you started.

Reference files (read when needed):
- `reference/cluster.md`: nodes, GPUs and gres names, partitions, limits, storage paths, quotas, commands.
- `reference/pricing.md`: prices, the billing formula and how to estimate and report costs.
- `reference/templates.md`: sbatch templates (CPU, single-GPU, multi-GPU DDP, arrays, /tmp staging, interactive).
- `scripts/hpc_cost.py`: EUR cost of your or your account's jobs from Slurm accounting.
- `scripts/job_efficiency.py`: requested vs used CPU and memory for finished or running jobs (`seff` is not installed).
- `scripts/watch_jobs.py`: flags stuck jobs and jobs whose metric lags a reference run, and cancels them on request.
- `scripts/wait_jobs.sh`: blocks until a job finishes or fails (see "Waiting on jobs").

## Before you submit

1. **Find the account to charge.** Always pass `-A <account>` (`#SBATCH -A ...`). UT users have `uthpc` and project accounts;
   ETAIS users must use their `ealloc_...` allocation, otherwise jobs are rejected. List yours with
   `sacctmgr show association where user=$USER format=account,partition,maxtres`. Ask the user which project pays if it is
   not obvious, and don't guess.
2. **Keep work off the login node.** Login sessions are capped at 6 GB RAM and 2 cores. Staff may kill heavy processes
   there without warning and suspend access. Fine on the login node: editing, `git`, `sbatch`/`squeue`/`sacct`, small
   file inspection, `wait_jobs.sh`. Everything else (installs, downloads, data conversion, compilation of large
   projects, evaluation, anything over ~2 minutes) goes into a job. Never run processes on compute or GPU nodes outside
   Slurm; that can get UTHPC access revoked.
3. **Use CPU nodes when no GPU is needed.** Partition `main` (8 days, 128-core / 1 TB AMD nodes) for data conversion,
   preprocessing, evaluation that doesn't need a GPU, and monitoring jobs. `testing` (2 h) is for quick checks. Use
   `gpu` only for GPU work. Job arrays (`--array=0-99%20`) parallelise per-file CPU work well.
4. **Prove it small first.** Run a short smoke test (minutes, `testing` partition or a 1-GPU job with a tiny config)
   before a multi-GPU multi-day run. For research questions, screen with a cheap proxy (smaller data or fewer epochs,
   V100s) and repeat with a second seed to know the noise before spending full-run money on a difference.

## Sizing requests (you are billed for what you allocate, not what you use)

- **Memory:** request measured peak × ~1.2, not "plenty". The price is `max(cores, memory_GB/6)`, so 200 GB on 8
  cores costs as much as 33 cores. Measure peak with `scripts/job_efficiency.py <jobid>` (MaxRSS) and shrink the next
  submission. A pending job can be shrunk in place:
  `scontrol update JobId=<id> MinMemoryNode=<MB>`. Default if unspecified: 2 GB per CPU.
- **Cores:** give data-loader workers what they need, no more. A common pattern is `cpus-per-task` = loader workers +
  2 per GPU. Stay within the node's cores-per-GPU share (see `reference/cluster.md`) so GPUs on the node remain
  usable by others. Add `--hint=nomultithread` for CPU-bound work.
- **GPUs:** request the count your code uses and verify it with `nvidia-smi` (below). Multi-GPU only with
  DistributedDataParallel (one process per GPU), not DataParallel. More GPUs only pays off if per-GPU utilisation stays
  high. Keep the global batch size fixed when comparing runs across GPU counts.
- **GPU type:** V100 (`gpu:tesla`, fp16 only, no bf16) for short experiments, evaluation and benchmarks. A100
  (`a100-40g`, `a100-80g`) or H200 for long training (bf16 is more stable than fp16). H200 costs 4× an A100-hour, so
  use it when it is free and the speed-up justifies it. B200 is restricted (public sector only; access may need a
  request to support). falcon3 has 16 GB V100s; exclude it when your job needs 32 GB.
  Let Slurm choose among acceptable types by excluding unsuitable nodes (`--gres=gpu:4 --exclude=falcon[1-6],...`)
  rather than pinning one node, so the job starts sooner.
- **Time:** set a realistic `--time` (the default is 10 min). Shorter jobs get priority and fit before maintenance
  reservations. Checkpoint regularly and support resume, so a job that hits the limit or is preempted can continue.

## Data and disk

- **Home** (`$HOME` on GPFS) has quota limits (typically 2 TB and 1-2 M files) and is **not backed up** (only 2 weekly
  snapshots in `.snapshots`). Check with `myquota` before creating large caches, and keep 10-20% free: a full home
  breaks running jobs. Many small files hurt GPFS; pack datasets into fewer larger files (npz, tar, shards) where you can.
- **Project folders** (`/gpfs/space/projects/<name>`, paid, weekly tape backup) are for data that must survive.
  Caches, conda envs and pip dirs are excluded from backup.
- **Node-local SSD `/tmp`** is much faster than GPFS for read-heavy training (GPFS cold reads from one job were
  about 200 MB/s and a few hundred files/s). Sizes: pegasus 1.6 TB, falcon 5 TB, ares/artemis 8 TB, pegasus2 15 TB,
  firefly 28 TB. If the loader is I/O bound (low GPU utilisation, high iowait), stage data at job start:
  `rsync -a --delete /gpfs/.../dataset/ /tmp/$USER/dataset/`. rsync skips unchanged files, so repeat runs on the same
  node are nearly free. Slurm doesn't track `/tmp` space (`--tmp` doesn't work), so check `df -h /tmp` in the job and
  clean up what you don't intend to reuse (a `trap ... EXIT` in the script). See `reference/templates.md`.
- Don't compress or decompress in parallel on GPFS. Do it in `/tmp` inside a job.

## While jobs run

- **Queue state:** `squeue --me -o "%.10i %.20j %.8T %.10M %.10L %R"`. The reason column explains waits
  (`Priority`, `Resources`, `ReqNodeNotAvail` = maintenance reservation, `DependencyNeverSatisfied` = cancel it).
  `squeue -j <id> --start` gives Slurm's (pessimistic) start estimate. `sprio -j <id>` and `sshare -U` show priority and
  fair share. If a job is blocked only by a too-narrow node list, widen it: `scontrol update job <id> ExcNodeList=...`.
- **GPU use:** `srun --jobid <id> --overlap nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv`
  (one snapshot, not `watch`). Below ~50% utilisation means a data or CPU bottleneck: fix the loader, stage to `/tmp`,
  or use fewer GPUs.
- **CPU and memory use:** `scripts/job_efficiency.py <id>` (`sstat`/`sacct`), or the ELK dashboard
  https://elk.hpc.ut.ee (per-minute CPU and memory utilisation, UT login).
- **Logs:** always write stdout/stderr (`-o logs/%x-%j.out`) and print throughput (iterations/s) and key metrics
  periodically, so stuck or slow jobs are visible.

## Waiting on jobs (token budget)

Every wake re-processes your whole context, and short waits let the prompt cache expire, so each check-in re-pays it in
full.
- After submitting, wait with ONE blocking call: `${CLAUDE_SKILL_DIR}/scripts/wait_jobs.sh 50 <jobids>` with a Bash
  timeout ≥ 51 min. It returns when any job leaves PENDING/RUNNING or after 50 min (keeps a 1 h cache warm). Never
  schedule fixed 5/10/15-min check-ins and never `sleep` in separate tool calls.
- On return, inspect compactly: its sacct lines plus `tail -n 15 <log>` or
  `grep -m5 -iE 'error|nan|oom|Traceback' <log>`. Never cat whole logs or paste full nvidia-smi/squeue/sacct tables.
- Nothing actionable changed? Call `wait_jobs.sh` again immediately, without commentary or re-analysis.
- Remaining jobs need more than ~2 h? Write job IDs, purpose and expected finish to a small state file
  (e.g. `state/<task>.json`) and return that summary to the caller instead of waiting.
- Keep notes short; don't restate earlier findings on each wake.
- For automatic stuck/lagging detection on long runs, run `scripts/watch_jobs.py` as a tiny CPU job. It is not an
  LLM loop and costs no tokens.

## Cancel what is not worth finishing

Cancel without hesitation (`scancel <id>`; arrays `scancel <id>_[3-5]`):
- **Stuck:** no log progress for much longer than one logging interval, 0% GPU utilisation, NCCL hangs at startup.
- **Broken:** NaN losses, repeated OOM restarts, wrong data path discovered after launch.
- **Clearly losing:** in comparative experiments, a run whose validation metric is worse than its matched reference
  *at the same step/epoch* by more than the known noise margin. Compare at equal progress, not final vs early.
  `scripts/watch_jobs.py` automates both checks (run it as a small CPU job).
- **Oversized:** a job using a fraction of its allocation. Cancel it and resubmit smaller; it lowers the bill.

Report cancellations and their reason to the user.

## Costs and accounting

- Price (from 1 July 2026, EUR, VAT added outside UT): CPU/memory `max(cores, GB/6) × 0.012` per hour, plus GPUs:
  A100 0.5, H200 2.0, B200 2.0 per GPU-hour. V100 is unlisted; treat it as ≤ 0.5. Details and caveats are in
  `reference/pricing.md`.
- Before proposing a big run, state its expected GPU-hours and EUR (GPUs × hours × rate + CPU/memory units).
- Track spending with `scripts/hpc_cost.py --account <acct> --start YYYY-MM-DD` (per job, per GPU type, total), and
  `sreport -t hours cluster AccountUtilizationByUser account=<acct> start=... --tres=cpu,gres/gpu`. Slurm's own
  `billing` TRES is just the CPU count and doesn't equal the invoice. Invoices come via ETAIS allocations.

## Cluster-specific gotchas

- **DDP on PCIe multi-GPU nodes shared by several jobs** (e.g. pegasus): NCCL can hang at init. Set
  `export NCCL_P2P_DISABLE=1`. Use `NCCL_DEBUG=INFO` to diagnose.
- **Variable-size batches** (point clouds, variable-length sequences) fragment GPU memory:
  `export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` avoids spurious OOMs.
- **Load modules or activate environments inside the job script** (`module purge; module load ...`). Use a module's
  Python, not the system one, for venvs. Put conda/pip/Singularity caches outside home if space is tight
  (`SINGULARITY_CACHEDIR`, `SINGULARITY_TMPDIR=/tmp`).
- **Interactive sessions and `screen` die with the login node,** which restarts often. Use `sbatch` for anything that
  must finish.
- **Per-user limits:** typically 600 cores at a time and job arrays up to index 1000. Only ports 8000-8080 are reachable
  from outside for services such as Jupyter or TensorBoard.
- **Help:** support@hpc.ut.ee (limits, priority bumps, reservations, project folders, restores).
