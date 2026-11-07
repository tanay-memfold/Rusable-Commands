#!/usr/bin/env python3
"""runner.py <group> <seed> <states...>: run the verifier from the laptop with time limits it enforces itself.
Env: CASE_LIMIT (s, default 240), BATCH_LIMIT (s, default 3600), MODES, FNS. A case over its limit, or a lost connection,
is written to the log and the results as a failure; the verifier is stopped with a plain kill and resumes at the next case.
The log and results are per group: results-<group>.log and ../results/<group>/<group>.json."""
import json, os, select, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
group, seed, states = sys.argv[1], sys.argv[2], sys.argv[3:]
CASE_LIMIT = int(os.environ.get("CASE_LIMIT", "240")); BATCH_LIMIT = int(os.environ.get("BATCH_LIMIT", "3600"))
TOOLS = os.environ.get("TOOLS", "reminders-test"); VERIFIER = os.environ.get("VERIFIER", "verify_reminders.py"); OUTDIR = os.environ.get("OUTDIR", "reminders-test/out")
extra = " ".join(f"{k}={os.environ[k]}" for k in ("MODES", "FNS") if os.environ.get(k))
LOG = open(os.path.join(HERE, f"results-{group}.log"), "a", buffering=1)
def note(text): LOG.write(text + "\n"); print(text, flush=True)
def mvm(*a, **k): return subprocess.run([os.path.join(HERE, "mvm.sh"), *a], capture_output=True, text=True, timeout=k.get("timeout", 60))
os.makedirs(os.path.join(HERE, "..", "results", group), exist_ok=True)
start, resume, part, cases, meta, attempt_fail = time.monotonic(), 0, 0, [], {}, 0
def collect(name):
    global meta
    try:
        d = json.loads(mvm("get", f"/Users/admin/{OUTDIR}/{name}.json").stdout)
        cases.extend(d["cases"]); meta = meta or d["meta"]
        return bool(d["meta"].get("finished"))
    except Exception as e:
        note(f"NOTE couldn't read {name}'s results: {type(e).__name__}")
    return False
def save():
    with open(os.path.join(HERE, "..", "results", group, f"{group}.json"), "w") as h:
        json.dump({"group": group, "meta": meta, "cases": cases}, h, indent=1, ensure_ascii=False)
    open(os.path.join(HERE, "..", "results", f"{group}.clone"), "w").write("RusableTest (fresh from golden)")
last_case = None
while True:
    part += 1; name = f"{group}.{part}"
    cmd = f"cd ~/{TOOLS} && RESUME={resume} {extra} python3 -u {VERIFIER} {name} {int(seed)+part} {' '.join(states)}"
    p = subprocess.Popen([os.path.join(HERE, "mvm.sh"), "sh", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    os.set_blocking(p.stdout.fileno(), False)
    last, buffer, done, why = time.monotonic(), "", False, None
    while True:
        ready, _, _ = select.select([p.stdout], [], [], 5)
        if ready:
            chunk = p.stdout.read()
            if chunk == "" or chunk is None:
                if p.poll() is not None: break
            else:
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    note(line[:400]); last = time.monotonic()
                    if line.startswith("CASE "): last_case = line.split(" ", 2); resume = int(last_case[1])
                    if line.startswith("DONE"): done = True
        if done or (p.poll() is not None and not ready): break
        if time.monotonic() - last > CASE_LIMIT: why = f"no progress for {CASE_LIMIT}s"; break
        if time.monotonic() - start > BATCH_LIMIT: why = f"batch limit {BATCH_LIMIT}s"; break
    if why or done:
        p.terminate()
        try: p.wait(10)
        except subprocess.TimeoutExpired: p.kill()
    if not done and why is None: why = "the connection to the verifier ended early"
    if why == "the connection to the verifier ended early":
        # One retry across the whole run: a second drop stops it, and the script running the batches sees STOP.
        drops = os.path.join(HERE, "DROPS"); count = (int(open(drops).read()) if os.path.exists(drops) else 0) + 1
        open(drops, "w").write(str(count)); note(f"NOTE connection drop {count} at {time.strftime('%H:%M:%S')}")
        if count >= 3:
            open(os.path.join(HERE, "STOP"), "w").close(); collect(name); save(); note(f"BATCH STOPPED {group}: third connection drop in a row"); break
    finished = collect(name)
    if (done and not why) or finished:
        # The results say the run finished, even if its connection stayed open or its last lines were lost.
        save(); note(f"BATCH DONE {group}" + (f" ({why})" if why else "")); break
    desc = " ".join(last_case[2:]) if last_case else "before any case"
    fn, mode, state, kind = (last_case[2].split() + ["?"] * 4)[:4] if last_case else ("verifier", "ui", "?", "?")
    note(f"FAIL time limit: {desc}: {why}")
    if not any(c["function"] == fn and c["mode"] == mode and c["state"] == state and c["kind"] == kind for c in cases):
        cases.append({"function": fn, "mode": mode, "state": state, "kind": kind, "passed": False, "checks": {"within_time_limit": False}, "detail": why, "seconds": None})
    save()
    try: mvm("sh", f'test -f ~/{TOOLS}/verifier.pid && kill $(cat ~/{TOOLS}/verifier.pid) 2>/dev/null; rm -f ~/{TOOLS}/verifier.pid', timeout=30)
    except Exception: note("NOTE couldn't reach the VM to stop the verifier")
    if time.monotonic() - start > BATCH_LIMIT: note(f"BATCH STOPPED {group}: time limit"); break
    alive = False
    try: alive = mvm("sh", "echo up", timeout=30).stdout.strip() == "up"
    except Exception: pass
    if not alive: note(f"BATCH STOPPED {group}: the VM isn't answering"); break
    time.sleep(3)
if done: open(os.path.join(HERE, "DROPS"), "w").write("0")  # a finished batch ends a run of drops
print(f"{group}: PASS {sum(c['passed'] for c in cases)} FAIL {sum(not c['passed'] for c in cases)}", flush=True)
