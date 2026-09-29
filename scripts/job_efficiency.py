#!/usr/bin/env python3
"""Requested vs used resources of Slurm jobs (replacement for `seff`, which Rocket lacks): CPU efficiency
(TotalCPU / (Elapsed x cores)) and peak memory (max MaxRSS over steps) vs allocated memory, with a suggested
--mem (peak x 1.2). Works for finished jobs (sacct) and running ones (sstat for the batch/extern steps).
GPU utilisation is not in accounting: check it with `srun --jobid <id> --overlap --pty nvidia-smi`.

usage: job_efficiency.py JOBID [JOBID ...]
"""
import re, subprocess, sys


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()


def seconds(t):
    """Slurm time [D-]HH:MM:SS[.fff] or MM:SS.fff -> seconds."""
    if not t:
        return 0.0
    days, _, t = t.rpartition('-')
    parts = [float(p) for p in t.split(':')]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return (int(days) if days else 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def gb(v):
    m = re.match(r'([\d.]+)([KMGT]?)', v or '')
    if not m:
        return 0.0
    return float(m.group(1)) * {'K': 1 / 1024 ** 2, 'M': 1 / 1024, 'G': 1, 'T': 1024, '': 1 / 1024 ** 3}[m.group(2)]


for job in sys.argv[1:]:
    head = run(['sacct', '-X', '-P', '-n', '-j', job, '-o', 'JobName,State,ElapsedRaw,AllocTRES%120,NodeList'])
    if not head:
        print(f'{job}: not found')
        continue
    name, state, elapsed, tres, nodes = head[0].split('|')
    t = dict(kv.split('=', 1) for kv in tres.split(',') if '=' in kv)
    cores, mem_alloc, gpus = int(t.get('cpu', 1)), gb(t.get('mem', '0')), t.get('gres/gpu', '0')
    steps = [r.split('|') for r in run(['sacct', '-P', '-n', '-j', job, '-o', 'JobID,MaxRSS,TotalCPU'])]
    peak = max((gb(s[1]) for s in steps if s[1]), default=0.0)
    cpu_used = sum(seconds(s[2]) for s in steps if '.' in s[0])
    if state.startswith('RUNNING'):
        live = [r.split('|') for r in run(['sstat', '-P', '-n', '-j', f'{job}.batch', '-o', 'MaxRSS,AveCPU'])]
        if live:
            peak = max(peak, gb(live[0][0]))
            cpu_used = max(cpu_used, seconds(live[0][1]))
    elapsed = int(elapsed or 0)
    cpu_eff = cpu_used / max(elapsed * cores, 1)
    print(f'{job} {name} [{state}] on {nodes}: {elapsed / 3600:.2f} h, {cores} cores, {gpus} GPUs, {mem_alloc:.0f} GB allocated')
    print(f'   CPU efficiency {100 * cpu_eff:.0f}% ({cpu_used / 3600:.1f} of {elapsed * cores / 3600:.1f} core-h)'
          f'{"  <- consider fewer cores" if cpu_eff < 0.5 and elapsed > 600 else ""}')
    print(f'   peak memory {peak:.1f} GB of {mem_alloc:.0f} GB ({100 * peak / max(mem_alloc, 1e-9):.0f}%)'
          f' -> suggested --mem={max(1, round(peak * 1.2))}G'
          f'{"  <- over-allocated" if peak and peak < 0.5 * mem_alloc else ""}')
