#!/bin/bash
# fresh.sh: shut down, reset from golden, boot, install test files inside ~/textedit-test/_tools only.
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
$M down && $M reset && $M up && $M put textedit-test/_tools ax.py bigclip.py vcommon.py verify_textedit.py && (cd ../textedit && ../reminders_local/mvm.sh put textedit-test/_tools textedit.py)
