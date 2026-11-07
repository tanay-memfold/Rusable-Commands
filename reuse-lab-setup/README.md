# Reuse lab setup

How the commands in this repo were verified, so the lab can be set up again on another machine. A laptop drives a
throwaway macOS VM on a Mac mini over SSH; every batch of tests runs in a fresh copy of a golden VM, and results
are read back from files and app databases, not through the app being tested.

Nothing private is in this folder: no keys, passwords, hostnames or addresses. Those go in `lab.env` files you
make from the `.example` files; they are git-ignored.

## Layout

| Path | What it is |
|---|---|
| `libs/kit/` | Shared test kit: Accessibility helpers (`ax.py`), large-clipboard check (`bigclip.py`), case runner (`vkit.py`), `fresh.sh` (fresh VM with the tools installed), `scaffold.py` (start a new app library), `explore_app.py` (dump an app's menus and windows) |
| `libs/reminders_local/` | The VM driver and runners used by every app: `mvm.sh`, `run_app.sh`, `runner.py`, `fresh.sh`, `watch.sh`, `wait_run.sh`, `batch.sh` |
| `libs/<app>_local/` | Each app's verifier (`verify_*.py`), its database readers, and `build_catalog.py` |
| `libs/verify/` | The first verifiers (Notes, Calendar, Finder) from the macOS 26.6.2 runs |
| `libs/report.py`, `libs/publish.py`, `libs/check_catalog.py`, `libs/root_readme.py` | Aggregate results, publish a verified library into this repo, check every catalog, rebuild the root README |
| `mini-relay/` | The relay that lets SSH start and stop the VM (see below) |

## The Mac mini

1. **UTM 4.7 or later**, and SSH login from the laptop with a key.
2. **`~/rusable-lab/`**, holding:
   - `golden.utm`: the golden VM. It is never booted; copies are made from it.
   - `RusableTest.utm`: the test VM, re-made from golden before each batch with `cp -c` (an APFS clone, instant and
     nearly free).
   - `relay/`: the two scripts from `mini-relay/`, plus `relay/lab.env` with the VM's UUID.
   - `ssh/`: a key used only for the test VM (`id_rusable`) and its own `known_hosts`. Never commit these.
3. **Screen access** for permission prompts: in System Settings › General › Sharing › Remote Management, allow the
   account **Observe** and **Control** only. Then `vnc://<mini>` from the laptop shows the Mini's screen, with UTM's
   VM window on it.

### Why the relay

`utmctl` is refused over SSH (`OSStatus -1743`). The relay runs in a Terminal window on the Mini's desktop, where
`utmctl` works, and reads requests from a file queue. It does only status, start and stop, for one VM UUID, and
exits after 30 idle minutes. `mvm.sh up` opens it with `open -a Terminal`, and `rusable-utmctl` (run over SSH) sends one
request and waits.

## The golden VM

- macOS 15.6.1, user `admin`, with the apps to be tested installed.
- Remote Login on, and the public half of `id_rusable` in `admin`'s `authorized_keys`.
- Accessibility allowed for the SSH session, so the tests can drive apps.
- macOS permission prompts are never answered by the tests. When one is needed, a person clicks Allow over Screen
  Sharing, and that VM is saved as a new base (for example `golden-shortcuts.utm`, with the Shortcuts Events grant).

## The laptop

1. Copy `libs/` somewhere, and `libs/lab.env.example` to `libs/lab.env`. Fill in the Mini's SSH target, the VM's
   address and its UUID.
2. Copy each app's library from this repo next to its tests: `libs/<app>/<module>.py`. For example, the Preview
   library goes in `libs/preview/preview.py`.
3. Check the lab: `libs/reminders_local/mvm.sh check`. It prints the number of running VMs, other benchmark runs, free
   disk, and whether the test copy and golden are there.

## Running a batch

```bash
cd libs/reminders_local
./run_app.sh preview preview.py preview-test verify_preview.py ../kit/fresh.sh 'prv-1:1234:closed,open,other_app,hidden'
```

Each `group:seed:states` spec gets its own fresh VM. Before each one, `run_app.sh` shuts our VM down and stops for good
if any other VM or benchmark run is going, because the Mini is shared. Results land in `libs/results/<group>/`.

Then:

```bash
python3 report.py preview prv-1 prv-2
python3 publish.py preview preview preview.py <path to this repo>
python3 check_catalog.py <path to this repo>
```

A command is published only when every case of it passed on its final code, and `publish.py` writes its `VERIFIED`
record (macOS and app version) into the library.

## Rules the lab keeps

- Throwaway copies only. Golden bases are never booted, and nothing outside `~/rusable-lab` on the Mini is touched.
- Made-up data only, and only items the tests created are changed or deleted.
- Two fix attempts per failing command, each a different approach; after that the command is left out and the README
  says why.
- No passwords, sign-ins, purchases or macOS permission prompts answered by the tests.
