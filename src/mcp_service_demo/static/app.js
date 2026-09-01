const state = {
  view: "briefing",
  health: null,
  splunkStatus: null,
  splunkSettings: null,
  tools: [],
  tickets: [],
  activeTicket: null,
  chat: [
    {
      role: "agent",
      text: "I can investigate the configured Splunk environment and work with the service desk through live MCP tools. Try asking whether **checkout-api** is healthy, or ask me to investigate **INC-1042**.",
      mode: "ready",
    },
  ],
  timeline: [],
  investigation: null,
  busy: false,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function richText(value = "") {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/^• (.+)$/gm, "<span class=\"bullet-line\">• $1</span>")
    .replace(/\n/g, "<br>");
}

function relativeTime(timestamp) {
  if (!timestamp) return "—";
  const delta = Math.max(0, Date.now() - new Date(timestamp).getTime());
  const minutes = Math.floor(delta / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function navigate(view) {
  state.view = view;
  $$(".view").forEach((node) => node.classList.toggle("active", node.id === `view-${view}`));
  $$(".nav-item").forEach((node) => node.classList.toggle("active", node.dataset.view === view));
  if (view === "agent") renderChat();
  if (view === "desk" && !state.activeTicket && state.tickets.length) selectTicket(state.tickets[0].id);
  window.history.replaceState(null, "", `#${view}`);
}

function renderToolCatalog() {
  $("#tool-count").textContent = state.tools.length || "—";
  $("#hero-tool-count").textContent = state.tools.length || "—";
  $("#mini-tool-list").innerHTML = state.tools.length
    ? state.tools
        .map(
          (tool) =>
            `<span class="mini-tool ${escapeHtml(tool.server)}" title="${escapeHtml(tool.description)}">${escapeHtml(tool.server)}.${escapeHtml(tool.name)}</span>`,
        )
        .join("")
    : '<span class="mini-tool">MCP servers unavailable</span>';
}

function renderConnectionStatus() {
  const pill = $("#connection-pill");
  const live = state.health?.splunk_data_mode === "live";
  const splunkReady = state.splunkStatus?.ready;
  pill.classList.remove("online", "offline");
  pill.classList.add(splunkReady ? "online" : "offline");
  pill.querySelector("span:last-child").textContent = splunkReady
    ? `2 MCP servers · Splunk ${live ? "live" : "fixture"}`
    : live
      ? "Splunk needs a scenario"
      : "MCP servers online";
  $("#data-source-label").innerHTML = live
    ? "<span></span> Live protocol · Real Splunk endpoint"
    : "<span></span> Live protocol · Fixture telemetry";
}

function renderSplunkSettings(settings) {
  state.splunkSettings = settings;
  const mode = settings.data_mode || "fixture";
  const modeInput = $(`input[name="data-mode"][value="${mode}"]`);
  if (modeInput) modeInput.checked = true;
  $("#settings-source").textContent = settings.source || "Environment defaults";
  $("#splunk-rest-url").value = settings.rest_url || "";
  $("#splunk-rest-token").value = "";
  $("#splunk-rest-token").placeholder = settings.rest_token_configured
    ? "Configured — leave blank to keep"
    : "Enter a Splunk access token";
  $("#rest-token-hint").textContent = settings.rest_token_configured
    ? "A token is configured. Enter a value only to replace it."
    : "Required for live Splunk unless basic auth is supplied by the environment.";
  $("#splunk-token-scheme").value = settings.rest_token_scheme || "Bearer";
  $("#splunk-rest-verify").checked = settings.rest_verify_ssl !== false;
  $("#splunk-rest-ca").value = settings.rest_ca_bundle_path || "";
  $("#splunk-hec-url").value = settings.hec_url || "";
  $("#splunk-hec-token").value = "";
  $("#splunk-hec-token").placeholder = settings.hec_token_configured
    ? "Configured — leave blank to keep"
    : "Enter the demo HEC token";
  $("#hec-token-hint").textContent = settings.hec_token_configured
    ? "A HEC token is configured. Enter a value only to replace it."
    : "Required to publish or reset the scenario in live mode.";
  $("#splunk-hec-verify").checked = settings.hec_verify_ssl !== false;
  $("#splunk-hec-ca").value = settings.hec_ca_bundle_path || "";
  const contract = settings.contract || {};
  $("#contract-values").innerHTML = [
    `app=${contract.app || "—"}`,
    `index=${contract.index || "—"}`,
    `sourcetype=${contract.sourcetype || "—"}`,
    `scenario=${contract.scenario_id || "—"}`,
  ]
    .map((value) => `<span>${escapeHtml(value)}</span>`)
    .join("");
}

function splunkSettingsPayload() {
  return {
    data_mode: $('input[name="data-mode"]:checked')?.value || "fixture",
    rest_url: $("#splunk-rest-url").value.trim(),
    rest_token: $("#splunk-rest-token").value.trim(),
    rest_token_scheme: $("#splunk-token-scheme").value,
    rest_verify_ssl: $("#splunk-rest-verify").checked,
    rest_ca_bundle_path: $("#splunk-rest-ca").value.trim(),
    hec_url: $("#splunk-hec-url").value.trim(),
    hec_token: $("#splunk-hec-token").value.trim(),
    hec_verify_ssl: $("#splunk-hec-verify").checked,
    hec_ca_bundle_path: $("#splunk-hec-ca").value.trim(),
  };
}

function showConnectionResult(message, isError = false) {
  const result = $("#connection-result");
  result.hidden = false;
  result.classList.toggle("error", isError);
  result.textContent = message;
}

async function openSplunkSettings() {
  const dialog = $("#splunk-settings-dialog");
  $("#connection-result").hidden = true;
  dialog.showModal();
  try {
    renderSplunkSettings(await api("/api/settings/splunk"));
  } catch (error) {
    showConnectionResult(`Settings could not be loaded: ${error.message}`, true);
  }
}

async function testSplunkConnection() {
  const button = $("#test-splunk-button");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Testing…";
  $("#connection-result").hidden = true;
  try {
    const result = await api("/api/settings/splunk/test", {
      method: "POST",
      body: JSON.stringify(splunkSettingsPayload()),
    });
    showConnectionResult(result.message, result.status !== "success");
  } catch (error) {
    showConnectionResult(`Connection test failed: ${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function saveSplunkConnection(event) {
  event.preventDefault();
  const button = $("#save-splunk-button");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    const result = await api("/api/settings/splunk", {
      method: "PUT",
      body: JSON.stringify(splunkSettingsPayload()),
    });
    renderSplunkSettings(result.settings);
    state.health = await api("/api/health");
    state.splunkStatus = await api("/api/splunk/status").catch((error) => ({
      ready: false,
      error: error.message,
    }));
    renderConnectionStatus();
    $("#splunk-settings-dialog").close();
    toast("Splunk connection saved");
  } catch (error) {
    showConnectionResult(`Connection could not be saved: ${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

function renderChat() {
  const thread = $("#chat-thread");
  thread.innerHTML = state.chat
    .map((message) => {
      if (message.typing) {
        return '<div class="message agent"><div class="message-avatar" aria-hidden="true">✦</div><div class="typing"><i></i><i></i><i></i></div></div>';
      }
      return `
        <div class="message ${message.role}">
          ${message.role === "agent" ? '<div class="message-avatar" aria-hidden="true">✦</div>' : ""}
          <div class="message-bubble">
            ${richText(message.text)}
            ${message.role === "agent" && message.mode ? `<div class="message-meta">${escapeHtml(message.mode)}</div>` : ""}
          </div>
        </div>`;
    })
    .join("");
  thread.scrollTop = thread.scrollHeight;
  renderTimeline(state.timeline);
}

function renderTimeline(events) {
  const empty = $("#timeline-empty");
  const timeline = $("#tool-timeline");
  empty.style.display = events.length ? "none" : "block";
  timeline.innerHTML = events
    .map(
      (event, index) => `
        <article class="tool-event ${escapeHtml(event.server)} ${event.status === "error" ? "error" : ""}">
          <div class="tool-event-icon">${event.status === "error" ? "!" : index + 1}</div>
          <div class="tool-event-card">
            <div class="tool-event-head">
              <b>${escapeHtml(event.title)}</b>
              <span>${escapeHtml(event.duration_ms)} ms</span>
            </div>
            <div class="tool-server">${escapeHtml(event.server)}.${escapeHtml(event.tool)}</div>
            <p class="tool-summary">${escapeHtml(event.summary)}</p>
            <div class="tool-args">${escapeHtml(JSON.stringify(event.arguments))}</div>
          </div>
        </article>`,
    )
    .join("");
}

async function sendChat(message) {
  if (!message.trim() || state.busy) return;
  state.busy = true;
  state.chat.push({ role: "user", text: message.trim() }, { role: "agent", typing: true });
  renderChat();
  try {
    const result = await api("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({ message: message.trim(), ticket_id: state.activeTicket?.id || null }),
    });
    state.chat.pop();
    state.chat.push({ role: "agent", text: result.message, mode: `${result.mode} · ${result.timeline.length} MCP calls` });
    state.timeline = result.timeline;
    if (result.ticket_updated) await refreshTickets(result.ticket_id);
  } catch (error) {
    state.chat.pop();
    state.chat.push({ role: "agent", text: `I couldn't complete that workflow: ${error.message}`, mode: "error" });
    toast(error.message, true);
  } finally {
    state.busy = false;
    renderChat();
  }
}

function renderTicketList() {
  $("#queue-count").textContent = state.tickets.length;
  $("#ticket-list").innerHTML = state.tickets
    .map(
      (ticket) => `
        <button class="ticket-card ${ticket.priority.toLowerCase()} ${state.activeTicket?.id === ticket.id ? "active" : ""}" data-ticket-id="${escapeHtml(ticket.id)}">
          <span class="priority-rail"></span>
          <span class="ticket-card-main">
            <span class="ticket-card-top"><b>${escapeHtml(ticket.id)}</b><span>${escapeHtml(ticket.priority)}</span></span>
            <span class="ticket-card-title">${escapeHtml(ticket.title)}</span>
            <span class="ticket-card-bottom"><span class="ticket-state">${escapeHtml(ticket.status)}</span><span>${relativeTime(ticket.updated_at)}</span></span>
          </span>
        </button>`,
    )
    .join("");
  $$("[data-ticket-id]").forEach((button) => button.addEventListener("click", () => selectTicket(button.dataset.ticketId)));
}

async function selectTicket(ticketId) {
  try {
    state.activeTicket = await api(`/api/tickets/${encodeURIComponent(ticketId)}`);
    state.investigation = null;
    renderTicketList();
    renderTicket();
  } catch (error) {
    toast(error.message, true);
  }
}

function noteLabel(kind) {
  if (kind === "work_note") return "Internal work note";
  if (kind === "customer") return "Customer comment";
  return "System activity";
}

function renderTicket() {
  const ticket = state.activeTicket;
  if (!ticket) return;
  const investigation = state.investigation
    ? `<div class="investigation-summary">
        <b>✦ Splunk investigation complete</b>
        <p>${richText(state.investigation.message)}</p>
        <div class="investigation-steps">${state.investigation.timeline.map((item) => `<span>✓ ${escapeHtml(item.title)}</span>`).join("")}</div>
      </div>`
    : "";
  const notes = ticket.notes
    .slice()
    .reverse()
    .map(
      (note) => `
        <article class="note ${escapeHtml(note.kind)}">
          <div class="note-head">
            <div class="note-author"><i></i>${escapeHtml(note.author)} <span>· ${noteLabel(note.kind)}</span></div>
            <time class="note-time">${relativeTime(note.created_at)}</time>
          </div>
          <div class="note-body">${escapeHtml(note.body)}</div>
          ${note.evidence_refs?.length ? `<div class="evidence-links">${note.evidence_refs.map((ref) => `<span class="evidence-link">${escapeHtml(ref)}</span>`).join("")}</div>` : ""}
        </article>`,
    )
    .join("");
  $("#ticket-column").innerHTML = `
    <div class="ticket-toolbar">
      <div class="ticket-breadcrumb">My work / <b>${escapeHtml(ticket.id)}</b></div>
      <div class="ticket-actions">
        <button class="button secondary small" id="open-agent-button">Open in agent</button>
        <button class="button primary ask-splunk" id="ask-splunk-button">Ask Splunk</button>
      </div>
    </div>
    ${investigation}
    <div class="ticket-hero">
      <div class="ticket-id-row">
        <span class="priority-badge ${ticket.priority.toLowerCase()}">${escapeHtml(ticket.priority)} incident</span>
        <span class="state-badge">${escapeHtml(ticket.status)}</span>
      </div>
      <h2>${escapeHtml(ticket.title)}</h2>
      <div class="ticket-description">${escapeHtml(ticket.description)}</div>
    </div>
    <div class="ticket-facts">
      <div class="fact"><span>Service</span><b>${escapeHtml(ticket.service)}</b></div>
      <div class="fact"><span>Assigned to</span><b>${escapeHtml(ticket.assignee)}</b></div>
      <div class="fact"><span>Requester</span><b>${escapeHtml(ticket.requester)}</b></div>
      <div class="fact"><span>Impact</span><b>${escapeHtml(ticket.impact)}</b></div>
      <div class="fact"><span>Opened</span><b>${relativeTime(ticket.created_at)}</b></div>
    </div>
    <div class="ticket-content-grid">
      <div>
        <div class="section-title"><h3>Activity</h3><span>${ticket.notes.length} entries</span></div>
        <div class="activity-feed">${notes}</div>
      </div>
      <aside>
        <div class="agent-callout">
          <span class="workspace-kicker">MCP-powered action</span>
          <h4>Investigate without leaving the ticket</h4>
          <p>The agent will use this ticket as context, query Splunk through MCP, and add a sourced work note.</p>
          <button class="button" id="ask-splunk-side">Ask Splunk about this ticket</button>
        </div>
        <div class="context-card">
          <h4>Ticket context</h4>
          <div class="context-row"><span>Urgency</span><b>${escapeHtml(ticket.urgency)}</b></div>
          <div class="context-row"><span>Service</span><b>${escapeHtml(ticket.service)}</b></div>
          <div class="context-row"><span>Status</span><b>${escapeHtml(ticket.status)}</b></div>
        </div>
      </aside>
    </div>`;
  $("#ask-splunk-button").addEventListener("click", askSplunk);
  $("#ask-splunk-side").addEventListener("click", askSplunk);
  $("#open-agent-button").addEventListener("click", () => {
    navigate("agent");
    $("#chat-input").value = `Investigate ${ticket.id} and update the ticket`;
    $("#chat-input").focus();
  });
}

async function askSplunk() {
  if (!state.activeTicket || state.busy) return;
  state.busy = true;
  const buttons = $$("#ask-splunk-button, #ask-splunk-side");
  buttons.forEach((button) => {
    button.disabled = true;
    button.classList.add("loading");
    button.textContent = "Investigating…";
  });
  try {
    const result = await api(`/api/agent/investigate/${encodeURIComponent(state.activeTicket.id)}`, {
      method: "POST",
      body: JSON.stringify({ write_back: true }),
    });
    state.investigation = result;
    state.timeline = result.timeline;
    await refreshTickets(result.ticket_id);
    state.investigation = result;
    renderTicket();
    toast(`${result.ticket_id} enriched with Splunk evidence`);
  } catch (error) {
    toast(error.message, true);
    renderTicket();
  } finally {
    state.busy = false;
  }
}

async function refreshTickets(selectedId = null) {
  const payload = await api("/api/tickets");
  state.tickets = payload.tickets;
  if (selectedId) state.activeTicket = await api(`/api/tickets/${encodeURIComponent(selectedId)}`);
  renderTicketList();
  if (state.activeTicket) renderTicket();
}

async function resetDemo() {
  if (state.busy) return;
  state.busy = true;
  try {
    await api("/api/demo/reset", { method: "POST", body: "{}" });
    state.splunkStatus = await api("/api/splunk/status").catch(() => state.splunkStatus);
    state.investigation = null;
    state.timeline = [];
    state.chat = [
      { role: "agent", text: "The demo has been reset. **INC-1042** is ready for a fresh investigation.", mode: "scenario ready" },
    ];
    await refreshTickets("INC-1042");
    renderChat();
    renderConnectionStatus();
    toast("Demo scenario restored");
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.busy = false;
  }
}

function toast(message, isError = false) {
  const node = document.createElement("div");
  node.className = `toast ${isError ? "error" : ""}`;
  node.textContent = message;
  $("#toast-region").append(node);
  window.setTimeout(() => node.remove(), 3600);
}

function bindEvents() {
  $$('[data-view]').forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view)));
  $("#settings-button").addEventListener("click", openSplunkSettings);
  $("#settings-close").addEventListener("click", () => $("#splunk-settings-dialog").close());
  $("#splunk-settings-dialog").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) event.currentTarget.close();
  });
  $("#test-splunk-button").addEventListener("click", testSplunkConnection);
  $("#splunk-settings-form").addEventListener("submit", saveSplunkConnection);
  $("#reset-button").addEventListener("click", resetDemo);
  $("#chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("#chat-input");
    const message = input.value;
    input.value = "";
    input.style.height = "auto";
    sendChat(message);
  });
  $("#chat-input").addEventListener("input", (event) => {
    event.target.style.height = "auto";
    event.target.style.height = `${Math.min(event.target.scrollHeight, 130)}px`;
  });
  $("#chat-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("#chat-form").requestSubmit();
    }
  });
  $$('[data-prompt]').forEach((button) => button.addEventListener("click", () => sendChat(button.dataset.prompt)));
}

async function bootstrap() {
  bindEvents();
  const initialView = ["briefing", "agent", "desk"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "briefing";
  try {
    const [health, toolPayload, ticketPayload, splunkStatus] = await Promise.all([
      api("/api/health"),
      api("/api/mcp/tools"),
      api("/api/tickets"),
      api("/api/splunk/status").catch((error) => ({ ready: false, error: error.message })),
    ]);
    state.health = health;
    state.splunkStatus = splunkStatus;
    state.tools = toolPayload.tools;
    state.tickets = ticketPayload.tickets;
    renderConnectionStatus();
    $("#agent-mode").textContent = health.agent_mode === "openai" ? "OpenAI + MCP" : "Guided MCP";
    renderToolCatalog();
    renderTicketList();
    renderChat();
    navigate(initialView);
  } catch (error) {
    const pill = $("#connection-pill");
    pill.classList.add("offline");
    pill.querySelector("span:last-child").textContent = "Service unavailable";
    renderToolCatalog();
    toast(error.message, true);
  }
}

bootstrap();
