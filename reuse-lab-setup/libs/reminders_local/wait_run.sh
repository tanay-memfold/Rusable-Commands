#!/bin/bash
# wait_run.sh <process pattern> <log file>...: wait until the run ends. If its logs don't grow for 20 minutes, stop it with a plain kill.
pat=$1; shift; last=""; since=$(date +%s)
while pgrep -f "$pat" >/dev/null; do
  now=$(cat "$@" results-*.log 2>/dev/null | wc -c)
  if [ "$now" != "$last" ]; then last=$now; since=$(date +%s); fi
  if [ $(( $(date +%s) - since )) -gt 1200 ]; then echo "NO LOG GROWTH for 20 minutes: stopping $pat with a plain kill"; pkill -f "$pat"; pkill -f runner.py; break; fi
  sleep 30
done
date '+%H:%M run ended'; tail -6 "$1" | cut -c1-200
