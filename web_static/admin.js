(() => {
  "use strict";

  const loginView = document.querySelector("#admin-login-view");
  const adminView = document.querySelector("#admin-view");
  const grantMessage = document.querySelector("#grant-message");
  let csrfToken = "";
  let selectedPlayer = null;
  let selectedItem = null;

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (csrfToken && options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrfToken;
    const response = await fetch(path, { credentials: "same-origin", ...options, headers });
    let data = {};
    try { data = await response.json(); } catch (_) { data = {}; }
    if (!response.ok) throw new Error(data.detail || "管理端暂时无法响应。");
    return data;
  }

  function showAdmin(session) {
    csrfToken = session.csrf_token || "";
    document.querySelector("#admin-name").textContent = session.player_name || "管理员";
    document.querySelector("#admin-uid").textContent = `UID ${session.uid}`;
    loginView.hidden = true;
    adminView.hidden = false;
  }

  function showLogin(message = "") {
    csrfToken = "";
    adminView.hidden = true;
    loginView.hidden = false;
    document.querySelector("#admin-login-error").textContent = message;
  }

  function makeButton(label, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "text-button";
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
  }

  function renderPlayers(players) {
    const root = document.querySelector("#player-results");
    root.replaceChildren();
    if (!players.length) {
      root.textContent = "没有找到匹配玩家。";
      return;
    }
    players.forEach((player) => {
      const row = document.createElement("div");
      row.className = "data-row";
      const info = document.createElement("div");
      const title = document.createElement("div");
      title.className = "row-title";
      title.textContent = `${player.name} · UID ${player.uid}`;
      const meta = document.createElement("div");
      meta.className = "row-meta";
      meta.textContent = `${player.role_name || "未选角色"}｜战力 ${player.power}｜灵石 ${player.lingshi}｜仙玉 ${player.xianyu}`;
      info.append(title, meta);
      row.append(info, makeButton("选择", () => {
        selectedPlayer = player;
        document.querySelector("#selected-player").textContent = `${player.name} · UID ${player.uid}`;
        document.querySelector("#selected-player").classList.remove("warning");
        grantMessage.textContent = "已选择玩家，请继续选择资源与数量。";
      }));
      root.appendChild(row);
    });
  }

  function renderItems(items) {
    const root = document.querySelector("#item-results");
    root.replaceChildren();
    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "item-row";
      const info = document.createElement("div");
      const title = document.createElement("div");
      title.className = "row-title";
      title.textContent = `${item.name} · #${item.id}`;
      const meta = document.createElement("div");
      meta.className = "row-meta";
      meta.textContent = item.description;
      info.append(title, meta);
      row.append(info, makeButton("选用", () => {
        selectedItem = item;
        document.querySelector("#selected-item").value = String(item.id);
        document.querySelector("#item-query").value = `${item.name} (#${item.id})`;
      }));
      root.appendChild(row);
    });
  }

  async function searchPlayers(query = "") {
    const data = await api(`/api/admin/players?q=${encodeURIComponent(query)}`);
    renderPlayers(data.players || []);
  }

  async function searchItems() {
    const query = document.querySelector("#item-query").value.trim();
    const data = await api(`/api/admin/items?q=${encodeURIComponent(query)}`);
    renderItems(data.items || []);
  }

  function requirePlayer() {
    if (!selectedPlayer) throw new Error("请先从玩家查询结果中选择目标玩家。 ");
  }

  async function loadAudit() {
    const data = await api("/api/admin/audit?limit=50");
    const root = document.querySelector("#audit-rows");
    root.replaceChildren();
    (data.records || []).forEach((record) => {
      const row = document.createElement("tr");
      const values = [
        record.created_at,
        String(record.operator_uid),
        record.target_uid == null ? "—" : String(record.target_uid),
        record.action,
        record.status,
        JSON.stringify(record.detail),
      ];
      values.forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.appendChild(cell);
      });
      root.appendChild(row);
    });
  }

  document.querySelector("#admin-login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorNode = document.querySelector("#admin-login-error");
    errorNode.textContent = "正在核验管理权限……";
    try {
      const login = await api("/api/admin/auth/link", {
        method: "POST",
        body: JSON.stringify({
          uid: Number(document.querySelector("#admin-login-uid").value),
          code: document.querySelector("#admin-login-code").value,
        }),
      });
      showAdmin({ uid: login.uid, player_name: "管理员", csrf_token: login.csrf_token });
      await Promise.all([searchPlayers(), loadAudit()]);
    } catch (error) {
      errorNode.textContent = error.message;
    }
  });

  document.querySelector("#player-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await searchPlayers(document.querySelector("#player-query").value.trim()); }
    catch (error) { grantMessage.textContent = error.message; }
  });

  document.querySelector("#item-search-button").addEventListener("click", async () => {
    try { await searchItems(); }
    catch (error) { grantMessage.textContent = error.message; }
  });

  document.querySelector("#item-grant-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      requirePlayer();
      if (!selectedItem) throw new Error("请先查询并选择物品。 ");
      const amount = Number(document.querySelector("#item-amount").value);
      if (!window.confirm(`确认向 ${selectedPlayer.name}（${selectedPlayer.uid}）发放 ${selectedItem.name} × ${amount}？`)) return;
      const data = await api("/api/admin/grants/item", {
        method: "POST",
        body: JSON.stringify({
          target_uid: selectedPlayer.uid,
          item_key: String(selectedItem.id),
          amount,
          request_id: `web-admin-${crypto.randomUUID()}`,
        }),
      });
      grantMessage.textContent = `发放成功：${data.result.item_name} × ${data.result.amount}，当前数量 ${data.result.balance_after}。`;
      await loadAudit();
    } catch (error) { grantMessage.textContent = error.message; }
  });

  document.querySelector("#xianyu-grant-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      requirePlayer();
      const amount = Number(document.querySelector("#xianyu-amount").value);
      if (!window.confirm(`确认向 ${selectedPlayer.name}（${selectedPlayer.uid}）发放仙玉 × ${amount}？`)) return;
      const data = await api("/api/admin/grants/xianyu", {
        method: "POST",
        body: JSON.stringify({
          target_uid: selectedPlayer.uid,
          amount,
          request_id: `web-admin-${crypto.randomUUID()}`,
        }),
      });
      grantMessage.textContent = `发放成功：仙玉 × ${data.result.amount}，当前余额 ${data.result.balance_after}。`;
      await Promise.all([loadAudit(), searchPlayers(document.querySelector("#player-query").value.trim())]);
    } catch (error) { grantMessage.textContent = error.message; }
  });

  document.querySelector("#refresh-audit").addEventListener("click", () => loadAudit().catch((error) => { grantMessage.textContent = error.message; }));

  document.querySelector("#admin-logout").addEventListener("click", async () => {
    try { await api("/api/admin/session", { method: "DELETE" }); } catch (_) { /* 清理本地视图 */ }
    showLogin("管理会话已撤销。再次进入需重新获取管理绑定码。");
  });

  (async () => {
    try {
      const session = await api("/api/admin/session");
      showAdmin(session);
      await Promise.all([searchPlayers(), loadAudit()]);
    } catch (_) {
      showLogin();
    }
  })();
})();
