# Rocket cluster facts

From https://docs.hpc.ut.ee/public/ and the Rocket service page, checked against the live cluster on 2026-09-29.
Hardware and limits change, so verify with the commands at the end when it matters.

## Access

- `ssh <user>@rocket.hpc.ut.ee` from the UT network or UT VPN. Login nodes: login1/login2.hpc.ut.ee.
  Login sessions are limited to 6 GB RAM and 2 cores.
- ETAIS users: create the Rocket allocation at https://minu.etais.ee, add an SSH key and a FreeIPA account, and submit
  with `-A ealloc_...`.
- OnDemand (Jupyter/RStudio as Slurm jobs): https://ondemand.hpc.ut.ee. The account is `uthpc` for UT login. Sessions
  don't stop when idle; delete them under "My Interactive Sessions".

## Partitions (live)

| Partition | Default time | Max time | Nodes | Notes |
|---|---|---|---|---|
| main (default) / amd | 10 min | 8 days | ares[1-20], artemis[1-18] | 128 cores (256 threads), 1 TB RAM, 8 TB local SSD per node |
| testing | 10 min | 2 h | artemis[19-20] | short tests |
| long | 10 min | 30 days | artemis[17-20] | long CPU jobs |
| gpu | 10 min | 8 days | falcon[1-6], pegasus, pegasus2, firefly[1-3], shepard[2-3] | see GPU table |

Default allocation if you specify nothing: 1 CPU, 2 GB per CPU, 10 minutes.

## GPU nodes

| Node | GPUs | gres | Cores (threads) | RAM | Cores/GPU | RAM/GPU | Local SSD | Price EUR/GPU-h |
|---|---|---|---|---|---|---|---|---|
| falcon1-2 | 7× V100 32 GB (docs: 6) | `gpu:tesla` | 24 (48) | 500 GB | 4 | 70-80 GB | 5 TB | not listed |
| falcon3 | 6× V100 **16 GB** | `gpu:tesla` | 48 (96) | 500 GB | 8 | 80 GB | 5 TB | not listed |
| falcon4-6 | 8× V100 32 GB | `gpu:tesla` | 32 (64) | 500 GB | 4 | 60 GB | 5 TB | not listed |
| pegasus | 4× A100 40 GB (PCIe) | `gpu:a100-40g` | 96 (192) | 500 GB | 24 | 120 GB | 1.6 TB | 0.5 |
| pegasus2 | 8× A100 80 GB | `gpu:a100-80g` | 128 (256) | 2 TB | 16 | 250 GB | 15 TB | 0.5 |
| firefly1-3 | 4× H200 141 GB | `gpu:h200-141g` | 128 (256) | 1.5 TB | 32 | 375 GB | 28 TB | 2.0 |
| shepard2-3 | 8× B200 192 GB | `gpu:b200-180g` | 256 (512) | 3 TB | 32 | 375 GB | ? | 2.0 (public sector only) |

- `--gres=gpu:<type>:<n>` pins a type, and `--gres=gpu:<n>` takes any. The V100 memory size can't be selected by gres
  (only `gpu:tesla`), so exclude falcon3 when you need 32 GB.
- GPUs are exclusive to your job. V100 has no bf16. A100, H200 and B200 do.
- `--gpus-per-task` can't be combined with `--gres`.
- `sinfo -N -o "%N %G %c %m %t"` lists nodes, GPUs, CPUs, memory and state.

## Limits and scheduling (live)

- 600 cores per user at a time (QOS `normal`). `MaxArraySize=1001`.
- Multifactor priority: fair share dominates (weight 10000, 14-day half-life), then age, job size and partition
  (1000 each). Shorter jobs are favoured by the backfill scheduler. Check with `sprio -j <id>` and `sshare -U`.
- `scontrol show reservation` shows maintenance windows. Jobs whose `--time` overlaps them stay pending with
  `ReqNodeNotAvail`.
- Common errors: `Job violates accounting/QOS policy` (a limit was reached), `Requested time limit is invalid`
  (over the partition maximum), `Requested node configuration is not available` (the resource combination doesn't exist).

## Storage

| Area | Path | Quota | Backup |
|---|---|---|---|
| Home | `$HOME` (`/gpfs/helios/home/<user>`, older docs: `/gpfs/space/home/<user>`) | ~2 TB, 1-2 M files (`myquota`) | **none**, weekly snapshots (2 kept) in `.snapshots` |
| Project | `/gpfs/space/projects/<project>` (request from support) | none by default, paid | weekly tape; caches/conda/pip/tmp dirs excluded |
| Node-local SSD | `/tmp` on the compute node | node size (above) | none; delete what you don't reuse |
| SFTP export | `sftp.hpc.ut.ee` (`/gpfs/terra/export`) | | weekly snapshots (3) |

- GPFS (`/gpfs/space`, `/gpfs/helios`) has a flash tier but is shared: many small files and parallel
  (de)compression are slow for everyone.
- Slurm reports `TmpDisk=0`, so `--tmp` can't reserve local disk. Check `df -h /tmp` inside the job.
- Transfers: `rsync -avP src user@rocket.hpc.ut.ee:dst` (`-n` dry run). Also scp, sftp, FileZilla (port 22).

## Software

- Lmod: `module avail <kw>`, `module spider <kw>`, `module load name/version`, `module purge`. Python packages are
  `py-*` modules, e.g. `python/3.14.0`, `cuda/12`, `miniconda3`, `py-virtualenv`, `singularity`, `squashfs`.
- venv: `module load python/...` (or `py-virtualenv`), `virtualenv env`, `source env/bin/activate`. conda:
  `module load miniconda3`. Environments go in `~/.conda/envs`, which counts against the home quota.
- Singularity: `module load singularity squashfs`, `singularity pull docker://nvcr.io/nvidia/pytorch:<tag>`,
  `singularity exec --nv --bind /gpfs image.sif python ...`. Set `SINGULARITY_CACHEDIR` (outside home if tight) and
  `SINGULARITY_TMPDIR=/tmp`.

## Command cheat sheet

```bash
sacctmgr show association where user=$USER format=account,partition,maxtres   # accounts you can charge
squeue --me -o "%.10i %.20j %.8T %.10M %.10L %.6D %R"                         # your jobs
squeue -j <id> --start                                                         # estimated start
scontrol show job <id>            # details (-dd: also the script)
scontrol update job <id> ExcNodeList=... / MinMemoryNode=<MB> / TimeLimit=...  # fix a pending job
scontrol hold <id> / scontrol release <id>                                     # park a pending job
sacct -j <id> -o JobID,State,Elapsed,AllocTRES%60,MaxRSS,TotalCPU,ExitCode    # after the fact
sstat -j <id>.batch -o MaxRSS,AveCPU                                            # running job
srun --jobid <id> --overlap --pty nvidia-smi                                    # GPU use of a running job
scancel <id> | scancel <id>_[1-3] | scancel --me --state=PD                     # cancel
myquota                                                                         # home quota
sreport -t hours cluster AccountUtilizationByUser account=<acct> start=YYYY-MM-DD --tres=cpu,gres/gpu
```

Failure signatures in the job log: `CANCELLED ... DUE TO TIME LIMIT`, `exceeded memory limit ... being killed`
(host RAM, so raise `--mem`), `CUDA out of memory` (GPU memory, so a smaller batch or `expandable_segments`),
`Disk quota exceeded` (`myquota`).
