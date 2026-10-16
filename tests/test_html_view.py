"""HTML mail in the app: sanitized, sandboxed, remote images held back."""

from __future__ import annotations

import email
from email.message import EmailMessage

from mailgrant.imap_client import _html_to_reader, html_body
from mailgrant.web import html_view

RECEIPT = """<!doctype html><html><head><style>body,html{height:100%!important}
.amount{font-size:28px}</style><title>Recibo</title></head>
<body style="background:#f4f4f4" bgcolor="#f4f4f4"><table width="600" align="center">
<tr><td><img src="https://cdn.example.com/logo.png" width="120" alt="Loja"></td></tr>
<tr><td class="amount" style="color:#00a650">R$ 9,90</td></tr>
<tr><td><img src="cid:qr@loja"></td></tr></table></body></html>"""


def test_layout_survives_and_nothing_runs() -> None:
    out = html_view.sanitize(
        RECEIPT
        + '<img src=x onerror="alert(1)"><a href="javascript:alert(1)">a</a>'
        + '<a href="data:text/html,<b>x</b>">d</a><iframe src="https://e.x"></iframe>'
        + '<form action="https://e.x"><input name="senha"></form><script>alert(1)</script>'
        + '<svg onload="alert(1)"></svg><link rel="stylesheet" href="https://e.x/a.css">'
        + '<object data="https://e.x/x.swf"></object><base href="https://e.x/">'
    )
    for gone in ("onerror", "javascript:", "data:text", "<iframe", "<form", "<input", "<script",
                 "alert(1)</", "onload", "<link", "<object", "<base", "<title"):  # fmt: skip
        assert gone not in out, gone
    assert '<table width="600" align="center">' in out
    assert 'class="amount" style="color:#00a650"' in out
    assert ".amount{font-size:28px}" in out  # the mail's own <style> stays
    assert 'target="_blank"' in out and 'rel="noopener noreferrer"' in out
    # The page colour set on <body> moves to a wrapper the parser keeps.
    assert out.startswith('<div style="background:#f4f4f4" bgcolor="#f4f4f4">')


def test_inline_images_come_from_the_message() -> None:
    msg = EmailMessage()
    msg.set_content("texto")
    msg.add_alternative(RECEIPT, subtype="html")
    msg.get_payload()[1].add_related(b"\x89PNG", maintype="image", subtype="png", cid="<qr@loja>")
    parsed = email.message_from_bytes(msg.as_bytes())
    inline = html_view.inline_parts(parsed)
    assert inline == {"qr@loja": "data:image/png;base64,iVBORw=="}
    assert 'src="data:image/png;base64,iVBORw=="' in html_view.sanitize(
        html_body(parsed) or "", inline
    )


def test_remote_images_are_detected_and_held_back() -> None:
    assert html_view.has_remote(RECEIPT)
    assert html_view.has_remote('<td style="background-image:url( https://e.x/a.png)">')
    assert html_view.has_remote('<td background="//e.x/a.png">')
    assert not html_view.has_remote('<img src="cid:x"><a href="https://e.x">link</a>')
    assert "img-src data:;" in html_view.policy(images=False)
    assert "img-src data: https: http:;" in html_view.policy(images=True)
    for p in (html_view.policy(True), html_view.policy(False)):
        assert "script-src" not in p and "default-src 'none'" in p
        assert "allow-scripts" not in p and "frame-ancestors 'self'" in p


def test_document_lets_the_frame_shrink() -> None:
    doc = html_view.document(RECEIPT)
    # The mail pins html/body to 100% height; our rule comes after it.
    assert doc.index("height:100%!important") < doc.index("height:auto!important")


def test_reader_text_drops_table_markup() -> None:
    text = _html_to_reader(RECEIPT)
    assert "|" not in text and "---" not in text
    assert "R$ 9,90" in text


def test_held_back_images_keep_their_place_quietly() -> None:
    assert "visibility:hidden" in html_view.document(RECEIPT, images=False)
    assert "visibility:hidden" not in html_view.document(RECEIPT, images=True)
    # The src is not rewritten: the frame's CSP is what blocks the request.
    assert "https://cdn.example.com/logo.png" in html_view.document(RECEIPT, images=False)
