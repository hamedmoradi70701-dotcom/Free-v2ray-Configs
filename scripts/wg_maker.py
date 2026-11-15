# -*- coding: utf-8 -*-
"""
wg_maker.py — وایرگاردسازِ رادار: اشتراکِ شخصیِ وایرگارد با کلید، ساخته و
تست‌شده توسطِ خودِ ربات.

چطور کار می‌کند
───────────────
۱) حساب‌های واقعیِ WARP+ از ورکرهای ثبتِ کلودفلر گرفته می‌شود (همان‌هایی که
   پنلِ X4G استفاده می‌کند) — هر حساب کلیدِ لایسنس و مهلتِ واقعیِ خودش را دارد.
۲) برای هر حساب، کانفیگِ AmneziaWG با «فرمولِ برنده» ساخته می‌شود
   (Jc=۳، Jmin=۱، Jmax=۳، هدرهای استانداردِ H1..H4 = ۱..۴، MTU=۱۲۸۰).
۳) تونلِ هر کانفیگ روی خودِ رانر **واقعاً** بالا آورده می‌شود (wg-quick) و
   زمانِ پاسخ و کشورِ خروجی‌اش اندازه گرفته می‌شود — عددِ پینگ اندازه‌گیریِ
   واقعی است، نه نمایشی. ⚠️ این پینگ از سرورِ ربات (آمریکا) گرفته می‌شود؛
   روی نتِ هر کاربر فرق می‌کند، ولی زنده‌بودنِ کانفیگ را ثابت می‌کند.
۴) برای هر کلید (همان لایسنسِ حساب) یک فایلِ اشتراکِ شخصی در
   `subs/keys/<license>.conf` نوشته می‌شود که هر دور با سریع‌ترین اندپوینتِ
   زندهٔ همان حساب بازنویسی می‌شود — کلید ثابت می‌ماند، کانفیگ تازه می‌شود.
۵) بهترین‌های دور در `subs/wg_best.zip` (آمادهٔ ایمپورتِ یکجای AmneziaWG) و
   گزارشِ کاملِ تست‌ها در `stats/wg_report.json` منتشر می‌شود.

رجیستریِ حساب‌ها در `stats/wg_registry.json` بینِ دورها نگه داشته می‌شود
(همان الگوی `stats/survival.json`). این حساب‌ها رایگان و عمومی‌اند و خودِ
فایل‌های اشتراک هم همان کلیدِ خصوصی را در بر دارند — رجیستری چیزِ اضافه‌ای
لو نمی‌دهد.

سقف‌ها: حداکثرِ ۳۰ کلیدِ فعال؛ دورِ اول ۱۰ کلید ساخته می‌شود و هر دور ۲ تای
تازه اضافه می‌شود. بودجهٔ تستِ تونل در هر دور محدود است تا زمانِ اجرا منفجر
نشود. کلیدی که ۳ دورِ پیاپی تستش رد شود یا مهلتش بگذرد، بازنشسته می‌شود.
"""
from __future__ import annotations

import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional

_WORKERS = [
    "https://warp.configwireguard.workers.dev/",
    "https://warp.configwireguard2.workers.dev/",
    "https://warp.configwireguard3.workers.dev/",
    "https://warp.configwireguard4.workers.dev/",
]
_IP_LIST_URL = ("https://raw.githubusercontent.com/DarknessShade/"
                "Amnezia-VPN-Config/main/IP.txt")
_FALLBACK_EPS = ["8.6.112.13:4177", "162.159.192.1:2408",
                 "188.114.96.0:2408", "162.159.193.5:2408"]
_MAX_KEYS = 30
_BOOTSTRAP_KEYS = 10
_NEW_KEYS_PER_RUN = 2
_MAX_FAILS = 3
_TRACE_URL = "https://1.1.1.1/cdn-cgi/trace"
_IFACE = "wgr0"
_KERNEL_BROKEN = False
_WGGO = ""  # مسیرِ باینریِ wireguard-go (موتورِ نرم‌افزاری)


def _http_get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "RadarWG/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _field(conf: str, name: str) -> str:
    m = re.search(name + r"\s*=\s*(.+)", conf)
    return m.group(1).strip() if m else ""


def _mint_account() -> Optional[Dict[str, Any]]:
    """یک حسابِ واقعیِ WARP+ از ورکرهای ثبت می‌گیرد؛ None اگر همه خواب بودند."""
    workers = list(_WORKERS)
    random.shuffle(workers)
    for w in workers:
        try:
            data = json.loads(_http_get(w))
        except Exception:
            continue
        conf = data.get("config") or ""
        ai = data.get("account_info") or {}
        if not data.get("success") or "PrivateKey" not in conf:
            continue
        return {
            "license": ai.get("license", ""),
            "account_type": ai.get("account_type", "WARP+ free"),
            "created": ai.get("created", ""),
            "expires": ai.get("expires", ""),
            "private_key": _field(conf, "PrivateKey"),
            "address": _field(conf, "Address"),
            "dns": _field(conf, "DNS") or "1.1.1.1, 1.0.0.1",
            "peer_key": _field(conf, "PublicKey"),
            "best_ep": "",
            "best_ms": None,
            "fails": 0,
        }
    return None


def _clean_endpoints() -> List[str]:
    try:
        lines = [x.strip() for x in _http_get(_IP_LIST_URL).splitlines()]
        eps = [x for x in lines
               if re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", x)]
        if eps:
            return eps
    except Exception:
        pass
    return list(_FALLBACK_EPS)


def _build_conf(acct: Dict[str, Any], endpoint: str) -> str:
    return (
        "[Interface]\n"
        f"PrivateKey = {acct['private_key']}\n"
        f"Address = {acct['address']}\n"
        f"DNS = {acct['dns']}\n"
        "MTU = 1280\n"
        "Jc = 3\nJmin = 1\nJmax = 3\n"
        "H1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n"
        "\n[Peer]\n"
        f"PublicKey = {acct['peer_key']}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        f"Endpoint = {endpoint}\n"
        "PersistentKeepalive = 25"
    )


def _sh(args: List[str], timeout: int = 45) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True,
                          timeout=timeout)


def _ensure_wg_tools() -> bool:
    global _WGGO
    if not (shutil.which("wg") and shutil.which("wg-quick")):
        try:  # روی رانرِ گیت‌هاب نصبِ بدونِ رمز ممکن است؛ جای دیگر بی‌صدا رد می‌شود
            _sh(["sudo", "-n", "apt-get", "update", "-qq"], timeout=120)
            _sh(["sudo", "-n", "apt-get", "install", "-y", "-qq",
                 "wireguard-tools"], timeout=180)
        except Exception:
            pass
    try:  # شاید فقط ماژولِ کرنل لود نشده باشد
        _sh(["sudo", "-n", "modprobe", "wireguard"], timeout=30)
    except Exception:
        pass
    found = shutil.which("wireguard-go")
    if found:
        _WGGO = found
    elif shutil.which("go"):
        # موتورِ نرم‌افزاری (userspace) — روی رانرهایی که ساختِ اینترفیسِ کرنلی
        # بسته است، تونل را با TUN بالا می‌آورد. یک بار ساخته و کش می‌شود.
        try:
            dst = "/tmp/radar-wireguard-go"
            if not os.path.exists(dst):
                src = "/tmp/radar-wggo-src"
                _sh(["git", "clone", "--depth", "1",
                     "https://git.zx2c4.com/wireguard-go", src], timeout=180)
                _sh(["go", "build", "-o", dst, "."], timeout=300)
                # go build باید داخلِ پوشهٔ سورس اجرا شود:
                if not os.path.exists(dst):
                    r = subprocess.run(["go", "build", "-o", dst, "."],
                                       cwd=src, capture_output=True,
                                       text=True, timeout=300)
            if os.path.exists(dst):
                _WGGO = dst
        except Exception:
            pass
    return bool(shutil.which("wg"))


def _poll_traffic() -> Dict[str, Any]:
    """تا ~۹ ثانیه هندشیک و ترافیکِ واقعی را صبر و اندازه می‌گیرد."""
    for _ in range(6):
        hs = _sh(["sudo", "-n", "wg", "show", _IFACE,
                  "latest-handshakes"], timeout=15)
        shook = any(int(p[1]) > 0 for p in
                    (ln.split() for ln in hs.stdout.splitlines())
                    if len(p) >= 2 and p[1].isdigit())
        t0 = time.time()
        tr = _sh(["curl", "-s", "--max-time", "10", _TRACE_URL],
                 timeout=20)
        ms = int((time.time() - t0) * 1000)
        body = tr.stdout or ""
        if shook and "ip=" in body:
            loc = re.search(r"loc=(\w+)", body)
            ip = re.search(r"ip=(\S+)", body)
            return {"ok": True, "ms": ms,
                    "loc": loc.group(1) if loc else "",
                    "exit_ip": ip.group(1) if ip else ""}
        time.sleep(1.5)
    return {"ok": False, "error": "no-handshake-or-traffic"}


def _test_tunnel_userspace(conf: str) -> Dict[str, Any]:
    """موتورِ نرم‌افزاری: wireguard-go + ‎`wg setconf`‎ + روتِ فقط-برای-تست."""
    if not _WGGO:
        return {"ok": False, "error": "no-userspace-binary"}
    addr = ""
    for ln in conf.splitlines():
        if ln.startswith("Address"):
            addr = ln.split("=", 1)[1].split(",")[0].strip()
            break
    keep = []
    for ln in conf.splitlines():
        if ln.startswith(("DNS", "Jc", "Jmin", "Jmax", "H1", "H2", "H3",
                          "H4", "Address", "MTU")):
            continue
        keep.append(ln)
    setconf = "\n".join(keep) + "\n"
    sc_path = f"/tmp/{_IFACE}-set.conf"
    proc = None
    try:
        with io.open(sc_path, "w", encoding="utf-8") as fh:
            fh.write(setconf)
        _sh(["sudo", "-n", "ip", "link", "del", _IFACE], timeout=15)
        proc = subprocess.Popen(["sudo", "-n", _WGGO, _IFACE],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        for _ in range(10):  # صبر برای ساختِ تونل و سوکتِ UAPI
            if _sh(["sudo", "-n", "wg", "show", _IFACE],
                   timeout=10).returncode == 0:
                break
            time.sleep(0.7)
        r = _sh(["sudo", "-n", "wg", "setconf", _IFACE, sc_path],
                timeout=20)
        if r.returncode != 0:
            return {"ok": False,
                    "error": "setconf: " + (r.stderr or "")[:280]}
        if addr:
            _sh(["sudo", "-n", "ip", "addr", "add", addr, "dev", _IFACE],
                timeout=15)
        _sh(["sudo", "-n", "ip", "link", "set", "up", "dev", _IFACE],
            timeout=15)
        _sh(["sudo", "-n", "ip", "route", "add", "1.1.1.1/32", "dev",
             _IFACE], timeout=15)
        return _poll_traffic()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:280]}
    finally:
        try:
            _sh(["sudo", "-n", "ip", "link", "del", _IFACE], timeout=15)
        except Exception:
            pass
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            os.unlink(sc_path)
        except OSError:
            pass


def _test_tunnel(conf: str) -> Dict[str, Any]:
    """تونل را واقعاً بالا می‌آورد و زمانِ پاسخ + خروجی را اندازه می‌گیرد."""
    global _KERNEL_BROKEN
    if not _KERNEL_BROKEN:
        res = _test_tunnel_kernel(conf)
        if res.get("ok") or "ip link add" not in str(res.get("error", "")):
            return res
        _KERNEL_BROKEN = True  # کرنل بسته است؛ از این دور نرم‌افزاری می‌رویم
    return _test_tunnel_userspace(conf)


def _test_tunnel_kernel(conf: str) -> Dict[str, Any]:
    if not (shutil.which("wg") and shutil.which("wg-quick")):
        return {"ok": False, "error": "no-wg-tools"}
    path = f"/tmp/{_IFACE}.conf"
    test_conf = "\n".join(l for l in conf.splitlines()
                          if not l.startswith("DNS")) + "\n"
    try:
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(test_conf)
        os.chmod(path, 0o600)
        _sh(["sudo", "-n", "wg-quick", "down", path], timeout=30)
        up = _sh(["sudo", "-n", "wg-quick", "up", path], timeout=60)
        if up.returncode != 0:
            return {"ok": False,
                    "error": "wg-up: " + (up.stderr or "")[:280]}
        try:
            return _poll_traffic()
        finally:
            _sh(["sudo", "-n", "wg-quick", "down", path], timeout=30)
    except Exception as e:  # تست هرگز نباید ناشر را بخواباند
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:280]}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def run(out_dir: str) -> Dict[str, Any]:
    """نقطهٔ ورود — از `pipeline._main` فقط در اجرای واقعیِ ورک‌فلو صدا می‌شود."""
    stats_dir = os.path.join(out_dir, "stats")
    keys_dir = os.path.join(out_dir, "subs", "keys")
    os.makedirs(stats_dir, exist_ok=True)
    os.makedirs(keys_dir, exist_ok=True)
    reg_path = os.path.join(stats_dir, "wg_registry.json")

    registry: List[Dict[str, Any]] = []
    if os.path.exists(reg_path):
        try:
            registry = json.load(io.open(reg_path, encoding="utf-8")) \
                .get("keys", [])
        except Exception:
            registry = []

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # بازنشستگیِ مهلت‌گذشته‌ها
    registry = [k for k in registry
                if not k.get("expires") or k["expires"] > now_iso]

    bootstrap = int(os.environ.get("RADAR_WG_BOOTSTRAP", _BOOTSTRAP_KEYS))
    want = bootstrap if not registry else _NEW_KEYS_PER_RUN
    minted = 0
    for _attempt in range(2):  # ورکرها گاهی از IP رانر قفل می‌کنند؛ یک دورِ دیگر
        added = 0
        for _ in range(max(0, min(want, _MAX_KEYS - len(registry)))):
            acct = _mint_account()
            if acct and acct["license"]:
                registry.append(acct)
                added += 1
        minted += added
        if added or _attempt == 1:
            break
        time.sleep(5)

    eps = _clean_endpoints()
    tools_ok = False if os.environ.get("RADAR_WG_NO_TESTS") == "1" \
        else _ensure_wg_tools()
    budget = int(os.environ.get("RADAR_WG_MAX_TESTS", "40"))
    results: List[Dict[str, Any]] = []
    best_rows: List[Dict[str, Any]] = []

    for acct in registry:
        cands: List[str] = []
        if acct.get("best_ep"):
            cands.append(acct["best_ep"])
        for ep in random.sample(eps, min(3, len(eps))):
            if ep not in cands:
                cands.append(ep)
        best: Optional[Dict[str, Any]] = None
        for ep in cands[:3]:
            if budget <= 0:
                break
            budget -= 1
            conf = _build_conf(acct, ep)
            res = _test_tunnel(conf) if tools_ok else \
                {"ok": False, "error": "no-wg-tools"}
            res.update({"license": acct["license"], "endpoint": ep})
            results.append(res)
            if res.get("ok") and (best is None or res["ms"] < best["ms"]):
                best = res
        if best:
            acct["best_ep"] = best["endpoint"]
            acct["best_ms"] = best["ms"]
            acct["fails"] = 0
            best_rows.append({"license": acct["license"],
                              "endpoint": best["endpoint"],
                              "ms": best["ms"], "loc": best.get("loc", ""),
                              "expires": acct.get("expires", "")})
        else:
            acct["fails"] = int(acct.get("fails", 0)) + 1
            if not acct.get("best_ep"):
                acct["best_ep"] = cands[0] if cands else _FALLBACK_EPS[0]

        conf = _build_conf(acct, acct["best_ep"])
        head = ["# 📡 Radar — اشتراک شخصی وایرگارد",
                f"# key: {acct['license']}",
                f"# account: {acct.get('account_type', 'WARP+ free')}"
                f" — expires: {acct.get('expires', '')[:10]}"]
        if acct.get("best_ms") is not None and acct.get("fails", 0) == 0:
            head.append(f"# bot-tested ping: {acct['best_ms']} ms"
                        " (از سرور ربات)")
        head.append(f"# updated: {now_iso}")
        with io.open(os.path.join(keys_dir, acct["license"] + ".conf"),
                     "w", encoding="utf-8") as fh:
            fh.write("\n".join(head) + "\n" + conf + "\n")

    # حذفِ فایلِ کلیدهای بازنشسته/حذف‌شده از درختِ خروجی
    active = {k["license"] + ".conf" for k in registry}
    for name in os.listdir(keys_dir):
        if name not in active:
            try:
                os.unlink(os.path.join(keys_dir, name))
            except OSError:
                pass

    registry = [k for k in registry if int(k.get("fails", 0)) < _MAX_FAILS]

    # بهترین‌های دور: زیپِ آمادهٔ ایمپورت + فهرستِ خوانا
    best_rows.sort(key=lambda r: r["ms"])
    top = best_rows[:10]
    if top:
        zpath = os.path.join(out_dir, "subs", "wg_best.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            by_lic = {k["license"]: k for k in registry}
            for i, row in enumerate(top, 1):
                acct = by_lic.get(row["license"])
                if acct:
                    z.writestr(f"radar-wg-{i}.conf",
                               _build_conf(acct, row["endpoint"]))
        with io.open(os.path.join(out_dir, "subs", "wg_best.txt"),
                     "w", encoding="utf-8") as fh:
            fh.write("# 📡 Radar — بهترین وایرگاردهای تست‌شدهٔ این دور\n")
            fh.write(f"# updated: {now_iso}\n")
            for i, row in enumerate(top, 1):
                fh.write(f"#{i} ping={row['ms']}ms ep={row['endpoint']} "
                         f"loc={row['loc']} key={row['license']} "
                         f"file=subs/keys/{row['license']}.conf\n")

    report = {"generated_at": now_iso, "tools_ok": tools_ok,
              "minted": minted,
              "keys_active": len(registry),
              "tested": len(results),
              "ok": sum(1 for r in results if r.get("ok")),
              "results": results}
    with io.open(os.path.join(stats_dir, "wg_report.json"), "w",
                 encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    with io.open(reg_path, "w", encoding="utf-8") as fh:
        json.dump({"keys": registry}, fh, ensure_ascii=False, indent=1)

    print(f"[wg] keys={len(registry)} tested={len(results)} "
          f"ok={report['ok']} tools_ok={tools_ok}", file=sys.stderr)
    return report


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else ".")
