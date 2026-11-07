"""What every verifier needs, inside the VM. Everything happens inside ~/<name>-test; results are read independently of the command tested.
Kit(name, module, app, group, seed): k.case(fn, mode, state, kind, setup, call, read, changes=..., big=False)."""
import hashlib, json, os, subprocess, sys, time, traceback, unicodedata, zlib, struct
HOME = os.path.expanduser("~")
class Outside(BaseException): pass
def nfc(p): return unicodedata.normalize("NFC", p)
def _front():
    from vcommon import osa
    try: return osa('tell application "System Events" to return name of first process whose frontmost is true')
    except RuntimeError: return ""
class Kit:
    def __init__(self, name, lib, app, group, seed, errors, start=None, clean=None):
        from vcommon import Recorder, Values
        import bigclip
        self.bigclip, self.lib, self.app, self.errors = bigclip, lib, app, errors
        self.ROOT = f"{HOME}/{name}-test"; self.TOOLS = f"{self.ROOT}/_tools"; self.DATA = f"{self.ROOT}/data"; self.name = name
        os.makedirs(self.DATA, exist_ok=True)
        self.V = Values(seed); self.start = start or (lambda state: None); self.clean = clean or (lambda state: True)
        self.rec = Recorder(group, {"versions": lib._versions(), "code_sha": hashlib.sha256(open(lib.__file__, "rb").read()).hexdigest()[:12], "seed": seed, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
        self.resume = int(os.environ.get("RESUME", "0")); self.only = set(filter(None, os.environ.get("FNS", "").split(",")))
        self.n = 0; self.fails = {}; self.outside0 = self.outside_view()
        open(f"{self.TOOLS}/verifier.pid", "w").write(str(os.getpid()))
    def inside(self, path):
        real = os.path.realpath(path)
        if not (real == self.ROOT or real.startswith(self.ROOT + os.sep)): raise Outside(f"a test path is outside {self.ROOT}: {path}")
        return path
    def outside_view(self):
        out = {}
        for n in os.listdir(HOME):
            if n in (f"{self.name}-test", "Library") or n.startswith("."): continue
            try: out[n] = os.lstat(os.path.join(HOME, n)).st_mtime
            except OSError: out[n] = None
        return out
    def check_outside(self, where):
        now = self.outside_view()
        if now != self.outside0: raise Outside(f"something outside the test folder changed at {where}: {sorted(k for k in set(now) | set(self.outside0) if now.get(k) != self.outside0.get(k))}")
    def tree(self):
        out = {}
        for base, dirs, files in os.walk(self.DATA):
            for n in dirs: out[nfc(os.path.join(base, n))] = None
            for n in files:
                p = os.path.join(base, n)
                if n == ".DS_Store" or os.path.islink(p): continue
                out[nfc(p)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
        return out
    def word(self): return self.V.word(1).replace(" ", "")
    def case(self, fn, mode, state, kind, setup, call, read, changes=lambda c: set(), big=False, clip=True, before=None, after=None, front=True):
        if self.only and fn not in self.only: return
        self.n += 1
        if self.n <= self.resume or self.fails.get((fn, mode), 0) >= 3: return
        print(f"CASE {self.n} {fn} {mode} {state} {kind}", flush=True)
        try:
            ctx = setup() or {}
            for v in ctx.values():
                if isinstance(v, str) and v.startswith("/"): self.inside(v)
            self.start(state, ctx) if self.start.__code__.co_argcount == 2 else self.start(state)
            if before: before(ctx)
            want = self.bigclip.fill(self.V.rng.randint(1, 10**9)) if big else None
            small = None
            if clip and not big:
                small = f"keep {self.V.word(1)}"; subprocess.run(["pbcopy"], input=small.encode())
            b = self.tree(); front0 = _front(); began = time.monotonic()
            try: res, err = call(ctx), None
            except (self.errors, ValueError) as e: res, err = None, e
            secs = round(time.monotonic() - began, 1)
            front1 = _front() if mode != "ui" and front else None  # before the test's own after-step, which may bring the app forward
            if after and err is None: after(ctx)
            end = time.monotonic() + 8
            while True:
                a = self.tree(); checks = read(ctx, b, a, res, err)
                if all(checks.values()) or time.monotonic() > end: break
                time.sleep(0.4)
            allowed = {nfc(x) for x in changes(ctx)}
            changed = [p for p in set(a) | set(b) if a.get(p, 0) != b.get(p, 0) and p not in allowed and not any(p.startswith(x + os.sep) for x in allowed)]
            checks["others_unchanged"] = not changed
            if want: checks.update(self.bigclip.check(want))
            elif clip: checks["clipboard_kept"] = subprocess.run(["pbpaste"], capture_output=True).stdout.decode(errors="replace") == small
            if mode == "ui": checks["nothing_left_open"] = bool(self.clean(state))
            elif front: checks["front_app_unchanged"] = front1 == front0 and (after is not None or _front() == front0)
            detail = repr(err)[:160] if err else (("changed: " + ", ".join(sorted(os.path.relpath(p, self.DATA) for p in changed))[:300]) if changed else None)
            self.rec.case(fn, mode, state, kind, checks, detail, secs)
            if not all(checks.values()): self.fails[(fn, mode)] = self.fails.get((fn, mode), 0) + 1
        except Outside: raise
        except Exception:
            self.rec.case(fn, mode, state, kind, {"harness": False}, traceback.format_exc()[-300:]); self.fails[(fn, mode)] = self.fails.get((fn, mode), 0) + 1
    def run(self, only, groups):
        """groups: [(label, function)]; only: labels from the command line."""
        try:
            try:
                self.check_outside("start")
                for label, fn in groups:
                    if label in only:
                        print(f"== state starts: {label} at {time.strftime('%H:%M:%S')}", flush=True); fn(); self.check_outside(label)
            except Outside as o:
                self.rec.data["meta"]["outside"] = str(o); print("OUTSIDE", o, flush=True)
        finally:
            self.rec.data["meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S"); self.rec.save(); print("DONE", flush=True)
def png(path, w=40, h=30, rgb=(200, 40, 60)):
    """A small made-up PNG."""
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"".join(b"\0" + bytes(rgb) * w for _ in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
