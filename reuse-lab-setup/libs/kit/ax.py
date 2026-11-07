"""Direct macOS Accessibility calls with ctypes: find elements by role and name, press, focus, read. No coordinates."""
import ctypes, ctypes.util, subprocess, time
AS = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
CF = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
P = ctypes.c_void_p
for f, res, args in [(AS.AXUIElementCreateApplication, P, [ctypes.c_int]),
                     (AS.AXUIElementCopyAttributeValue, ctypes.c_int, [P, P, ctypes.POINTER(P)]),
                     (AS.AXUIElementSetAttributeValue, ctypes.c_int, [P, P, P]),
                     (AS.AXUIElementPerformAction, ctypes.c_int, [P, P]),
                     (CF.CFStringCreateWithCString, P, [P, ctypes.c_char_p, ctypes.c_uint32]),
                     (CF.CFStringGetLength, ctypes.c_long, [P]), (CF.CFStringGetMaximumSizeForEncoding, ctypes.c_long, [ctypes.c_long, ctypes.c_uint32]),
                     (CF.CFStringGetCString, ctypes.c_bool, [P, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]),
                     (CF.CFGetTypeID, ctypes.c_ulong, [P]), (CF.CFStringGetTypeID, ctypes.c_ulong, []), (CF.CFArrayGetTypeID, ctypes.c_ulong, []),
                     (CF.CFArrayGetCount, ctypes.c_long, [P]), (CF.CFArrayGetValueAtIndex, P, [P, ctypes.c_long]),
                     (CF.CFRelease, None, [P])]:
    f.restype, f.argtypes = res, args
UTF8 = 0x08000100
TRUE = P.in_dll(CF, "kCFBooleanTrue")
_cache = {}
def cf(s):
    if s not in _cache:
        _cache[s] = CF.CFStringCreateWithCString(None, s.encode(), UTF8)
    return _cache[s]
def text(v):
    if not v or CF.CFGetTypeID(v) != CF.CFStringGetTypeID():
        return None
    size = CF.CFStringGetMaximumSizeForEncoding(CF.CFStringGetLength(v), UTF8) + 1
    buf = ctypes.create_string_buffer(size)
    return buf.value.decode() if CF.CFStringGetCString(v, buf, size, UTF8) else None
def attr(e, name):
    out = P()
    return out.value if AS.AXUIElementCopyAttributeValue(e, cf(name), ctypes.byref(out)) == 0 else None
def sattr(e, name):
    return text(attr(e, name))
def children(e):
    v = attr(e, "AXChildren")
    if not v or CF.CFGetTypeID(v) != CF.CFArrayGetTypeID():
        return []
    return [CF.CFArrayGetValueAtIndex(v, i) for i in range(CF.CFArrayGetCount(v))]
def app(name):
    pid = int(subprocess.run(["pgrep", "-x", name], capture_output=True, text=True).stdout.split()[0])
    return AS.AXUIElementCreateApplication(pid)
def walk(root):
    stack = [root]
    while stack:
        e = stack.pop()
        yield e
        stack.extend(reversed(children(e)))
def names(e):
    return [sattr(e, a) or "" for a in ("AXDescription", "AXTitle")]
def find(root, role, wanted, exact=False):
    for e in walk(root):
        if sattr(e, "AXRole") == role and any((n == wanted if exact else wanted in n) for n in names(e)):
            return e
    return None
def press(e): return AS.AXUIElementPerformAction(e, cf("AXPress"))
def focus(e): return AS.AXUIElementSetAttributeValue(e, cf("AXFocused"), TRUE)
