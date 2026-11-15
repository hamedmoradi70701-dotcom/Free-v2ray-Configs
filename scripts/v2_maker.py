# -*- coding: utf-8 -*-
"""
v2_maker.py — اشتراک‌سازِ شخصیِ V2Ray رادار: برای هر کلید، یک اشتراکِ جدا
که خودِ ربات هر دور از استخرِ تست‌شده‌اش می‌چیند و تازه‌اش می‌کند.

چطور کار می‌کند
───────────────
۱) ربات برای هر «کلید» (توکنی مثل `RDR-AB12CD-EF3456`) یک فایلِ اشتراکِ
   شخصی در `subs/v2keys/<KEY>.txt` نگه می‌دارد؛ رجیستریِ کلیدها در
   `stats/v2_registry.json` بینِ دورها می‌ماند (الگوی `survival.json`).
۲) محتوای هر اشتراک از خروجیِ **همان دورِ** ربات چیده می‌شود: ۲۰ تای اولِ
   طلایی‌ها (سریع‌ترین‌های تستِ تونلِ واقعیِ ربات)، همهٔ کانفیگ‌های ایرانِ
   همان دور، و یک برشِ چرخانِ مخصوصِ همان کلید از استخرِ تأییدشده‌ها — پس
   هر کلید ترکیبِ خودش را دارد و هر دور با کانفیگ‌های تازه می‌چرخد.
۳) دو ردیفِ اول به سبکِ اشتراک‌های شیک نام‌گذاری می‌شوند (ردیفِ اشتراک +
   «هر موقع قطع شد بروزرسانی کن») و پارامترهای `allowInsecure` از همهٔ
   خط‌ها پاک می‌شوند (v2rayNG جدید با آن‌ها ارور می‌دهد).

⚠️ رک: این‌ها کانفیگِ ساخته‌شده از صفر نیستند — سرورِ شخصی وجود ندارد که
ربات رویش کانفیگِ نو ثبت کند؛ «ساختن» این‌جا یعنی چیدن و تازه‌کردنِ یک
اشتراکِ شخصیِ کلیددار از کانفیگ‌هایی که ربات همان دور واقعاً تستِ تونل
کرده است. تست‌ها از سرورِ ربات (آمریکا) است، نه از نتِ کاربر.

سقف: ۳۰ کلید؛ دورِ اول ۱۰ کلید و هر دور ۲ کلیدِ تازه.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import secrets
import sys
import time
from typing import Any, Dict, List

_MAX_KEYS = 30
_BOOTSTRAP_KEYS = 10
_NEW_KEYS_PER_RUN = 2
_GOLDEN_HEAD = 20
_PER_KEY_VERIFIED = 60


def _read_lines(path: str) -> List[str]:
    try:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            return [ln.strip() for ln in fh
                    if ln.strip() and not ln.startswith("#")]
    except OSError:
        return []


def _scrub(line: str) -> str:
    line = re.sub(r"([?&])(allowInsecure|insecure)=[^&#]*", r"\1", line,
                  flags=re.I)
    return (line.replace("?&", "?").replace("&&", "&")
            .replace("&#", "#").replace("?#", "#"))


def _core(line: str) -> str:
    return line.split("#", 1)[0]


def _set_remark(line: str, text: str) -> str:
    from urllib.parse import quote
    return _core(line) + "#" + quote(text)


def _new_key() -> str:
    return "RDR-" + secrets.token_hex(3).upper() + "-" + \
        secrets.token_hex(3).upper()


def run(out_dir: str) -> Dict[str, Any]:
    """نقطهٔ ورود — از `pipeline._main` فقط در اجرای واقعیِ ورک‌فلو."""
    stats_dir = os.path.join(out_dir, "stats")
    keys_dir = os.path.join(out_dir, "subs", "v2keys")
    os.makedirs(stats_dir, exist_ok=True)
    os.makedirs(keys_dir, exist_ok=True)
    reg_path = os.path.join(stats_dir, "v2_registry.json")

    registry: List[Dict[str, Any]] = []
    if os.path.exists(reg_path):
        try:
            registry = json.load(io.open(reg_path, encoding="utf-8")) \
                .get("keys", [])
        except Exception:
            registry = []

    want = _BOOTSTRAP_KEYS if not registry else _NEW_KEYS_PER_RUN
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for _ in range(max(0, min(want, _MAX_KEYS - len(registry)))):
        registry.append({"key": _new_key(), "created": now_iso})

    golden = _read_lines(os.path.join(out_dir, "subs", "golden.txt"))
    iran = _read_lines(os.path.join(out_dir, "Countries", "Iran.txt"))
    verified = _read_lines(os.path.join(out_dir, "verified",
                                        "configs.txt"))
    run_tag = time.strftime("%Y%m%d", time.gmtime())

    counts: Dict[str, int] = {}
    for entry in registry:
        key = entry["key"]
        rng = random.Random(
            hashlib.sha256((key + run_tag).encode()).hexdigest())
        seen = set()
        lines: List[str] = []

        def take(src: List[str], limit: int = 0) -> None:
            n = 0
            for raw in src:
                c = _core(raw)
                if c in seen:
                    continue
                seen.add(c)
                lines.append(_scrub(raw))
                n += 1
                if limit and n >= limit:
                    break

        take(golden, _GOLDEN_HEAD)
        take(iran)
        pool = [l for l in verified if _core(l) not in seen]
        if pool:
            take(rng.sample(pool, min(_PER_KEY_VERIFIED, len(pool))))
        if lines:
            lines[0] = _set_remark(
                lines[0], f"👤 اشتراک شخصی رادار 📡 (✅ فعال)({key})")
        if len(lines) > 1:
            lines[1] = _set_remark(lines[1], "🔄 هر موقع قطع شد بروزرسانی کن")
        head = [f"#profile-title: 📡 رادار | اشتراک شخصی {key}",
                "#profile-update-interval: 1"]
        with io.open(os.path.join(keys_dir, key + ".txt"), "w",
                     encoding="utf-8") as fh:
            fh.write("\n".join(head + lines) + "\n")
        counts[key] = len(lines)

    active = {e["key"] + ".txt" for e in registry}
    for name in os.listdir(keys_dir):
        if name not in active:
            try:
                os.unlink(os.path.join(keys_dir, name))
            except OSError:
                pass

    report = {"generated_at": now_iso, "keys_active": len(registry),
              "pool": {"golden": len(golden), "iran": len(iran),
                       "verified": len(verified)},
              "per_key_counts": counts}
    with io.open(os.path.join(stats_dir, "v2_report.json"), "w",
                 encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    with io.open(reg_path, "w", encoding="utf-8") as fh:
        json.dump({"keys": registry}, fh, ensure_ascii=False, indent=1)
    print(f"[v2] keys={len(registry)} pool_verified={len(verified)} "
          f"golden={len(golden)} iran={len(iran)}", file=sys.stderr)
    return report


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else ".")
