#!/bin/bash
# run_app.sh <folder> <module.py> <tools dir in VM> <verifier> <fresh script> <group:seed:state,state>...: batches, a fresh VM each.
cd "$(dirname "$0")"; M=./mvm.sh; R=./runner.py
folder=$1 module=$2 tools=$3 ver=$4 fresh=$5; shift 5
stop() { echo "STOPPED: $*"; exit 1; }
for spec in "$@"; do
  group=${spec%%:*}; rest=${spec#*:}; seed=${rest%%:*}; states=${rest#*:}; states=${states//,/ }
  [ -e STOP ] && stop "the connection or VM dropped, or the watcher fired"
  $M check | grep -q 'bench or his relay 0' || { $M down; $M relay-shutdown; touch STOP; stop "$($M check)"; }
  # Ours is shut down first, so any VM still running is someone else's: then stop for good.
  $M down >/dev/null 2>&1
  $M check | grep -q '^VMs 0 |' || { $M relay-shutdown; touch STOP; stop "another VM is running: $($M check)"; }
  $fresh 2>&1 | tail -1
  want=$(shasum -a 256 "../$folder/$module" | cut -c1-12)
  got=$($M sh "shasum -a 256 ~/$tools/$module" | cut -c1-12)
  if [ "$want" != "$got" ]; then echo "fresh VM didn't take ($got); one more try"; sleep 30; $fresh 2>&1 | tail -1; got=$($M sh "shasum -a 256 ~/$tools/$module" | cut -c1-12); fi
  [ "$want" = "$got" ] || stop "$group: code in the VM ($got) isn't the final code ($want)"
  up=$($M sh 'date +%s; sysctl -n kern.boottime' | tr -c '0-9\n' ' ' | awk 'NR==1{n=$1} NR==2{print n-$1}')
  [ "${up:-999}" -lt 400 ] || stop "$group: the VM isn't freshly started (up ${up}s)"
  TOOLS=$tools VERIFIER=$ver OUTDIR=$tools/out CASE_LIMIT=${CASE_LIMIT:-240} BATCH_LIMIT=${BATCH_LIMIT:-3400} FNS=${FNS:-} MODES=${MODES:-} $R "$group" "$seed" $states | grep -vE '^(PASS|CASE) ' | cut -c1-300
  echo "$want" > "../results/$group.sha"
done
$M check
