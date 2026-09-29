#!/usr/bin/env python3
"""Estimated EUR cost of Slurm jobs on the UT HPC Rocket cluster from `sacct` (allocated resources x elapsed time).

Rates (hpc.ut.ee/pricing/overview, valid from 2026-07-01): CPU/memory max(cores, GB/6) x 0.012 EUR per hour; GPU per
GPU-hour: A100 0.5, H200 2.0, B200 2.0, V100 not listed (0.5 assumed). CPU/memory is added on top of GPUs (upper
bound; the pricing pages don't say whether GPU jobs also pay it). VAT is not included.

usage: hpc_cost.py [--account ACCT] [--user USER|--all-users] [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                   [--by job|gpu|day|user] [--jobs ID,ID]
"""
import argparse, collections, datetime, re, signal, subprocess

CPU_RATE = 0.012                                   # EUR per core-hour, also per 6 GB-hour
GPU_RATE = {'a100': 0.5, 'h200': 2.0, 'b200': 2.0, 'tesla': 0.5, 'v100': 0.5, 'l40s': 0.5, 'rtx6000': 1.0}
NODE_GPU = {'falcon': 'tesla', 'pegasus2': 'a100', 'pegasus': 'a100', 'firefly': 'h200', 'shepard': 'b200'}


def mem_gb(value):
    """AllocTRES mem value (e.g. 200G, 16000M, 1.5T) -> GB."""
    m = re.match(r'([\d.]+)([KMGT]?)', value)
    scale = {'K': 1 / 1024 ** 2, 'M': 1 / 1024, 'G': 1, 'T': 1024, '': 1 / 1024}[m.group(2)]
    return float(m.group(1)) * scale


def gpu_type(tres, nodes):
    for key in tres:
        if key.startswith('gres/gpu:'):
            name = key.split(':', 1)[1].lower()
            return next((t for t in GPU_RATE if name.startswith(t)), name)
    return next((t for prefix, t in NODE_GPU.items() if nodes.startswith(prefix)), 'unknown')


def main():
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # quiet when piped into head
    ap = argparse.ArgumentParser()
    ap.add_argument('--account')
    ap.add_argument('--user')
    ap.add_argument('--all-users', action='store_true')
    ap.add_argument('--start', default=(datetime.date.today() - datetime.timedelta(days=30)).isoformat())
    ap.add_argument('--end', default='now')
    ap.add_argument('--by', default='gpu', choices=['job', 'gpu', 'day', 'user'])
    ap.add_argument('--jobs')
    a = ap.parse_args()
    cmd = ['sacct', '-X', '-P', '-n', '-S', a.start, '-E', a.end,
           '-o', 'JobID,JobName%40,User,Account,NodeList,ElapsedRaw,AllocTRES%120,State,Start']
    if a.jobs:
        cmd += ['-j', a.jobs]
    if a.account:
        cmd += ['-A', a.account]
    if a.all_users:
        cmd += ['-a']
    elif a.user:
        cmd += ['-u', a.user]
    rows = [r.split('|') for r in subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.splitlines()]
    groups = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0])   # gpu_h, gpu_eur, cpu_mem_eur, jobs
    total_gpu, total_cpu = 0.0, 0.0
    for job, name, user, acct, nodes, elapsed, tres, state, start in rows:
        if not elapsed or elapsed == '0' or not tres:
            continue
        t = dict(kv.split('=', 1) for kv in tres.split(',') if '=' in kv)
        hours = int(elapsed) / 3600
        cores = int(t.get('cpu', 0))
        gb = mem_gb(t['mem']) if 'mem' in t else 0.0
        ngpu = int(t.get('gres/gpu', 0))
        gtype = gpu_type(t, nodes) if ngpu else '-'
        cpu_mem = max(cores, gb / 6) * hours * CPU_RATE
        gpu_eur = ngpu * hours * GPU_RATE.get(gtype, 0.5) if ngpu else 0.0
        total_gpu += gpu_eur
        total_cpu += cpu_mem
        key = {'job': f'{job} {name[:28]} ({state.split()[0]})', 'gpu': gtype, 'day': start[:10], 'user': user}[a.by]
        g = groups[key]
        g[0] += ngpu * hours
        g[1] += gpu_eur
        g[2] += cpu_mem
        g[3] += 1
    print(f'{a.by:<45s} {"jobs":>5s} {"GPU-h":>9s} {"GPU EUR":>9s} {"CPU/mem EUR":>12s} {"total EUR":>10s}')
    for key, (gh, ge, ce, n) in sorted(groups.items(), key=lambda kv: -(kv[1][1] + kv[1][2])):
        print(f'{key:<45s} {n:5d} {gh:9.1f} {ge:9.2f} {ce:12.2f} {ge + ce:10.2f}')
    print(f'{"TOTAL (" + a.start + " .. " + a.end + ")":<45s} {len(rows):5d} {sum(g[0] for g in groups.values()):9.1f} '
          f'{total_gpu:9.2f} {total_cpu:12.2f} {total_gpu + total_cpu:10.2f}')
    print('Estimate from allocated resources; excludes VAT and storage. V100 priced at 0.5 EUR/GPU-h (unlisted).')


if __name__ == '__main__':
    main()
