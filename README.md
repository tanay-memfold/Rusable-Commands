# Reusable Commands

Verified, replayable UI commands for macOS apps. Each command is a short list of steps on named on-screen
controls (buttons, fields, menu items, list rows), with its inputs left as blanks. Any agent that can read the
macOS accessibility tree and press, type and send keys can replay one.

Only verified commands are stored here. Nothing is added from a single run.

## Commands

| App | Command | File |
|---|---|---|
| Notes | make a note titled {title} in Notes | [commands/notes/title.json](commands/notes/title.json) |
| Notes | make a note titled {title} with the text {text} in Notes | [commands/notes/body.json](commands/notes/body.json) |
| Notes | add the text {text} to the note titled {title} in Notes | [commands/notes/add-text.json](commands/notes/add-text.json) |
| Notes | make a folder named {name} in Notes | [commands/notes/folder.json](commands/notes/folder.json) |
| Notes | make a note titled {title} in the Notes folder {folder} | [commands/notes/in-folder.json](commands/notes/in-folder.json) |
| Notes | pin the note titled {title} in Notes | [commands/notes/pin.json](commands/notes/pin.json) |
| Reminders | make a list {name} in Reminders | [commands/reminders/list.json](commands/reminders/list.json) |
| Reminders | add a reminder {title} to the list {list} in Reminders | [commands/reminders/in-list.json](commands/reminders/in-list.json) |

`index.json` lists the same commands for programs.

## What "verified" means

A command is stored only if all of these held, each in a fresh macOS VM:

1. It was learned from a run that did the task and ended done.
2. Its steps were replayed and ended done from two different start states: the app closed, and the app open
   with other items in it.
3. Every run was confirmed by reading the app's own data (for example the Notes database), not only by the
   agent saying it was done.
4. Every run used new, made-up values.

A single failed replay keeps a command out. Steps on raw screen positions, drags and gestures are never stored.

## File format

See [schema.json](schema.json). In short:

- `request`: the request it answers, with `{param}` blanks.
- `params`: the blanks, in the order they appear in `request`.
- `precondition`: what must be true before step 1. Replay opens the app by name and waits for its window; a
  command never stores how the app was reached.
- `steps`: in order. Each is one of:
  - `press` a `control` (`role` + `name`)
  - `type` `text` into a `control`
  - `key`, with `keys` such as `Return`
- `verification`: the start state, run id and data checks of each run, the date, and the engine used.

### Control names

- `{param}` in a name or text is replaced with the value.
- `…` stands for any text. `{title}…` matches a list row whose name starts with the title, `…{title}` one whose
  name ends with it.
- In `text`, `\n` is a line break. In Notes the first line of the note is its title.

## Replaying a command

1. Fill every blank in `steps` with the request's values.
2. Make the precondition true: open the app by name, bring it to the front, wait for a window.
3. For each step, find the control with that role and name on screen, then press, type or send the key.
4. After each step, check it took effect (the typed value shows on screen). If a step's control is missing or
   nothing changes, stop and hand the task back to the agent. Don't guess.

## Scope and versions

Recorded on macOS 26.6.2, Notes 4.13 and Reminders 7.0, in English. Control names can change with app
versions or languages, so check `app.version` and `platform.version` before replaying, and verify again on a
new version.

Learned and verified with Voice Actions 3.9.3 and 3.9.4. The steps don't depend on that engine.
