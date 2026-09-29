# Pricing and cost estimation

Source: https://hpc.ut.ee/pricing/overview and https://hpc.ut.ee/pricing/calculate-costs (UT order No. 3-1/AT/108,
valid from 1 July 2026). Prices in EUR. VAT (24%) is added for accounts outside the University of Tartu.

## Rates

| Resource | Price |
|---|---|
| CPU | 0.012 EUR per core-hour |
| Memory | 0.012 EUR per 6 GB-hour |
| CPU/memory charge | `max(cores, memory_GB / 6) × hours × 0.012` (whichever has more units) |
| A100 (40 or 80 GB) | 0.5 EUR per GPU-hour |
| H200 | 2.0 EUR per GPU-hour |
| B200 (public sector only) | 2.0 EUR per GPU-hour |
| V100 | not listed ("GPU from 0.5"); assume ≤ 0.5 |
| Project storage (GPFS) | 80 EUR per TB-year (+30 for a tape copy) |
| S3 object storage | 160 EUR per TB-year |
| Home directory | free up to the default quota |

Examples from the docs: 1 core, 2 GB, 10 h costs `max(1, 2/6) × 10 × 0.012 = 0.12 EUR`. 1 core, 12 GB, 10 h costs
`max(1, 12/6) × 10 × 0.012 = 0.24 EUR`.

**Open points:** the pricing pages don't say whether GPU jobs pay the CPU/memory units *in addition to* the GPU rate.
`scripts/hpc_cost.py` assumes they do (an upper bound) and prints the two parts separately. Invoicing goes through ETAIS
allocations, and Slurm's `billing` TRES (equal to the CPU count) is not the invoice.

## Billing is on the allocation

You pay for what you **allocate** for as long as the job runs, not what you use. What that means in practice:
- An idle GPU or a finished-but-still-running job costs the same as a busy one, so end jobs promptly.
- Oversized `--mem` is billed. For example, 4 A100s × 36 h with 400 GB and 64 cores:
  - GPUs: 144 GPU-h × 0.5 = 72 EUR
  - CPU/memory: `max(64, 400/6 = 67) × 36 × 0.012 = 29 EUR`
  - With 200 GB and 32 cores the CPU/memory part is 14 EUR.

## Estimating a run before submitting

```
gpu_cost   = n_gpus × expected_hours × gpu_rate
cpu_mem    = max(cores, mem_GB / 6) × expected_hours × 0.012
total      ≈ gpu_cost + cpu_mem        (upper bound, see open point above)
```

Measure `expected_hours` from a short run (seconds per step × steps). State GPU-hours and EUR when proposing a run.

## Reporting spending

- `scripts/hpc_cost.py --account <acct> --start 2026-09-01 [--user <u>] [--by job|gpu|day]` prices every job from
  `sacct` with the rates above.
- `sreport -t hours cluster AccountUtilizationByUser account=<acct> start=YYYY-MM-DD --tres=cpu,gres/gpu` gives Slurm's
  own core-hour and GPU-hour totals, a cross-check without prices.
- ETAIS users: usage reports per allocation at https://minu.etais.ee.
