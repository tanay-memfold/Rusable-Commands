#!/bin/bash
. "$(dirname "$0")/../lab.env"
# Every 2 minutes: if another VM or bench.sh appears, or disk is low, shut ours down cleanly and report. If the copy is gone, report.
here=$(cd "$(dirname "$0")" && pwd)
while true; do
  s=$(ssh -o BatchMode=yes -o ConnectTimeout=10 -o RequestTTY=no "$MINI" "echo \$(ps -axo comm= | grep -cE 'Virtualization\.VirtualMachine|qemu|QEMU') \$(ps -axo command= | grep -cE '[b]ench\.sh|[r]un_name[ =]full-|[u]tmctl_server\.sh') \$(df -k /System/Volumes/Data | awk 'NR==2{print int(\$4/1048576)}') \$(test -d \$HOME/rusable-lab/RusableTest.utm && echo copy || echo nocopy)" 2>/dev/null)
  set -- $s
  if [ -n "${4:-}" ]; then
    [ "$4" = nocopy ] && { echo "COPY GONE: $s"; exit 0; }
    if [ "$1" -ge 2 ] || [ "$2" -ge 1 ] || [ "$3" -lt 6 ]; then echo "SHUTTING DOWN: VMs $1 bench $2 free $3"; touch "$here/STOP"; "$here/mvm.sh" down; "$here/mvm.sh" relay-shutdown; exit 0; fi
  fi
  sleep 120
done
