# rocket-hpc: Claude Code skill for the UT HPC Rocket cluster

A [Claude Code](https://claude.com/claude-code) skill for running training jobs and other processing on the University
of Tartu HPC Rocket cluster (Slurm). With it, Claude:

- charges jobs to the right account (`-A`) and keeps heavy work off the login nodes
- uses CPU partitions when no GPU is needed, and picks suitable GPU types (V100 / A100 / H200 / B200)
- sizes cores, memory, GPUs and time conservatively (billing is on the allocation) and checks actual usage
- stages I/O-heavy datasets to node-local SSD (`/tmp`) with incremental `rsync`
- monitors jobs, and cancels stuck ones or ones clearly lagging a reference run
- estimates and reports costs from Slurm accounting and the published prices, and watches disk quota

## Installation

### 1. Prerequisites

- An account on the Rocket cluster (UT account, or an ETAIS allocation) and SSH access to `rocket.hpc.ut.ee`
  from the UT network or VPN.
- [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) installed where you work with the cluster,
  usually on the login node itself:
  ```bash
  curl -fsSL https://claude.ai/install.sh | bash      # installs to ~/.local/bin/claude
  ```
  Claude Code only edits files and submits Slurm jobs there. The skill makes sure the actual computation runs as jobs,
  not on the login node.

### 2. Install the skill for all your projects (recommended)

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/UT-ADL/rocket-hpc-skill.git ~/.claude/skills/rocket-hpc
```

The directory name (`rocket-hpc`) must match the `name:` in `SKILL.md`. Personal skills in `~/.claude/skills/` are
available in every Claude Code session.

### 2b. Or install it for one project only

```bash
cd <your-project>
git clone https://github.com/UT-ADL/rocket-hpc-skill.git .claude/skills/rocket-hpc
```

To share it with the project's other users, commit it (or add it as a git submodule) under `.claude/skills/`.

### 3. Check that Claude sees it

Start `claude` (restart it if it was already running) and ask "which skills do you have?", or type `/` and look for `rocket-hpc`.
`rocket-hpc` should be listed. Claude uses it automatically when you ask about Slurm jobs on Rocket. You can also
invoke it explicitly with `/rocket-hpc`.

### 4. Tell Claude which account pays

The skill always asks which Slurm account to charge (`-A`) unless it's obvious. To avoid being asked every time, put
it in your project's `CLAUDE.md`, e.g. `Charge Slurm jobs to account <account> (-A <account>).` To see your accounts:
`sacctmgr show association where user=$USER format=account`.

### 5. Recommended Claude Code settings

Agents waiting on Slurm jobs burn most of their tokens re-processing context on each wake-up. In `~/.claude/settings.json`:

```json
{
  "subagentPromptCacheTtl": "1h",
  "env": { "BASH_MAX_TIMEOUT_MS": "3300000" }
}
```

- `subagentPromptCacheTtl`: subagents otherwise get a 5-minute prompt cache, even on a subscription (needs Claude Code
  v2.1.242+).
- `BASH_MAX_TIMEOUT_MS`: lets a single `scripts/wait_jobs.sh` call block for up to 55 minutes.

### Update and uninstall

Existing installs pick up new versions (e.g. `scripts/wait_jobs.sh`) with a pull:

```bash
git -C ~/.claude/skills/rocket-hpc pull        # update
rm -rf ~/.claude/skills/rocket-hpc             # uninstall
```

## Contents

| Path | Purpose |
|---|---|
| `SKILL.md` | workflow and rules Claude follows |
| `reference/cluster.md` | nodes, GPUs and gres names, partitions, limits, storage, command cheat sheet |
| `reference/pricing.md` | prices (valid from 2026-07-01), billing formula, cost estimation |
| `reference/templates.md` | sbatch templates: CPU, array, single-GPU, multi-GPU DDP, `/tmp` staging, interactive |
| `scripts/hpc_cost.py` | EUR cost of jobs from `sacct`, by job, GPU type, day or user |
| `scripts/job_efficiency.py` | requested vs used CPU and memory, suggested `--mem` (Rocket has no `seff`) |
| `scripts/watch_jobs.py` | flags stuck jobs and jobs lagging a reference run, optionally cancels them |
| `scripts/wait_jobs.sh` | blocks until a job leaves PENDING/RUNNING (or a time cap), then prints compact `sacct` lines |

The scripts also work without Claude, e.g. `python3 scripts/hpc_cost.py --account <acct> --start 2026-09-01`.

## Sources and caveats

Facts come from https://docs.hpc.ut.ee/public/ and https://hpc.ut.ee/pricing/overview, checked against the live cluster
on 2026-09-29 (the docs are out of date in places, e.g. partition node lists and per-user limits). Hardware, limits and
prices change, so corrections are welcome. The pricing pages don't list a V100 price or say whether GPU jobs also pay
CPU/memory units; `hpc_cost.py` assumes 0.5 EUR per V100-hour and adds CPU/memory, so its totals are an upper bound.
