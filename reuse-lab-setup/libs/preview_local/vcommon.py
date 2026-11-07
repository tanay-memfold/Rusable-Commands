"""Shared pieces of the in-clone verifiers: shell and script calls for setting up start states (never the library
under test), screenshots and their comparison, fresh values, and result recording."""
import json
import os
import random
import subprocess
import time
import zlib

HOME = os.path.expanduser("~")
OUT = os.path.join(HOME, "preview-test", "_tools", "out")
REGION = "0,26,1024,660"
WORDS = ["Quartz", "River", "Glass", "Tide", "Maple", "Copper", "Harbor", "Meadow", "Lantern", "Canyon", "Ember",
         "Willow", "Cobalt", "Summit", "Marble", "Orchid", "Fjord", "Basalt", "Saffron", "Juniper", "Indigo", "Larch"]
SPECIAL = ["Café crème ✨", 'Say "hi" — it\'s fine', "Zoë & Jürgen 🚲", "Ünïcødé ☕️ test", "50% off <b>bold</b>"]


def sh(command: str, check: bool = False) -> str:
    done = subprocess.run(["/bin/sh", "-c", command], capture_output=True, text=True)
    if check and done.returncode:
        raise RuntimeError(f"{command}: {done.stderr.strip()}")
    return done.stdout.strip()


def osa(script: str, *args: str, lang: str = "AppleScript") -> str:
    done = subprocess.run(["osascript", "-l", lang, "-e", script, *args], capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(done.stderr.strip())
    return done.stdout.strip()


def se(body: str, *args: str) -> str:
    """A System Events step inside process `APP` given as argv[1] (setup only)."""
    return osa("on run argv\ntell application \"System Events\" to tell process (item 1 of argv)\n" + body +
               "\nend tell\nend run", *args)


class Values:
    """Fresh made-up values; none repeats within a run."""

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.used = set()

    def word(self, words: int = 2) -> str:
        while True:
            value = " ".join(self.rng.choice(WORDS) for _ in range(words)) + f" {self.rng.randint(10, 9999)}"
            if value not in self.used:
                self.used.add(value)
                return value

    def special(self) -> str:
        while True:
            value = f"{self.rng.choice(SPECIAL)} {self.rng.randint(10, 9999)}"
            if value not in self.used:
                self.used.add(value)
                return value


def screenshot(name: str, region: str = REGION) -> str:
    """The screen below the menu bar and above the Dock (region: x,y,w,h in points)."""
    path = os.path.join(OUT, "shots", name + ".png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sh(f"screencapture -x -R{region} '{path}'")
    return path


def png_rows(path: str) -> list:
    """The PNG's filtered scanlines (identical pixels give identical rows from the same encoder)."""
    with open(path, "rb") as handle:
        data = handle.read()
    position, idat, width, height, depth = 8, b"", 0, 0, 4
    while position < len(data):
        length = int.from_bytes(data[position:position + 4], "big")
        kind = data[position + 4:position + 8]
        chunk = data[position + 8:position + 8 + length]
        if kind == b"IHDR":
            width, height = int.from_bytes(chunk[0:4], "big"), int.from_bytes(chunk[4:8], "big")
            depth = {6: 4, 2: 3}.get(chunk[9], 4) * chunk[8] // 8
        elif kind == b"IDAT":
            idat += chunk
        position += 12 + length
    raw = zlib.decompress(idat)
    stride = width * depth + 1
    return [raw[row * stride:(row + 1) * stride] for row in range(height)]


def rows_changed(before: str, after: str) -> int:
    first, second = png_rows(before), png_rows(after)
    if len(first) != len(second):
        return max(len(first), len(second))
    return sum(1 for a, b in zip(first, second) if a != b)


class Recorder:
    def __init__(self, group: str, meta: dict):
        self.path = os.path.join(OUT, f"{group}.json")
        os.makedirs(OUT, exist_ok=True)
        self.data = {"group": group, "meta": meta, "cases": []}

    def case(self, function: str, mode: str, state: str, kind: str, checks: dict, detail=None, seconds=None):
        ok = all(checks.values()) if checks else False
        self.data["cases"].append({"function": function, "mode": mode, "state": state, "kind": kind,
                                   "passed": ok, "checks": checks, "detail": detail, "seconds": seconds})
        mark = "PASS" if ok else "FAIL"
        failed = [name for name, value in checks.items() if not value]
        print(f"{mark} {function} [{mode}] {state} {kind} {failed if failed else ''} {detail if not ok else ''}",
              flush=True)
        self.save()

    def save(self):
        with open(self.path, "w") as handle:
            json.dump(self.data, handle, indent=1, ensure_ascii=False, default=str)


def wait(test, timeout: float = 15, step: float = 0.3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = test()
        except Exception:
            value = None
        if value:
            return value
        time.sleep(step)
    return None
