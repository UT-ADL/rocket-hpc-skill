#!/usr/bin/env python3
"""Watch Slurm jobs for two conditions and (optionally) cancel them:
  - stuck: the job's log file has not been written to for `stall_minutes`,
  - lagging: the job's metric at a given progress point is worse than a reference run's metric at the same point by
    more than `margin` (compare at equal progress, e.g. the same epoch).
Metrics are parsed from each log with a regex with two groups: progress (e.g. epoch) and value.

Config (JSON):
{
  "cancel": false,                      # true: scancel offenders; false: only report
  "interval_minutes": 15,
  "stall_minutes": 45,
  "higher_is_better": true,
  "margin": 0.03,                       # tolerated gap below the reference (use ~2-3x the seed-to-seed noise)
  "regex": "epoch (\\\\d+) .*val_map ([\\\\d.]+)",
  "reference": {"log": "logs/baseline-123.out"},          # or {"values": {"6": 0.45, "12": 0.52}}
  "jobs": {"456": "logs/variant_a-456.out", "457": "logs/variant_b-457.out"}
}
Run it as a tiny CPU job (sbatch -p main -c 1 --mem=1G -t 2-00:00:00 --wrap "python watch_jobs.py cfg.json") or
as a light loop on the login node. Stops when none of the watched jobs is pending or running.
usage: watch_jobs.py config.json [--once]
"""
import json, os, re, subprocess, sys, time


def metrics(path, regex):
    out = {}
    if os.path.exists(path):
        for m in re.finditer(regex, open(path, errors='replace').read()):
            out[m.group(1)] = float(m.group(2))
    return out


def job_state(job):
    r = subprocess.run(['squeue', '-h', '-j', job, '-o', '%T'], capture_output=True, text=True).stdout.strip()
    return r or 'FINISHED'


def check(cfg):
    ref = cfg['reference'].get('values') or metrics(cfg['reference']['log'], cfg['regex'])
    ref = {str(k): v for k, v in ref.items()}
    sign = 1 if cfg.get('higher_is_better', True) else -1
    active = False
    for job, log in cfg['jobs'].items():
        state = job_state(job)
        if state not in ('RUNNING', 'PENDING'):
            continue
        active = True
        if state != 'RUNNING':
            continue
        reason = None
        if os.path.exists(log) and (time.time() - os.path.getmtime(log)) / 60 > cfg.get('stall_minutes', 45):
            reason = f'log idle for {(time.time() - os.path.getmtime(log)) / 60:.0f} min'
        mine = metrics(log, cfg['regex'])
        common = [p for p in mine if p in ref]
        if common and reason is None:
            p = max(common, key=lambda x: float(x))
            gap = sign * (ref[p] - mine[p])
            status = f'{job}: at {p} {mine[p]:.4f} vs reference {ref[p]:.4f}'
            print(time.strftime('%H:%M'), status, flush=True)
            if gap > cfg['margin']:
                reason = f'lags reference by {gap:.4f} (> margin {cfg["margin"]}) at {p}'
        if reason:
            print(time.strftime('%H:%M'), f'{job}: {reason}' + (' -> scancel' if cfg.get('cancel') else ' (report only)'),
                  flush=True)
            if cfg.get('cancel'):
                subprocess.run(['scancel', job])
    return active


if __name__ == '__main__':
    cfg = json.load(open(sys.argv[1]))
    while check(cfg) and '--once' not in sys.argv:
        time.sleep(60 * cfg.get('interval_minutes', 15))
