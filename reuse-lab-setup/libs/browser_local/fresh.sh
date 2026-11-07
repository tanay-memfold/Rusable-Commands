#!/bin/bash
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
$M down && $M reset && $M up && $M put browser-test ax.py vcommon.py verify_safari.py bigclip.py && (cd ../safari && ../reminders_local/mvm.sh put browser-test safari.py)
