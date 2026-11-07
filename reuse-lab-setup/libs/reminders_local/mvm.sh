#!/bin/bash
# mvm.sh: the Reminders test VM on the Mac mini, over SSH. No tart. Only ever RusableTest and ~/rusable-lab.
#   mvm.sh check | reset | up | down | sh '<cmd>' | put <dir> <files...> | get <path> | shell (stdin) | relay-shutdown
set -u
. "$(dirname "$0")/../lab.env"  # MINI, VM_IP, VM_UUID
mini() { ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 -o RequestTTY=no -o ForwardAgent=no "$MINI" "$@"; }
VM='ssh -i $HOME/rusable-lab/ssh/id_rusable -o IdentitiesOnly=yes -o IdentityAgent=none -o BatchMode=yes -o ConnectTimeout=8 -o ServerAliveInterval=15 -o ServerAliveCountMax=4 -o RequestTTY=no -o PreferredAuthentications=publickey -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOME/rusable-lab/ssh/known_hosts -o ForwardAgent=no -o LogLevel=ERROR admin@'"$VM_IP"
COMMON='LAB=$HOME/rusable-lab; C=$LAB/RusableTest.utm; G=$LAB/'"${GOLDEN:-golden.utm}"'; R=$LAB/relay
vms() { ps -axo comm= | grep -cE "Virtualization\.VirtualMachine|qemu|QEMU"; }
others() { ps -axo command= | grep -cE "[b]ench\.sh|[r]un_name[ =]full-|[u]tmctl_server\.sh"; }
freegb() { df -k /System/Volumes/Data | awk "NR==2{print int(\$4/1048576)}"; }
ours() { [ "$(plutil -extract Information.Name raw -o - "$C/config.plist" 2>/dev/null)" = RusableTest ] && [ "$(plutil -extract Information.UUID raw -o - "$C/config.plist" 2>/dev/null)" = '"$VM_UUID"' ]; }
'
cmd=${1:-}; [ $# -gt 0 ] && shift
case "$cmd" in
check)
  mini /bin/sh <<REMOTE
$COMMON
echo "VMs \$(vms) | bench or his relay \$(others) | free GB \$(freegb) | copy \$(ours && echo ok || echo MISSING) | golden \$([ -d "\$G" ] && echo ok || echo MISSING)"
REMOTE
  ;;
reset)
  mini /bin/sh <<REMOTE
$COMMON
set -u
[ "\$(vms)" = 0 ] || { echo "reset refused: a VM is running"; exit 1; }
[ "\$(others)" = 0 ] || { echo "reset refused: bench or his relay is running"; exit 1; }
ours && [ -d "\$G" ] || { echo "reset refused: copy or golden is missing"; exit 1; }
for f in \$(cd "\$G/Data" && ls); do
  before=\$(df -k /System/Volumes/Data | awk 'NR==2{print \$4}')
  [ -e "\$C/Data/.new-\$f" ] && { echo "leftover temp file: stopping"; exit 1; }
  cp -c "\$G/Data/\$f" "\$C/Data/.new-\$f" & p=\$!; s=\$(date +%s)
  while kill -0 \$p 2>/dev/null; do
    now=\$(df -k /System/Volumes/Data | awk 'NR==2{print \$4}')
    if [ \$((before-now)) -gt 2097152 ] || [ \$(( \$(date +%s)-s )) -gt 60 ]; then kill \$p; echo "GUARD stopped cp: not cloning"; exit 1; fi
    sleep 1
  done
  wait \$p || { echo "cp -c failed for \$f: stopping"; exit 1; }
  mv -f "\$C/Data/.new-\$f" "\$C/Data/\$f"
done
echo "reset done, free GB \$(freegb)"
REMOTE
  ;;
up)
  mini /bin/sh <<REMOTE || exit 1
$COMMON
[ "\$(vms)" = 0 ] && [ "\$(others)" = 0 ] && [ "\$(freegb)" -ge 6 ] && ours || { echo "not starting: VMs \$(vms), bench \$(others), free \$(freegb), copy \$(ours && echo ok || echo missing)"; exit 1; }
if [ ! -e "\$R/alive" ] || [ \$(( \$(date +%s) - \$(stat -f %m "\$R/alive") )) -gt 5 ]; then
  open -a Terminal "\$R/rusable-relay.command"; echo "\$(date '+%F %T') relay opened in Terminal" >> "\$LAB/CREATED.txt"
  i=0; while [ \$i -lt 15 ] && { [ ! -e "\$R/alive" ] || [ \$(( \$(date +%s) - \$(stat -f %m "\$R/alive") )) -gt 5 ]; }; do sleep 1; i=\$((i+1)); done
fi
out=\$("\$R/rusable-utmctl" start 2>&1); rc=\$?; echo "start rc \$rc: \$(echo "\$out" | tr '\n' ' ')"
[ "\$rc" = 0 ] || exit 1
i=0; while [ \$i -lt 60 ]; do $VM -n 'stat -f%Su /dev/console' 2>/dev/null | grep -qx admin && { echo "VM up after \$((i*5))s, VMs \$(vms)"; exit 0; }; sleep 5; i=\$((i+1)); done
echo "VM didn't answer SSH in 5 minutes"; exit 1
REMOTE
  ;;
down)
  mini /bin/sh <<REMOTE
$COMMON
[ "\$(vms)" = 0 ] && { echo "no VM running"; exit 0; }
$VM -n 'pkill -x TextEdit; pkill -x Contacts; pkill -x Reminders; pkill -x Calendar; pkill -x Notes; pkill -x Safari; pkill -x Preview; pkill -x Keka; pkill -x "System Settings"; pkill -x Obsidian; pkill -x soffice; pkill -x Automator; pkill -x Shortcuts; pkill -x Electron; pkill -x "Code"; pkill -x "Anaconda-Navigator"; pkill -f anaconda3/bin/anaconda-navigator; pkill -f Anaconda-Navigator.app/Contents/MacOS/run.py; pkill -x Xcode; pkill -x OBS; sleep 2; perl -e "alarm 20; exec @ARGV" osascript -e "tell application \"System Events\" to shut down"' 2>&1 | cut -c1-120
i=0; while [ \$i -lt 36 ]; do [ "\$(vms)" = 0 ] && { echo "VM down after \$((i*5))s, free GB \$(freegb)"; exit 0; }; sleep 5; i=\$((i+1)); done
echo "VM still running after 3 minutes: not forcing it"; exit 1
REMOTE
  ;;
sh) mini "$VM -n $(printf %q "$*")" ;;
shell) mini "$VM /bin/sh" ;;
put) dir=$1; shift; COPYFILE_DISABLE=1 tar cf - "$@" | mini "$VM $(printf %q "mkdir -p \$HOME/$dir && tar xf - -C \$HOME/$dir")" ;;
get) mini "$VM -n $(printf %q "cat \"$1\"")" ;;
save-base)
  # save-base <name>: clone RusableTest's disk into a new base. Never overwrites, never a full copy.
  N=$1; NOTE=${2:-base with Chrome}; mini /bin/sh <<REMOTE
$COMMON
set -u
[ "\$(vms)" = 0 ] || { echo "refused: a VM is running"; exit 1; }
ours || { echo "refused: copy missing"; exit 1; }
T="\$LAB/$N"; [ -e "\$T" ] && { echo "refused: \$T exists"; exit 1; }
mkdir -p "\$T/Data"
for f in \$(cd "\$C/Data" && ls); do
  before=\$(df -k /System/Volumes/Data | awk 'NR==2{print \$4}')
  cp -c "\$C/Data/\$f" "\$T/Data/\$f" & p=\$!; s=\$(date +%s)
  while kill -0 \$p 2>/dev/null; do
    now=\$(df -k /System/Volumes/Data | awk 'NR==2{print \$4}')
    if [ \$((before-now)) -gt 2097152 ] || [ \$(( \$(date +%s)-s )) -gt 60 ]; then kill \$p; echo "GUARD stopped cp: not cloning"; exit 1; fi
    sleep 1
  done
  wait \$p || { echo "cp -c failed for \$f: stopping"; exit 1; }
done
echo "\$(date '+%F %T') $N: $NOTE, cloned with cp -c from RusableTest's disk; never registered or booted" >> "\$LAB/CREATED.txt"
echo "saved $N, free GB \$(freegb)"; ls -la "\$T/Data"
REMOTE
  ;;
relay-shutdown) mini '$HOME/rusable-lab/relay/rusable-utmctl shutdown' ;;
*) echo "usage" >&2; exit 2 ;;
esac
