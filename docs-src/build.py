#!/usr/bin/env python3
"""Build the GitHub Pages landing page from `docs-src/`.

    python3 docs-src/build.py            # writes docs/index.html and docs/<lang>/index.html
    python3 docs-src/build.py --check    # exit 1 if the committed pages are stale

Inputs
    docs-src/template.html   one template for all languages
    docs-src/i18n/en.json    English strings (the reference key set)
    docs-src/i18n/fa.json    Persian strings (must carry exactly the same keys)
    docs-src/i18n/zh.json    Chinese strings (same keys)
    docs-src/i18n/ru.json    Russian strings (same keys)
    docs-src/i18n/ar.json    Arabic strings (same keys; RTL like Persian)
    docs/styles.css, docs/app.js, docs/vendor/*.js
                             hand-written runtime; their content hash becomes the
                             `?v=` cache-buster so a deploy never serves stale CSS/JS

Template syntax
    {{a.b}}      string from the language file, HTML-escaped
    {{{a.b}}}    string from the language file, inserted raw (keys end in `_html`)
    {{@x}}       build variable, HTML-escaped
    {{{@x}}}     build variable, inserted raw (pre-escaped JSON / generated HTML)

Only the Python standard library is used, so the page can be rebuilt anywhere.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DOCS = os.path.join(REPO, "docs")

SITE = "https://hamedmoradi70701-dotcom.github.io/Free-v2ray-Configs/"
REPO_URL = "https://github.com/hamedmoradi70701-dotcom/Free-v2ray-Configs"
RAW = "https://raw.githubusercontent.com/hamedmoradi70701-dotcom/Free-v2ray-Configs/main"
QR_VENDOR = "vendor/qrcode-generator-1.4.4.js"

LANGS = {
    "en": {
        "out": "index.html",
        "dir": "ltr",
        "base": "",
        "canonical": SITE,
        "og_locale": "en_US",
        "font_preload": "fonts/manrope-latin.woff2",
        "sister_href": "https://hamedmoradi70701-dotcom.github.io/Free-Telegram-Proxy/",
    },
    "fa": {
        "out": "fa/index.html",
        "dir": "rtl",
        "base": "../",
        "canonical": SITE + "fa/",
        "og_locale": "fa_IR",
        "font_preload": "fonts/estedad-arabic.woff2",
        "sister_href": "https://hamedmoradi70701-dotcom.github.io/Free-Telegram-Proxy/fa/",
    },
    "zh": {
        "out": "zh/index.html",
        "dir": "ltr",
        "base": "../",
        "canonical": SITE + "zh/",
        "og_locale": "zh_CN",
        "font_preload": "fonts/manrope-latin.woff2",
        "sister_href": "https://hamedmoradi70701-dotcom.github.io/Free-Telegram-Proxy/",
    },
    "ru": {
        "out": "ru/index.html",
        "dir": "ltr",
        "base": "../",
        "canonical": SITE + "ru/",
        "og_locale": "ru_RU",
        "font_preload": "fonts/manrope-latin.woff2",
        "sister_href": "https://hamedmoradi70701-dotcom.github.io/Free-Telegram-Proxy/",
    },
    "ar": {
        "out": "ar/index.html",
        "dir": "rtl",
        "base": "../",
        "canonical": SITE + "ar/",
        "og_locale": "ar_SA",
        "font_preload": "fonts/estedad-arabic.woff2",
        "sister_href": "https://hamedmoradi70701-dotcom.github.io/Free-Telegram-Proxy/",
    },
}

# Switcher order and endonym labels: فارسی · English · 中文 · Русский · العربية
LANG_ORDER = ["fa", "en", "zh", "ru", "ar"]
LANG_LABELS = {
    "fa": "فارسی",
    "en": "English",
    "zh": "中文",
    "ru": "Русский",
    "ar": "العربية",
}

_TOKEN = re.compile(r"\{\{\{(@?[\w.]+)\}\}\}|\{\{(@?[\w.]+)\}\}")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _short_hash(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:10]


def _flatten(obj, prefix: str = "") -> dict:
    out = {}
    for key, val in obj.items():
        name = f"{prefix}{key}"
        if isinstance(val, dict):
            out.update(_flatten(val, name + "."))
        else:
            out[name] = val
    return out


def _script_json(obj) -> str:
    """JSON that is safe inside <script>: no `</script>`, no `<!--`, no U+2028/9."""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (text.replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def _faq_html(items) -> str:
    rows = []
    for i, (q, a) in enumerate(items):
        rows.append(
            f'      <details class="faq-item" id="faq-{i + 1}">'
            f"<summary><span>{html.escape(q)}</span>"
            '<span class="faq-plus" aria-hidden="true"></span></summary>'
            f"<p>{html.escape(a)}</p></details>")
    return "\n".join(rows)


def _rel_href(cur: str, target: str) -> str:
    """Relative link from one language page to another (en lives at the root,
    every other language in its own folder, mirroring the old en/fa pairing)."""
    if cur == target:
        return "./"
    if target == "en":
        return "../"
    return f"{target}/" if cur == "en" else f"../{target}/"


def _lang_menu_html(cur: str) -> str:
    """Header language switcher: a <details> dropdown listing all languages,
    the current one marked active. Labels are endonyms, so the menu reads the
    same on every page."""
    items = []
    for code in LANG_ORDER:
        active = ' class="active" aria-current="true"' if code == cur else ""
        items.append(
            f'<a href="{_rel_href(cur, code)}" hreflang="{code}" '
            f'lang="{code}"{active}>{LANG_LABELS[code]}</a>')
    return (
        '<details class="lang-menu"><summary class="lang-control">'
        '<span aria-hidden="true" class="lang-glyph">文</span>'
        f'{html.escape(LANG_LABELS[cur])}'
        '<span aria-hidden="true" class="lang-caret">▾</span></summary>'
        f'<nav class="lang-list">{"".join(items)}</nav></details>')


def _lang_links_html(cur: str) -> str:
    """Flat links to every *other* language (mobile menu + footer)."""
    return "".join(
        f'<a href="{_rel_href(cur, code)}" hreflang="{code}" '
        f'lang="{code}">{LANG_LABELS[code]}</a>'
        for code in LANG_ORDER if code != cur)


def _hreflang_html() -> str:
    lines = [
        f'<link rel="alternate" hreflang="{code}" '
        f'href="{LANGS[code]["canonical"]}">'
        for code in LANG_ORDER
    ]
    lines.append(
        f'<link rel="alternate" hreflang="x-default" '
        f'href="{LANGS["en"]["canonical"]}">')
    return "\n".join(lines)


def _og_alts_html(cur: str) -> str:
    return "\n".join(
        f'<meta property="og:locale:alternate" '
        f'content="{LANGS[code]["og_locale"]}">'
        for code in LANG_ORDER if code != cur)


def _jsonld(strings: dict, lang: str, canonical: str) -> dict:
    faq = strings["faq"]["items"]
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": SITE + "#website",
                "url": SITE,
                "name": "رادار Free V2Ray Configs",
                "inLanguage": ["en", "fa", "zh", "ru", "ar"],
            },
            {
                "@type": "WebPage",
                "@id": canonical + "#webpage",
                "url": canonical,
                "name": strings["meta"]["title"],
                "description": strings["meta"]["desc"],
                "inLanguage": lang,
                "isPartOf": {"@id": SITE + "#website"},
            },
            {
                "@type": "SoftwareSourceCode",
                "name": "Free-v2ray-Configs",
                "codeRepository": REPO_URL,
                "programmingLanguage": "Python",
                "license": "https://spdx.org/licenses/MIT.html",
                "creator": {"@type": "Person", "name": "0xRadikal",
                            "url": "https://github.com/0xRadikal"},
            },
            {
                "@type": "Dataset",
                "name": "Free V2Ray Configs (verified subscription)",
                "description": strings["meta"]["desc"],
                "url": canonical,
                "sameAs": REPO_URL,
                "isAccessibleForFree": True,
                "license": "https://spdx.org/licenses/MIT.html",
                "creator": {"@type": "Person", "name": "0xRadikal"},
                "distribution": [
                    {"@type": "DataDownload", "encodingFormat": "text/plain",
                     "contentUrl": f"{RAW}/verified/configs_base64.txt"},
                    {"@type": "DataDownload", "encodingFormat": "text/plain",
                     "contentUrl": f"{RAW}/verified/configs.txt"},
                    {"@type": "DataDownload", "encodingFormat": "application/yaml",
                     "contentUrl": f"{RAW}/verified/clash.yaml"},
                    {"@type": "DataDownload", "encodingFormat": "application/json",
                     "contentUrl": f"{RAW}/verified/singbox.json"},
                    {"@type": "DataDownload", "encodingFormat": "application/json",
                     "contentUrl": f"{RAW}/index.json"},
                ],
            },
            {
                "@type": "FAQPage",
                "inLanguage": lang,
                "mainEntity": [
                    {"@type": "Question", "name": q,
                     "acceptedAnswer": {"@type": "Answer", "text": a}}
                    for q, a in faq
                ],
            },
        ],
    }


def render(lang: str, template: str, strings: dict, hashes: dict) -> str:
    cfg = LANGS[lang]
    flat = _flatten(strings)
    build = {
        "lang": lang,
        "dir": cfg["dir"],
        "base": cfg["base"],
        "canonical": cfg["canonical"],
        "hreflang_html": _hreflang_html(),
        "og_locale": cfg["og_locale"],
        "og_alts_html": _og_alts_html(lang),
        "lang_menu_html": _lang_menu_html(lang),
        "lang_links_html": _lang_links_html(lang),
        "font_preload": cfg["font_preload"],
        "sister_href": cfg["sister_href"],
        "css_v": hashes["css"],
        "js_v": hashes["js"],
        "qr_v": hashes["qr"],
        "faq_html": _faq_html(strings["faq"]["items"]),
        "jsonld": _script_json(_jsonld(strings, lang, cfg["canonical"])),
        "i18n_json": _script_json({"lang": lang, "dir": cfg["dir"], **strings["js"]}),
    }
    missing = []

    def sub(m: re.Match) -> str:
        raw_key, esc_key = m.group(1), m.group(2)
        key = raw_key or esc_key
        if key.startswith("@"):
            val = build.get(key[1:])
        else:
            val = flat.get(key)
        if not isinstance(val, str):
            missing.append(key)
            return ""
        if raw_key is not None:
            if not key.startswith("@") and not key.endswith("_html"):
                raise SystemExit(f"build: raw insertion of non-_html key {key!r}")
            return val
        return html.escape(val, quote=True)

    out = _TOKEN.sub(sub, template)
    if missing:
        raise SystemExit(f"build[{lang}]: unresolved template keys: {sorted(set(missing))}")
    if "{{" in out or "}}" in out.replace("}}]}", ""):
        leftover = re.findall(r"\{\{.{0,40}", out)
        if leftover:
            raise SystemExit(f"build[{lang}]: leftover template syntax: {leftover[:3]}")
    return out


def _check_parity(strings_by_lang: dict) -> None:
    en = strings_by_lang["en"]
    ref_keys = set(_flatten(en))
    ref_js = _flatten(en["js"])
    for lang, s in strings_by_lang.items():
        keys = set(_flatten(s))
        if keys != ref_keys:
            raise SystemExit(f"build: en/{lang} key mismatch: "
                             f"only-en={sorted(ref_keys - keys)} "
                             f"only-{lang}={sorted(keys - ref_keys)}")
        if len(s["faq"]["items"]) != len(en["faq"]["items"]):
            raise SystemExit(f"build: en/{lang} FAQ item count differs")
        for key, val in _flatten(s["js"]).items():
            if set(re.findall(r"\{\w+\}", val)) != set(re.findall(r"\{\w+\}", ref_js[key])):
                raise SystemExit(f"build[{lang}]: placeholder mismatch in js.{key}")


def main(argv) -> int:
    check = "--check" in argv
    template = _read(os.path.join(HERE, "template.html"))
    strings = {lang: json.loads(_read(os.path.join(HERE, "i18n", f"{lang}.json")))
               for lang in LANGS}
    _check_parity(strings)
    hashes = {
        "css": _short_hash(os.path.join(DOCS, "styles.css")),
        "js": _short_hash(os.path.join(DOCS, "app.js")),
        "qr": _short_hash(os.path.join(DOCS, QR_VENDOR)),
    }
    stale = []
    for lang, cfg in LANGS.items():
        page = render(lang, template, strings[lang], hashes)
        path = os.path.join(DOCS, cfg["out"])
        if check:
            current = _read(path) if os.path.exists(path) else None
            if current != page:
                stale.append(cfg["out"])
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(page)
        print(f"build: docs/{cfg['out']}  {len(page.encode('utf-8')):,} B")
    if stale:
        print(f"build --check: stale, rebuild with `python3 docs-src/build.py`: {stale}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
