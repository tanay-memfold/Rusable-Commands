"""Writes gmail/catalog.json. Local only."""
import json
MODE = {"name": "mode", "type": "str", "required": False, "default": "ui", "meaning": "Must be \"ui\": Gmail has no background mode."}
MATCH = {"name": "match", "type": "str", "required": True, "default": None, "meaning": "The message's exact subject."}
SENDER = {"name": "sender", "type": "str | None", "required": False, "default": None, "meaning": "The sender's name as shown in the row, when the same subject exists more than once."}
FIELDS = {"name": "fields", "type": "str | list | None", "required": False, "default": None, "meaning": "Row fields to return, as a comma-separated string or a list; adds labels if asked."}
LIMIT = {"name": "limit", "type": "int", "required": False, "default": 20, "meaning": "The most rows to return; one page holds at most 50."}
TO = {"name": "to", "type": "str | list", "required": True, "default": None, "meaning": "One address or a list of addresses."}
SUBJECT = {"name": "subject", "type": "str", "required": True, "default": None, "meaning": "One non-empty line."}
def BODY(verb): return {"name": "body", "type": "str", "required": False, "default": "", "meaning": f"The message text; an empty or whitespace-only body is refused before anything else runs, so always give one when you {verb}."}
ROW = ["sender", "subject", "date", "snippet", "unread", "starred"]
COMMON = [{"name": "ValueError", "when": "an argument is invalid"},
          {"name": "StateBlocked", "when": "a compose or reply window holds typed text, or another app came to the front; nothing is changed"},
          {"name": "SignedOut", "when": "Gmail isn't signed in; the call doesn't try to sign in"},
          {"name": "UnsupportedLanguage", "when": "Gmail's elements weren't found by their English names"},
          {"name": "NotSupported", "when": "mode isn't \"ui\", or the command wasn't verified"},
          {"name": "UIError", "when": "a named element never appeared within the timeout"}]
NOTFOUND = {"name": "NotFound", "when": "no message has that exact subject, from that sender if given; nothing is changed"}
AMBIG = {"name": "Ambiguous", "when": "more than one message matches; nothing is changed"}
GUARD = {"name": "RecipientNotAllowed", "when": "GMAIL_ALLOWED_RECIPIENTS isn't set, or a recipient isn't on it or can't be confirmed; nothing is sent"}
def CONF(what): return {"name": "NotConfirmed", "when": what}
BROWSER = "Safari is signed in to Gmail in a session you set up, with its display language set to English; the program has Accessibility and Automation for System Events."
SAMEBROWSER = "Read-back in testing used the same browser and page, so it isn't independent of Gmail itself."
EMPTY = "A message with an empty body can't be found by exact subject, so it raises NotFound and changes nothing."
NOGET = "message_get is left out because it wasn't shown reliable, so use message_search or message_list to read rows, which opens nothing."
ARCHIVE_GAP = "Archiving the same message twice wasn't verified, because that repeat case never completed."
REPLY_STATES = "Replying was tested only with Safari closed, another app in front, a message open and a popup open, not from the other eight start states."
RESENT = "On NotConfirmed the message may have gone out, so check Sent before retrying and don't resend automatically."
def cmd(name, description, args, requests, effects, precondition, postcondition, returns, errors, gaps=None, confirm=None):
    c = {"name": name, "description": description, "args": args, "modes": {"verified": ["ui"], "default": "ui"}, "example_requests": requests,
         "effects": effects, "destructive": confirm is not None, "precondition": precondition, "postcondition": postcondition, "returns": returns, "errors": errors}
    if confirm: c["confirm"] = confirm
    if gaps: c["known_gaps"] = gaps
    return c
rowreturn = {"type": "list", "fields": ROW, "optional_fields": ["labels"]}
actret = lambda extra: {"type": "object", "fields": ROW + extra}
commands = [
 cmd("message_search", "Runs any Gmail search and returns the matching rows without opening a message.", [{"name": "query", "type": "str", "required": True, "default": None, "meaning": "Any Gmail search text."}, LIMIT, FIELDS, MODE],
     ["Find emails from billing", "Search my mail for the invoice", "Do I have mail about the Goa trip?"], "read_only", BROWSER, "Nothing is changed and no message is opened.", rowreturn, COMMON, [NOGET, EMPTY, SAMEBROWSER, "Only one page is read, so at most 50 rows come back."]),
 cmd("message_list", "Lists the rows under a label without opening a message.", [{"name": "label", "type": "str", "required": False, "default": "Inbox", "meaning": "The label to list."}, LIMIT, FIELDS, MODE],
     ["What's in my inbox?", "List my recent mail", "Show the mail under my Travel label"], "read_only", BROWSER, "Nothing is changed and no message is opened.", rowreturn, COMMON, [NOGET, SAMEBROWSER, "Only one page is read, so at most 50 rows come back."]),
 cmd("message_send", "Sends a new message to addresses on the allowed list, then reads it back from Sent.", [TO, SUBJECT, BODY("send"), MODE],
     ["Email the team about Friday", "Send Sam a note saying I'm running late", "Send this summary to my own address"], "non_idempotent", BROWSER + " GMAIL_ALLOWED_RECIPIENTS lists every recipient.", "The message was read back from Sent; it can't be taken back.", {"type": "object", "fields": ["to", "subject", "sent"]},
     COMMON + [GUARD, CONF("Send was pressed but the message wasn't read back from Sent; it may have gone out")], [RESENT, "Empty-body sends are refused with ValueError.", "Attachments, CC and BCC aren't supported.", SAMEBROWSER], "Send this message to <to> with the subject <subject>?"),
 cmd("draft_create", "Saves a new draft and reads it back from Drafts, without ever sending it.", [TO, SUBJECT, BODY("save a draft"), MODE],
     ["Draft an email to Sam", "Save a draft about the budget", "Write a draft but don't send it"], "non_idempotent", BROWSER, "A draft exists in Drafts; nothing was sent.", {"type": "object", "fields": ["to", "subject", "draft"]},
     COMMON + [CONF("Save & close was pressed but the draft wasn't read back from Drafts")], ["Empty-body drafts are refused with ValueError.", "Attachments, CC and BCC aren't supported.", SAMEBROWSER]),
 cmd("message_reply", "Replies to a conversation's newest message and reads the reply's own text back, which marks the conversation read.", [MATCH, {"name": "body", "type": "str", "required": True, "default": None, "meaning": "The reply text; it must not be empty."}, SENDER, MODE],
     ["Reply to the invoice email saying thanks", "Answer the Friday plans message", "Reply that I'll be there"], "non_idempotent", BROWSER + " GMAIL_ALLOWED_RECIPIENTS lists the reply's recipients.", "The reply's text was read back in the conversation, which is now marked read; it can't be taken back.", {"type": "object", "fields": ["subject", "to", "sent"]},
     COMMON + [NOTFOUND, AMBIG, GUARD, CONF("Send was pressed but the reply's own text wasn't read back; it may have gone out")], [RESENT, REPLY_STATES, "A reply form shows names, so a reply-to address that differs behind the same display name can't be seen.", EMPTY, SAMEBROWSER], "Reply to <match> with this text?"),
 cmd("message_archive", "Removes a message from the Inbox without opening it.", [MATCH, SENDER, MODE],
     ["Archive the invoice email", "Get the receipt out of my inbox", "Archive that message"], "idempotent", BROWSER, "The message is out of the Inbox and still exists.", actret(["archived"]), COMMON + [NOTFOUND, AMBIG], [ARCHIVE_GAP, EMPTY, SAMEBROWSER]),
 cmd("message_trash", "Moves a message to the Bin without opening it.", [MATCH, SENDER, MODE],
     ["Bin the invoice email", "Delete that message", "Move the receipt to the trash"], "non_idempotent", BROWSER, "The message is in the Bin, and nothing is permanently deleted.", actret(["trashed"]), COMMON + [NOTFOUND, AMBIG], [EMPTY, SAMEBROWSER], "Move <match> to the Bin?"),
 cmd("message_star", "Stars a message without opening it, and a starred message stays starred.", [MATCH, SENDER, MODE],
     ["Star the invoice email", "Mark that message as important with a star", "Star the Friday plans email"], "idempotent", BROWSER, "The message is starred.", actret([]), COMMON + [NOTFOUND, AMBIG], [EMPTY, SAMEBROWSER, "There is no command to remove a star."]),
 cmd("message_mark_read", "Marks a message read without opening it.", [MATCH, SENDER, MODE],
     ["Mark the invoice email as read", "Mark that message read", "Clear the unread dot on the receipt"], "idempotent", BROWSER, "The message is marked read.", actret([]), COMMON + [NOTFOUND, AMBIG], [EMPTY, SAMEBROWSER, "There is no command to mark a message unread."]),
]
catalog = {"app": "Gmail", "import": "import gmail", "macos_version": "26.6.2 (25G83)", "app_version": "26.6.2 (21624.5.1.11.3)", "commands": commands}
json.dump(catalog, open("../gmail/catalog.json", "w"), indent=2, ensure_ascii=False); open("../gmail/catalog.json", "a").write("\n")
print(len(commands))
