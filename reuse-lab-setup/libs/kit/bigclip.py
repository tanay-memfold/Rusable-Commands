"""A very large clipboard for the verifiers, set and read back without the library under test: more than 1 MB as an
argument would be refused, so a restore passed as an argument fails. Text is read back with pbpaste."""
import base64, hashlib, json, random, subprocess
KIND = "com.rusable.test.big"
SET = r"""ObjC.import("AppKit");
function run() {
  const a = JSON.parse(ObjC.unwrap($.NSString.alloc.initWithDataEncoding($.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile, $.NSUTF8StringEncoding)));
  const pb = $.NSPasteboard.generalPasteboard, item = $.NSPasteboardItem.alloc.init;
  pb.clearContents;
  item.setStringForType($(a.text), "public.utf8-plain-text");
  item.setDataForType($.NSData.alloc.initWithBase64EncodedStringOptions(a.data, 0), a.kind);
  pb.writeObjects($([item]));
  return "ok";
}"""
GET = r"""ObjC.import("AppKit");
function run(argv) {
  const pb = $.NSPasteboard.generalPasteboard, items = ObjC.unwrap(pb.pasteboardItems) || [];
  const d = pb.dataForType(argv[0]);
  return items.length + " " + (d.isNil() ? "" : ObjC.unwrap(d.base64EncodedStringWithOptions(0)));
}"""
def _sha(b): return hashlib.sha256(b).hexdigest()
def fill(seed: int) -> dict:
    rng = random.Random(seed)
    text = "".join(rng.choice("abcdefghij klmnop\n") for _ in range(2_500_000))
    data = rng.getrandbits(8_000_000).to_bytes(1_000_000, "big")
    done = subprocess.run(["osascript", "-l", "JavaScript", "-e", SET], input=json.dumps({"text": text, "data": base64.b64encode(data).decode(), "kind": KIND}), capture_output=True, text=True)
    if done.returncode: raise RuntimeError(done.stderr.strip())
    want = {"text": _sha(text.encode()), "data": _sha(data)}
    got = check(want)
    if not all(got.values()): raise RuntimeError(f"the large clipboard wasn't set: {got}")
    return want
def check(want: dict) -> dict:
    text = subprocess.run(["pbpaste"], capture_output=True).stdout
    got = subprocess.run(["osascript", "-l", "JavaScript", "-e", GET, KIND], capture_output=True, text=True).stdout.strip().split(" ", 1)
    return {"clipboard_text_restored": _sha(text) == want["text"], "clipboard_data_restored": len(got) == 2 and _sha(base64.b64decode(got[1])) == want["data"], "clipboard_one_item": got[0] == "1"}
