#!/usr/bin/env python3
"""ارسالِ خودکارِ بهترین کانفیگ‌های تأییدشده به کانالِ تلگرامِ رادار.

بعد از انتشارِ موفقِ هر دور اجرا می‌شود (گامِ «📣 Post to Telegram channel»
در `.github/workflows/aggregate.yml`). توکنِ ربات فقط از متغیرِ محیطیِ
`TELEGRAM_BOT_TOKEN` خوانده می‌شود (در CI از Secretsِ مخزن می‌آید) و هرگز
در هیچ فایل یا لاگی چاپ نمی‌شود.

قراردادِ این گام: **هرگز نباید اجرا را بشکند.** اگر توکن تنظیم نشده باشد،
فایل‌های داده نباشند، یا تلگرام خطا بدهد، پیامِ واضحی چاپ می‌شود و اسکریپت
با کدِ ۰ تمام می‌شود.
"""

import html
import json
import os
import sys
import urllib.error
import urllib.request

CHAT_ID = "@radarconfing"
SITE_URL = "https://hamedmoradi70701-dotcom.github.io/Free-v2ray-Configs/fa/"
SUBSCRIPTION_URL = (
    "https://raw.githubusercontent.com/"
    "hamedmoradi70701-dotcom/Free-v2ray-Configs/main/top100.txt"
)

MAX_MESSAGE_CHARS = 4096          # سقفِ پیامِ تلگرام
MAX_CONFIGS = 10                  # حداکثر کانفیگ در هر پست
MIN_CONFIGS = 3                   # اگر پیام جا نشد، تا این تعداد کم می‌شود
HTTP_TIMEOUT_SECONDS = 30

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_stats():
    """آمارِ دور از `index.json` — اگر فایل یا فیلدی نبود، همان بخش حذف می‌شود."""
    stats = {}
    try:
        with open(os.path.join(ROOT, "index.json"), encoding="utf-8") as fh:
            index = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"notify_telegram: index.json unreadable ({exc}); "
              "posting without stats.")
        return stats

    cascade = index.get("cascade_categories") or {}
    verified = _int_or_none((cascade.get("verified") or {}).get("unique"))
    if verified is not None:
        stats["verified"] = verified
    fast = _int_or_none((cascade.get("fast") or {}).get("unique"))
    if fast is not None:
        stats["fast"] = fast

    countries = index.get("countries")
    country_count = None
    if isinstance(countries, dict):
        country_count = _int_or_none(countries.get("count"))
        if country_count is None and isinstance(countries.get("configs"), int):
            country_count = None  # «configs» شمارِ کانفیگ است، نه کشور
    elif isinstance(countries, list):
        country_count = len(countries)
    if country_count is not None:
        stats["countries"] = country_count

    updated_at = index.get("updated_at")
    if isinstance(updated_at, str) and updated_at:
        stats["updated_at"] = updated_at
    return stats


def read_top_configs(limit=MAX_CONFIGS):
    """اولین کانفیگ‌های `top100.txt` — سطرهای `#` (سرآیندِ اشتراک) رد می‌شوند."""
    configs = []
    try:
        with open(os.path.join(ROOT, "top100.txt"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                configs.append(line)
                if len(configs) >= limit:
                    break
    except OSError as exc:
        print(f"notify_telegram: top100.txt unreadable ({exc}); "
              "posting without configs.")
    return configs


def compose_message(stats, configs):
    """یک پیامِ HTML برای تلگرام؛ متنِ داینامیک escape می‌شود."""
    esc = html.escape
    parts = ["📡 <b>رادار — کانفیگ‌های تازه رسید</b>"]

    stat_bits = []
    if "verified" in stats:
        stat_bits.append(f"✅ تأییدشده: <b>{stats['verified']}</b>")
    if "fast" in stats:
        stat_bits.append(f"⚡ سریع: <b>{stats['fast']}</b>")
    if "countries" in stats:
        stat_bits.append(f"🌍 {stats['countries']} کشور")
    if stat_bits:
        parts.append(" · ".join(stat_bits))
    if "updated_at" in stats:
        parts.append(f"🕒 به‌روزرسانی: {esc(stats['updated_at'])}")

    if configs:
        parts.append("")
        parts.append(f"🏆 <b>{len(configs)} کانفیگِ برترِ این دور</b> "
                     "(برای کپی، روی هرکدام بزنید):")
        parts.extend(f"<code>{esc(cfg)}</code>" for cfg in configs)

    parts.append("")
    parts.append(f"🌐 سایت رادار: {esc(SITE_URL)}")
    parts.append(f"🔗 اشتراکِ ۱۰۰ کانفیگِ برتر: {esc(SUBSCRIPTION_URL)}")
    parts.append(f"📣 کانال: {esc(CHAT_ID)}")
    return "\n".join(parts)


def fit_message(stats, configs):
    """پیام را زیرِ سقفِ ۴۰۹۶ کاراکتر نگه می‌دارد: کانفیگ از ته کم می‌شود."""
    chosen = list(configs)
    message = compose_message(stats, chosen)
    while len(message) > MAX_MESSAGE_CHARS and len(chosen) > MIN_CONFIGS:
        chosen.pop()
        message = compose_message(stats, chosen)
    return message


def send_message(token, text):
    """POST به Bot API. روی هر خطا پیامِ واضح چاپ و False برمی‌گردد."""
    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request,
                                    timeout=HTTP_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        print(f"notify_telegram: Telegram returned HTTP {exc.code}: {detail}")
        return False
    except (urllib.error.URLError, OSError) as exc:
        print(f"notify_telegram: network error talking to Telegram: {exc}")
        return False
    if not body.get("ok"):
        print(f"notify_telegram: Telegram API not ok: "
              f"{json.dumps(body, ensure_ascii=False)[:300]}")
        return False
    message_id = (body.get("result") or {}).get("message_id")
    print(f"notify_telegram: posted to {CHAT_ID} (message_id={message_id}).")
    return True


def main():
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        print("notify_telegram: TELEGRAM_BOT_TOKEN is not set — "
              "skipping Telegram post.")
        return 0

    stats = read_stats()
    configs = read_top_configs()
    message = fit_message(stats, configs)
    send_message(token, message)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # این گام هرگز نباید ورک‌فلو را بشکند
        print(f"notify_telegram: unexpected error (ignored): {exc!r}")
        sys.exit(0)
