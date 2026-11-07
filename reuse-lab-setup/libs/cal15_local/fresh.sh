#!/bin/bash
# fresh.sh: fresh VM with ~/cal15-test/_tools ready (the library and this folder's test files).
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's/"reminders-test", "out"/"cal15-test", "_tools", "out"/' ../reminders_local/vcommon.py > vcommon.py; cp ../kit/vkit.py ../kit/ax.py ../kit/bigclip.py .
$M down && $M reset && $M up && $M put cal15-test/_tools ax.py bigclip.py vcommon.py vkit.py cal_more_db.py verify_cal15.py && (cd ../calendar && ../reminders_local/mvm.sh put cal15-test/_tools calendar_app.py)
