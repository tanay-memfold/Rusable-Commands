#!/bin/bash
# fresh.sh: fresh VM with ~/anaconda-test/_tools ready (the library and this folder's test files).
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's/"reminders-test", "out"/"anaconda-test", "_tools", "out"/' ../reminders_local/vcommon.py > vcommon.py; cp ../kit/vkit.py ../kit/ax.py ../kit/bigclip.py .
$M down && $M reset && $M up && $M put anaconda-test/_tools ax.py bigclip.py vcommon.py vkit.py verify_anaconda_day4.py && (cd ../anaconda && ../reminders_local/mvm.sh put anaconda-test/_tools anaconda.py)
