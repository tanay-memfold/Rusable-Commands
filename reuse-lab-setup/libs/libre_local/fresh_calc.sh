#!/bin/bash
# fresh_calc.sh: fresh VM with ~/libre-test/_tools ready (calc.py and this folder's test files).
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's/"reminders-test", "out"/"libre-test", "_tools", "out"/' ../reminders_local/vcommon.py > vcommon.py; cp ../kit/vkit.py ../kit/ax.py ../kit/bigclip.py .
$M down && $M reset && $M up && $M put libre-test/_tools ax.py bigclip.py vcommon.py vkit.py verify_calc.py lo_close.py && (cd ../libreoffice && ../reminders_local/mvm.sh put libre-test/_tools calc.py)
