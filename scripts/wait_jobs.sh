#!/bin/bash
# wait_jobs.sh <max_min> <jobid>... — block until any job leaves PENDING/RUNNING, or max_min minutes pass.
# Prints one compact sacct line per job. Cheap enough for the login node (one sacct call per minute).
if (( $# < 2 )); then echo "usage: wait_jobs.sh <max_min> <jobid>..." >&2; exit 2; fi
max=$(( $1*60 )); shift; ids=$(IFS=,; echo "$*"); t=0
while (( t < max )); do
  s=$(sacct -j "$ids" -X -n -P -o State | sort -u)
  [[ -n $s ]] && grep -qvE '^(PENDING|RUNNING)$' <<<"$s" && break
  sleep 60; t=$((t+60))
done
sacct -j "$ids" -X -n -o JobID%15,JobName%25,State,Elapsed,ExitCode
