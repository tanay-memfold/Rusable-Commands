#!/bin/bash
# fresh.sh: shut down, reset from golden, boot, install test files.
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
$M down && $M reset && $M up && $M put contacts-test ax.py bigclip.py vcommon.py con_db.py verify_contacts.py && (cd ../contacts && ../reminders_local/mvm.sh put contacts-test contacts.py)
