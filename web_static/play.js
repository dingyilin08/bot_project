(() => {
  "use strict";

  const loginView = document.querySelector("#login-view");
  const gameView = document.querySelector("#game-view");
  const resultPanel = document.querySelector("#result-panel");
  const actionPanel = document.querySelector("#action-panel");
  const requestState = document.querySelector("#request-state");
  let csrfToken = "";
  let busy = false;

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (csrfToken && options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrfToken;
    const response = await fetch(path, { credentials: "same-origin", ...options, headers });
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok) throw new Error(data.detail || "道场暂时无法响应，请稍后重试。");
    return data;
  }

  function setBusy(value, label = "") {
    busy = value;
    requestState.textContent = value ? (label || "推演中……") : "道场已连接";
    requestState.classList.toggle("warning", value);
    document.querySelectorAll("button").forEach((button) => {
      if (!button.closest("#login-view")) button.disabled = value;
    });
  }

  function showGame(session) {
    csrfToken = session.csrf_token || "";
    document.querySelector("#top-player-name").textContent = session.player_name;
    document.querySelector("#top-player-uid").textContent = `UID ${session.uid}`;
    loginView.hidden = true;
    gameView.hidden = false;
  }

  function showLogin(message = "") {
    csrfToken = "";
    gameView.hidden = true;
    loginView.hidden = false;
    document.querySelector("#login-error").textContent = message;
  }

  function number(value) {
    return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
  }

  function renderDashboard(data) {
    const player = data.player;
    const role = data.role;
    document.querySelector("#top-player-name").textContent = player.name;
    document.querySelector("#top-player-uid").textContent = `UID ${player.uid}`;
    document.querySelector("#player-power").textContent = number(player.power);
    document.querySelector("#player-lingshi").textContent = number(player.lingshi);
    document.querySelector("#player-xianyu").textContent = number(player.xianyu);
    document.querySelector("#dungeon-attempts").textContent = number(player.dungeon_attempts);
    document.querySelector("#cultivation-state").textContent = player.cultivating ? "参悟中" : "未参悟";
    if (role) {
      document.querySelector("#role-name").textContent = role.name;
      document.querySelector("#role-stage").textContent = `${role.world} · ${role.stage}`;
      document.querySelector("#role-level").textContent = `Lv.${role.level}`;
      document.querySelector("#role-attack").textContent = number(role.attack);
      document.querySelector("#role-health").textContent = number(role.health);
    } else {
      document.querySelector("#role-name").textContent = "尚未选择";
      document.querySelector("#role-stage").textContent = "请先选择初始角色";
      document.querySelector("#role-level").textContent = "—";
      document.querySelector("#role-attack").textContent = "—";
      document.querySelector("#role-health").textContent = "—";
    }
  }

  function appendTextLine(line) {
    const trimmed = line.trim();
    if (!trimmed) return;
    if (trimmed === "***" || /^-{3,}$/.test(trimmed)) {
      resultPanel.appendChild(document.createElement("hr"));
      return;
    }
    const heading = trimmed.match(/^#{1,6}\s*(.+)$/);
    const node = document.createElement(heading ? "h3" : "p");
    let text = heading ? heading[1] : trimmed;
    text = text.replace(/\*\*(.*?)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1");
    if (text.startsWith(">")) {
      node.className = "quote";
      text = text.replace(/^>\s*/, "");
    }
    node.textContent = text;
    resultPanel.appendChild(node);
  }

  function renderResponse(data) {
    resultPanel.replaceChildren();
    (data.content || "暂无回音。").split(/\r?\n/).forEach(appendTextLine);
    actionPanel.replaceChildren();
    (data.actions || []).forEach((action) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = action.label;
      button.addEventListener("click", () => {
        if (action.command.endsWith(" ")) {
          const input = document.querySelector("#command-input");
          input.value = action.command;
          input.focus();
        } else {
          runCommand(action.command, action.label);
        }
      });
      actionPanel.appendChild(button);
    });
  }

  async function loadDashboard() {
    renderDashboard(await api("/api/web/dashboard"));
  }

  async function runCommand(command, label = command) {
    if (busy) return;
    setBusy(true, `正在施行：${label}`);
    document.querySelector("#stage-title").textContent = label.replace(/[*：:].*$/, "");
    try {
      const data = await api("/api/web/command", {
        method: "POST",
        body: JSON.stringify({ command, request_id: `web-${crypto.randomUUID()}` }),
      });
      renderResponse(data);
      await loadDashboard();
    } catch (error) {
      renderResponse({ content: `##### 本次推演未完成\n\n${error.message}`, actions: [] });
    } finally {
      setBusy(false);
    }
  }

  document.querySelector("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorNode = document.querySelector("#login-error");
    errorNode.textContent = "正在核验绑定码……";
    try {
      const login = await api("/api/web/auth/link", {
        method: "POST",
        body: JSON.stringify({
          uid: Number(document.querySelector("#login-uid").value),
          code: document.querySelector("#login-code").value,
        }),
      });
      showGame({ uid: login.uid, player_name: "道友", csrf_token: login.csrf_token });
      await loadDashboard();
      await runCommand("今日修行", "今日修行");
    } catch (error) {
      errorNode.textContent = error.message;
    }
  });

  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-button").forEach((item) => item.classList.remove("active"));
      if (button.classList.contains("nav-button")) button.classList.add("active");
      runCommand(button.dataset.command, button.textContent.trim());
    });
  });

  document.querySelector("#command-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#command-input");
    if (input.value.trim()) runCommand(input.value.trim(), input.value.trim());
  });

  document.querySelector("#refresh-dashboard").addEventListener("click", async () => {
    if (busy) return;
    setBusy(true, "刷新状态……");
    try { await loadDashboard(); } finally { setBusy(false); }
  });

  document.querySelector("#logout-button").addEventListener("click", async () => {
    try { await api("/api/web/session", { method: "DELETE" }); } catch (_) { /* 清本地视图 */ }
    showLogin("已安全退出。再次进入需重新获取 QQ 绑定码。");
  });

  (async () => {
    try {
      const session = await api("/api/web/session");
      showGame(session);
      await loadDashboard();
      await runCommand("今日修行", "今日修行");
    } catch (_) {
      showLogin();
    }
  })();
})();
