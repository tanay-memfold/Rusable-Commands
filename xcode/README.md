# Xcode commands

`xcode.py`: plain Python functions for Xcode: make a new project from a template, open a project, and build it. Python 3.9+, standard library
only. Put this folder on `sys.path` (or copy the file next to your program) and `import xcode`.

```python
import xcode

xcode.project_new(name="MySwiftApp", folder="~/Documents/XcodeProjects")            # iOS › App
xcode.project_new(name="Notes Mac", folder="~/Projects", platform="macOS")
xcode.project_open(path="~/Documents/XcodeProjects/MySwiftApp/MySwiftApp.xcodeproj")
xcode.project_build(path="~/Projects/Notes Mac/Notes Mac.xcodeproj")   # {"succeeded": True, "products": [".../Notes Mac.app"]}
```

**Verified on macOS 15.6.1 with Xcode 16.4 only. This doesn't cover macOS 26 or any other version.** On another version, results
gain `"unverified_version": true` and both versions.

## How it works

UI mode only. Menu items are clicked by name; the template chooser's platform tabs and templates are chosen by name, the options page's
fields by Xcode's own ids (Product Name, Organization Identifier), and the save and open dialogs are filled in through Go to Folder
(the path is pasted through the clipboard, which is restored afterwards). No screen coordinates. It depends on English names.

Opening a project through Xcode's own scripting worked but brought Xcode to the front, so it isn't offered as a background mode.

If an Xcode sheet is open, an untouched template chooser is cancelled; one holding a typed product name, or any other sheet, makes the
call raise `StateBlocked` and change nothing.

## Functions

### project_new(name, folder, platform="iOS", template="App", organization="com.example", git=False, mode="ui") → {name, path, folder, platform, template}
**File > New > Project…**, the platform tab, the template, **Next**, Product Name and Organization Identifier, **Next**, the folder,
**Create**. Xcode makes `folder/name/name.xcodeproj` with the template's sources and opens it. Interface, language, testing and storage
keep Xcode's defaults (SwiftUI, Swift). No team is chosen, so the project isn't signed; nothing asks for an account. `platform` is
`"iOS"` or `"macOS"`; only the App template and `git=False` were verified. `AlreadyExists` if `folder/name` is taken; `NotFound` if the
folder or the template doesn't exist.

### project_open(path, mode="ui") → {name, path}
**File > Open…**, going to the `.xcodeproj` or `.xcworkspace` in the dialog.

### project_build(path, mode="ui") → {name, succeeded, products}
**Product > Build** for the project's current scheme and destination, opening the project first if Xcode doesn't show it. It waits
for this build's own result (up to 10 minutes): `succeeded` and the newly built apps in Xcode's DerivedData. A failed build returns
`succeeded: false` and no products (Xcode can leave a partly built app behind). Only macOS App builds were verified. If the scheme
needs platform support Xcode would download (here an iOS app needed iOS 18.5 support), the offer is declined with **Cancel**, nothing
is downloaded, and `NotSupported` is raised. Added on day 3 in its own section of the file and tested on its own; the code above it is
unchanged.

## How it was verified

In fresh copies of one VM, with made-up names (including spaces and accents) inside one test folder, with Xcode closed, open, with
another project open, behind another app, and hidden. New projects were read back from the files Xcode wrote: `project.pbxproj`
(its SDKROOT for the platform and its bundle identifier) and the App template's sources, with no Git repository. Every other file in
the test folder was compared before and after, with one exception: Xcode rewrites the per-user window-state file
(`xcuserdata/<you>.xcuserdatad/UserInterfaceState.xcuserstate`) of every project already open in it when its windows change, so for
projects open before a call that one file wasn't compared. Opening was checked by Xcode's window title and document, which isn't
independent of Xcode. Builds were read from DerivedData (a newly built app with its executable) and from Xcode's own build logs (no failed
command; for a source file made not to compile, the compiler's error). Every case set a small clipboard first and checked it came back, and both commands ran with a very large clipboard.

| Function | Mode | Verified | Cases | Start states |
|---|---|---|---|---|
| `project_build` | ui | yes | 12 | app closed, app hidden, app open, another app in front, project_open |
| `project_new` | ui | yes | 25 | app closed, app hidden, app open, another app in front, project_open |
| `project_open` | ui | yes | 7 | app closed, app hidden, app open, another app in front |

Verified on macOS 15.6.1 (24G90), xcode 16.4 (23792), 2026-11-06, in fresh VM clones.

## Permissions

**Accessibility** and **Automation** for System Events.
