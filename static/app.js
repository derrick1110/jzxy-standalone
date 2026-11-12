const state = {
  busy: false,
};

const welcomeState = document.getElementById("welcome-state");
const messageList = document.getElementById("message-list");
const chatScroll = document.getElementById("chat-scroll");
const chatForm = document.getElementById("chat-form");
const questionInput = document.getElementById("question-input");
const sendButton = document.getElementById("send-button");
const resetButton = document.getElementById("reset-button");
const newsCount = document.getElementById("news-count");
const newsCountTop = document.getElementById("news-count-top");
const latestDate = document.getElementById("latest-date");

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function renderMarkdown(text) {
  const blocks = text.trim().split(/\n{2,}/);
  return blocks
    .map((block) => {
      const lines = block.split("\n");
      const isList = lines.every((line) => /^\s*[-*]\s+/.test(line));
      if (isList) {
        const items = lines
          .map((line) => `<li>${inlineMarkdown(line.replace(/^\s*[-*]\s+/, ""))}</li>`)
          .join("");
        return `<ul>${items}</ul>`;
      }
      return `<p>${inlineMarkdown(block).replaceAll("\n", "<br>")}</p>`;
    })
    .join("");
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    chatScroll.scrollTop = chatScroll.scrollHeight;
  });
}

function createMessageElement(role, content, options = {}) {
  const message = document.createElement("div");
  message.className = `message ${role}${options.error ? " error" : ""}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = role === "user" ? "我" : "AI";

  const main = document.createElement("div");
  main.className = "message-main";

  const label = document.createElement("p");
  label.className = "message-label";
  label.textContent = role === "user" ? "你" : "荆院资讯助手";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.innerHTML = renderMarkdown(content);

  main.append(label, bubble);

  if (role === "assistant" && !options.error && !options.loading) {
    const footnote = document.createElement("div");
    footnote.className = "message-footnote";
    const sourceCount = Array.isArray(options.sources) ? options.sources.length : 0;
    const toolText = options.toolUsed
      ? `已检索本地公开新闻库${sourceCount ? ` · ${sourceCount} 条来源` : ""}`
      : "基于对话回答";
    footnote.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 5 6v5c0 4.6 2.8 8.1 7 10 4.2-1.9 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-4"/></svg>';
    const footnoteText = document.createElement("span");
    footnoteText.textContent = toolText;
    footnote.appendChild(footnoteText);
    main.appendChild(footnote);
  }

  if (Array.isArray(options.sources) && options.sources.length) {
    main.appendChild(createSources(options.sources));
  }

  message.append(avatar, main);
  return message;
}

function createSources(sources) {
  const wrap = document.createElement("div");
  wrap.className = "sources";

  sources.forEach((source) => {
    const card = document.createElement("a");
    card.className = "source-card";
    card.href = source.url || "#";
    card.target = "_blank";
    card.rel = "noopener noreferrer";

    const top = document.createElement("div");
    top.className = "source-top";
    const label = document.createElement("span");
    label.className = "source-label";
    label.textContent = "荆州学院官网";
    const date = document.createElement("span");
    date.className = "source-date";
    date.textContent = source.publish_date || "";
    top.append(label, date);

    const title = document.createElement("h3");
    title.className = "source-title";
    title.textContent = source.title || "未命名新闻";

    const summary = document.createElement("p");
    summary.className = "source-summary";
    summary.textContent = source.summary || "";

    const open = document.createElement("span");
    open.className = "source-open";
    open.textContent = "查看官网原文 ↗";
    card.append(top, title, summary, open);
    wrap.appendChild(card);
  });

  return wrap;
}

function appendMessage(role, content, options = {}) {
  const element = createMessageElement(role, content, options);
  messageList.appendChild(element);
  scrollToBottom();
  return element;
}

function appendTyping() {
  const element = createMessageElement("assistant", "", { loading: true });
  const bubble = element.querySelector(".message-bubble");
  bubble.classList.add("typing-bubble");
  bubble.innerHTML =
    '<span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span><span>正在检索公开资讯…</span>';
  messageList.appendChild(element);
  scrollToBottom();
  return element;
}

function setBusy(value) {
  state.busy = value;
  sendButton.disabled = value;
  questionInput.disabled = value;
}

function resizeInput() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 120)}px`;
}

async function sendQuestion(rawQuestion) {
  const question = rawQuestion.trim();
  if (!question || state.busy) {
    return;
  }

  if (welcomeState) {
    welcomeState.classList.add("hidden");
  }

  appendMessage("user", question);
  questionInput.value = "";
  resizeInput();
  setBusy(true);
  const typing = appendTyping();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || data.detail || "请求失败，请稍后重试。");
    }

    typing.remove();
    appendMessage("assistant", data.reply, {
      sources: data.sources || [],
      toolUsed: Boolean(data.tool_used),
    });
  } catch (error) {
    typing.remove();
    appendMessage("assistant", error.message || "网络连接失败，请稍后重试。", {
      error: true,
    });
  } finally {
    setBusy(false);
    questionInput.focus();
  }
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendQuestion(questionInput.value);
});

questionInput.addEventListener("input", resizeInput);
questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendQuestion(questionInput.value);
  }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    sendQuestion(button.dataset.prompt || "");
  });
});

resetButton.addEventListener("click", () => {
  if (state.busy) {
    return;
  }
  messageList.replaceChildren();
  if (welcomeState) {
    welcomeState.classList.remove("hidden");
  }
  questionInput.value = "";
  resizeInput();
  questionInput.focus();
});

async function loadMeta() {
  try {
    const response = await fetch("/api/meta");
    if (!response.ok) {
      return;
    }
    const meta = await response.json();
    if (newsCount) {
      newsCount.textContent = String(meta.count ?? "--");
    }
    if (newsCountTop) {
      newsCountTop.textContent = `本地资讯 ${meta.count ?? "--"} 条`;
    }
    if (latestDate) {
      latestDate.textContent = meta.latest_date || "--";
    }
  } catch {
    // 页面仍可使用静态内容，API 请求时会给出明确错误。
  }
}

loadMeta();
resizeInput();
