#!/bin/bash
# fresh.sh: fresh VM with ~/obsidian-test/_tools ready (the library and this folder's test files).
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's/"reminders-test", "out"/"obsidian-test", "_tools", "out"/' ../reminders_local/vcommon.py > vcommon.py; cp ../kit/vkit.py ../kit/ax.py ../kit/bigclip.py .
$M down && $M reset && $M up && $M put obsidian-test/_tools ax.py bigclip.py vcommon.py vkit.py verify_obsidian.py && (cd ../obsidian && ../reminders_local/mvm.sh put obsidian-test/_tools obsidian.py)
