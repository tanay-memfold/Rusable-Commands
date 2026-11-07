#!/bin/bash
# fresh.sh <test name> <lib folder> <module.py> [local files in the kit or lib folder...]: fresh VM with ~/<name>-test/_tools ready.
cd "$(dirname "$0")"; n=$1 f=$2 m=$3; shift 3; M=../reminders_local/mvm.sh
sed "s/\"reminders-test\", \"out\"/\"$n-test\", \"_tools\", \"out\"/" ../reminders_local/vcommon.py > vcommon.py
$M down && $M reset && $M up && $M put $n-test/_tools ax.py bigclip.py vcommon.py vkit.py "$@" && (cd ../$f && ../reminders_local/mvm.sh put $n-test/_tools $m)
