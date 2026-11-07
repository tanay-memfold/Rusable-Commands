#!/bin/bash
# fresh.sh: fresh VM with ~/notes15-test/_tools ready (the library and this folder's test files).
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's/"reminders-test", "out"/"notes15-test", "_tools", "out"/' ../reminders_local/vcommon.py > vcommon.py; cp ../kit/vkit.py ../kit/ax.py ../kit/bigclip.py .
$M down && $M reset && $M up && $M put notes15-test/_tools ax.py bigclip.py vcommon.py vkit.py notes_db.py att_db.py verify_notes15.py && (cd ../notes && ../reminders_local/mvm.sh put notes15-test/_tools notes.py)
