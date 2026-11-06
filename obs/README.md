# OBS Studio commands

`obs.py`: plain Python functions for OBS Studio: add scenes and color or text sources, start and stop recording. Python 3.9+, standard library only. Put this
folder on `sys.path` (or copy the file next to your program) and `import obs`.

```python
import obs

obs.scene_add(name="Interview")
obs.source_add(name="Lower third", kind="text", text="Live in 5")
obs.recording_start()          # raises StateBlocked if the scene has no video source
# ... later
obs.recording_stop()           # {"path": "~/Movies/2026-11-06 14-02-11.mov", "bytes": ...}
```

**Verified on macOS 15.6.1 with OBS Studio 32.0.1 only. This doesn't cover macOS 26 or any other version.** On another version,
results gain `"unverified_version": true` and both versions.

## How it works

UI mode only (OBS has no scripting for this). Buttons are found by name through the macOS Accessibility API and pressed; the scene name
is set in OBS's own name dialog. No screen coordinates. It depends on English names. Scenes are read from OBS's scene-collection file,
and the recordings folder from OBS's profile settings.

OBS's own questions are answered like this: on first launch, "Check for updates automatically?" gets **Don't Check**. After OBS quit
unexpectedly, "Run in Safe Mode?" gets **Run in Normal Mode**. With no video source in the scene, "you will only be outputting a blank
screen" gets **No** (the call raises `StateBlocked`) unless you pass `allow_blank=True`.

**Left out:** image and media sources (OBS didn't take a file path typed into its properties through Accessibility), and display,
window, game or camera capture. Those need macOS's Screen Recording or Camera permission, and these
commands never answer permission prompts. Add such sources in OBS yourself, then `recording_start()` records them.

## Functions

### scene_add(name, mode="ui") → {name, scenes}
**Scenes › Add**, the name, **OK**. `AlreadyExists` if the scene exists.

### source_add(name, kind, text=None, mode="ui") → {name, kind, scene}
**Sources › Add**, **Color Source** or **Text (FreeType 2)**, **Create new** with the name, **OK**, then in its properties the text,
**OK**. Added to the current scene, with OBS's default color, font and size. `AlreadyExists` if a source or scene has the name;
`StateBlocked` if a source dialog or properties window is already open. Added on day 3 in its own section of the file and tested on
its own; the code above it is unchanged.

### recording_start(allow_blank=False, mode="ui") → {recording, folder}
**Controls › Start Recording**. `StateBlocked` if OBS is already recording.

### recording_stop(mode="ui") → {path, bytes}
**Controls › Stop Recording**, then the file: the newest video in OBS's recordings folder written in the last 15 seconds, once its
size stops changing. `StateBlocked` if OBS isn't running or isn't recording.

## How it was verified

In fresh copies of one VM, with made-up scene names (including quotes, accents and emoji), with OBS closed, open, behind another
app, and hidden. Scenes and sources were read back from OBS's scene-collection file (a text source's text exactly, with quotes, emoji and a line
break, and each in the current scene, with every other source unchanged). Recordings were read from the files themselves: a new file
in ~/Movies that grows while recording and stops growing after `recording_stop`, which AVFoundation reads as a video longer than
3 seconds, and nothing else in ~/Movies changed. Every case set a small clipboard first and checked it came back, and one ran with a
very large clipboard.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `recording_start` | ui | yes | 10 | app closed, app hidden, app open, another app in front |
| `recording_stop` | ui | yes | 6 | app closed, app hidden, app open, another app in front |
| `scene_add` | ui | yes | 12 | app closed, app hidden, app open, another app in front |
| `source_add` | ui | yes | 15 | app closed, app hidden, app open, another app in front |

Verified on macOS 15.6.1 (24G90), obs 32.0.1, 2026-11-06, in fresh VM clones.

## Permissions

**Accessibility** and **Automation** for System Events. Nothing asked for Screen Recording or Camera in testing. The test VM has no
microphone, so on a Mac with one, OBS's default Mic/Aux source may make macOS ask for Microphone access when OBS starts or records.
These commands don't answer that prompt.
