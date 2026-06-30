(function () {
  "use strict";

  const API = "";
  let currentNovel = null;
  let chatMode = "write";
  let sending = false;

  const AGENT_LABELS = {
    chief:   { name: "Chief 总编",     icon: "👨‍💼" },
    planner: { name: "Planner 规划师", icon: "🧠" },
    writer:  { name: "Writer 写手",   icon: "✍️" },
    critic:  { name: "Critic 审稿人", icon: "🔍" },
    system:  { name: "System",        icon: "⚙️" },
  };

  const $novelList = document.getElementById("novel-list");
  const $welcome = document.getElementById("welcome");
  const $workspace = document.getElementById("workspace");
  const $novelTitle = document.getElementById("novel-title");
  const $messagesWrite = document.getElementById("messages-write");
  const $messagesAsk = document.getElementById("messages-ask");
  const $input = document.getElementById("user-input");
  const $btnSend = document.getElementById("btn-send");
  const $btnDeleteLast = document.getElementById("btn-delete-last");
  const $memoryPanel = document.getElementById("memory-panel");
  const $chaptersPanel = document.getElementById("chapters-panel");
  const $modalOverlay = document.getElementById("modal-overlay");
  const $novelNameInput = document.getElementById("novel-name-input");
  const $fileInput = document.getElementById("file-input");
  const $freeChat = document.getElementById("free-chat");

  // ========== Novel List ==========
  async function loadNovels() {
    const res = await fetch(`${API}/api/novels`);
    const novels = await res.json();
    $novelList.innerHTML = "";
    novels.forEach((n) => {
      const li = document.createElement("li");
      li.dataset.name = n.name;
      if (currentNovel === n.name) li.classList.add("active");

      const nameSpan = document.createElement("span");
      nameSpan.className = "novel-name";
      nameSpan.textContent = `${n.name}（${n.chapter_count}章）`;
      nameSpan.addEventListener("click", () => selectNovel(n.name));

      const actions = document.createElement("span");
      actions.className = "novel-actions";

      const btnRename = document.createElement("button");
      btnRename.className = "novel-action-btn";
      btnRename.title = "重命名";
      btnRename.textContent = "✏";
      btnRename.addEventListener("click", (e) => {
        e.stopPropagation();
        renameNovel(n.name);
      });

      const btnDelete = document.createElement("button");
      btnDelete.className = "novel-action-btn novel-action-del";
      btnDelete.title = "删除";
      btnDelete.textContent = "✕";
      btnDelete.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteNovel(n.name);
      });

      actions.appendChild(btnRename);
      actions.appendChild(btnDelete);
      li.appendChild(nameSpan);
      li.appendChild(actions);
      $novelList.appendChild(li);
    });
  }

  async function deleteNovel(name) {
    if (!confirm(`确定要删除「${name}」及其所有数据吗？此操作不可撤销。`)) return;
    try {
      const res = await fetch(`${API}/api/novels/${encodeURIComponent(name)}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok || !data.success) {
        alert("删除失败：" + (data.error || data.message || "未知错误"));
        return;
      }
      if (currentNovel === name) {
        currentNovel = null;
        $workspace.classList.add("hidden");
        $freeChat.classList.add("hidden");
        $welcome.classList.remove("hidden");
        closeAllPanels();
      }
      loadNovels();
    } catch (err) {
      alert("删除请求失败：" + err.message);
    }
  }

  async function renameNovel(name) {
    const newName = prompt(`请输入「${name}」的新名称：`, name);
    if (!newName || newName.trim() === "" || newName.trim() === name) return;
    try {
      const resp = await fetch(`${API}/api/novels/${encodeURIComponent(name)}/rename`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_name: newName.trim() }),
      });
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data.success) {
        if (currentNovel === name) {
          currentNovel = newName.trim();
          $novelTitle.textContent = currentNovel;
        }
        loadNovels();
      } else {
        alert("重命名失败，可能目标名称已存在");
      }
    } catch (err) {
      alert("重命名请求失败：" + err.message);
    }
  }

  let _progressPollTimer = null;

  function selectNovel(name) {
    currentNovel = name;
    $welcome.classList.add("hidden");
    $freeChat.classList.add("hidden");
    $workspace.classList.remove("hidden");
    $novelTitle.textContent = name;
    $messagesWrite.innerHTML = "";
    $messagesAsk.innerHTML = "";
    document.getElementById("mode-toggle").classList.remove("hidden");
    $btnDeleteLast.classList.remove("hidden");
    closeAllPanels();
    loadNovels();
    resetMemoryUI();
    loadMemoryData(name);
    checkMemoryUpdateStatus(name);
  }

  function resetMemoryUI() {
    stopProgressPolling();
    const $progress = document.getElementById("memory-progress");
    const $btnUpdate = document.getElementById("btn-update-memory");
    const $btnStop = document.getElementById("btn-stop-memory");
    $progress.classList.add("hidden");
    $progress.textContent = "";
    $btnUpdate.disabled = false;
    $btnStop.classList.add("hidden");
    $btnStop.disabled = false;
    $btnStop.textContent = "停止更新";
    memoryUpdateReader = null;
  }

  async function checkMemoryUpdateStatus(novelName) {
    try {
      const res = await fetch(`${API}/api/memory/${encodeURIComponent(novelName)}/update-status`);
      const data = await res.json();
      if (data.running) {
        $memoryPanel.classList.remove("hidden");
        const $progress = document.getElementById("memory-progress");
        const $btnUpdate = document.getElementById("btn-update-memory");
        const $btnStop = document.getElementById("btn-stop-memory");
        $progress.classList.remove("hidden");
        $progress.textContent = "记忆更新进行中：" + (data.message || "") + "\n";
        $btnUpdate.disabled = true;
        $btnStop.classList.remove("hidden");
        startProgressPolling(novelName);
      }
    } catch (_) {}
  }

  async function loadMemoryData(novelName) {
    try {
      const res = await fetch(`${API}/api/memory/${encodeURIComponent(novelName)}`);
      const data = await res.json();
      document.getElementById("memory-worldview").textContent = data.worldview || "（空）";
      document.getElementById("memory-timeline").textContent =
        data.timeline.length
          ? data.timeline.map(e => {
              let s = `【${e.chapter}】`;
              if (e.entities && e.entities.length) s += ` [${e.entities.join(", ")}]`;
              s += `\n${e.content}`;
              return s;
            }).join("\n\n")
          : "（空）";
      const summary = data.recent_summary;
      let summaryText = "";
      if (summary.recent_summary) summaryText += "【近章总结】\n" + summary.recent_summary + "\n\n";
      if (summary.recent_3_chapters && summary.recent_3_chapters.length) {
        summaryText += `【最近3章原文】共 ${summary.recent_3_chapters.length} 章`;
      }
      document.getElementById("memory-summary").textContent = summaryText || "（空）";

      let epText = "";
      if (data.entity_profiles && Object.keys(data.entity_profiles).length > 0) {
        for (const [name, info] of Object.entries(data.entity_profiles)) {
          epText += `【${name}】\n描述：${info.description || "无"}\n当前状态：${info.current_status || "无"}\n最后更新：第 ${(info.last_updated_chapter || 0) + 1} 章\n\n`;
        }
      }
      const $epNode = document.getElementById("memory-entity-profiles");
      if ($epNode) $epNode.textContent = epText.trim() || "（空）";

      const $sgNode = document.getElementById("memory-style-guidelines");
      if ($sgNode) $sgNode.textContent = data.style_guidelines || "（空）";
    } catch (_) {}
  }

  function startProgressPolling(novelName) {
    stopProgressPolling();
    _progressPollTimer = setInterval(async () => {
      if (currentNovel !== novelName) { stopProgressPolling(); return; }
      try {
        const res = await fetch(`${API}/api/memory/${encodeURIComponent(novelName)}/update-status`);
        const data = await res.json();
        const $progress = document.getElementById("memory-progress");
        if (data.running) {
          $progress.textContent = "记忆更新进行中：" + (data.message || "") + "\n";
          $progress.scrollTop = $progress.scrollHeight;
        } else {
          $progress.textContent += (data.message || "更新已结束") + "\n";
          stopProgressPolling();
          document.getElementById("btn-update-memory").disabled = false;
          document.getElementById("btn-stop-memory").classList.add("hidden");
          refreshMemoryPanel();
        }
      } catch (_) { stopProgressPolling(); }
    }, 2000);
  }

  function stopProgressPolling() {
    if (_progressPollTimer) {
      clearInterval(_progressPollTimer);
      _progressPollTimer = null;
    }
  }

  function enterFreeChat() {
    stopProgressPolling();
    currentNovel = null;
    $welcome.classList.add("hidden");
    $workspace.classList.add("hidden");
    $freeChat.classList.remove("hidden");
    document.getElementById("free-messages").innerHTML = "";
    loadNovels();
  }

  // ========== Create Novel ==========
  document.getElementById("btn-new-novel").addEventListener("click", () => {
    $modalOverlay.classList.remove("hidden");
    $novelNameInput.value = "";
    $novelNameInput.focus();
  });

  document.getElementById("modal-cancel").addEventListener("click", () => {
    $modalOverlay.classList.add("hidden");
  });

  document.getElementById("modal-confirm").addEventListener("click", async () => {
    const name = $novelNameInput.value.trim();
    if (!name) return;
    await fetch(`${API}/api/novels`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    $modalOverlay.classList.add("hidden");
    await loadNovels();
    selectNovel(name);
  });

  // ========== Upload Novel ==========
  document.getElementById("btn-upload").addEventListener("click", () => {
    $fileInput.click();
  });

  $fileInput.addEventListener("change", async () => {
    const file = $fileInput.files[0];
    if (!file) return;
    const name = file.name.replace(/\.(json|txt)$/i, "");
    const isTxt = /\.txt$/i.test(file.name);

    const form = new FormData();
    form.append("name", name);
    form.append("file", file);

    const uploadBtn = document.getElementById("btn-upload");
    const origText = uploadBtn.textContent;
    if (isTxt) uploadBtn.textContent = "解析章节中...";
    uploadBtn.disabled = true;

    try {
      const resp = await fetch(`${API}/api/novels/upload`, { method: "POST", body: form });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        alert("上传失败：" + (err.detail || err.message || resp.statusText));
        return;
      }
    } catch (err) {
      alert("上传请求失败：" + err.message);
      return;
    } finally {
      uploadBtn.textContent = origText;
      uploadBtn.disabled = false;
    }

    $fileInput.value = "";
    await loadNovels();
    selectNovel(name);
  });

  // ========== Free Chat Button ==========
  document.getElementById("btn-free-chat").addEventListener("click", enterFreeChat);

  // ========== Mode Toggle ==========
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      chatMode = btn.dataset.mode;
      $input.placeholder =
        chatMode === "write" ? "输入续写指令..." : "输入你的问题...";
      
      if (chatMode === "write") {
        $messagesWrite.classList.remove("hidden");
        $messagesAsk.classList.add("hidden");
      } else {
        $messagesWrite.classList.add("hidden");
        $messagesAsk.classList.remove("hidden");
      }
      scrollToBottom(chatMode === "write" ? $messagesWrite : $messagesAsk);
    });
  });

  // ========== Chat Helpers ==========
  function addMessage(role, html, container) {
    const target = container || (chatMode === "write" ? $messagesWrite : $messagesAsk);
    const div = document.createElement("div");
    div.className = `message ${role}`;
    div.innerHTML = `<div class="bubble">${html}</div>`;
    target.appendChild(div);
    scrollToBottom(target);
    return div.querySelector(".bubble");
  }

  function addAgentCard(agent, message, detail) {
    const info = AGENT_LABELS[agent] || AGENT_LABELS.system;
    const card = document.createElement("div");
    card.className = `agent-card ${agent}`;
    card.dataset.agent = agent;

    let html = `<div class="agent-label">${info.icon} ${info.name} <span class="spinner"></span></div>`;
    html += `<div class="agent-content">${escapeHtml(message)}</div>`;

    if (detail) {
      const id = "detail-" + Math.random().toString(36).slice(2, 8);
      html += `<div class="agent-toggle" data-target="${id}">▶ 展开详情</div>`;
      html += `<div class="agent-detail" id="${id}">${escapeHtml(detail)}</div>`;
    }

    card.innerHTML = html;
    const target = chatMode === "write" ? $messagesWrite : $messagesAsk;
    target.appendChild(card);
    scrollToBottom(target);

    const toggle = card.querySelector(".agent-toggle");
    if (toggle) {
      toggle.addEventListener("click", () => {
        const detailEl = card.querySelector(".agent-detail");
        const isOpen = detailEl.classList.toggle("open");
        toggle.textContent = isOpen ? "▼ 收起详情" : "▶ 展开详情";
      });
    }

    return card;
  }

  function finalizeAgentCard(card, message, detail, extraClass) {
    if (!card) return;
    const spinner = card.querySelector(".spinner");
    if (spinner) spinner.remove();

    if (message) {
      card.querySelector(".agent-content").textContent = message;
    }
    if (extraClass) {
      card.classList.add(extraClass);
    }
    if (detail && !card.querySelector(".agent-detail")) {
      const id = "detail-" + Math.random().toString(36).slice(2, 8);
      const toggleHtml = `<div class="agent-toggle" data-target="${id}">▶ 展开详情</div>`;
      const detailHtml = `<div class="agent-detail" id="${id}">${escapeHtml(detail)}</div>`;
      card.insertAdjacentHTML("beforeend", toggleHtml + detailHtml);
      card.querySelector(".agent-toggle").addEventListener("click", () => {
        const detailEl = card.querySelector(".agent-detail");
        const isOpen = detailEl.classList.toggle("open");
        card.querySelector(".agent-toggle").textContent = isOpen ? "▼ 收起详情" : "▶ 展开详情";
      });
    } else if (detail) {
      card.querySelector(".agent-detail").textContent = detail;
    }
    scrollToBottom();
  }

  function scrollToBottom(container) {
    const area = container ? container.closest(".chat-area-inner") || container.parentElement : document.getElementById("chat-area");
    if (area) area.scrollTop = area.scrollHeight;
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function renderMarkdown(text) {
    let html = escapeHtml(text);
    html = html.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    html = html.replace(/^### (.+)$/gm, "<h4>$1</h4>");
    html = html.replace(/^## (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^# (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
      // brief visual feedback handled by caller
    }).catch(() => {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    });
  }

  // ========== Novel Chat ==========
  $btnSend.addEventListener("click", sendMessage);
  $input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  async function sendMessage() {
    if (sending || !currentNovel) return;
    const content = $input.value.trim();
    if (!content) return;

    sending = true;
    $btnSend.disabled = true;
    $input.value = "";

    addMessage("user", escapeHtml(content));

    const endpoint = chatMode === "write" ? "/api/chat/write" : "/api/chat/ask";
    let currentAgentCard = null;
    let writeBubble = null;
    let fullText = "";

    if (chatMode === "ask") {
      writeBubble = addMessage("assistant", '<span class="typing">思考中...</span>');
    }

    try {
      const resp = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ novel_name: currentNovel, content }),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        const errBubble = writeBubble || addMessage("assistant", "");
        errBubble.innerHTML = `<span style="color:var(--danger)">服务器错误 (${resp.status})：${escapeHtml(errText)}</span>`;
        sending = false;
        $btnSend.disabled = false;
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));

            if (evt.type === "agent_start") {
              console.log("[SSE] agent_start", evt.agent);
              if (currentAgentCard) {
                finalizeAgentCard(currentAgentCard);
              }
              currentAgentCard = addAgentCard(evt.agent, evt.message);
              // Clear detail text buffer for the new agent
              currentAgentCard.dataset.detailText = "";
              
              if (evt.agent === "writer") {
                fullText = "";
                if (!writeBubble) {
                  writeBubble = addMessage("assistant", '<span class="typing">创作中...</span>');
                }
              }
            } else if (evt.type === "agent_token") {
              if (currentAgentCard) {
                currentAgentCard.dataset.detailText = (currentAgentCard.dataset.detailText || "") + (evt.content || "");
                // Ensure detail block exists
                let detailEl = currentAgentCard.querySelector(".agent-detail");
                if (!detailEl) {
                  const id = "detail-" + Math.random().toString(36).slice(2, 8);
                  const toggleHtml = `<div class="agent-toggle open" data-target="${id}">▼ 收起详情</div>`;
                  const detailHtml = `<div class="agent-detail open" id="${id}"></div>`;
                  currentAgentCard.insertAdjacentHTML("beforeend", toggleHtml + detailHtml);
                  detailEl = currentAgentCard.querySelector(".agent-detail");
                  currentAgentCard.querySelector(".agent-toggle").addEventListener("click", function() {
                    const isOpen = detailEl.classList.toggle("open");
                    this.textContent = isOpen ? "▼ 收起详情" : "▶ 展开详情";
                  });
                }
                detailEl.innerHTML = renderMarkdown(currentAgentCard.dataset.detailText);
                scrollToBottom();
              }
            } else if (evt.type === "agent_done") {
              console.log("[SSE] agent_done", evt.agent);
              if (currentAgentCard) {
                let extra = null;
                if (evt.agent === "critic" && evt.accepted) extra = "passed";
                // If the backend provided final content, use it. Otherwise use what we accumulated.
                const finalContent = evt.content !== undefined ? evt.content : currentAgentCard.dataset.detailText;
                finalizeAgentCard(currentAgentCard, evt.message, finalContent, extra);
                currentAgentCard = null;
              }
            } else if (evt.type === "agent_info" || evt.type === "info") {
              console.log("[SSE] info", evt.message);
              addAgentCard(evt.agent || "system", evt.message);
              const target = chatMode === "write" ? $messagesWrite : $messagesAsk;
              const card = target.lastElementChild;
              const spinner = card.querySelector(".spinner");
              if (spinner) spinner.remove();
              if (evt.content) {
                  finalizeAgentCard(card, evt.message, evt.content);
              }
            } else if (evt.type === "token") {
              if (!writeBubble) {
                fullText = "";
                writeBubble = addMessage("assistant", '<span class="typing">创作中...</span>');
              }
              fullText += evt.content;
              writeBubble.innerHTML = renderMarkdown(fullText);
              scrollToBottom();
            } else if (evt.type === "done") {
              console.log("[SSE] done");
              if (currentAgentCard) {
                finalizeAgentCard(currentAgentCard);
                currentAgentCard = null;
              }
              if (evt.chapter_title) {
                if (!writeBubble) {
                  fullText = "";
                  writeBubble = addMessage("assistant", "");
                }
                let suffix = `\n\n---\n*已保存为 ${evt.chapter_title}`;
                if (evt.rounds) suffix += `（共 ${evt.rounds} 轮审核）`;
                suffix += `*`;
                fullText += suffix;
                writeBubble.innerHTML = renderMarkdown(fullText);
              }
              loadNovels();
            } else if (evt.type === "error") {
              const errBubble = writeBubble || addMessage("assistant", "");
              errBubble.innerHTML = `<span style="color:var(--danger)">错误：${escapeHtml(evt.message)}</span>`;
            }
          } catch (_) {}
        }
      }
    } catch (err) {
      const errBubble = writeBubble || addMessage("assistant", "");
      errBubble.innerHTML = `<span style="color:var(--danger)">请求失败：${escapeHtml(err.message)}</span>`;
    }

    sending = false;
    $btnSend.disabled = false;
  }

  // ========== Free Chat (with context) ==========
  const $freeSend = document.getElementById("btn-free-send");
  const $freeClear = document.getElementById("btn-free-clear");
  const $freeInput = document.getElementById("free-input");
  const $freeMessages = document.getElementById("free-messages");
  let freeChatHistory = [];

  if ($freeSend) {
    $freeSend.addEventListener("click", sendFreeMessage);
    $freeInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendFreeMessage();
      }
    });
  }

  if ($freeClear) {
    $freeClear.addEventListener("click", () => {
      freeChatHistory = [];
      $freeMessages.innerHTML = "";
    });
  }

  async function sendFreeMessage() {
    if (sending) return;
    const content = $freeInput.value.trim();
    if (!content) return;

    sending = true;
    $freeSend.disabled = true;
    $freeInput.value = "";

    freeChatHistory.push({ role: "user", content });
    addMessage("user", escapeHtml(content), $freeMessages);
    const bubble = addMessage("assistant", '<span class="typing">思考中...</span>', $freeMessages);
    let fullText = "";

    try {
      const resp = await fetch(`${API}/api/chat/free`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: freeChatHistory.slice(-20) }),
      });

      if (!resp.ok) {
        bubble.innerHTML = `<span style="color:var(--danger)">服务器错误 (${resp.status})</span>`;
        sending = false;
        $freeSend.disabled = false;
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "token") {
              fullText += evt.content;
              bubble.innerHTML = renderMarkdown(fullText);
              const area = document.getElementById("free-chat-area");
              if (area) area.scrollTop = area.scrollHeight;
            } else if (evt.type === "error") {
              bubble.innerHTML = `<span style="color:var(--danger)">错误：${escapeHtml(evt.message)}</span>`;
            }
          } catch (_) {}
        }
      }
      if (fullText) {
        freeChatHistory.push({ role: "assistant", content: fullText });
      }
    } catch (err) {
      bubble.innerHTML = `<span style="color:var(--danger)">请求失败：${escapeHtml(err.message)}</span>`;
    }

    sending = false;
    $freeSend.disabled = false;
  }

  // ========== Delete Last Chapter ==========
  $btnDeleteLast.addEventListener("click", async () => {
    if (!currentNovel) return;
    if (!confirm("确定要删除最近一章吗？此操作会同步回滚对应的世界观/时间线/实体索引/摘要。")) return;
    const res = await fetch(`${API}/api/chat/${encodeURIComponent(currentNovel)}/last`, {
      method: "DELETE",
    });
    const data = await res.json();
    if (data.success) {
      addMessage("assistant", '<em style="color:var(--text-secondary)">已删除最近一章（记忆已同步回滚）</em>');
      loadNovels();
      refreshMemoryPanel();
    } else {
      alert("删除失败：" + (data.error || data.message || "可能没有可删除的章节"));
    }
  });

  // ========== Panels ==========
  function closeAllPanels() {
    $memoryPanel.classList.add("hidden");
    $chaptersPanel.classList.add("hidden");
  }

  document.querySelectorAll(".panel-close").forEach((btn) => {
    btn.addEventListener("click", closeAllPanels);
  });

  // Memory Panel
  document.getElementById("btn-memory").addEventListener("click", async () => {
    if (!currentNovel) return;
    closeAllPanels();
    $memoryPanel.classList.remove("hidden");
    await loadMemoryData(currentNovel);
    checkMemoryUpdateStatus(currentNovel);
  });

  // Update Memory (with stop support)
  let memoryUpdateReader = null;

  document.getElementById("btn-update-memory").addEventListener("click", async () => {
    if (!currentNovel) return;
    
    // 先检查是否已经在运行
    try {
      const statusRes = await fetch(`${API}/api/memory/${encodeURIComponent(currentNovel)}/update-status`);
      const statusData = await statusRes.json();
      if (statusData.running) {
        alert("该小说已有更新任务在运行，请等待完成或停止后再试");
        checkMemoryUpdateStatus(currentNovel);
        return;
      }
    } catch (_) {}
    
    // 弹出选项让用户选择重构方式
    const rebuildTarget = prompt("请选择更新内容：\n1. 全量更新 (默认)\n2. 仅更新世界观\n3. 仅更新时间线", "1");
    if (rebuildTarget === null) return; // 用户取消
    
    let targetParam = "all";
    if (rebuildTarget === "2") targetParam = "worldview";
    else if (rebuildTarget === "3") targetParam = "timeline";
    
    let startChapterParam = -1;
    const startChapterStr = prompt("请输入从第几章开始重构（输入数字，例如 1 表示从第1章开始，留空或输入负数表示从最新未处理章节继续）：", "");
    if (startChapterStr !== null && startChapterStr.trim() !== "") {
        const parsed = parseInt(startChapterStr.trim(), 10);
        if (!isNaN(parsed) && parsed > 0) {
            startChapterParam = parsed - 1; // 转换为 0-based index
        }
    }

    const $btnUpdate = document.getElementById("btn-update-memory");
    const $btnStop = document.getElementById("btn-stop-memory");
    const $progress = document.getElementById("memory-progress");
    $btnUpdate.disabled = true;
    $btnStop.classList.remove("hidden");
    $progress.classList.remove("hidden");
    $progress.textContent = "开始更新...\n";

    try {
      const resp = await fetch(`${API}/api/memory/${encodeURIComponent(currentNovel)}/update?start_chapter=${startChapterParam}&rebuild_target=${targetParam}`, {
        method: "POST",
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({ error: resp.statusText }));
        $progress.textContent += "错误：" + (errData.error || `服务器错误 ${resp.status}`) + "\n";
        $btnUpdate.disabled = false;
        $btnStop.classList.add("hidden");
        return;
      }
      memoryUpdateReader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await memoryUpdateReader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "worldview_updated") {
              document.getElementById("memory-worldview").textContent = evt.content || "（空）";
            } else if (evt.type === "timeline_updated") {
              const tl = evt.timeline || [];
              document.getElementById("memory-timeline").textContent =
                tl.length
                  ? tl.map(e => {
                      let s = `【${e.chapter}】`;
                      if (e.entities && e.entities.length) s += ` [${e.entities.join(", ")}]`;
                      s += `\n${e.content}`;
                      return s;
                    }).join("\n\n")
                  : "（空）";
            } else if (evt.type === "progress") {
              $progress.textContent += evt.message + "\n";
              $progress.scrollTop = $progress.scrollHeight;
            } else if (evt.type === "done") {
              $progress.textContent += "全部更新完成！\n";
              $progress.scrollTop = $progress.scrollHeight;
            } else if (evt.type === "stopped") {
              $progress.textContent += "已停止，进度已保存，下次可继续\n";
              $progress.scrollTop = $progress.scrollHeight;
            } else if (evt.type === "error") {
              $progress.textContent += "错误：" + evt.message + "\n";
              $progress.scrollTop = $progress.scrollHeight;
            }
          } catch (_) {}
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        $progress.textContent += "请求失败：" + err.message + "\n";
        $progress.scrollTop = $progress.scrollHeight;
      }
    }

    memoryUpdateReader = null;
    
    // 如果是因为网络错误断开，尝试通过状态接口确认后端是否真的停了
    try {
      const statusRes = await fetch(`${API}/api/memory/${encodeURIComponent(currentNovel)}/update-status`);
      const statusData = await statusRes.json();
      if (statusData.running) {
        $progress.textContent += "注意：前端连接已断开，但后端任务可能仍在运行。请稍后刷新状态或点击停止。\n";
        $progress.scrollTop = $progress.scrollHeight;
        checkMemoryUpdateStatus(currentNovel);
        return;
      }
    } catch (_) {}

    $btnUpdate.disabled = false;
    $btnStop.classList.add("hidden");
    refreshMemoryPanel();
  });

  document.getElementById("btn-stop-memory").addEventListener("click", async () => {
    const novelToCancel = currentNovel;
    if (!novelToCancel) return;
    const $btnStop = document.getElementById("btn-stop-memory");
    $btnStop.disabled = true;
    $btnStop.textContent = "正在停止...";

    try {
      await fetch(`${API}/api/memory/${encodeURIComponent(novelToCancel)}/cancel`, {
        method: "POST",
      });
    } catch (_) {}

    if (memoryUpdateReader) {
      try { memoryUpdateReader.cancel(); } catch (_) {}
    }

    // 增加一个轮询，确保后端真正停止并释放锁后，再恢复按钮状态
    const checkInterval = setInterval(async () => {
      try {
        const res = await fetch(`${API}/api/memory/${encodeURIComponent(novelToCancel)}/update-status`);
        const data = await res.json();
        if (!data.running) {
          clearInterval(checkInterval);
          $btnStop.disabled = false;
          $btnStop.textContent = "停止更新";
          $btnStop.classList.add("hidden");
          document.getElementById("btn-update-memory").disabled = false;
          refreshMemoryPanel();
        }
      } catch (_) {
        clearInterval(checkInterval);
      }
    }, 2000);
  });

  async function refreshMemoryPanel() {
    if (!currentNovel) return;
    await loadMemoryData(currentNovel);
  }

  // ========== Chapters Panel (with copy) ==========
  document.getElementById("btn-chapters").addEventListener("click", async () => {
    if (!currentNovel) return;
    closeAllPanels();
    $chaptersPanel.classList.remove("hidden");

    const res = await fetch(`${API}/api/novels/${encodeURIComponent(currentNovel)}/chapters`);
    const chapters = await res.json();
    const $list = document.getElementById("chapters-list");
    $list.innerHTML = "";

    if (!chapters.length) {
      $list.innerHTML = '<p style="color:var(--text-secondary);padding:12px;">暂无章节</p>';
      return;
    }

    chapters.forEach((ch, i) => {
      const div = document.createElement("div");
      div.className = "chapter-item";

      const header = document.createElement("div");
      header.className = "chapter-header";

      const titleEl = document.createElement("div");
      titleEl.className = "chapter-title";
      titleEl.textContent = ch.title || `第${i + 1}章`;

      const copyBtn = document.createElement("button");
      copyBtn.className = "chapter-copy-btn";
      copyBtn.textContent = "复制";
      copyBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        let copyText = ch.text || "";
        if (ch.prompt) copyText = `【用户指令】${ch.prompt}\n\n${copyText}`;
        copyToClipboard(copyText);
        copyBtn.textContent = "已复制";
        setTimeout(() => { copyBtn.textContent = "复制"; }, 1500);
      });

      header.appendChild(titleEl);
      header.appendChild(copyBtn);

      const preview = document.createElement("div");
      preview.className = "chapter-preview";
      preview.textContent = (ch.text || "").slice(0, 120);

      div.appendChild(header);
      div.appendChild(preview);

      div.addEventListener("click", () => {
        let content = `### ${ch.title}\n\n`;
        if (ch.prompt) content += `> **用户指令：** ${ch.prompt}\n\n`;
        content += ch.text;
        addMessage("assistant", renderMarkdown(content));
        closeAllPanels();
      });

      $list.appendChild(div);
    });
  });

  // ========== Mobile sidebar toggle ==========
  document.addEventListener("click", (e) => {
    const sidebar = document.getElementById("sidebar");
    if (window.innerWidth <= 768) {
      if (e.target.closest("#sidebar")) return;
      sidebar.classList.remove("open");
    }
  });

  if (window.innerWidth <= 768) {
    const hamburger = document.createElement("button");
    hamburger.textContent = "\u2630";
    hamburger.style.cssText =
      "position:fixed;top:8px;left:8px;z-index:60;background:var(--accent);color:#fff;border:none;border-radius:6px;padding:6px 10px;font-size:18px;cursor:pointer;";
    hamburger.addEventListener("click", (e) => {
      e.stopPropagation();
      document.getElementById("sidebar").classList.toggle("open");
    });
    document.body.appendChild(hamburger);
  }

  // ========== Init ==========
  loadNovels();
})();
