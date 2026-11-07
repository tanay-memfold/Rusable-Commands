#!/bin/bash
# fresh.sh: shut down, reset from golden, boot, install test files inside ~/finder-test/_tools only.
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
$M down && $M reset && $M up && $M put finder-test/_tools ax.py vcommon.py verify_finder.py bigclip.py && (cd ../finder && ../reminders_local/mvm.sh put finder-test/_tools finder.py)
