#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
افزوده‌های رادار — تاریخچهٔ اجراها و خلاصهٔ هشدار (لایهٔ فرعیِ آبشار).

دو خروجیِ تازه، هر دو زیرِ `stats/`:

  • `stats/history.json`   — هر دور یک رکورد به تهِ آن افزوده می‌شود:
    {ts, verified_count, country_count, sources_ok, sources_total}.
    سقفِ نگه‌داری ۲۰۰۰ رکوردِ آخر است تا فایل بی‌نهایت باد نکند.
    مصرف‌کننده‌اش بخشِ «ماشین زمان» در سایت است (نمودارِ رشد).
  • `stats/last_run.json`  — خلاصهٔ **همین دور** برای گامِ اطلاع‌رسانی:
    شمارِ تأییدشده، شمارِ دورِ قبل، درصدِ افت، و فهرستِ منابعی که این
    دور مُرده‌اند (خطا داده‌اند یا صفر کانفیگ برگردانده‌اند).
    `notify_telegram.py` فقط همین فایل را می‌خواند؛ اگر نبود، هیچ
    بخشِ هشداری به پیامِ کانال افزوده نمی‌شود.

قراردادِ این ماژول همان قراردادِ بقیهٔ افزوده‌های آبشار است: **هرگز
نباید انتشار را بشکند.** همهٔ خواندن‌ها خطاپذیر و بی‌صدا-با-هشدارند و
فراخوان (`pipeline.run_pipeline`) هم آن را در `try` صدا می‌زند؛ نوشتن‌ها
اتمیک‌اند (tmp + replace) تا فایلِ نیم‌نوشته هرگز منتشر نشود.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

#: سقفِ سابِ طلایی: ۵۰ سریع‌ترین کانفیگِ تأییدشدهٔ هر دور.
GOLDEN_N = 50

#: مسیرهای خروجی، نسبت به ریشهٔ خروجی (`out_dir`).
STATS_DIR = "stats"
HISTORY_NAME = "history.json"
LAST_RUN_NAME = "last_run.json"

#: سقفِ رکوردهای تاریخچه؛ با ~۱۵ دقیقه فاصلهٔ اجراها، ۲۰۰۰ رکورد
#: یعنی حدود ۲۰ روزِ پیوسته — برای نمودارِ رشدِ سایت کافی است و فایل
#: را زیرِ چندصد کیلوبایت نگه می‌دارد.
MAX_HISTORY = 2000

#: وضعیت‌هایی که در `health.json` «مرده» به شمار نمی‌آیند:
#: `ok` یعنی منبع این دور کانفیگ داده؛ `disabled` یعنی ماشینِ وضعیتِ
#: خودِ مخزن آن را پس از چند دورِ صفرِ پیاپی کنار گذاشته — وضعیتِ
#: ایستاده است، نه رخدادِ تازه، و هشدارِ هر-دوری برایش اسپم می‌شود.
_NON_DEAD_STATUSES = frozenset({"ok", "disabled"})


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _atomic_write_json(path: str, doc: Any) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)  # اتمیک: فایلِ نیم‌نوشته بدتر از هیچ است


def read_history(out_dir: str) -> List[Dict[str, Any]]:
    """تاریخچهٔ موجود؛ هر خرابی → فهرستِ خالی (هشدار روی stderr)."""
    path = os.path.join(out_dir, STATS_DIR, HISTORY_NAME)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ {path} خوانده نشد ({exc}); تاریخچه از نو شروع می‌شود",
              file=sys.stderr)
        return []
    if not isinstance(doc, list):
        print(f"⚠️ {path} یک فهرست نیست; تاریخچه از نو شروع می‌شود",
              file=sys.stderr)
        return []
    return [row for row in doc if isinstance(row, dict)]


def append_history(out_dir: str, entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """یک رکورد به تهِ تاریخچه می‌افزاید و ۲۰۰۰تای آخر را نگه می‌دارد."""
    history = read_history(out_dir)
    history.append(entry)
    history = history[-MAX_HISTORY:]
    _atomic_write_json(os.path.join(out_dir, STATS_DIR, HISTORY_NAME), history)
    return history


def _read_health(out_dir: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(out_dir, "health.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ {path} خوانده نشد ({exc}); آمارِ منابع در دسترس نیست",
              file=sys.stderr)
        return None
    return doc if isinstance(doc, dict) else None


def sources_summary(health: Optional[Dict[str, Any]]) -> Tuple[int, int]:
    """(سالم، کل) از `health.json`؛ نبودِ داده → (۰، ۰)."""
    if not health:
        return 0, 0
    summary = health.get("summary")
    if isinstance(summary, dict):
        try:
            return int(summary.get("ok") or 0), int(summary.get("total") or 0)
        except (TypeError, ValueError):
            pass
    sources = health.get("sources")
    if isinstance(sources, list):
        ok = sum(1 for s in sources
                 if isinstance(s, dict) and s.get("status") == "ok")
        return ok, len(sources)
    return 0, 0


def dead_sources(health: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """منابعی که این دور مُرده‌اند: خطا/خالی، یا `ok` با شمارِ صفر.

    `disabled`ها عمداً بیرون‌اند (وضعیتِ ایستاده، نه رخداد — همان تعریفِ
    `_NON_DEAD_STATUSES`). هر منبع یک بار، بر پایهٔ URL، گزارش می‌شود.
    """
    if not health:
        return []
    sources = health.get("sources")
    if not isinstance(sources, list):
        return []
    dead: List[Dict[str, Any]] = []
    seen = set()
    for src in sources:
        if not isinstance(src, dict):
            continue
        status = str(src.get("status") or "")
        count = src.get("count")
        try:
            count = int(count) if count is not None else None
        except (TypeError, ValueError):
            count = None
        is_dead = status not in _NON_DEAD_STATUSES or (
            status == "ok" and count == 0)
        if not is_dead:
            continue
        url = str(src.get("url") or "")
        if url in seen:
            continue
        seen.add(url)
        dead.append({
            "name": str(src.get("name") or url or "?"),
            "url": url,
            "status": status,
            "count": count,
        })
    return dead


def record_run(out_dir: str, verified_count: int,
               country_count: int) -> Dict[str, Any]:
    """پایانِ هر دور صدا زده می‌شود: تاریخچه + `stats/last_run.json`.

    ترتیبِ خواندن مهم است: شمارِ دورِ قبل باید **پیش از** افزودنِ رکوردِ
    این دور از تهِ تاریخچه خوانده شود، وگرنه افت همیشه با خودش سنجیده
    می‌شود و هیچ‌وقت دیده نمی‌شود.
    """
    ts = _utc_now_iso()
    health = _read_health(out_dir)
    sources_ok, sources_total = sources_summary(health)
    dead = dead_sources(health)

    history_before = read_history(out_dir)
    prev_verified: Optional[int] = None
    if history_before:
        prev_val = history_before[-1].get("verified_count")
        if isinstance(prev_val, int):
            prev_verified = prev_val

    entry = {
        "ts": ts,
        "verified_count": int(verified_count),
        "country_count": int(country_count),
        "sources_ok": sources_ok,
        "sources_total": sources_total,
    }
    append_history(out_dir, entry)

    drop_pct: Optional[float] = None
    if prev_verified:
        drop_pct = round(
            100.0 * (prev_verified - int(verified_count)) / prev_verified, 1)

    last_run = {
        "ts": ts,
        "verified_count": int(verified_count),
        "prev_verified_count": prev_verified,
        "drop_pct": drop_pct,
        "dead_sources": dead,
        "sources_ok": sources_ok,
        "sources_total": sources_total,
    }
    _atomic_write_json(os.path.join(out_dir, STATS_DIR, LAST_RUN_NAME),
                       last_run)
    return last_run
