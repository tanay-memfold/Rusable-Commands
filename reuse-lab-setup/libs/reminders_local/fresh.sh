#!/bin/bash
# fresh.sh: shut down, reset from golden, boot, install test files.
cd "$(dirname "$0")"
./mvm.sh down && ./mvm.sh reset && ./mvm.sh up && ./mvm.sh put reminders-test ax.py bigclip.py vcommon.py rem_db.py verify_reminders.py && (cd ../reminders && ../reminders_local/mvm.sh put reminders-test reminders.py)
