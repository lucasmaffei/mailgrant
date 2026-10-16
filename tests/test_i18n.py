"""The web app's languages: every text the code asks for exists everywhere."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from mailgrant.web import i18n

STATIC = Path(__file__).resolve().parents[1] / "src" / "mailgrant" / "web" / "static"
SOURCE = (STATIC / "app.js").read_text()
LOCALES = ["pt-BR", "es", "fr", "zh-CN"]
# Intl.PluralRules categories each language needs; "many" is optional where
# CLDR uses it only for very large numbers.
CATEGORIES = {
    "pt-BR": ({"one", "other"}, {"many"}),
    "es": ({"one", "other"}, {"many"}),
    "fr": ({"one", "other"}, {"many"}),
    "zh-CN": ({"other"}, set()),
}

_STR = r'"((?:[^"\\]|\\.)*)"'


def _js(text: str) -> str:
    return json.loads('"' + text.replace("\\'", "'") + '"')


SINGLES = {_js(m) for m in re.findall(r"(?<![\w.])t\(\s*" + _STR, SOURCE)}
PLURALS = {
    _js(a): _js(b)
    for a, b in re.findall(r"(?<![\w.])tn\([^\"]*?,\s*" + _STR + r"\s*,\s*" + _STR, SOURCE)
}


def placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


def load(lang: str) -> dict:
    return json.loads((STATIC / "i18n" / f"{lang}.json").read_text())


def test_the_scan_finds_the_texts() -> None:
    # Guards the regexes: a refactor that hides calls from them would pass vacuously.
    assert len(SINGLES) > 200 and len(PLURALS) >= 5
    assert "Inbox" in SINGLES and "{n} message" in PLURALS
    assert not SINGLES & set(PLURALS), "a text is used both as plural and as single"


@pytest.mark.parametrize("lang", LOCALES)
def test_locale_has_every_text_and_nothing_stale(lang: str) -> None:
    table = load(lang)
    assert sorted((SINGLES | set(PLURALS)) - set(table)) == [], "missing"
    assert sorted(set(table) - SINGLES - set(PLURALS)) == [], "stale"


@pytest.mark.parametrize("lang", LOCALES)
def test_translations_keep_the_placeholders(lang: str) -> None:
    table = load(lang)
    for key in SINGLES:
        value = table[key]
        assert isinstance(value, str) and value.strip(), key
        assert placeholders(value) == placeholders(key), (lang, key, value)
    need, optional = CATEGORIES[lang]
    for one, many in PLURALS.items():
        forms = table[one]
        assert isinstance(forms, dict), (lang, one)
        assert need <= set(forms) <= need | optional, (lang, one, sorted(forms))
        allowed = placeholders(one) | placeholders(many)
        for form in forms.values():
            # A singular may drop the number ("Arquivada."), never invent one.
            assert placeholders(form) <= allowed, (lang, one, form)


def test_app_knows_the_same_languages_as_the_server() -> None:
    listed = re.search(r"const LANGS = \{([^}]*)\}", SOURCE)
    assert listed
    codes = re.findall(r'"?([\w-]+)"?\s*:', listed.group(1))
    assert tuple(codes) == i18n.LANGUAGES
    assert sorted(p.stem for p in (STATIC / "i18n").glob("*.json")) == sorted(LOCALES)


def test_service_worker_caches_every_locale() -> None:
    sw = (STATIC / "sw.js").read_text()
    for lang in LOCALES:
        assert f'"/app/static/i18n/{lang}.json"' in sw


def test_server_catalogue_is_complete() -> None:
    keys = set(i18n.MESSAGES["en"])
    for lang in i18n.LANGUAGES:
        table = i18n.MESSAGES[lang]
        assert set(table) == keys, lang
        for key in keys:
            assert placeholders(table[key]) == placeholders(i18n.MESSAGES["en"][key]), (lang, key)


def test_server_picks_the_chosen_then_the_resolved_language() -> None:
    def store(**prefs: str) -> SimpleNamespace:
        return SimpleNamespace(get_pref=lambda key, default=None: prefs.get(key, default))

    assert i18n.language(store()) == "en"
    assert i18n.language(store(ui_lang="fr")) == "fr"
    assert i18n.language(store(lang="zh-CN", ui_lang="fr")) == "zh-CN"
    assert i18n.language(store(lang="xx", ui_lang="es")) == "es"
    assert i18n.text("pt-BR", "agent_sent", agent="hermes") == "hermes enviou um e-mail"
    assert i18n.text("xx", "new_mail") == "New email"
