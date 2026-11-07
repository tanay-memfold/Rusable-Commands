#!/bin/bash
# fresh.sh: fresh VM with ~/notesold-test/_tools ready: the old verifier unchanged, its helpers, the library, and a wrapper.
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's#OUT = os.path.join(HOME, "verify-out")#OUT = os.path.join(HOME, "notesold-test", "_tools", "out")#' ../verify/vcommon.py > vcommon.py
cp ../verify/verify_notes.py ../verify/notes_db.py .
# Test fix (day 3b): front() returned an error when nothing was frontmost after the app quit; it now gives "".
python3 -c "import sys;p='verify_notes.py';s=open(p).read();o='''def front():\n    return osa('tell application \"System Events\" to return name of first process whose frontmost is true')''';n='''def front():\n    try:\n        return osa('tell application \"System Events\" to return name of first process whose frontmost is true')\n    except RuntimeError:\n        return \"\"''';assert s.count(o)==1;open(p,'w').write(s.replace(o,n))"
$M down && $M reset && $M up && $M put notesold-test/_tools vcommon.py verify_notes.py notes_db.py run_verify_notes.py && (cd ../notes && ../reminders_local/mvm.sh put notesold-test/_tools notes.py)
