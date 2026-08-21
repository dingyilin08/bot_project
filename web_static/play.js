(() => {
  "use strict";

  const loginView = document.querySelector("#login-view");
  const gameView = document.querySelector("#game-view");
  const resultPanel = document.querySelector("#result-panel");
  const actionPanel = document.querySelector("#action-panel");
  const requestState = document.querySelector("#request-state");
  const collectionPanel = document.querySelector("#collection-panel");
  const collectionContent = document.querySelector("#collection-content");
  let csrfToken = "";
  let busy = false;
  let currentCollection = "";

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
        if (action.requires_input) {
          const input = document.querySelector("#command-input");
          input.value = `${action.command} `;
          input.placeholder = `请补充“${action.label}”所需内容后施行`;
          input.focus();
        } else {
          runCommand(action.command, action.label);
        }
      });
      actionPanel.appendChild(button);
    });
  }

  function collectionCard(titleText, metaText, stats, actionLabel, actionCommand) {
    const card = document.createElement("article");
    card.className = "collection-card";
    const title = document.createElement("h4");
    title.textContent = titleText;
    const meta = document.createElement("p");
    meta.className = "collection-meta";
    meta.textContent = metaText;
    const detail = document.createElement("p");
    detail.textContent = stats;
    card.append(title, meta, detail);
    if (actionLabel && actionCommand) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = actionLabel;
      button.addEventListener("click", () => runCommand(actionCommand, actionLabel));
      card.appendChild(button);
    }
    return card;
  }

  async function loadCollection(view) {
    currentCollection = view;
    collectionContent.replaceChildren();
    collectionPanel.hidden = false;
    if (view === "roles") {
      document.querySelector("#collection-title").textContent = "诸天角色";
      const data = await api("/api/web/roles");
      (data.roles || []).forEach((role) => {
        collectionContent.appendChild(collectionCard(
          `${role.name}${role.active ? " · 出战" : ""}`,
          `${role.world}｜${role.stage}｜Lv.${role.level}`,
          `攻击 ${number(role.attack)} · 防御 ${number(role.defense)} · 气血 ${number(role.health)}`,
          role.active ? "查看当前角色" : "设为出战",
          role.active ? "当前角色" : `出战 ${role.id}`,
        ));
      });
    } else if (view === "inventory") {
      document.querySelector("#collection-title").textContent = "乾坤背包";
      const data = await api("/api/web/inventory?page=1&page_size=60");
      (data.items || []).forEach((item) => {
        collectionContent.appendChild(collectionCard(
          `${item.name} × ${number(item.amount)}`,
          `物品编号 #${item.id}｜类别 ${item.type}`,
          item.description || "暂无物品说明。",
          "查看详情",
          `物品信息 ${item.name}`,
        ));
      });
      if (!(data.items || []).length) collectionContent.textContent = "背包空空如也。";
    }
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
      if (currentCollection && !collectionPanel.hidden) await loadCollection(currentCollection);
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
      if (button.dataset.view) {
        loadCollection(button.dataset.view).catch((error) => {
          collectionContent.textContent = error.message;
        });
      } else if (button.classList.contains("nav-button")) {
        collectionPanel.hidden = true;
        currentCollection = "";
      }
      runCommand(button.dataset.command, button.textContent.trim());
    });
  });

  document.querySelector("#command-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#command-input");
    if (input.value.trim()) {
      runCommand(input.value.trim(), input.value.trim());
      input.placeholder = "也可输入已有游戏指令，例如：角色背包";
    }
  });

  document.querySelector("#refresh-dashboard").addEventListener("click", async () => {
    if (busy) return;
    setBusy(true, "刷新状态……");
    try { await loadDashboard(); } finally { setBusy(false); }
  });

  document.querySelector("#close-collection").addEventListener("click", () => {
    collectionPanel.hidden = true;
    currentCollection = "";
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
