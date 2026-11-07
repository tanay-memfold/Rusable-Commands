#!/bin/bash
# fresh.sh: fresh VM with ~/obs-test/_tools ready (the library and this folder's test files).
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's/"reminders-test", "out"/"obs-test", "_tools", "out"/' ../reminders_local/vcommon.py > vcommon.py; cp ../kit/vkit.py ../kit/ax.py ../kit/bigclip.py .
$M down && $M reset && $M up && $M put obs-test/_tools ax.py bigclip.py vcommon.py vkit.py verify_obs.py && (cd ../obs && ../reminders_local/mvm.sh put obs-test/_tools obs.py)
