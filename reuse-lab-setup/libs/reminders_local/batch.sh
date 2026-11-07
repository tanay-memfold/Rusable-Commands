#!/bin/bash
# batch.sh <group> <seed> <states...>: a fresh VM, one verifier run, results copied back.
cd "$(dirname "$0")"; g=$1 s=$2; shift 2
./fresh.sh 2>&1 | tail -2 || exit 1
./mvm.sh sh "cd ~/reminders-test && python3 -u verify_reminders.py $g $s $*" > "results-$g.log" 2>&1
mkdir -p "../results/$g"; ./mvm.sh get "/Users/admin/reminders-test/out/$g.json" > "../results/$g/$g.json"; echo lib-RusableTest > "../results/$g.clone"
echo "done $g: PASS $(grep -c '^PASS' results-$g.log) FAIL $(grep -c '^FAIL' results-$g.log)"; grep -E '^FAIL|Traceback' "results-$g.log" | cut -c1-220 | head -30
