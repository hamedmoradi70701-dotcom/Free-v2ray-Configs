/* Radar login gate — talks to radar-auth.pages.dev; session kept in localStorage. */
(function () {
  "use strict";
  var API = "https://radar-login-70701.pages.dev/auth";
  var KEY = "radar_session";
  var gate = document.getElementById("radarGate");
  if (!gate) return;

  var STR = {
    fa: { login: "ورود", signup: "ساخت حساب", user: "نام کاربری", pass: "رمز عبور", go: "ورود به رادار", goNew: "ساخت حساب و ورود", title: "رادار", sub: "برای دیدن کانفیگ‌ها اول وارد شو", wait: "صبر کن...", netErr: "خطا در اتصال — دوباره تلاش کن", have: "حساب داری؟", nohave: "حساب نداری؟" },
    en: { login: "Log in", signup: "Sign up", user: "Username", pass: "Password", go: "Enter Radar", goNew: "Create account & enter", title: "Radar", sub: "Log in to see the configs", wait: "Please wait...", netErr: "Connection error — try again", have: "Have an account?", nohave: "No account yet?" },
    ar: { login: "تسجيل الدخول", signup: "إنشاء حساب", user: "اسم المستخدم", pass: "كلمة المرور", go: "دخول رادار", goNew: "إنشاء حساب والدخول", title: "رادار", sub: "سجّل الدخول لرؤية الإعدادات", wait: "انتظر...", netErr: "خطأ في الاتصال — حاول مجددًا", have: "لديك حساب؟", nohave: "ليس لديك حساب؟" },
    ru: { login: "Вход", signup: "Регистрация", user: "Имя пользователя", pass: "Пароль", go: "Войти в Радар", goNew: "Создать аккаунт и войти", title: "Радар", sub: "Войдите, чтобы увидеть конфиги", wait: "Подождите...", netErr: "Ошибка соединения — ещё раз", have: "Есть аккаунт?", nohave: "Нет аккаунта?" },
    zh: { login: "登录", signup: "注册", user: "用户名", pass: "密码", go: "进入雷达", goNew: "注册并进入", title: "雷达", sub: "登录后查看配置", wait: "请稍候...", netErr: "连接错误 — 请重试", have: "已有账号？", nohave: "还没有账号？" }
  };
  var lang = (document.documentElement.lang || "fa").slice(0, 2);
  var t = STR[lang] || STR.fa;

  function getSession() {
    try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; }
  }
  function setSession(s) {
    try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {}
  }
  function clearSession() {
    try { localStorage.removeItem(KEY); } catch (e) {}
  }
  function unlock() {
    document.documentElement.classList.remove("radar-locked");
    gate.style.display = "none";
    gate.innerHTML = "";
  }
  function lock() {
    document.documentElement.classList.add("radar-locked");
    gate.style.display = "flex";
    renderForm();
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
    function submit() {
      var user = document.getElementById("rgUser").value.trim();
      var pass = document.getElementById("rgPass").value;
      var err = document.getElementById("rgErr");
      err.textContent = "";
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
    go.addEventListener("click", submit);
    document.getElementById("rgPass").addEventListener("keydown", function (e) { if (e.key === "Enter") submit(); });
  }

  var session = getSession();
  if (!session || !session.token) { lock(); return; }
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
