# sbatch templates

Replace `<account>`, paths and sizes. Keep `-o` logs, `-A`, a realistic `-t` and measured `--mem`.

## CPU job (preprocessing, conversion, evaluation without GPU)

```bash
#!/bin/bash
#SBATCH -A <account>
#SBATCH -p main
#SBATCH -J convert
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH -t 04:00:00
#SBATCH -o logs/%x-%j.out
module purge; module load python/3.14.0
source ~/envs/myenv/bin/activate
python convert.py --workers "$SLURM_CPUS_PER_TASK"
```

## Array job (one task per shard or file group; `%20` = at most 20 at once)

```bash
#!/bin/bash
#SBATCH -A <account>
#SBATCH -p main
#SBATCH -J shards
#SBATCH -c 2
#SBATCH --mem=8G
#SBATCH -t 02:00:00
#SBATCH --array=0-99%20
#SBATCH -o logs/%x_%A_%a.out
python process.py --task "$SLURM_ARRAY_TASK_ID" --ntasks 100    # script processes files[task::ntasks]
```

Make tasks idempotent (skip outputs that already exist) so failed tasks can be resubmitted:
`sbatch --array=23,34 job.sh`.

## Single-GPU job (experiments, evaluation, benchmarks on V100)

```bash
#!/bin/bash
#SBATCH -A <account>
#SBATCH -p gpu
#SBATCH --gres=gpu:tesla:1
#SBATCH --exclude=falcon3            # 16 GB V100s; drop this if 16 GB is enough
#SBATCH -c 6
#SBATCH --mem=48G
#SBATCH -t 03:00:00
#SBATCH -o logs/%x-%j.out
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
python eval.py
```

## Multi-GPU training (DDP, one node, bf16 GPUs)

```bash
#!/bin/bash
#SBATCH -A <account>
#SBATCH -p gpu
#SBATCH -J train
#SBATCH --gres=gpu:4                                   # any 4 GPUs ...
#SBATCH --exclude=falcon[1-6],shepard[2-3]             # ... that are not V100 (no bf16) or restricted B200
#SBATCH -c 32                                          # ~8 cores per GPU (loader workers + 2)
#SBATCH --mem=200G                                     # measured peak x 1.2
#SBATCH -t 2-00:00:00
#SBATCH -o logs/%x-%j.out
export NCCL_P2P_DISABLE=1                              # avoid NCCL init hangs on shared PCIe nodes
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
NGPU=$(nvidia-smi -L | wc -l)
WORKERS=$(( SLURM_CPUS_PER_TASK / NGPU - 2 ))
torchrun --standalone --nproc_per_node="$NGPU" train.py --workers "$WORKERS" --resume "$@"
```

- Save a checkpoint every epoch (or N steps) and make `--resume` pick up the latest, so time limits and node
  failures cost minutes, not days.
- Log step time and a validation metric at fixed intervals, so progress can be compared between runs
  (`scripts/watch_jobs.py`).

## Staging data to node-local SSD (for I/O-bound training)

```bash
DATA=/tmp/$USER/mydataset
mkdir -p "$DATA"
df -h /tmp | tail -1                                   # Slurm doesn't track /tmp space: check it
t0=$(date +%s)
rsync -a --delete /gpfs/space/projects/<proj>/mydataset/ "$DATA/"    # incremental: fast on a node that has it
echo "staged in $(( $(date +%s) - t0 )) s, $(du -sh "$DATA" | cut -f1)"
# keep the copy for reuse by later jobs on this node, or remove it at exit:
# trap 'rm -rf "$DATA"' EXIT
python train.py --data "$DATA"
```

- Staging pays off when the job reads the dataset more than about once, and when GPU utilisation with GPFS input is low.
- Repeat runs reuse the copy only if they land on the same node. Pinning with `-w node` makes them wait longer, so only
  pin when the copy is large and the node is usually free.
- Shared nodes' `/tmp` is used by others too. Don't fill it, and remove stale copies you no longer need.

## Interactive session (quick debugging only; dies with the login node)

```bash
srun -A <account> -p testing -t 30:00 -c 4 --mem=16G --pty bash
srun -A <account> -p gpu --gres=gpu:tesla:1 -t 30:00 -c 4 --mem=32G --pty bash
srun --jobid <running_job_id> --overlap --pty bash           # a shell inside your running job
```

## Chaining and small helper jobs

```bash
sbatch --dependency=afterok:<jobid> eval.sh                  # run after a job succeeds
sbatch -A <account> -p main -c 1 --mem=1G -t 2-00:00:00 --wrap "python watch_jobs.py watch.json"   # tiny monitor job
```
