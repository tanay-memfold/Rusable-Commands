#!/bin/bash
# fresh_settings.sh: fresh VM with ~/settings-test/_tools ready (system_settings.py and this folder's test files).
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's/"reminders-test", "out"/"settings-test", "_tools", "out"/' ../reminders_local/vcommon.py > vcommon.py; cp ../kit/vkit.py ../kit/ax.py ../kit/bigclip.py .
$M down && $M reset && $M up && $M put settings-test/_tools ax.py bigclip.py vcommon.py vkit.py verify_settings.py && (cd ../settings && ../reminders_local/mvm.sh put settings-test/_tools system_settings.py)
