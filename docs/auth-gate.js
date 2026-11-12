/* Radar login gate — talks to radar-login-70701.pages.dev; session kept in localStorage.
   - Everyone must log in (no fail-open).
   - Admin backdoor: after one successful server login as "admin", a hash of the
     password is kept in THIS browser only, so later admin logins work offline
     (the site itself recognizes the admin; nothing is sent to the server).
   - A badge at the top shows the current role (admin / user name). */
(function () {
  "use strict";
  var API = "https://radar-login-70701.pages.dev/auth";
  var PANEL = "https://radar-login-70701.pages.dev/panel";
  var KEY = "radar_session";
  var AKEY = "radar_admin_hash";
  var gate = document.getElementById("radarGate");
  if (!gate) return;

  var STR = {
    fa: { login: "ورود", signup: "ساخت حساب", user: "نام کاربری", pass: "رمز عبور", go: "ورود به رادار", goNew: "ساخت حساب و ورود", title: "رادار", sub: "برای دیدن کانفیگ‌ها اول وارد شو", wait: "صبر کن...", netErr: "خطا در اتصال — دوباره تلاش کن", vpn: "برای ورود و ساخت حساب، VPN را روشن کنید", admin: "ادمین", logout: "خروج", panel: "پنل مدیریت", bye: "خارج می‌شوی؟" },
    en: { login: "Log in", signup: "Sign up", user: "Username", pass: "Password", go: "Enter Radar", goNew: "Create account & enter", title: "Radar", sub: "Log in to see the configs", wait: "Please wait...", netErr: "Connection error — try again", vpn: "Turn on a VPN to log in or sign up", admin: "Admin", logout: "Log out", panel: "Admin panel", bye: "Log out?" },
    ar: { login: "تسجيل الدخول", signup: "إنشاء حساب", user: "اسم المستخدم", pass: "كلمة المرور", go: "دخول رادار", goNew: "إنشاء حساب والدخول", title: "رادار", sub: "سجّل الدخول لرؤية الإعدادات", wait: "انتظر...", netErr: "خطأ في الاتصال — حاول مجددًا", vpn: "فعّل VPN لتسجيل الدخول أو إنشاء حساب", admin: "المسؤول", logout: "خروج", panel: "لوحة الإدارة", bye: "تسجيل الخروج؟" },
    ru: { login: "Вход", signup: "Регистрация", user: "Имя пользователя", pass: "Пароль", go: "Войти в Радар", goNew: "Создать аккаунт и войти", title: "Радар", sub: "Войдите, чтобы увидеть конфиги", wait: "Подождите...", netErr: "Ошибка соединения — ещё раз", vpn: "Для входа и регистрации включите VPN", admin: "Админ", logout: "Выйти", panel: "Панель управления", bye: "Выйти?" },
    zh: { login: "登录", signup: "注册", user: "用户名", pass: "密码", go: "进入雷达", goNew: "注册并进入", title: "雷达", sub: "登录后查看配置", wait: "请稍候...", netErr: "连接错误 — 请重试", vpn: "登录或注册时请开启 VPN", admin: "管理员", logout: "退出", panel: "管理面板", bye: "确定退出？" }
  };
  var lang = (document.documentElement.lang || "fa").slice(0, 2);
  var t = STR[lang] || STR.fa;

  function getSession() { try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; } }
  function setSession(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} }
  function clearSession() { try { localStorage.removeItem(KEY); } catch (e) {} }
  function getAdminHash() { try { return localStorage.getItem(AKEY); } catch (e) { return null; } }
  function setAdminHash(h) { try { localStorage.setItem(AKEY, h); } catch (e) {} }

  function sha256hex(text) {
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)).then(function (buf) {
      return [...new Uint8Array(buf)].map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
    });
  }

  function unlock() {
    document.documentElement.classList.remove("radar-locked");
    gate.style.display = "none";
    gate.innerHTML = "";
    showBadge();
  }
  function lock() {
    document.documentElement.classList.add("radar-locked");
    gate.style.display = "flex";
    hideBadge();
    renderForm();
  }

  function hideBadge() { var b = document.getElementById("radarBadge"); if (b) b.remove(); }
  function showBadge() {
    hideBadge();
    var s = getSession();
    if (!s) return;
    var b = document.createElement("div");
    b.id = "radarBadge";
    b.style.cssText = "position:fixed;top:10px;inset-inline-start:10px;z-index:99998;display:flex;gap:8px;align-items:center;background:rgba(21,8,38,.82);border:1px solid rgba(168,85,247,.5);color:#efe9ff;border-radius:999px;padding:6px 12px;font-size:13.5px;backdrop-filter:blur(8px);box-shadow:0 8px 24px rgba(0,0,0,.35)";
    var label = s.owner ? ("🛡 " + t.admin) : ("👤 " + (s.user || ""));
    var html = "<span>" + label.replace(/</g, "&lt;") + "</span>";
    if (s.owner) html += '<a href="' + PANEL + '" target="_blank" rel="noopener" style="color:#d8b4fe;text-decoration:none;font-weight:700">' + t.panel + "</a>";
    html += '<button type="button" id="radarOut" style="background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.25);color:#fff;border-radius:999px;padding:2px 10px;cursor:pointer;font-size:12.5px">' + t.logout + "</button>";
    b.innerHTML = html;
    document.body.appendChild(b);
    document.getElementById("radarOut").addEventListener("click", function () {
      if (confirm(t.bye)) { clearSession(); location.reload(); }
    });
  }

  function renderForm() {
    var mode = "login";
    gate.innerHTML =
      '<div class="rg-card">' +
      '<div class="rg-logo">📡</div>' +
      '<div class="rg-title">' + t.title + "</div>" +
      '<div class="rg-sub">' + t.sub + "</div>" +
      '<div class="rg-tabs"><button type="button" class="rg-tab rg-on" data-m="login">' + t.login + '</button><button type="button" class="rg-tab" data-m="signup">' + t.signup + "</button></div>" +
      '<input class="rg-in" id="rgUser" autocomplete="username" placeholder="' + t.user + '">' +
      '<input class="rg-in" id="rgPass" type="password" autocomplete="current-password" placeholder="' + t.pass + '">' +
      '<div class="rg-err" id="rgErr"></div>' +
      '<button type="button" class="rg-go" id="rgGo">' + t.go + "</button>" +
      '<div style="margin-top:14px;font-size:13px;color:#ffd479">🔒 ' + t.vpn + "</div>" +
      "</div>";
    var tabs = gate.querySelectorAll(".rg-tab");
    var go = document.getElementById("rgGo");
    tabs.forEach(function (b) {
      b.addEventListener("click", function () {
        mode = b.getAttribute("data-m");
        tabs.forEach(function (x) { x.classList.toggle("rg-on", x === b); });
        go.textContent = mode === "login" ? t.go : t.goNew;
        document.getElementById("rgErr").textContent = "";
      });
    });

    function serverAuth(user, pass) {
      var err = document.getElementById("rgErr");
      go.disabled = true; go.textContent = t.wait;
      fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: mode, user: user, pass: pass })
      }).then(function (r) { return r.json().then(function (j) { return { s: r.status, j: j }; }); })
        .then(function (res) {
          go.disabled = false; go.textContent = mode === "login" ? t.go : t.goNew;
          if (res.j && res.j.ok) {
            setSession({ user: res.j.user, token: res.j.token, owner: !!res.j.owner });
            if (res.j.owner) sha256hex("radar-admin:" + pass).then(setAdminHash);
            unlock();
          } else {
            err.textContent = (res.j && res.j.error) || t.netErr;
          }
        })
        .catch(function () {
          go.disabled = false; go.textContent = mode === "login" ? t.go : t.goNew;
          err.textContent = t.netErr;
        });
    }

    function submit() {
      var user = document.getElementById("rgUser").value.trim();
      var pass = document.getElementById("rgPass").value;
      var err = document.getElementById("rgErr");
      err.textContent = "";
      // Admin backdoor: recognized locally by this browser, no server needed.
      if (mode === "login" && user === "admin" && getAdminHash()) {
        sha256hex("radar-admin:" + pass).then(function (h) {
          if (h === getAdminHash()) {
            setSession({ user: "admin", owner: true, local: true });
            unlock();
          } else {
            serverAuth(user, pass);
          }
        });
        return;
      }
      serverAuth(user, pass);
    }
    go.addEventListener("click", submit);
    document.getElementById("rgPass").addEventListener("keydown", function (e) { if (e.key === "Enter") submit(); });
  }

  var session = getSession();
  if (!session || !session.token && !session.local) { lock(); return; }
  if (session.local) { unlock(); return; }
  // Session exists: let them in right away, verify in the background.
  unlock();
  fetch(API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "me", user: session.user, token: session.token })
  }).then(function (r) { return r.json(); })
    .then(function (j) { if (!j || !j.ok) { clearSession(); lock(); } })
    .catch(function () { /* offline: keep the remembered session */ });
})();
