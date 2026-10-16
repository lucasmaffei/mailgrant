"""HTML e-mail bodies, made safe to show in the app.

Most mail people actually get (receipts, banks, newsletters) is laid out in
HTML tables, and flattened to text it turns into rows of `| | |`. So the app
shows the real HTML, in an iframe that gets three locks of its own:

- the markup is sanitized here (no script, no forms, no event handlers, no
  frames, no remote stylesheet);
- the document carries a CSP with no script source at all, and a CSP sandbox
  without `allow-scripts`, so even markup that slipped through cannot run;
- the iframe itself is sandboxed in the page the same way.

Remote images are blocked by that CSP unless the person asks for them: a
remote image tells the sender when, and from where, the mail was opened.
Inline images (`cid:`) come from the message itself and always show.
"""

from __future__ import annotations

import base64
import re
from email.message import Message

import nh3

# What layout e-mail uses, minus anything that acts: no form, input, button,
# iframe, object, embed, link, meta, base or script.
_TAGS = set(nh3.ALLOWED_TAGS) | {"font", "style", "tfoot", "center", "big", "section", "main"}

_LAYOUT = {
    "align", "valign", "width", "height", "bgcolor", "background", "border",
    "cellpadding", "cellspacing", "color", "face", "size", "dir", "lang",
    "style", "class", "id", "title", "role", "nowrap",
}  # fmt: skip

_ATTRS: dict[str, set[str]] = {"*": _LAYOUT}
for _tag, _allowed in nh3.ALLOWED_ATTRIBUTES.items():
    _ATTRS[_tag] = set(_allowed) | _LAYOUT
_ATTRS.setdefault("td", set()).update({"colspan", "rowspan", "headers"})
_ATTRS["img"] = {"src", "alt", "width", "height", "align", "border", "hspace", "vspace"} | _LAYOUT
_ATTRS["a"] = {"href", "name"} | _LAYOUT

_SCHEMES = {"http", "https", "mailto", "tel", "data"}

# Remote things the CSP will hold back: <img src>, background= and CSS url().
_REMOTE = re.compile(
    r"""(?:\bsrc|\bbackground)\s*=\s*["']?\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//""",
    re.IGNORECASE,
)
_CID = re.compile(r"""\bcid:([^"'\s)>]+)""", re.IGNORECASE)
_BODY = re.compile(r"<body\b([^>]*)>", re.IGNORECASE)
_BODY_ATTR = re.compile(r"""\b(style|bgcolor)\s*=\s*("[^"]*"|'[^']*')""", re.IGNORECASE)

INLINE_LIMIT = 10 * 1024 * 1024  # inline images embedded per message, in bytes

# Emails often pin html/body to the window height ("height: 100% !important"),
# which would keep the frame from shrinking to its content. These come last
# so they win over the message's own rules of the same weight.
_BASE = (
    "html{color-scheme:light;background:#fff}"
    "body{margin:0;padding:16px;color:#111;"
    "font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    "overflow-wrap:break-word}"
    "img{max-width:100%;height:auto}"
    "pre{white-space:pre-wrap}"
)
_LAST = "html,body{height:auto!important;min-height:0!important;overflow:visible!important}"


def has_remote(html: str | None) -> bool:
    return bool(html and _REMOTE.search(html))


def _keep_data_images(tag: str, attr: str, value: str) -> str | None:
    """`data:` only as an image, never as a link someone could click."""
    if value.lstrip().lower().startswith("data:"):
        if tag == "img" and attr == "src" and value.lstrip().lower().startswith("data:image/"):
            return value
        return None
    return value


def inline_parts(msg: Message) -> dict[str, str]:
    """Content-ID → data: URI for the images a message carries for itself."""
    out: dict[str, str] = {}
    total = 0
    for part in msg.walk():
        cid = (part.get("Content-ID") or "").strip().strip("<>")
        if not cid or not part.get_content_type().startswith("image/"):
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        total += len(payload)
        if total > INLINE_LIMIT:
            break
        data = base64.b64encode(payload).decode("ascii")
        out[cid] = f"data:{part.get_content_type()};base64,{data}"
    return out


def sanitize(html: str, inline: dict[str, str] | None = None) -> str:
    """The message's HTML as a fragment that cannot run anything."""
    inline = inline or {}
    if inline:
        html = _CID.sub(lambda m: inline.get(m.group(1), m.group(0)), html)
    # The parser drops <body>, and with it the page colour many mails set there.
    wrapper = ""
    if body := _BODY.search(html):
        wrapper = " ".join(f"{k.lower()}={v}" for k, v in _BODY_ATTR.findall(body.group(1)))
    return nh3.clean(
        f"<div {wrapper}>{html}</div>" if wrapper else html,
        tags=_TAGS,
        clean_content_tags={"script", "title"},
        attributes=_ATTRS,
        attribute_filter=_keep_data_images,
        url_schemes=_SCHEMES,
        set_tag_attribute_values={"a": {"target": "_blank"}},
        link_rel="noopener noreferrer",
        strip_comments=True,
    )


def document(html: str, inline: dict[str, str] | None = None, images: bool = True) -> str:
    # A held-back image keeps its place but not the broken-image icon. Its src
    # stays as it is; the CSP is what keeps it from loading.
    held = "" if images else 'img[src^="http"],img[src^="//"]{visibility:hidden}'
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="referrer" content="no-referrer">'
        f"<style>{_BASE}{held}</style></head><body>{sanitize(html, inline)}"
        f"<style>{_LAST}</style></body></html>"
    )


def policy(images: bool) -> str:
    """The frame's own CSP. No script source on purpose: nothing may run."""
    img = "data: https: http:" if images else "data:"
    return (
        f"default-src 'none'; style-src 'unsafe-inline'; img-src {img}; font-src data:; "
        "frame-ancestors 'self'; form-action 'none'; base-uri 'none'; "
        "sandbox allow-same-origin allow-popups allow-popups-to-escape-sandbox"
    )
