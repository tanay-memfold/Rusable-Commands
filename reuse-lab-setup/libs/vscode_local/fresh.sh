#!/bin/bash
# fresh.sh: fresh VM with ~/vscode-test/_tools ready (the library and this folder's test files).
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's/"reminders-test", "out"/"vscode-test", "_tools", "out"/' ../reminders_local/vcommon.py > vcommon.py; cp ../kit/vkit.py ../kit/ax.py ../kit/bigclip.py .
$M down && $M reset && $M up && $M put vscode-test/_tools ax.py bigclip.py vcommon.py vkit.py verify_vscode.py && (cd ../vscode && ../reminders_local/mvm.sh put vscode-test/_tools vscode.py)
