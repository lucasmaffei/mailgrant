"""The few texts the server writes for the person: push notifications.

Everything else is translated in the browser (static/i18n/*.json). A push
is composed here, before any page is open, so it follows the language the
person picked in Ajustes, or the one their browser last resolved to.
"""

from __future__ import annotations

LANGUAGES = ("en", "pt-BR", "es", "fr", "zh-CN")

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "push_works": "Notifications are working.",
        "agent_sent": "{agent} sent an email",
        "agent_sent_body": "From {mailbox} to {to}",
        "new_mail": "New email",
        "no_subject": "(no subject)",
    },
    "pt-BR": {
        "push_works": "As notificações estão funcionando.",
        "agent_sent": "{agent} enviou um e-mail",
        "agent_sent_body": "De {mailbox} para {to}",
        "new_mail": "Novo e-mail",
        "no_subject": "(sem assunto)",
    },
    "es": {
        "push_works": "Las notificaciones funcionan.",
        "agent_sent": "{agent} envió un correo",
        "agent_sent_body": "De {mailbox} a {to}",
        "new_mail": "Correo nuevo",
        "no_subject": "(sin asunto)",
    },
    "fr": {
        "push_works": "Les notifications fonctionnent.",
        "agent_sent": "{agent} a envoyé un e-mail",
        "agent_sent_body": "De {mailbox} à {to}",
        "new_mail": "Nouvel e-mail",
        "no_subject": "(sans objet)",
    },
    "zh-CN": {
        "push_works": "通知已正常工作。",
        "agent_sent": "{agent} 发送了一封邮件",
        "agent_sent_body": "从 {mailbox} 发给 {to}",
        "new_mail": "新邮件",
        "no_subject": "（无主题）",
    },
}


def language(store) -> str:  # type: ignore[no-untyped-def]
    """The explicit choice, else what the browser resolved to, else English."""
    for key in ("lang", "ui_lang"):
        lang = store.get_pref(key, "")
        if lang in LANGUAGES:
            return str(lang)
    return "en"


def text(lang: str, key: str, **values: str) -> str:
    template = MESSAGES.get(lang, MESSAGES["en"]).get(key) or MESSAGES["en"][key]
    return template.format(**values)
