#!/bin/bash
# fresh.sh: fresh VM with ~/calold-test/_tools ready: the old verifier unchanged, its helpers, the library, and a wrapper.
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
sed 's#OUT = os.path.join(HOME, "verify-out")#OUT = os.path.join(HOME, "calold-test", "_tools", "out")#' ../verify/vcommon.py > vcommon.py
cp ../verify/verify_calendar.py ../verify/calendar_db.py .
# Test fix (day 3b): front() returned an error when nothing was frontmost after the app quit; it now gives "".
python3 -c "import sys;p='verify_calendar.py';s=open(p).read();o='''def front():\n    return osa('tell application \"System Events\" to return name of first process whose frontmost is true')''';n='''def front():\n    try:\n        return osa('tell application \"System Events\" to return name of first process whose frontmost is true')\n    except RuntimeError:\n        return \"\"''';assert s.count(o)==1;open(p,'w').write(s.replace(o,n))"
$M down && $M reset && $M up && $M put calold-test/_tools vcommon.py verify_calendar.py calendar_db.py run_verify_calendar.py && (cd ../calendar && ../reminders_local/mvm.sh put calold-test/_tools calendar_app.py)
