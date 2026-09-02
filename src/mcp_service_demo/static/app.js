const state = {
  view: "briefing",
  health: null,
  splunkStatus: null,
  splunkSettings: null,
  llmSettings: null,
  connections: [],
  tools: [],
  tickets: [],
  activeTicket: null,
  catalogContext: null,
  chat: [
    {
      role: "agent",
      text: "I can preserve context across the service desk, service catalog, and Splunk through live MCP tools. Try asking why **checkout-api** is failing, or ask me to investigate **INC-1042**.",
      mode: "ready",
    },
  ],
  timeline: [],
  investigation: null,
  busy: false,
};

const toolNarratives = {
  get_service_context: {
    usefulness: "Prevents routing by guesswork by supplying the authoritative owner, dependencies, escalation channel, and runbook.",
    when: "Immediately after the ticket is read and again whenever responsibility or a dependency is in question.",
  },
  get_ticket: {
    usefulness: "Grounds the investigation in the employee's actual request, business impact, priority, and current activity.",
    when: "The first operation in every ticket-led investigation.",
  },
  list_my_tickets: {
    usefulness: "Lets the agent work from the analyst's real queue instead of requiring a copied ticket number.",
    when: "When the employee asks what needs attention or wants a queue summary.",
  },
  add_work_note: {
    usefulness: "Completes the workflow by preserving findings and evidence in the system of record.",
    when: "Only after evidence collection and explicit authorization to update the ticket.",
  },
  update_ticket_status: {
    usefulness: "Moves the incident through its governed workflow without leaving the agent experience.",
    when: "When the employee explicitly requests a valid status transition.",
  },
  assign_ticket: {
    usefulness: "Routes accountability to a named analyst and records the assignment change as ticket activity.",
    when: "When an operator reassigns the incident from the service-desk controls.",
  },
  escalate_ticket: {
    usefulness: "Routes the incident to an assignment group with a durable reason and visible escalation state.",
    when: "After evidence and catalog context justify involving another operational group.",
  },
  splunk_run_query: {
    usefulness: "Executes approved, scenario-scoped SPL against the real Splunk endpoint and returns structured evidence.",
    when: "Behind focused health, baseline, log, and trace operations selected by the agent.",
  },
  splunk_get_info: {
    usefulness: "Confirms which Splunk platform the agent is connected to and its operational status.",
    when: "During connection validation, not routine incident analysis.",
  },
  splunk_get_indexes: {
    usefulness: "Shows which governed data repositories are available to the connected identity.",
    when: "During setup or when validating the demo data contract.",
  },
  splunk_get_index_info: {
    usefulness: "Explains an index's configuration and health when data availability is in question.",
    when: "When troubleshooting ingestion or retention rather than the incident itself.",
  },
  splunk_get_metadata: {
    usefulness: "Surfaces hosts, sources, and sourcetypes so the agent can understand the shape of available telemetry.",
    when: "During discovery or when a search needs to be narrowed safely.",
  },
  splunk_get_user_list: {
    usefulness: "Demonstrates that MCP discovery can expose administrative capabilities while the agent presents only the incident-safe subset.",
    when: "Administration only; it is deliberately excluded from the incident agent's focused tool surface.",
  },
  splunk_get_user_info: {
    usefulness: "Confirms the connected Splunk identity and roles without exposing credentials.",
    when: "During connection and authorization troubleshooting.",
  },
  splunk_get_kv_store_collections: {
    usefulness: "Shows that the same MCP server can expose platform services beyond search without adding bespoke UI integrations.",
    when: "Platform administration, not this incident path.",
  },
  splunk_get_knowledge_objects: {
    usefulness: "Makes approved searches, macros, lookups, and other Splunk knowledge available for governed reuse.",
    when: "When an enterprise replaces demo SPL with its own curated operational content.",
  },
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

async function streamApi(path, options = {}, onMessage = () => {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const message = JSON.parse(line);
      onMessage(message);
      if (message.type === "error") throw new Error(message.message);
      if (message.type === "result") finalResult = message.result;
    }
    if (done) break;
  }
  return finalResult;
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
            `<button type="button" class="mini-tool ${escapeHtml(tool.server)}" data-tool-server="${escapeHtml(tool.server)}" data-tool-name="${escapeHtml(tool.name)}">${escapeHtml(tool.server)}.${escapeHtml(tool.name)}</button>`,
        )
        .join("")
    : '<span class="mini-tool">MCP servers unavailable</span>';
  $$('[data-tool-name]', $("#mini-tool-list")).forEach((button) =>
    button.addEventListener("click", () => openToolDetail(button.dataset.toolServer, button.dataset.toolName)),
  );
}

function renderConnectionStatus() {
  const pill = $("#connection-pill");
  const live = state.health?.splunk_data_mode === "live";
  const splunkReady = state.splunkStatus?.ready;
  const scenarioFresh = state.splunkStatus?.fresh !== false;
  const presentationReady = splunkReady && scenarioFresh;
  pill.classList.remove("online", "offline");
  pill.classList.add(presentationReady ? "online" : "offline");
  pill.querySelector("span:last-child").textContent = presentationReady
    ? `3 MCP servers · Splunk ${live ? "live" : "fixture"}`
    : splunkReady && !scenarioFresh
      ? "Reset demo to refresh Splunk data"
      : live
        ? "Splunk needs a scenario"
        : "MCP servers online";
  $("#data-source-label").innerHTML = live
    ? "<span></span> Live protocol · Real Splunk endpoint"
    : "<span></span> Live protocol · Fixture telemetry";
}

function renderAgentMode() {
  const llmActive = state.health?.agent_mode === "openai";
  const model = state.health?.agent_model || "LLM";
  const badge = $("#agent-mode");
  if (badge) badge.textContent = llmActive ? `${model} + MCP` : "Guided MCP";
  const setupButton = $("#setup-button");
  if (setupButton) {
    setupButton.classList.toggle("configured", Boolean(state.health?.llm_configured));
    setupButton.title = llmActive
      ? `LLM-assisted mode is active with ${model}`
      : "Configure guided or LLM-assisted agent mode";
  }
}

function toolBoundary(tool) {
  if (tool.server === "catalog") return "Read-only authoritative context. It cannot change ownership or assign blame.";
  if (tool.server === "splunk") return "Read-only in this incident workflow. Searches are scoped to the deterministic demo dataset.";
  if (["add_work_note", "update_ticket_status", "assign_ticket", "escalate_ticket"].includes(tool.name)) {
    return "Controlled write to the service desk. The action is visible, persistent, and resettable.";
  }
  return "Read-only service-desk context owned by the ticket platform.";
}

function openToolDetail(server, name) {
  const tool = state.tools.find((item) => item.server === server && item.name === name);
  if (!tool) return;
  const narrative = toolNarratives[name] || {
    usefulness: tool.description,
    when: "Available when the employee's request requires this platform capability.",
  };
  $("#tool-dialog-server").textContent = `${server} MCP · ${tool.title}`;
  $("#tool-dialog-title").textContent = `${server}.${name}`;
  $("#tool-detail").innerHTML = `
    <section class="tool-detail-intro"><span class="settings-step">What the system exposes</span><p>${escapeHtml(tool.description)}</p></section>
    <div class="tool-detail-grid">
      <article><span>Why it matters here</span><p>${escapeHtml(narrative.usefulness)}</p></article>
      <article><span>When it is used</span><p>${escapeHtml(narrative.when)}</p></article>
      <article><span>Permission boundary</span><p>${escapeHtml(toolBoundary(tool))}</p></article>
    </div>
    <div class="tool-schema">${escapeHtml(JSON.stringify(tool.input_schema || {}, null, 2))}</div>`;
  $("#tool-dialog").showModal();
}

function renderConnections() {
  const descriptions = {
    splunk: "Operational evidence: service health, baselines, logs, deployments, and traces.",
    tickets: "Employee workflow: queues, ticket context, assignment, escalation, notes, and status.",
    catalog: "Operational authority: service ownership, dependencies, escalation path, and runbooks.",
  };
  const icons = { splunk: ["S", "splunk-icon"], tickets: ["N", "desk-icon"], catalog: ["C", "catalog-icon"] };
  $("#connections-overview").innerHTML = state.connections
    .map((server) => {
      const tools = state.tools.filter((tool) => tool.server === server.name);
      const [letter, iconClass] = icons[server.name] || ["M", "agent-icon"];
      const mode = server.name === "splunk" ? (state.health?.splunk_data_mode === "live" ? "Real Splunk" : "Fixture telemetry") : server.name === "tickets" ? "Read + controlled write" : "Read only";
      return `<article class="connection-card">
        <div class="system-icon ${iconClass}">${letter}</div>
        <div><h3>${escapeHtml(server.title)}</h3><p>${escapeHtml(descriptions[server.name] || "MCP capability server")}</p><div class="connection-endpoint">${escapeHtml(server.url)}</div><div class="connection-meta"><span>Streamable HTTP</span><span>${escapeHtml(mode)}</span><span>${tools.length} tools</span></div></div>
        <span class="connection-state">Connected</span>
        <div class="connection-card-tools">${tools.map((tool) => `<button type="button" class="mini-tool ${escapeHtml(tool.server)}" data-connection-tool="${escapeHtml(tool.server)}:${escapeHtml(tool.name)}">${escapeHtml(tool.name)}</button>`).join("")}</div>
      </article>`;
    })
    .join("");
  $$('[data-connection-tool]', $("#connections-overview")).forEach((button) =>
    button.addEventListener("click", () => {
      const [server, name] = button.dataset.connectionTool.split(":");
      $("#connections-dialog").close();
      openToolDetail(server, name);
    }),
  );
}

function openConnections() {
  renderConnections();
  $("#connections-dialog").showModal();
}

function renderSplunkSettings(settings) {
  state.splunkSettings = settings;
  const mode = settings.data_mode || "fixture";
  const modeInput = $(`input[name="data-mode"][value="${mode}"]`);
  if (modeInput) modeInput.checked = true;
  $("#settings-source").textContent = settings.source || "Environment defaults";
  $("#splunk-mcp-url").value = settings.mcp_url || "";
  $("#splunk-mcp-token").value = "";
  $("#splunk-mcp-token").placeholder = settings.mcp_token_configured
    ? "Configured — leave blank to keep"
    : "Optional bearer token";
  $("#mcp-token-hint").textContent = settings.mcp_token_configured
    ? "A bearer token is configured. Enter a value only to replace it."
    : "Optional for the local Splunk Operations server.";
  $("#splunk-mcp-verify").checked = settings.mcp_verify_ssl !== false;
  $("#splunk-mcp-ca").value = settings.mcp_ca_bundle_path || "";
  $("#splunk-rest-url").value = settings.rest_url || "";
  $("#splunk-rest-token").value = "";
  $("#splunk-rest-token").placeholder = settings.rest_token_configured
    ? "Configured — leave blank to keep"
    : "Optional direct REST token";
  $("#rest-token-hint").textContent = settings.rest_token_configured
    ? "A token is configured. Enter a value only to replace it."
    : "Only required when the bundled local MCP server performs the searches.";
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
    mcp_url: $("#splunk-mcp-url").value.trim(),
    mcp_token: $("#splunk-mcp-token").value.trim(),
    mcp_verify_ssl: $("#splunk-mcp-verify").checked,
    mcp_ca_bundle_path: $("#splunk-mcp-ca").value.trim(),
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

function switchSetupTab(tab) {
  $$('[data-setup-tab]').forEach((button) => {
    const active = button.dataset.setupTab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $$('[data-setup-panel]').forEach((panel) => {
    const active = panel.dataset.setupPanel === tab;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
}

async function openSetup(tab = "splunk") {
  const dialog = $("#setup-dialog");
  $("#connection-result").hidden = true;
  $("#llm-connection-result").hidden = true;
  switchSetupTab(tab);
  if (!dialog.open) dialog.showModal();
  try {
    const [splunkSettings, llmSettings] = await Promise.all([
      api("/api/settings/splunk"),
      api("/api/settings/llm"),
    ]);
    renderSplunkSettings(splunkSettings);
    renderLLMSettings(llmSettings);
  } catch (error) {
    showConnectionResult(`Settings could not be loaded: ${error.message}`, true);
  }
}

async function testMcpConnection() {
  const button = $("#test-mcp-button");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Testing…";
  $("#connection-result").hidden = true;
  try {
    const result = await api("/api/settings/splunk/mcp/test", {
      method: "POST",
      body: JSON.stringify(splunkSettingsPayload()),
    });
    showConnectionResult(result.message, result.status !== "success");
  } catch (error) {
    showConnectionResult(`MCP endpoint test failed: ${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
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
    renderAgentMode();
    $("#setup-dialog").close();
    toast("Splunk connection saved");
  } catch (error) {
    showConnectionResult(`Connection could not be saved: ${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

function renderLLMSettings(settings) {
  state.llmSettings = settings;
  const mode = settings.agent_mode || "guided";
  const modeInput = $(`input[name="agent-mode"][value="${mode}"]`);
  if (modeInput) modeInput.checked = true;
  $("#llm-settings-source").textContent = settings.source || "Environment defaults";
  $("#llm-base-url").value = settings.base_url || "https://api.openai.com/v1";
  $("#llm-model").value = settings.model || "gpt-5-mini";
  $("#llm-api-key").value = "";
  $("#llm-api-key").placeholder = settings.api_key_configured
    ? "Configured — leave blank to keep"
    : "Enter an API key";
  $("#llm-api-key-hint").textContent = settings.api_key_configured
    ? "An API key is configured. Enter a value only to replace it."
    : "Required only when LLM-assisted mode is enabled.";
  $("#clear-llm-key-row").hidden = !settings.api_key_configured;
  $("#clear-llm-api-key").checked = false;
  $("#llm-active-status").textContent =
    settings.active_mode === "openai" ? `Active · ${settings.model}` : "Active · Guided";
  const tuning = settings.tuning || {};
  $("#llm-tuning-profile").textContent = tuning.max_tool_calls
    ? `${tuning.profile || "Balanced"} · ${tuning.max_tool_calls} calls · ${tuning.max_parallel_tools} parallel`
    : "balanced limits";
}

function llmSettingsPayload() {
  const clearApiKey = $("#clear-llm-api-key").checked;
  return {
    agent_mode: clearApiKey
      ? "guided"
      : $('input[name="agent-mode"]:checked')?.value || "guided",
    base_url: $("#llm-base-url").value.trim(),
    api_key: $("#llm-api-key").value.trim(),
    model: $("#llm-model").value.trim(),
    clear_api_key: clearApiKey,
  };
}

function showLLMResult(message, isError = false) {
  const result = $("#llm-connection-result");
  result.hidden = false;
  result.classList.toggle("error", isError);
  result.textContent = message;
}

async function testLLMConnection() {
  const button = $("#test-llm-button");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Testing…";
  $("#llm-connection-result").hidden = true;
  try {
    const result = await api("/api/settings/llm/test", {
      method: "POST",
      body: JSON.stringify(llmSettingsPayload()),
    });
    showLLMResult(result.message, result.status !== "success");
  } catch (error) {
    showLLMResult(`Model connection test failed: ${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function saveLLMConnection(event) {
  event.preventDefault();
  const button = $("#save-llm-button");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Saving…";
  try {
    const result = await api("/api/settings/llm", {
      method: "PUT",
      body: JSON.stringify(llmSettingsPayload()),
    });
    renderLLMSettings(result.settings);
    state.health = await api("/api/health");
    renderAgentMode();
    $("#setup-dialog").close();
    toast(
      state.health.agent_mode === "openai"
        ? `LLM-assisted mode enabled · ${state.health.agent_model}`
        : "Guided agent mode enabled",
    );
  } catch (error) {
    showLLMResult(`Agent settings could not be saved: ${error.message}`, true);
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
        <article class="tool-event ${escapeHtml(event.server)} ${escapeHtml(event.status || "complete")}">
          <div class="tool-event-icon">${event.status === "error" ? "!" : index + 1}</div>
          <div class="tool-event-card">
            <div class="tool-event-head">
              <b>${escapeHtml(event.title)}</b>
              <span>${event.status === "running" ? "In progress" : `${escapeHtml(event.duration_ms)} ms`}</span>
            </div>
            <div class="tool-server">${escapeHtml(event.server)}.${escapeHtml(event.tool)}</div>
            <p class="tool-summary">${escapeHtml(event.summary)}</p>
            <div class="tool-args">${escapeHtml(JSON.stringify(event.arguments))}</div>
          </div>
        </article>`,
    )
    .join("");
}

function setActivityStatus(label, running = false) {
  const status = $(".activity-status");
  status.innerHTML = `<i></i> ${escapeHtml(label)}`;
  status.classList.toggle("running", running);
}

function beginWorkflow(summary) {
  state.timeline = [
    {
      event_id: "workflow-start",
      server: "agent",
      tool: "select_tools",
      title: "Interpret request and select tools",
      arguments: {},
      status: "running",
      summary,
      duration_ms: 0,
    },
  ];
  setActivityStatus("Running", true);
}

function applyStreamMessage(message) {
  if (message.type !== "tool") return;
  const event = message.event;
  state.timeline = state.timeline.filter((item) => item.event_id !== "workflow-start");
  const index = state.timeline.findIndex((item) => item.event_id === event.event_id);
  if (index >= 0) state.timeline[index] = event;
  else state.timeline.push(event);
}

async function sendChat(message) {
  if (!message.trim() || state.busy) return;
  state.busy = true;
  state.chat.push({ role: "user", text: message.trim() }, { role: "agent", typing: true });
  beginWorkflow("Understanding intent and matching it to the discovered MCP capabilities.");
  renderChat();
  try {
    const result = await streamApi("/api/agent/chat/stream", {
      method: "POST",
      body: JSON.stringify({ message: message.trim(), ticket_id: state.activeTicket?.id || null }),
    }, (streamMessage) => {
      applyStreamMessage(streamMessage);
      renderTimeline(state.timeline);
    });
    if (!result) throw new Error("The agent stream ended without a result");
    state.chat.pop();
    state.chat.push({ role: "agent", text: result.message, mode: `${result.mode} · ${result.timeline.length} MCP calls` });
    state.timeline = result.timeline;
    setActivityStatus("Complete");
    if (result.ticket_updated) await refreshTickets(result.ticket_id);
  } catch (error) {
    state.chat.pop();
    state.chat.push({ role: "agent", text: `I couldn't complete that workflow: ${error.message}`, mode: "error" });
    setActivityStatus("Needs attention");
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
    state.catalogContext = await api(
      `/api/catalog/services/${encodeURIComponent(state.activeTicket.service)}`,
    ).catch(() => null);
    state.investigation = null;
    renderTicketList();
    renderTicket();
  } catch (error) {
    toast(error.message, true);
  }
}

function splunkEvidenceUrl(ref) {
  if (!ref.startsWith("splunk://")) return null;
  const server = state.connections.find((item) => item.name === "splunk");
  if (!server?.web_url) return null;
  const contract = state.splunkSettings?.contract || {};
  const app = contract.app || "search";
  const baseSearch = [
    "search",
    contract.index ? `index=\"${contract.index}\"` : "",
    contract.sourcetype ? `sourcetype=\"${contract.sourcetype}\"` : "",
    contract.scenario_id ? `scenario_id=\"${contract.scenario_id}\"` : "",
  ].filter(Boolean);
  let earliest = "-30m";
  if (ref.startsWith("splunk://search?")) {
    const params = new URLSearchParams(ref.split("?")[1] || "");
    if (params.get("service")) baseSearch.push(`service=\"${params.get("service")}\"`);
    if (params.get("q")) baseSearch.push(params.get("q"));
    earliest = params.get("earliest") || earliest;
  } else if (ref.startsWith("splunk://trace/")) {
    baseSearch.push(`trace_id=\"${decodeURIComponent(ref.slice("splunk://trace/".length))}\"`);
    earliest = "-90m";
  } else {
    return null;
  }
  return `${server.web_url}/en-US/app/${encodeURIComponent(app)}/search?q=${encodeURIComponent(baseSearch.join(" "))}&earliest=${encodeURIComponent(earliest)}`;
}

function evidenceMarkup(ref) {
  const splunkUrl = splunkEvidenceUrl(ref);
  if (splunkUrl) {
    return `<a class="evidence-link" href="${escapeHtml(splunkUrl)}" target="_blank" rel="noopener" title="Open this evidence in Splunk">${escapeHtml(ref)}</a>`;
  }
  if (ref.startsWith("catalog://services/")) {
    return `<button type="button" class="evidence-link" data-catalog-evidence="${escapeHtml(ref.slice("catalog://services/".length))}" title="Open the service catalog record">${escapeHtml(ref)}</button>`;
  }
  return `<span class="evidence-link">${escapeHtml(ref)}</span>`;
}

function openCatalogContext() {
  const context = state.catalogContext;
  if (!context) return;
  $("#tool-dialog-server").textContent = "catalog MCP · authoritative service record";
  $("#tool-dialog-title").textContent = context.display_name || context.service;
  $("#tool-detail").innerHTML = `
    <section class="tool-detail-intro"><span class="settings-step">Service Catalog</span><p>${escapeHtml(context.business_service)} · ${escapeHtml(context.criticality)}</p></section>
    <div class="tool-detail-grid">
      <article><span>Ownership</span><p>${escapeHtml(context.owner_team)}<br>On-call: ${escapeHtml(context.on_call)}<br>${escapeHtml(context.support_channel)}</p></article>
      <article><span>Dependencies</span><p>${context.dependencies.map((item) => `${escapeHtml(item.service)} — ${escapeHtml(item.role)}`).join("<br>") || "No cataloged dependencies"}</p></article>
      <article><span>First-response runbook</span><p>${escapeHtml(context.runbook.title)}<br>${escapeHtml(context.runbook.reference)}</p></article>
    </div>
    <div class="tool-schema">${escapeHtml(context.evidence_ref)}</div>`;
  $("#tool-dialog").showModal();
}

function noteLabel(kind) {
  if (kind === "work_note") return "Internal work note";
  if (kind === "customer") return "Customer comment";
  return "System activity";
}

function renderTicket() {
  const ticket = state.activeTicket;
  if (!ticket) return;
  const outcomes = state.investigation?.outcomes;
  const outcomeStrip = outcomes
    ? `<div class="outcome-strip" aria-label="Investigation outcomes">
        <div><b>${escapeHtml(outcomes.elapsed_seconds ?? "—")}s</b><span>time to evidence</span></div>
        <div><b>${escapeHtml(outcomes.systems_coordinated)}</b><span>systems coordinated</span></div>
        <div><b>${escapeHtml(outcomes.evidence_refs_preserved)}</b><span>sources preserved</span></div>
        <div><b>${escapeHtml(outcomes.manual_rekeying)}</b><span>manual re-keying</span></div>
      </div>`
    : "";
  const investigation = state.investigation
    ? `<div class="investigation-summary">
        <b>✦ Cross-system investigation complete</b>
        <p>${richText(state.investigation.message)}</p>
        <div class="investigation-steps">${state.investigation.timeline.map((item) => `<span>✓ ${escapeHtml(item.title)}</span>`).join("")}</div>
      </div>`
    : state.busy && state.timeline.length
      ? `<div class="investigation-summary">
          <b>✦ Cross-system investigation in progress</b>
          <p>The agent is preserving context as each MCP operation completes.</p>
          <div class="investigation-steps">${state.timeline.map((item) => `<span>${item.status === "complete" ? "✓" : "↻"} ${escapeHtml(item.title)}</span>`).join("")}</div>
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
          ${note.evidence_refs?.length ? `<div class="evidence-links">${note.evidence_refs.map(evidenceMarkup).join("")}</div>` : ""}
        </article>`,
    )
    .join("");
  $("#ticket-column").innerHTML = `
    <div class="ticket-toolbar">
      <div class="ticket-breadcrumb">My work / <b>${escapeHtml(ticket.id)}</b></div>
      <div class="ticket-actions">
        <button class="button secondary small" id="open-agent-button">Open in agent</button>
        <button class="button primary ask-splunk ${state.busy ? "loading" : ""}" id="ask-splunk-button" ${state.busy ? "disabled" : ""}>${state.busy ? "Investigating…" : "Ask Splunk"}</button>
      </div>
    </div>
    ${outcomeStrip}
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
      <div class="fact"><span>Assignment group</span><b>${escapeHtml(ticket.assignment_group)}</b></div>
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
          <h4>Work across systems from this ticket</h4>
          <p>Choose a full three-system investigation or a focused read-only action.</p>
          <div class="agent-actions">
            <button class="button ${state.busy ? "loading" : ""}" id="ask-splunk-side" ${state.busy ? "disabled" : ""}>${state.busy ? "Investigating…" : "Investigate and enrich"}</button>
            <button class="button secondary-action" id="check-health-side">Check current health</button>
            <button class="button secondary-action" id="show-catalog-side">View owner and runbook</button>
          </div>
        </div>
        ${state.catalogContext ? `<div class="context-card catalog-context-card" id="catalog-context-card">
          <h4>Service Catalog <span class="connection-state">Live</span></h4>
          <div class="context-row"><span>Owner</span><b>${escapeHtml(state.catalogContext.owner_team)}</b></div>
          <div class="context-row"><span>On-call</span><b>${escapeHtml(state.catalogContext.on_call)}</b></div>
          <div class="context-row dependencies"><span>Dependencies</span><div class="dependency-list">${state.catalogContext.dependencies.map((item) => `<span>${escapeHtml(item.service)}</span>`).join("")}</div></div>
          <div class="context-row"><span>Runbook</span><b>${escapeHtml(state.catalogContext.runbook.title)}</b></div>
          <button type="button" class="catalog-source" id="open-catalog-record">${escapeHtml(state.catalogContext.evidence_ref)}</button>
        </div>` : ""}
        <div class="context-card">
          <h4>Ticket context</h4>
          <div class="context-row"><span>Urgency</span><b>${escapeHtml(ticket.urgency)}</b></div>
          <div class="context-row"><span>Service</span><b>${escapeHtml(ticket.service)}</b></div>
          <div class="context-row"><span>Status</span><b>${escapeHtml(ticket.status)}</b></div>
        </div>
        <div class="context-card ticket-control-card">
          <h4>Ticket controls</h4>
          <div class="ticket-control"><label for="ticket-assignee">Assigned analyst</label><div class="ticket-control-row"><select id="ticket-assignee">${["Maya Chen", "Jordan Lee", "Priya Shah"].map((name) => `<option${name === ticket.assignee ? " selected" : ""}>${name}</option>`).join("")}</select><button class="button secondary" id="assign-ticket-button">Assign</button></div></div>
          <div class="ticket-control"><label for="ticket-escalation">Escalation group</label><div class="ticket-control-row"><select id="ticket-escalation">${[state.catalogContext?.on_call || "Commerce Platform", "Major Incident Management", "Application Reliability"].map((name) => `<option>${escapeHtml(name)}</option>`).join("")}</select><button class="button secondary" id="escalate-ticket-button">Escalate</button></div></div>
          <div class="ticket-control"><label for="ticket-status">Workflow status</label><div class="ticket-control-row"><select id="ticket-status">${["New", "Investigating", "Monitoring", "Resolved"].map((status) => `<option${status === ticket.status ? " selected" : ""}>${status}</option>`).join("")}</select><button class="button secondary" id="update-status-button">Update</button></div></div>
        </div>
      </aside>
    </div>`;
  $("#ask-splunk-button").addEventListener("click", askSplunk);
  $("#ask-splunk-side").addEventListener("click", askSplunk);
  $("#check-health-side").addEventListener("click", () => {
    navigate("agent");
    sendChat(`Is ${ticket.service} healthy right now?`);
  });
  $("#show-catalog-side").addEventListener("click", openCatalogContext);
  $("#open-catalog-record")?.addEventListener("click", openCatalogContext);
  $$('[data-catalog-evidence]').forEach((button) =>
    button.addEventListener("click", openCatalogContext),
  );
  $("#assign-ticket-button").addEventListener("click", () =>
    updateTicketControl("assign", { assignee: $("#ticket-assignee").value }, "Ticket reassigned"),
  );
  $("#escalate-ticket-button").addEventListener("click", () => {
    const assignmentGroup = $("#ticket-escalation").value;
    updateTicketControl(
      "escalate",
      { assignment_group: assignmentGroup, reason: "Operator escalation following service catalog routing guidance." },
      `Escalated to ${assignmentGroup}`,
    );
  });
  $("#update-status-button").addEventListener("click", () =>
    updateTicketControl("status", { status: $("#ticket-status").value }, "Ticket status updated"),
  );
  $("#open-agent-button").addEventListener("click", () => {
    navigate("agent");
    $("#chat-input").value = `Investigate ${ticket.id} and update the ticket`;
    $("#chat-input").focus();
  });
}

async function updateTicketControl(action, payload, successMessage) {
  if (!state.activeTicket || state.busy) return;
  state.busy = true;
  const ticketId = state.activeTicket.id;
  try {
    await api(`/api/tickets/${encodeURIComponent(ticketId)}/${action}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await refreshTickets(ticketId);
    toast(successMessage);
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.busy = false;
    renderTicket();
  }
}

async function askSplunk() {
  if (!state.activeTicket || state.busy) return;
  state.busy = true;
  state.investigation = null;
  beginWorkflow("Reading ticket context before selecting the cross-system investigation path.");
  renderTicket();
  try {
    const result = await streamApi(`/api/agent/investigate/${encodeURIComponent(state.activeTicket.id)}/stream`, {
      method: "POST",
      body: JSON.stringify({ write_back: true }),
    }, (streamMessage) => {
      applyStreamMessage(streamMessage);
      if (streamMessage.type === "tool") renderTicket();
    });
    if (!result) throw new Error("The investigation stream ended without a result");
    state.investigation = result;
    state.timeline = result.timeline;
    setActivityStatus("Complete");
    await refreshTickets(result.ticket_id);
    state.investigation = result;
    renderTicket();
    toast(`${result.ticket_id} enriched across ${result.outcomes.systems_coordinated} systems`);
  } catch (error) {
    setActivityStatus("Needs attention");
    toast(error.message, true);
  } finally {
    state.busy = false;
    renderTicket();
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
    toast("Demo scenario restored · Splunk and LLM setup preserved");
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.busy = false;
    renderTicket();
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
  $("#setup-button").addEventListener("click", () => openSetup("splunk"));
  $("#agent-mode").addEventListener("click", () => openSetup("llm"));
  $("#setup-close").addEventListener("click", () => $("#setup-dialog").close());
  $("#setup-dialog").addEventListener("click", (event) => {
    if (event.target === event.currentTarget) event.currentTarget.close();
  });
  $$('[data-setup-tab]').forEach((button) =>
    button.addEventListener("click", () => switchSetupTab(button.dataset.setupTab)),
  );
  $("#test-mcp-button").addEventListener("click", testMcpConnection);
  $("#test-splunk-button").addEventListener("click", testSplunkConnection);
  $("#splunk-settings-form").addEventListener("submit", saveSplunkConnection);
  $("#test-llm-button").addEventListener("click", testLLMConnection);
  $("#llm-settings-form").addEventListener("submit", saveLLMConnection);
  $("#reset-button").addEventListener("click", resetDemo);
  $("#connection-pill").addEventListener("click", openConnections);
  $$('[data-close-dialog]').forEach((button) =>
    button.addEventListener("click", () => $("#" + button.dataset.closeDialog).close()),
  );
  $$(".info-dialog").forEach((dialog) =>
    dialog.addEventListener("click", (event) => {
      if (event.target === event.currentTarget) event.currentTarget.close();
    }),
  );
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
    const [health, toolPayload, ticketPayload, splunkStatus, splunkSettings] = await Promise.all([
      api("/api/health"),
      api("/api/mcp/tools"),
      api("/api/tickets"),
      api("/api/splunk/status").catch((error) => ({ ready: false, error: error.message })),
      api("/api/settings/splunk"),
    ]);
    state.health = health;
    state.splunkStatus = splunkStatus;
    state.connections = toolPayload.servers;
    state.tools = toolPayload.tools;
    state.tickets = ticketPayload.tickets;
    renderSplunkSettings(splunkSettings);
    renderConnectionStatus();
    renderAgentMode();
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
