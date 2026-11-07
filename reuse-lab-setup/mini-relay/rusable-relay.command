#!/bin/sh
# Runs in a Terminal window on the Mini's desktop, where utmctl is allowed to work.
# Does one of three fixed things, only for RusableTest: status, start, stop. Everything else is refused and logged.
# Nothing from a request reaches a shell: the request's text is only compared with fixed words.
# Exits after 2 idle minutes, or when the SHUTDOWN file appears.
set -u
umask 077
PATH=/usr/bin:/bin
export PATH

LAB="$HOME/rusable-lab"
RELAY="$LAB/relay"
QUEUE="$RELAY/queue"
DONE="$RELAY/done"
LOG="$RELAY/relay.log"
LOCK="$RELAY/lock"
ALIVE="$RELAY/alive"
SHUTDOWN="$RELAY/SHUTDOWN"
COPY="$LAB/RusableTest.utm"
UTMCTL=/Applications/UTM.app/Contents/MacOS/utmctl
UUID=$(sed -n "s/^VM_UUID=//p" "$(dirname "$0")/lab.env")  # set in lab.env next to this script
NAME=RusableTest
IDLE_SECONDS=1800
CALL_SECONDS=60

log() {
    printf '%s %s\n' "$(date '+%F %T')" "$1" | tee -a "$LOG"
}

mkdir -p "$QUEUE" "$DONE"
if ! mkdir "$LOCK" 2>/dev/null; then
    log "another relay holds the lock: exiting"
    exit 1
fi
trap 'rm -f "$ALIVE"; rmdir "$LOCK"; log "relay stopped"' EXIT
trap 'exit 1' HUP INT TERM
rm -f "$SHUTDOWN"
log "relay started"

copy_is_ours() {
    [ "$(plutil -extract Information.UUID raw -o - "$COPY/config.plist" 2>/dev/null)" = "$UUID" ] &&
        [ "$(plutil -extract Information.Name raw -o - "$COPY/config.plist" 2>/dev/null)" = "$NAME" ]
}

vms_running() {
    ps -axo comm= | grep -cE 'Virtualization\.VirtualMachine|qemu|QEMU'
}

# Writes the answer next to the request. It appears all at once, so the client never reads half of it.
answer() {
    id=$1
    code=$2
    printf 'exit %s\n' "$code" >> "$QUEUE/$id.tmp"
    mv "$QUEUE/$id.tmp" "$QUEUE/$id.out"
}

refuse() {
    id=$1
    reason=$2
    log "REFUSED: $reason"
    printf 'refused: %s\n' "$reason" >> "$QUEUE/$id.tmp"
    answer "$id" 1
}

# Fixed commands only. The time limit exits with 142.
utm() {
    id=$1
    shift
    perl -e 'alarm shift; exec @ARGV' "$CALL_SECONDS" "$UTMCTL" "$@" >> "$QUEUE/$id.tmp" 2>&1
    answer "$id" $?
}

handle() {
    file=$1
    name=${file##*/}
    id=${name%.req}
    case "$id" in
        "" | *[!A-Za-z0-9-]*)
            log "REFUSED: a request with a bad file name"
            mv "$file" "$DONE/refused-$(date +%s)-$$.req"
            return
            ;;
    esac
    : > "$QUEUE/$id.tmp"
    if [ -L "$file" ] || [ ! -f "$file" ]; then
        refuse "$id" "not a plain file"
    elif [ "$(wc -c < "$file" | tr -d ' ')" -gt 16 ] || [ "$(wc -l < "$file" | tr -d ' ')" != 1 ]; then
        refuse "$id" "not one short line"
    else
        IFS= read -r verb < "$file"
        safe=$(printf '%s' "$verb" | tr -cd 'A-Za-z0-9_-' | cut -c1-16)
        if ! copy_is_ours; then
            refuse "$id" "RusableTest is missing or isn't ours"
        else
            case "$verb" in
                status)
                    log "status"
                    utm "$id" status "$UUID"
                    ;;
                start)
                    if [ "$(vms_running)" != 0 ]; then
                        refuse "$id" "start while a VM is running"
                    else
                        log "start"
                        utm "$id" start "$UUID"
                    fi
                    ;;
                stop)
                    log "stop (asks the guest to shut down)"
                    utm "$id" stop --request "$UUID"
                    ;;
                *)
                    refuse "$id" "not allowed: $safe"
                    ;;
            esac
        fi
    fi
    mv "$file" "$DONE/$id.req"
}

last=$(date +%s)
while :; do
    touch "$ALIVE"
    if [ -e "$SHUTDOWN" ]; then
        log "SHUTDOWN file found"
        rm -f "$SHUTDOWN"
        exit 0
    fi
    for file in "$QUEUE"/*.req; do
        if [ -e "$file" ] || [ -L "$file" ]; then
            handle "$file"
            last=$(date +%s)
        fi
    done
    if [ $(( $(date +%s) - last )) -ge "$IDLE_SECONDS" ]; then
        log "idle for $IDLE_SECONDS seconds"
        exit 0
    fi
    sleep 1
done
