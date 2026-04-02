function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function sanitizeUrl(value) {
  const candidate = String(value ?? "").trim();
  if (!candidate) {
    return "";
  }

  if (/^(https?:\/\/|mailto:|\/|#)/i.test(candidate)) {
    return candidate;
  }

  return "";
}

function renderInlineMarkdown(value) {
  let text = String(value ?? "");
  const codeTokens = [];

  text = text.replace(/`([^`\n]+)`/g, (_match, code) => {
    const index = codeTokens.length;
    codeTokens.push(`<code>${code}</code>`);
    return `@@INLINE_CODE_${index}@@`;
  });

  text = text.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label, url) => {
    const safeUrl = sanitizeUrl(url);
    if (!safeUrl) {
      return label;
    }

    return `<a href="${escapeAttribute(safeUrl)}" target="_blank" rel="noreferrer noopener">${label}</a>`;
  });

  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/__(.+?)__/g, "<strong>$1</strong>");
  text = text.replace(/(^|[\s(])\*([^*\n][^*]*?)\*(?=$|[\s).,!?:;])/gm, "$1<em>$2</em>");
  text = text.replace(/(^|[\s(])_([^_\n][^_]*?)_(?=$|[\s).,!?:;])/gm, "$1<em>$2</em>");
  text = text.replace(/~~(.+?)~~/g, "<del>$1</del>");

  return text.replace(/@@INLINE_CODE_(\d+)@@/g, (_match, index) => codeTokens[Number(index)] || "");
}

function renderMarkdown(value) {
  const normalized = String(value ?? "").replace(/\r\n?/g, "\n").trim();
  if (!normalized) {
    return "";
  }

  const codeBlocks = [];
  let text = escapeHtml(normalized).replace(/```([\w-]+)?\n([\s\S]*?)```/g, (_match, language, code) => {
    const index = codeBlocks.length;
    const languageClass = language ? ` class="language-${escapeAttribute(language)}"` : "";
    codeBlocks.push(`<pre><code${languageClass}>${code}</code></pre>`);
    return `@@CODE_BLOCK_${index}@@`;
  });

  const lines = text.split("\n");
  const blocks = [];
  let index = 0;

  function isCodeBlockToken(line) {
    return /^@@CODE_BLOCK_\d+@@$/.test(line);
  }

  function isListItem(line) {
    return /^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line);
  }

  function isBlockQuote(line) {
    return /^&gt;\s?/.test(line);
  }

  function isBlockStart(line) {
    return (
      /^#{1,6}\s+/.test(line) ||
      isBlockQuote(line) ||
      isListItem(line) ||
      isCodeBlockToken(line)
    );
  }

  while (index < lines.length) {
    const current = lines[index].trim();

    if (!current) {
      index += 1;
      continue;
    }

    if (isCodeBlockToken(current)) {
      blocks.push(current);
      index += 1;
      continue;
    }

    const headingMatch = current.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      blocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (isBlockQuote(current)) {
      const quoteLines = [];
      while (index < lines.length) {
        const quoted = lines[index].trim();
        if (!isBlockQuote(quoted)) {
          break;
        }
        quoteLines.push(quoted.replace(/^&gt;\s?/, ""));
        index += 1;
      }

      const quoteMarkup = quoteLines
        .filter(Boolean)
        .map((line) => `<p>${renderInlineMarkdown(line)}</p>`)
        .join("");

      blocks.push(`<blockquote>${quoteMarkup}</blockquote>`);
      continue;
    }

    if (isListItem(current)) {
      const ordered = /^\d+\.\s+/.test(current);
      const items = [];

      while (index < lines.length) {
        const candidate = lines[index].trim();
        if (!(ordered ? /^\d+\.\s+/.test(candidate) : /^[-*]\s+/.test(candidate))) {
          break;
        }

        items.push(
          ordered
            ? candidate.replace(/^\d+\.\s+/, "")
            : candidate.replace(/^[-*]\s+/, "")
        );
        index += 1;
      }

      const tagName = ordered ? "ol" : "ul";
      blocks.push(
        `<${tagName}>${items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</${tagName}>`
      );
      continue;
    }

    const paragraphLines = [current];
    index += 1;

    while (index < lines.length) {
      const candidate = lines[index].trim();
      if (!candidate || isBlockStart(candidate)) {
        break;
      }
      paragraphLines.push(candidate);
      index += 1;
    }

    blocks.push(`<p>${paragraphLines.map((line) => renderInlineMarkdown(line)).join("<br>")}</p>`);
  }

  return blocks.join("\n").replace(/@@CODE_BLOCK_(\d+)@@/g, (_match, blockIndex) => {
    return codeBlocks[Number(blockIndex)] || "";
  });
}

function renderBubbleContent(role, message) {
  if (role === "bot") {
    return `<div class="markdown-body">${renderMarkdown(message)}</div>`;
  }

  return `<div class="text-body">${escapeHtml(message).replace(/\n/g, "<br>")}</div>`;
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let index = 0;

  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }

  return `${size.toFixed(size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDateTime(value) {
  if (!value) {
    return "Chưa có";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }

  return parsed.toLocaleString("vi-VN");
}

async function readResponsePayload(response) {
  const contentType = response.headers.get("content-type") || "";
  let payload = {};

  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    payload = { error: await response.text() };
  }

  if (payload && typeof payload === "object" && payload.detail && !payload.error) {
    if (Array.isArray(payload.detail)) {
      payload.error = payload.detail
        .map((item) => item.msg || item.message || JSON.stringify(item))
        .join("; ");
    } else {
      payload.error = payload.detail;
    }
  }

  return payload;
}

function setStatusMessage(targetId, type, message, extraLines = []) {
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }

  target.innerHTML = `
    <div class="status-panel ${escapeHtml(type)}">
      <p>${escapeHtml(message)}</p>
      ${
        extraLines.length
          ? `<div class="status-lines">${extraLines.map((line) => `<p>${escapeHtml(line)}</p>`).join("")}</div>`
          : ""
      }
    </div>
  `;
}

let latestSyncReport = null;
let activeKnowledgeJobId = null;
let knowledgeJobPollTimer = null;
let knowledgeJobPollInFlight = false;

function jobProgressValue(job) {
  const parsed = Number(job?.progress ?? 0);
  if (!Number.isFinite(parsed)) {
    return 0;
  }
  return Math.max(0, Math.min(Math.round(parsed), 100));
}

function isActiveKnowledgeJob(job) {
  return Boolean(job) && ["queued", "running"].includes(String(job.status || ""));
}

function jobKindLabel(kind) {
  if (kind === "knowledge_upload") {
    return "Upload tài liệu";
  }
  if (kind === "knowledge_rebuild") {
    return "Rebuild kho tri thức";
  }
  return "Knowledge job";
}

function jobStageLabel(stage) {
  const labels = {
    queued: "Đang xếp hàng",
    starting: "Khởi động",
    preparing: "Chuẩn bị workspace",
    clean_markdown: "Làm sạch markdown",
    rag_markdown: "Tối ưu markdown cho RAG",
    corpora: "Chuẩn bị corpora",
    vector_build: "Build vector store",
    publishing: "Publish dữ liệu",
    completed: "Hoàn tất",
    failed: "Thất bại"
  };
  return labels[String(stage || "")] || String(stage || "Đang xử lý");
}

function jobStatusLabel(status) {
  const labels = {
    queued: "Chờ xử lý",
    running: "Đang chạy",
    completed: "Thành công",
    failed: "Thất bại"
  };
  return labels[String(status || "")] || String(status || "Không rõ");
}

function jobStatusClass(job) {
  if (job?.status === "completed") {
    return "success";
  }
  if (job?.status === "failed") {
    return "error";
  }
  return "info";
}

function compressText(value, limit = 180) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "";
  }
  if (normalized.length <= limit) {
    return normalized;
  }
  return `${normalized.slice(0, limit - 3)}...`;
}

function syncSummaryLines(sync) {
  if (!sync) {
    return [];
  }

  const cleanStats = sync.clean_stats || {};
  const ragReport = sync.rag_report || {};
  const vectorCounts = sync.vector_counts || {};

  return [
    `Route: ${sync.route || "all"}`,
    `Clean markdown: ${cleanStats.converted || 0} file`,
    `RAG markdown: ${ragReport.processed || 0} file`,
    `Vector chunks: handbook=${vectorCounts.handbook || 0}, policy=${vectorCounts.policy || 0}, faq=${vectorCounts.faq || 0}`
  ];
}

function knowledgeJobMessage(job) {
  if (!job) {
    return "";
  }

  if (job.status === "completed") {
    return job.result?.message || `${jobKindLabel(job.kind)} đã hoàn tất.`;
  }

  if (job.status === "failed") {
    return job.error || `${jobKindLabel(job.kind)} thất bại.`;
  }

  return `${jobKindLabel(job.kind)} đang được xử lý.`;
}

function knowledgeJobLines(job) {
  if (!job) {
    return [];
  }

  const lines = [
    `Trạng thái: ${jobStatusLabel(job.status)}`,
    `Tiến độ: ${jobProgressValue(job)}%`,
    `Bước: ${jobStageLabel(job.stage)}`
  ];

  if (job.payload?.route) {
    lines.push(`Route: ${job.payload.route}`);
  }

  if (job.payload?.saved_files?.length) {
    lines.push(`File mới: ${job.payload.saved_files.length}`);
  }

  const detail = compressText(job.detail, 220);
  if (detail && job.status !== "failed") {
    lines.push(detail);
  }

  if (job.status === "failed" && job.error) {
    lines.push(`Lỗi: ${job.error}`);
  }

  if (job.status === "completed" && job.result?.saved_files?.length) {
    lines.push(`Đã lưu: ${job.result.saved_files.length} file`);
  }

  if (job.status === "completed" && job.result?.sync) {
    lines.push(...syncSummaryLines(job.result.sync));
  }

  if (job.updated_at) {
    lines.push(`Cập nhật: ${formatDateTime(job.updated_at)}`);
  }

  return lines;
}

function jobCardMarkup(job) {
  const pillClass = job?.status === "completed" ? "success" : job?.status === "failed" ? "warning" : "";

  return `
    <article class="list-card">
      <div class="status-topline">
        <strong>${escapeHtml(jobKindLabel(job.kind))}</strong>
        <span class="pill ${pillClass}">${escapeHtml(jobStatusLabel(job.status))}</span>
      </div>
      <p class="muted-text">Tiến độ: ${escapeHtml(jobProgressValue(job))}% | ${escapeHtml(jobStageLabel(job.stage))}</p>
      <p class="muted-text">${escapeHtml(formatDateTime(job.updated_at || job.created_at))}</p>
      ${job.payload?.route ? `<p class="muted-text">Route: ${escapeHtml(job.payload.route)}</p>` : ""}
      ${job.error ? `<p class="muted-text">${escapeHtml(compressText(job.error, 140))}</p>` : ""}
    </article>
  `;
}

function latestCompletedSync(status) {
  const jobs = status?.jobs?.recent || [];
  const completedJob = jobs.find((job) => job.status === "completed" && job.result?.sync);
  return completedJob?.result?.sync || null;
}

function renderKnowledgeJobFeedback(job) {
  if (!job) {
    return;
  }

  const message = knowledgeJobMessage(job);
  const lines = knowledgeJobLines(job);
  const type = jobStatusClass(job);

  if (document.getElementById("uploadResult")) {
    setStatusMessage("uploadResult", type, message, lines);
  }

  if (document.getElementById("vectorResult")) {
    setStatusMessage("vectorResult", type, message, lines);
  }
}

function applyKnowledgeBusyState(job) {
  const busy = isActiveKnowledgeJob(job);
  const uploadSubmit = document.getElementById("uploadSubmit");
  const rebuildButton = document.getElementById("rebuildVectorButton");
  const uploadBusyText = document.getElementById("uploadBusyText");
  const vectorBusyText = document.getElementById("vectorBusyText");

  if (uploadSubmit) {
    uploadSubmit.disabled = busy;
  }

  if (rebuildButton) {
    rebuildButton.disabled = busy;
  }

  if (uploadBusyText) {
    const defaultText = uploadBusyText.dataset.defaultText || uploadBusyText.textContent;
    uploadBusyText.dataset.defaultText = defaultText;
    uploadBusyText.textContent = busy
      ? `${jobKindLabel(job.kind)} dang chay (${jobProgressValue(job)}%).`
      : defaultText;
  }

  if (vectorBusyText) {
    const defaultText = vectorBusyText.dataset.defaultText || vectorBusyText.textContent;
    vectorBusyText.dataset.defaultText = defaultText;
    vectorBusyText.textContent = busy
      ? `${jobKindLabel(job.kind)} dang chay (${jobProgressValue(job)}%).`
      : defaultText;
  }
}

function clearKnowledgePolling() {
  if (knowledgeJobPollTimer !== null) {
    window.clearTimeout(knowledgeJobPollTimer);
    knowledgeJobPollTimer = null;
  }
}

function scheduleKnowledgeJobPoll(jobId, delayMs = 1500) {
  clearKnowledgePolling();
  knowledgeJobPollTimer = window.setTimeout(() => {
    knowledgeJobPollTimer = null;
    void pollKnowledgeJob(jobId);
  }, delayMs);
}

function ensureKnowledgeJobPolling(job) {
  if (!isActiveKnowledgeJob(job)) {
    if (!knowledgeJobPollInFlight) {
      activeKnowledgeJobId = null;
      clearKnowledgePolling();
    }
    applyKnowledgeBusyState(null);
    return;
  }

  renderKnowledgeJobFeedback(job);
  applyKnowledgeBusyState(job);

  if (activeKnowledgeJobId === job.id && (knowledgeJobPollInFlight || knowledgeJobPollTimer !== null)) {
    return;
  }

  activeKnowledgeJobId = job.id;
  scheduleKnowledgeJobPoll(job.id, 1000);
}

async function pollKnowledgeJob(jobId) {
  if (!jobId || activeKnowledgeJobId !== jobId) {
    return;
  }

  knowledgeJobPollInFlight = true;

  try {
    const response = await fetch(`/api/knowledge/jobs/${encodeURIComponent(jobId)}`);
    const payload = await readResponsePayload(response);

    if (!response.ok) {
      throw new Error(payload.error || "Không thể tải trạng thái knowledge job.");
    }

    if (payload.result?.sync) {
      latestSyncReport = payload.result.sync;
    }

    renderKnowledgeJobFeedback(payload);
    applyKnowledgeBusyState(payload);

    if (isActiveKnowledgeJob(payload)) {
      knowledgeJobPollInFlight = false;
      scheduleKnowledgeJobPoll(jobId, 1500);
      return;
    }

    activeKnowledgeJobId = null;
    knowledgeJobPollInFlight = false;
    await loadKnowledgeBaseStatus({ silent: true, managePolling: false });
    applyKnowledgeBusyState(null);
  } catch (error) {
    knowledgeJobPollInFlight = false;

    const message =
      error instanceof Error ? error.message : "Không thể cập nhật tiến độ knowledge job.";

    if (document.getElementById("uploadResult")) {
      setStatusMessage("uploadResult", "error", message);
    }

    if (document.getElementById("vectorResult")) {
      setStatusMessage("vectorResult", "error", message);
    }

    if (activeKnowledgeJobId === jobId) {
      scheduleKnowledgeJobPoll(jobId, 3000);
    }
  }
}

function chatMessageMarkup({ role, message, routeLabel = "", sources = [] }) {
  const normalizedRole = role === "user" ? "user" : "bot";
  const badge = normalizedRole === "user" ? "Bạn" : "Assistant";
  const routeMarkup =
    normalizedRole === "bot" && routeLabel
      ? `<div class="message-meta"><span class="route-pill">${escapeHtml(routeLabel)}</span></div>`
      : "";
  const sourcesMarkup =
    normalizedRole === "bot" && sources.length
      ? `<div class="source-list">${sources.map((source) => `<span class="source-pill">${escapeHtml(source)}</span>`).join("")}</div>`
      : "";

  return `
    <div class="message-row ${normalizedRole}">
      <div class="message-badge">${escapeHtml(badge)}</div>
      <div class="bubble ${normalizedRole}">${renderBubbleContent(normalizedRole, message)}</div>
      ${routeMarkup}
      ${sourcesMarkup}
    </div>
  `;
}

function appendChatMessage(chatBox, payload) {
  chatBox.insertAdjacentHTML("beforeend", chatMessageMarkup(payload));
  chatBox.scrollTop = chatBox.scrollHeight;
}

function autosizeTextarea(textarea) {
  if (!textarea) {
    return;
  }

  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
}

async function sendMessage() {
  const input = document.getElementById("messageInput");
  const chatBox = document.getElementById("chatBox");
  const sendButton = document.getElementById("sendButton");

  if (!input || !chatBox || !sendButton) {
    return;
  }

  const message = input.value.trim();
  if (!message) {
    return;
  }

  appendChatMessage(chatBox, { role: "user", message });
  input.value = "";
  autosizeTextarea(input);

  sendButton.disabled = true;
  const typingMarkup = `
    <div class="message-row bot" id="typingMessage">
      <div class="message-badge">Assistant</div>
      <div class="bubble bot">Đang phân tích câu hỏi...</div>
    </div>
  `;
  chatBox.insertAdjacentHTML("beforeend", typingMarkup);
  chatBox.scrollTop = chatBox.scrollHeight;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message })
    });
    const payload = await readResponsePayload(response);
    document.getElementById("typingMessage")?.remove();

    if (!response.ok) {
      appendChatMessage(chatBox, {
        role: "bot",
        message: payload.error || "Không thể xử lý yêu cầu lúc này."
      });
      return;
    }

    appendChatMessage(chatBox, {
      role: "bot",
      message: payload.reply || "Không có nội dung trả lời.",
      routeLabel: payload.agent_label || payload.route || "",
      sources: payload.sources || []
    });
  } catch (_error) {
    document.getElementById("typingMessage")?.remove();
    appendChatMessage(chatBox, {
      role: "bot",
      message: "Không kết nối được với server."
    });
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

function routeCardMarkup(route) {
  const ready = Boolean(route.vector_ready);
  return `
    <article class="status-card">
      <div class="status-topline">
        <strong>${escapeHtml(route.label || route.route)}</strong>
        <span class="pill ${ready ? "success" : "warning"}">${ready ? "Sẵn sàng" : "Chưa build"}</span>
      </div>
      <p class="muted-text">Route: ${escapeHtml(route.route || "")}</p>
      <p class="muted-text">Tài liệu: ${escapeHtml(route.document_count || 0)}</p>
      <p class="muted-text">Cập nhật: ${escapeHtml(formatDateTime(route.vector_updated_at))}</p>
      <p class="path-text">${escapeHtml(route.vector_path || "")}</p>
    </article>
  `;
}

function uploadItemMarkup(item) {
  return `
    <article class="list-card">
      <div class="status-topline">
        <strong>${escapeHtml(item.filename || "")}</strong>
        <span class="pill">${escapeHtml(item.route || "")}</span>
      </div>
      <p class="muted-text">${escapeHtml(item.relative_path || "")}</p>
      <p class="muted-text">${escapeHtml(formatBytes(item.size_bytes))} | ${escapeHtml(formatDateTime(item.updated_at))}</p>
    </article>
  `;
}

function renderUploadPage(status) {
  const statusTarget = document.getElementById("uploadStatus");
  const uploadsTarget = document.getElementById("uploadList");
  const busyText = document.getElementById("uploadBusyText");

  if (busyText) {
    busyText.textContent = `Hỗ trợ tối đa ${status.max_upload_size_mb || 25} MB mỗi file. Định dạng: PDF, DOCX, Markdown (.md).`;
    busyText.dataset.defaultText = busyText.textContent;
  }

  if (statusTarget) {
    statusTarget.innerHTML = `
      <div class="status-grid">
        ${(status.routes || []).map(routeCardMarkup).join("") || '<p class="muted-text">Chưa có route nào.</p>'}
      </div>
      <div class="info-grid">
        <div class="info-row">
          <span>Upload root</span>
          <code>${escapeHtml(status.upload_root || "")}</code>
        </div>
        <div class="info-row">
          <span>Provider</span>
          <code>${escapeHtml((status.llm || {}).provider || "ollama")}</code>
        </div>
        <div class="info-row">
          <span>Model</span>
          <code>${escapeHtml((status.llm || {}).active_model || "Chưa rõ")}</code>
        </div>
        <div class="info-row">
          <span>Gemini</span>
          <code>${(status.llm || {}).gemini_configured ? "Đã cấu hình" : "Chưa cấu hình"}</code>
        </div>
      </div>
    `;
  }

  if (uploadsTarget) {
    const uploads = status.uploads || [];
    uploadsTarget.innerHTML = uploads.length
      ? uploads.map(uploadItemMarkup).join("")
      : '<p class="muted-text">Chưa có file nào được upload.</p>';
  }
}

function renderVectorPage(status) {
  const vectorTarget = document.getElementById("vectorStatus");
  const reportsTarget = document.getElementById("vectorReports");
  const activeJob = status?.jobs?.active || null;
  const recentJobs = status?.jobs?.recent || [];

  if (vectorTarget) {
    vectorTarget.innerHTML = (status.routes || []).length
      ? (status.routes || []).map(routeCardMarkup).join("")
      : '<p class="muted-text">Chưa có vector store nào.</p>';
  }

  if (reportsTarget) {
    const manifest = (status.reports || {}).manifest || {};
    const syncLines = syncSummaryLines(latestSyncReport);
    reportsTarget.innerHTML = `
      <div class="status-panel">
        <p>Manifest gần nhất: ${escapeHtml(formatDateTime(manifest.generated_at))}</p>
        <div class="status-lines">
          <p>Pipeline đang chạy: ${status.pipeline_busy ? "Có" : "Không"}</p>
          <p>Raw data dir: ${escapeHtml(status.raw_data_dir || "")}</p>
          <p>Vector root: ${escapeHtml(status.vector_root || "")}</p>
        </div>
      </div>
      ${
        activeJob
          ? `<div class="status-panel info"><p>${escapeHtml(knowledgeJobMessage(activeJob))}</p><div class="status-lines">${knowledgeJobLines(activeJob).map((line) => `<p>${escapeHtml(line)}</p>`).join("")}</div></div>`
          : ""
      }
      ${
        syncLines.length
          ? `<div class="status-panel success"><p>Lần đồng bộ gần nhất</p><div class="status-lines">${syncLines.map((line) => `<p>${escapeHtml(line)}</p>`).join("")}</div></div>`
          : ""
      }
      ${
        recentJobs.length
          ? `<div class="stack">${recentJobs.map(jobCardMarkup).join("")}</div>`
          : '<p class="muted-text">Chưa có knowledge job nào.</p>'
      }
    `;
  }
}

function renderKnowledgeBaseStatus(status) {
  const derivedSync = latestCompletedSync(status);
  if (derivedSync) {
    latestSyncReport = derivedSync;
  }

  renderUploadPage(status);
  renderVectorPage(status);
  ensureKnowledgeJobPolling(status?.jobs?.active || null);
}

async function loadKnowledgeBaseStatus(options = {}) {
  const { silent = false, managePolling = true } = options;

  if (!document.getElementById("uploadStatus") && !document.getElementById("vectorStatus")) {
    return null;
  }

  try {
    const response = await fetch("/api/vector/status");
    const payload = await readResponsePayload(response);
    if (!response.ok) {
      throw new Error(payload.error || "Không thể tải trạng thái kho dữ liệu.");
    }

    if (!managePolling) {
      const derivedSync = latestCompletedSync(payload);
      if (derivedSync) {
        latestSyncReport = derivedSync;
      }
      renderUploadPage(payload);
      renderVectorPage(payload);
      applyKnowledgeBusyState(payload?.jobs?.active || null);
      return payload;
    }

    renderKnowledgeBaseStatus(payload);
    return payload;
  } catch (error) {
    if (!silent) {
      const message = error instanceof Error ? error.message : "Không thể tải trạng thái kho dữ liệu.";
      setStatusMessage("uploadResult", "error", message);
      setStatusMessage("vectorResult", "error", message);
    }
    return null;
  }
}

async function loadHistory() {
  const historyBox = document.getElementById("historyBox");
  if (!historyBox) {
    return;
  }

  try {
    const response = await fetch("/api/history");
    const payload = await readResponsePayload(response);
    if (!response.ok) {
      throw new Error(payload.error || "Không thể tải lịch sử.");
    }

    if (!payload.length) {
      historyBox.innerHTML = '<p class="muted-text">Chưa có cuộc hội thoại nào.</p>';
      return;
    }

    historyBox.innerHTML = payload.map((item) => `
      <article class="history-entry">
        <p class="history-meta">${escapeHtml(item.timestamp)}</p>
        ${chatMessageMarkup({ role: "user", message: item.question })}
        ${chatMessageMarkup({ role: "bot", message: item.answer })}
      </article>
    `).join("");
  } catch (error) {
    historyBox.innerHTML = `<div class="status-panel error"><p>${escapeHtml(error instanceof Error ? error.message : "Không thể tải lịch sử.")}</p></div>`;
  }
}

async function clearHistory() {
  if (!window.confirm("Xóa toàn bộ lịch sử của session hiện tại?")) {
    return;
  }

  try {
    const response = await fetch("/api/history/clear", { method: "POST" });
    const payload = await readResponsePayload(response);
    if (!response.ok) {
      throw new Error(payload.error || "Không thể xóa lịch sử.");
    }
    await loadHistory();
  } catch (error) {
    setStatusMessage("historyBox", "error", error instanceof Error ? error.message : "Không thể xóa lịch sử.");
  }
}

function setupChatPage() {
  const input = document.getElementById("messageInput");
  const sendButton = document.getElementById("sendButton");
  const promptButtons = document.querySelectorAll("[data-prompt]");

  if (!input || !sendButton) {
    return;
  }

  autosizeTextarea(input);

  input.addEventListener("input", () => autosizeTextarea(input));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });

  sendButton.addEventListener("click", sendMessage);

  promptButtons.forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.prompt || "";
      autosizeTextarea(input);
      input.focus();
    });
  });
}

function setupUploadPage() {
  const form = document.getElementById("uploadForm");
  const submitButton = document.getElementById("uploadSubmit");
  const busyText = document.getElementById("uploadBusyText");
  if (!form || !submitButton || !busyText) {
    return;
  }

  busyText.dataset.defaultText = busyText.textContent;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const formData = new FormData(form);
    const files = formData.getAll("files");
    if (!files.length || !(files[0] instanceof File) || !files[0].name) {
      setStatusMessage("uploadResult", "error", "Bạn chưa chọn file để upload.");
      return;
    }

    submitButton.disabled = true;
    busyText.textContent = "Đang gửi file và tạo knowledge job...";
    setStatusMessage("uploadResult", "info", "Server dang tiep nhan upload va dua vao hang doi xu ly.");

    try {
      const response = await fetch("/api/upload", {
        method: "POST",
        body: formData
      });
      const payload = await readResponsePayload(response);
      if (!response.ok) {
        throw new Error(payload.error || "Upload thất bại.");
      }

      renderKnowledgeBaseStatus(payload.status || {});
      if (payload.job) {
        renderKnowledgeJobFeedback(payload.job);
        ensureKnowledgeJobPolling(payload.job);
      } else {
        setStatusMessage("uploadResult", "success", payload.message || "Đã tiếp nhận upload.");
      }
      form.reset();
    } catch (error) {
      setStatusMessage("uploadResult", "error", error instanceof Error ? error.message : "Upload thất bại.");
      submitButton.disabled = false;
      busyText.textContent =
        busyText.dataset.defaultText || "Hỗ trợ tối đa 25 MB mỗi file. Định dạng: PDF, DOCX, Markdown (.md).";
    }
  });
}

function setupVectorPage() {
  const rebuildButton = document.getElementById("rebuildVectorButton");
  const busyText = document.getElementById("vectorBusyText");
  if (!rebuildButton || !busyText) {
    return;
  }

  busyText.dataset.defaultText = busyText.textContent;

  rebuildButton.addEventListener("click", async () => {
    rebuildButton.disabled = true;
    busyText.textContent = "Đang tạo knowledge job rebuild...";
    setStatusMessage("vectorResult", "info", "Server dang tiep nhan lenh rebuild va dua vao hang doi xu ly.");

    try {
      const response = await fetch("/api/vector/rebuild", { method: "POST" });
      const payload = await readResponsePayload(response);
      if (!response.ok) {
        throw new Error(payload.error || "Rebuild thất bại.");
      }

      renderKnowledgeBaseStatus(payload.status || {});
      if (payload.job) {
        renderKnowledgeJobFeedback(payload.job);
        ensureKnowledgeJobPolling(payload.job);
      } else {
        setStatusMessage("vectorResult", "success", payload.message || "Đã tiếp nhận lệnh rebuild.");
      }
    } catch (error) {
      setStatusMessage("vectorResult", "error", error instanceof Error ? error.message : "Rebuild thất bại.");
      rebuildButton.disabled = false;
      busyText.textContent = busyText.dataset.defaultText || "Lenh nay chay lai clean, rag, corpora va vector store.";
    }
  });
}

function setupHistoryPage() {
  const clearButton = document.getElementById("clearHistoryButton");
  const historyBox = document.getElementById("historyBox");
  if (!historyBox) {
    return;
  }

  loadHistory();

  if (clearButton) {
    clearButton.addEventListener("click", clearHistory);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setupChatPage();
  setupUploadPage();
  setupVectorPage();
  setupHistoryPage();
  void loadKnowledgeBaseStatus();
});
