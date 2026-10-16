"""Real agent activity for the screenshots: python agent.py <lang> [base URL]."""
import json
import sys

import httpx

from content import CONTENT

lang = sys.argv[1] if len(sys.argv) > 1 else "en"
B = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:18200"
C = CONTENT[lang]
H = {"Accept": "application/json, text/event-stream", "Authorization": "Bearer hermes-e2e"}


def tool(name, **a):
    r = httpx.post(B + "/mcp", headers=H, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": a}})
    line = [x for x in r.text.splitlines() if x.startswith("data: ")][0]
    return json.loads(json.loads(line[6:])["result"]["content"][0]["text"])


bakery = sorted(C["mail"]["contact"], key=lambda x: (-x[2], x[3], x[4]))[1]
tool("get_message", mailbox="contact", uid="1")
tool("get_message", mailbox="contact", uid="2")
tool("send", mailbox="contact", to=[bakery[0].split("<")[1].rstrip(">")], subject=bakery[1],
     body_text=C["agent_reply"], in_reply_to=f"<demo1.{C['boxes']['contact']}>")
tool("delete_message", mailbox="billing", uid="1")  # hermes has no delete: shows up as denied
tool("get_message", mailbox="contact", uid="3")
print("agent activity created", lang)
