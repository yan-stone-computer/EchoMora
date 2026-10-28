const state = {
  groupId: "demo",
  userId: "u_alice",
  userName: "小岚",
  busy: false,
  lastRecall: [],
  snapshot: null,
};

const elements = {
  messageList: document.querySelector("#message-list"),
  emptyChat: document.querySelector("#empty-chat"),
  chatScroll: document.querySelector("#chat-scroll"),
  composer: document.querySelector("#composer"),
  input: document.querySelector("#message-input"),
  send: document.querySelector("#send-button"),
  typing: document.querySelector("#typing-row"),
  userSelect: document.querySelector("#user-select"),
  runtime: document.querySelector("#runtime"),
  runtimeLabel: document.querySelector("#runtime-label"),
  recallList: document.querySelector("#recall-list"),
  recallCount: document.querySelector("#recall-count"),
  memoryList: document.querySelector("#memory-list"),
  memoryCount: document.querySelector("#memory-count"),
  memorySubtitle: document.querySelector("#memory-subtitle"),
  graphSvg: document.querySelector("#graph-svg"),
  graphEmpty: document.querySelector("#graph-empty"),
  graphCount: document.querySelector("#graph-count"),
  affectLabel: document.querySelector("#affect-label"),
  affectValue: document.querySelector("#affect-value"),
  affectFill: document.querySelector("#affect-meter-fill"),
  sleep: document.querySelector("#sleep-button"),
  reset: document.querySelector("#reset-button"),
  toast: document.querySelector("#toast"),
};

function escapeText(value) {
  return String(value ?? "");
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = escapeText(text);
  return node;
}

function formatTime(timestamp) {
  const date = new Date(Number(timestamp) * 1000);
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function toast(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("is-error", isError);
  elements.toast.classList.add("is-visible");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => {
    elements.toast.classList.remove("is-visible");
  }, 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `请求失败（${response.status}）`);
  }
  return data;
}

function setBusy(value) {
  state.busy = value;
  elements.send.disabled = value;
  elements.input.disabled = value;
  elements.typing.classList.toggle("is-hidden", !value);
  if (value) {
    elements.chatScroll.scrollTop = elements.chatScroll.scrollHeight;
  }
}

function renderMessages(messages) {
  elements.messageList.replaceChildren();
  elements.emptyChat.classList.toggle("is-hidden", messages.length > 0);
  for (const message of messages) {
    const isSelf = message.user_id === state.userId;
    const article = el("article", `message${isSelf ? " is-self" : ""}`);
    const avatar = el("div", "avatar", isSelf ? state.userName.slice(0, 1) : "E");
    avatar.setAttribute("aria-hidden", "true");
    const main = el("div", "message-main");
    const meta = el("div", "message-meta");
    meta.append(
      el("span", "message-author", isSelf ? state.userName : "EchoMora"),
      el("time", "message-time", formatTime(message.created_at)),
    );
    const bubble = el("div", "message-bubble", message.content);
    main.append(meta, bubble);
    article.append(avatar, main);
    elements.messageList.append(article);
  }
  elements.chatScroll.scrollTop = elements.chatScroll.scrollHeight;
}

function renderAffect(affect) {
  const score = Number(affect?.score || 0);
  elements.affectLabel.textContent = affect?.label || "普通";
  elements.affectValue.textContent = `${score >= 0 ? "+" : ""}${score.toFixed(1)} / ±50`;
  const magnitude = Math.min(50, Math.abs(score));
  if (score < 0) {
    elements.affectFill.style.left = `${50 - magnitude}%`;
    elements.affectFill.style.width = `${magnitude}%`;
    elements.affectFill.style.backgroundColor = "var(--amber)";
  } else {
    elements.affectFill.style.left = "50%";
    elements.affectFill.style.width = `${magnitude}%`;
    elements.affectFill.style.backgroundColor = "var(--teal)";
  }
}

function renderRecall(hits) {
  state.lastRecall = hits || [];
  elements.recallList.replaceChildren();
  elements.recallCount.textContent = `${state.lastRecall.length} 条`;
  if (!state.lastRecall.length) {
    elements.recallList.append(el("p", "empty-note", "还没有触发召回。"));
    return;
  }
  for (const hit of state.lastRecall) {
    const item = el("article", "recall-item");
    const top = el("div", "recall-top");
    top.append(
      el("p", "recall-text", hit.text),
      el("span", "score", Number(hit.score).toFixed(3)),
    );
    const bar = el("div", "score-bar");
    const fill = el("span");
    fill.style.width = `${Math.min(100, Math.max(3, Number(hit.score) * 100))}%`;
    bar.append(fill);
    const factors = el(
      "div",
      "factor-line",
      `相似 ${Number(hit.similarity).toFixed(2)} · 重要 ${Number(hit.importance).toFixed(1)} · 新鲜 ${Number(hit.freshness).toFixed(2)}${hit.forgotten ? " · 软遗忘" : ""}`,
    );
    item.append(top, bar, factors);
    elements.recallList.append(item);
  }
}

function renderMemories(memories) {
  elements.memoryList.replaceChildren();
  elements.memoryCount.textContent = `${memories.length} 条`;
  if (!memories.length) {
    elements.memoryList.append(el("p", "empty-note", "当前用户还没有可见记忆。"));
    return;
  }
  for (const memory of memories.slice(0, 20)) {
    const item = el("article", "memory-item");
    item.append(el("p", "", memory.text));
    const meta = el("div", "memory-meta");
    meta.append(
      el("span", "state-chip", memory.kind),
      el(
        "span",
        `state-chip${memory.pinned ? " is-pinned" : ""}`,
        memory.pinned ? "固定保护" : `重要 ${Number(memory.importance).toFixed(1)}`,
      ),
      el(
        "span",
        `state-chip${memory.status === "suppressed" ? " is-suppressed" : ""}`,
        memory.status === "suppressed" ? "已软遗忘" : "可召回",
      ),
    );
    item.append(meta);
    elements.memoryList.append(item);
  }
}

function renderGraph(graph) {
  elements.graphSvg.replaceChildren();
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  elements.graphCount.textContent = `${nodes.length} 个节点`;
  elements.graphEmpty.hidden = nodes.length > 0;
  if (!nodes.length) return;

  const topNodes = nodes.slice(0, 12);
  const centerX = 280;
  const centerY = 135;
  const radiusX = 220;
  const radiusY = 92;
  const positions = new Map();
  topNodes.forEach((node, index) => {
    const angle = (index / Math.max(1, topNodes.length)) * Math.PI * 2 - Math.PI / 2;
    positions.set(node.id, {
      x: centerX + Math.cos(angle) * radiusX,
      y: centerY + Math.sin(angle) * radiusY,
    });
  });

  const nodeIds = new Set(topNodes.map((node) => node.id));
  for (const edge of edges) {
    if (!nodeIds.has(edge.source_node) || !nodeIds.has(edge.target_node)) continue;
    const begin = positions.get(edge.source_node);
    const end = positions.get(edge.target_node);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", begin.x);
    line.setAttribute("y1", begin.y);
    line.setAttribute("x2", end.x);
    line.setAttribute("y2", end.y);
    if (edge.valid_to) line.classList.add("is-inactive");
    elements.graphSvg.append(line);
  }

  for (const node of topNodes) {
    const position = positions.get(node.id);
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", position.x);
    circle.setAttribute("cy", position.y);
    circle.setAttribute("r", node.node_type === "person" ? 18 : 14);
    if (node.node_type === "person") circle.classList.add("is-person");
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = node.name;
    circle.append(title);
    elements.graphSvg.append(circle);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", position.x);
    label.setAttribute("y", position.y + (node.node_type === "person" ? 34 : 30));
    label.textContent = node.name.length > 8 ? `${node.name.slice(0, 7)}…` : node.name;
    elements.graphSvg.append(label);
  }
}

function renderSnapshot(snapshot) {
  state.snapshot = snapshot;
  renderMessages(snapshot.messages || []);
  renderAffect(snapshot.affect || {});
  renderMemories(snapshot.memories || []);
  renderGraph(snapshot.graph || {});
  renderRecall(snapshot.last_recall?.recalled || []);
  elements.memorySubtitle.textContent = `${state.userName} 可见范围 · ${snapshot.memories?.length || 0} 条长期记忆`;
}

async function loadHealth() {
  try {
    const health = await api("/api/health");
    elements.runtime.classList.toggle("is-online", health.llm === "deepseek");
    elements.runtimeLabel.textContent = health.llm === "deepseek" ? "DeepSeek 在线" : "离线规则演示";
  } catch (error) {
    elements.runtime.remove();
    toast(`无法连接本地服务：${error.message}`, true);
  }
}

async function loadSnapshot() {
  const params = new URLSearchParams({
    group_id: state.groupId,
    user_id: state.userId,
  });
  const snapshot = await api(`/api/snapshot?${params}`);
  renderSnapshot(snapshot);
  if (!snapshot.messages.length) {
    renderRecall([]);
  }
}

async function sendMessage(content) {
  if (!content.trim() || state.busy) return;
  setBusy(true);
  const optimistic = {
    id: `optimistic-${Date.now()}`,
    user_id: state.userId,
    user_name: state.userName,
    role: "user",
    content: content.trim(),
    created_at: Date.now() / 1000,
  };
  const existing = [...(state.snapshot?.messages || []), optimistic];
  renderMessages(existing);
  elements.input.value = "";
  try {
    const result = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        group_id: state.groupId,
        user_id: state.userId,
        user_name: state.userName,
        content,
        use_llm: true,
      }),
    });
    renderRecall(result.recalled || []);
    await loadSnapshot();
    const successful = result.mode === "deepseek";
    toast(
      successful
        ? `DeepSeek 回复 · 召回 ${result.recalled.length} 条记忆`
        : `离线回复 · 召回 ${result.recalled.length} 条记忆`,
    );
    if (result.llm_error) {
      toast(`DeepSeek 请求失败，已自动降级：${result.llm_error}`, true);
    }
  } catch (error) {
    await loadSnapshot().catch(() => {});
    toast(error.message, true);
  } finally {
    setBusy(false);
    elements.input.focus();
  }
}

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(elements.input.value);
});

elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.input.value = button.dataset.prompt || "";
    elements.input.focus();
  });
});

elements.userSelect.addEventListener("change", async (event) => {
  state.userId = event.target.value;
  state.userName = event.target.selectedOptions[0].dataset.name;
  try {
    await loadSnapshot();
    renderRecall([]);
    toast(`已切换到 ${state.userName}，个人记忆不会串线`);
  } catch (error) {
    toast(error.message, true);
  }
});

elements.sleep.addEventListener("click", async () => {
  elements.sleep.disabled = true;
  try {
    const result = await api("/api/sleep", {
      method: "POST",
      body: JSON.stringify({ group_id: state.groupId }),
    });
    await loadSnapshot();
    toast(
      `睡眠整理完成：软遗忘 ${result.soft_forgotten} 条，恢复 ${result.restored} 条`,
    );
  } catch (error) {
    toast(error.message, true);
  } finally {
    elements.sleep.disabled = false;
  }
});

elements.reset.addEventListener("click", async () => {
  try {
    await api("/api/reset", {
      method: "POST",
      body: JSON.stringify({ group_id: state.groupId }),
    });
    renderRecall([]);
    await loadSnapshot();
    toast("演示数据已清空");
  } catch (error) {
    toast(error.message, true);
  }
});

async function boot() {
  await Promise.all([loadHealth(), loadSnapshot()]);
  elements.input.focus();
}

boot().catch((error) => {
  toast(error.message, true);
});

