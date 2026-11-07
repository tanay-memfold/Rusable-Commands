#!/bin/bash
# fresh.sh: fresh VM from golden-shortcuts.utm (golden + the user's Shortcuts Events Allow) with ~/shortcuts-test/_tools ready.
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's/"reminders-test", "out"/"shortcuts-test", "_tools", "out"/' ../reminders_local/vcommon.py > vcommon.py; cp ../kit/vkit.py ../kit/ax.py ../kit/bigclip.py .
$M down && GOLDEN=golden-shortcuts.utm $M reset && $M up && $M put shortcuts-test/_tools ax.py bigclip.py vcommon.py vkit.py $(ls verify_shortcuts.py 2>/dev/null) && { [ -e ../shortcuts/shortcuts.py ] && (cd ../shortcuts && ../reminders_local/mvm.sh put shortcuts-test/_tools shortcuts.py) || true; }
