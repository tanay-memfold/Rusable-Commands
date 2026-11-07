#!/bin/bash
cd "$(dirname "$0")"; M=../reminders_local/mvm.sh
$M down && GOLDEN=golden-chrome.utm $M reset && $M up && $M put browser-test ax.py vcommon.py verify_chrome.py bigclip.py && (cd ../chrome && ../reminders_local/mvm.sh put browser-test chrome.py)
