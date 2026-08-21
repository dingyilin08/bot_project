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

  function renderDaoHeart(data) {
    collectionContent.replaceChildren();
    const event = data.event;
    const summary = document.createElement("article");
    summary.className = "collection-card dao-heart-summary";
    const title = document.createElement("h4");
    title.textContent = event.title;
    const description = document.createElement("p");
    description.textContent = event.description;
    const seed = document.createElement("p");
    seed.className = "collection-meta";
    seed.textContent = `今日天机种 ${event.seed}｜同一日结果固定`;
    const tendencies = document.createElement("p");
    tendencies.textContent = `清明 ${data.tendencies.clarity} · 勇毅 ${data.tendencies.courage} · 仁心 ${data.tendencies.compassion}`;
    summary.append(title, description, seed, tendencies);
    collectionContent.appendChild(summary);

    if (data.chosen) {
      const result = data.result || {};
      collectionContent.appendChild(collectionCard(
        `今日已择 · ${result.choice_label || data.choice_key}`,
        result.result_text || "今日问境已经完成。",
        `${(result.buff || {}).text || "道心余韵今日有效"} · 灵石 +${number((result.reward || {}).lingshi)}`,
      ));
      return;
    }
    (event.choices || []).forEach((choice) => {
      const card = collectionCard(
        `${choice.label} · ${choice.tendency}`,
        choice.description,
        `灵石 +${number(choice.reward.lingshi)} · ${choice.buff}`,
      );
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `选择${choice.tendency}之道`;
      button.addEventListener("click", () => chooseDaoHeart(choice.key));
      card.appendChild(button);
      collectionContent.appendChild(card);
    });
  }

  async function chooseDaoHeart(choice) {
    if (busy) return;
    setBusy(true, "正在叩问本心……");
    try {
      const result = await api("/api/web/dao-heart/choice", {
        method: "POST",
        body: JSON.stringify({ choice, request_id: `web-dao-${crypto.randomUUID()}` }),
      });
      renderResponse({
        content: `##### ${result.event_title} · ${result.choice_label}\n\n${result.result_text}\n\n获得灵石 ×${result.reward.lingshi}\n${result.buff.text}`,
        actions: [{ label: "开始参悟", command: "参悟" }],
      });
      renderDaoHeart(await api("/api/web/dao-heart"));
      await loadDashboard();
    } catch (error) {
      renderResponse({ content: `##### 道心抉择未完成\n\n${error.message}`, actions: [] });
    } finally {
      setBusy(false);
    }
  }

  function dungeonActionCard(titleText, metaText, stats, actions) {
    const card = collectionCard(titleText, metaText, stats);
    const row = document.createElement("div");
    row.className = "card-actions";
    actions.forEach(({ label, command, disabled }) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.disabled = Boolean(disabled);
      button.addEventListener("click", () => runCommand(command, label));
      row.appendChild(button);
    });
    card.appendChild(row);
    return card;
  }

  function renderDungeons(data) {
    collectionContent.replaceChildren();
    if (!data.role) {
      collectionContent.textContent = "当前没有出战角色，请先在角色道体中选择出战角色。";
      return;
    }
    if (data.active_progress) {
      const progress = data.active_progress;
      collectionContent.appendChild(dungeonActionCard(
        `历练中 · ${progress.dungeon_name}`,
        `第 ${progress.wave}/${progress.total_waves} 波｜气血 ${progress.player_hp_percent}%｜连胜 ${progress.kill_streak}`,
        `已击败 ${progress.defeated_count} 位敌手，总击杀 ${progress.total_kills}`,
        [{
          label: data.battle_active ? "继续当前回合" : "查看本波敌手",
          command: data.battle_active ? "战斗状态" : "查看怪物",
        }, { label: "放弃本次历练", command: "放弃副本" }],
      ));
      if (!data.battle_active) {
        progress.monsters.filter((monster) => !monster.defeated).forEach((monster) => {
          collectionContent.appendChild(dungeonActionCard(
            `${monster.type === "boss" ? "首领" : "敌手"} #${monster.index} · ${monster.name}`,
            monster.description || "秘境中的未知敌手",
            "尚可挑战",
            [{ label: `挑战 ${monster.name}`, command: `挑战怪物 ${monster.index}` }],
          ));
        });
      }
    }
    const remaining = Number(data.remaining_attempts || 0);
    (data.dungeons || []).forEach((dungeon) => {
      collectionContent.appendChild(dungeonActionCard(
        `#${dungeon.id} · ${dungeon.name}`,
        `${dungeon.world}｜Lv.${dungeon.min_level}+ · ${dungeon.min_stage}｜${dungeon.cross_world ? "跨界历练" : "同界历练"}`,
        `${dungeon.description}｜通关基础奖励：经验 ${number(dungeon.reward_exp)}、灵石 ${number(dungeon.reward_lingshi)}｜已通关 ${dungeon.clear_count} 次`,
        [
          { label: "查看秘境详情", command: `副本信息 ${dungeon.id}` },
          {
            label: remaining > 0 ? "开始挑战" : "校验今日额度",
            command: `挑战副本 ${dungeon.id}`,
            disabled: Boolean(data.active_progress),
          },
        ],
      ));
    });
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
    } else if (view === "dao-heart") {
      document.querySelector("#collection-title").textContent = "道心问境";
      renderDaoHeart(await api("/api/web/dao-heart"));
    } else if (view === "dungeons") {
      document.querySelector("#collection-title").textContent = "秘境历练";
      renderDungeons(await api("/api/web/dungeons?page=1&page_size=18"));
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
