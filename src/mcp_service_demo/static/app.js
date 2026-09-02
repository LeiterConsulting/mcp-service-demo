const state = {
  view: "briefing",
  health: null,
  audience: "executive",
  demoSettings: null,
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

const audienceProfiles = {
  executive: {
    label: "Executive",
    description: "Business outcomes, accountable execution, and governed cross-system coordination.",
    hero: "A governed agent.<br><em>Across systems of record.</em>",
    lede: "MCP turns approved enterprise capabilities into a coordinated operating layer. The agent investigates, verifies, and acts across systems while each platform retains authority.",
    proofFocus: "visible workflow",
    agentSystem: ["Incident coordination agent", "Chooses approved capabilities and preserves context"],
    systems: {
      splunk: "Operational evidence · health · change · traces",
      tickets: "Employee workflow · accountability · durable action",
      catalog: "Ownership · dependencies · escalation authority",
    },
    values: [
      ["Reduce errors", "No copy-and-paste evidence", "Typed results move between systems without manual re-keying."],
      ["Reduce time", "One investigation path", "Ownership, telemetry, and ticket updates happen in the employee's workflow."],
      ["Time to innocence", "Verify before escalating", "Dependency health narrows the fault domain before another team is paged."],
      ["Finish the work", "Write back with provenance", "The finding and its evidence land in the system of record."],
    ],
    storyTitle: "From report to governed action",
    story: [
      ["Establish the request", ["tickets.get_ticket"], "Ground the response in impact, priority, and the employee's system of record."],
      ["Resolve accountability", ["catalog.get_service_context"], "Identify the owner, dependencies, escalation path, and approved runbook."],
      ["Quantify materiality", ["splunk.get_service_health", "compare_service_baseline"], "Measure the current deviation instead of relying on the ticket description."],
      ["Locate the failure", ["splunk.search_logs", "trace_request"], "Correlate errors and follow one failed request across the service path."],
      ["Avoid a false escalation", ["get_service_health(inventory-api)"], "Verify the implicated dependency is healthy before involving another team."],
      ["Complete the work", ["tickets.add_work_note"], "Return the finding, accountable action, and evidence to the system of record."],
    ],
    agent: {
      kicker: "Executive workflow",
      title: "MCP incident agent",
      welcome: "I can coordinate the service desk, service catalog, and Splunk through governed MCP tools. Ask for the impact and accountable next action for **INC-1042**, or run the complete investigation.",
      note: "The protocol panel makes the cross-system execution visible without overwhelming the business narrative.",
      detailLabel: "Technical inputs",
      prompts: [
        ["Executive summary", "Give me an executive summary of INC-1042. Focus on impact, decision, and accountable next action."],
        ["Business impact", "What business service is affected by INC-1042, how material is the degradation, and who owns the response?"],
        ["Prove fault isolation", "Why is inventory-api not the likely fault domain for INC-1042?"],
        ["Investigate + update", "Investigate INC-1042 and update the ticket"],
      ],
    },
    toolSectionTitle: "Discovered capabilities",
    relevantTools: ["get_ticket", "get_service_context", "splunk_run_query", "add_work_note", "update_ticket_status", "escalate_ticket"],
    toolLens: "Connect the tool to faster, more accountable execution without replacing the authority of the source platform.",
    connections: "Three independently governed systems coordinated through one visible protocol workflow.",
    ticket: {
      kicker: "MCP-powered coordination",
      title: "Complete the response from this ticket",
      description: "Gather evidence, verify responsibility, and return a sourced action without moving the employee between systems.",
      primary: "Investigate with MCP",
      outcomes: ["time to evidence", "systems coordinated", "sources preserved", "manual re-keying"],
    },
  },
  engineering: {
    label: "Engineering",
    description: "Telemetry, baselines, traces, dependency verification, and precise technical action.",
    hero: "Faster diagnosis.<br><em>Without integration glue.</em>",
    lede: "MCP gives the agent typed access to operational context and actions. Engineers can move from a ticket to baselines, errors, traces, dependencies, and a durable work note in one workflow.",
    proofFocus: "traceable execution path",
    agentSystem: ["Engineering incident agent", "Selects focused operations and carries evidence forward"],
    systems: {
      splunk: "Metrics · baselines · error search · request traces",
      tickets: "Incident context · work notes · assignment · state",
      catalog: "Topology · ownership · dependency roles · runbook",
    },
    values: [
      ["Diagnose faster", "Baseline before opinion", "Current behavior is compared with the preceding window before a cause is proposed."],
      ["Trace precisely", "Follow one failed request", "A concrete trace connects the dominant error to the affected service path."],
      ["Protect focus", "Test dependency health", "Evidence prevents an unnecessary handoff to a healthy downstream team."],
      ["Close the loop", "Engineering evidence persists", "Metrics, trace, owner, runbook, and next action are written back together."],
    ],
    storyTitle: "The evidence-driven investigation",
    story: [
      ["Read incident context", ["tickets.get_ticket"], "Use the affected service and time window from the ticket instead of re-entering context."],
      ["Load service topology", ["catalog.get_service_context"], "Resolve the owner, dependency roles, escalation route, and first-response runbook."],
      ["Compare behavior", ["get_service_health", "compare_service_baseline"], "Quantify error-rate and latency movement around the reported start time."],
      ["Correlate and trace", ["search_logs", "trace_request"], "Find the dominant failure and inspect one representative request path."],
      ["Test the hypothesis", ["get_service_health(inventory-api)"], "Check the implicated dependency before deciding where the defect lives."],
      ["Persist the diagnosis", ["tickets.add_work_note"], "Write the evidence set and mitigation path back to the incident record."],
    ],
    agent: {
      kicker: "Engineering workflow",
      title: "Evidence-driven incident agent",
      welcome: "I can carry ticket context into service topology and live Splunk evidence through MCP. Ask me to compare **checkout-api** with baseline, trace a failure, or investigate **INC-1042** end to end.",
      note: "Every operation remains inspectable; expand Technical inputs for exact tool arguments.",
      detailLabel: "Technical inputs",
      prompts: [
        ["Compare baseline", "Compare checkout-api health with the preceding 30-minute baseline."],
        ["Find the failure", "Why are checkout-api errors increasing? Trace a representative failed request."],
        ["Check dependency", "Is inventory-api healthy, and what does that prove about the checkout-api fault domain?"],
        ["Investigate + update", "Investigate INC-1042 and update the ticket"],
      ],
    },
    toolSectionTitle: "Engineering capabilities",
    relevantTools: ["splunk_run_query", "splunk_get_metadata", "splunk_get_knowledge_objects", "get_service_context", "get_ticket", "add_work_note"],
    toolLens: "Show how a typed, discoverable operation replaces bespoke integration code while keeping inputs and results inspectable.",
    connections: "Typed operational capabilities carry ticket and topology context into live telemetry without custom point-to-point glue.",
    ticket: {
      kicker: "MCP-powered diagnosis",
      title: "Investigate with source evidence",
      description: "Carry ticket context into topology, baseline, logs, and traces, then persist the technical diagnosis.",
      primary: "Run MCP investigation",
      outcomes: ["time to evidence", "systems queried", "evidence references", "manual re-keying"],
    },
  },
  security: {
    label: "Security",
    description: "Capability boundaries, source provenance, explicit authorization, and durable audit evidence.",
    hero: "Governed action.<br><em>Across trust boundaries.</em>",
    lede: "MCP exposes explicit capabilities instead of ambient access. The agent can discover what is allowed, use read-only evidence sources, and make a controlled ticket write only when the workflow authorizes it.",
    proofFocus: "governed execution trail",
    agentSystem: ["Governed investigation agent", "Uses scoped tools with explicit read and write boundaries"],
    systems: {
      splunk: "Read-only evidence · scoped identity · structured results",
      tickets: "Controlled writes · durable activity · workflow state",
      catalog: "Read-only authority · ownership · approved runbooks",
    },
    values: [
      ["Least privilege", "Capabilities, not ambient access", "The agent receives named operations with schemas and platform-owned permissions."],
      ["Source grounded", "Claims follow evidence", "Ticket, catalog, and telemetry facts remain attributable to their systems of record."],
      ["Explicit action", "Writes require intent", "Read-only investigation does not silently become a service-desk change."],
      ["Reviewable", "Every operation is visible", "Tool, input, status, duration, and resulting ticket activity form a durable trail."],
    ],
    storyTitle: "The governed execution chain",
    story: [
      ["Establish authority", ["tickets.get_ticket"], "Read the incident record before using its context or claiming impact."],
      ["Use an authoritative source", ["catalog.get_service_context"], "Resolve ownership and runbook through a read-only catalog capability."],
      ["Query within boundary", ["splunk.splunk_run_query"], "Use the connected Splunk identity through a read-only MCP operation."],
      ["Preserve provenance", ["search_logs", "trace_request"], "Carry evidence references forward rather than transcribing unsupported claims."],
      ["Verify before routing", ["get_service_health(inventory-api)"], "Test the alternative hypothesis before escalating another trust domain."],
      ["Authorize one write", ["tickets.add_work_note"], "Create a visible, resettable work note only after evidence collection and explicit intent."],
    ],
    agent: {
      kicker: "Governed workflow",
      title: "MCP control-aware agent",
      welcome: "I can demonstrate the read and write boundaries across the service desk, catalog, and Splunk. Ask me to show the evidence chain or run **INC-1042** with an explicit ticket update.",
      note: "Each timeline entry labels its access boundary; technical inputs remain available on demand.",
      detailLabel: "Inputs and audit detail",
      prompts: [
        ["Show boundaries", "Explain the MCP read and write boundaries available for INC-1042 before taking action."],
        ["Trace provenance", "Investigate INC-1042 read-only and explain the provenance of each conclusion."],
        ["Verify authorization", "Which ticket action is authorized when I ask to investigate and update INC-1042?"],
        ["Investigate + audit", "Investigate INC-1042 and update the ticket with sourced evidence"],
      ],
    },
    toolSectionTitle: "Capabilities and boundaries",
    relevantTools: ["splunk_get_user_info", "splunk_get_indexes", "splunk_get_metadata", "get_ticket", "get_service_context", "splunk_run_query", "add_work_note"],
    toolLens: "Identify the source authority, access mode, input contract, and durable evidence produced by this capability.",
    connections: "The topology makes trust boundaries explicit: two read-only evidence sources and one controlled system-of-record write surface.",
    ticket: {
      kicker: "Governed MCP action",
      title: "Act through explicit capabilities",
      description: "Read authoritative context, collect sourced evidence, and perform a visible ticket write only with explicit intent.",
      primary: "Investigate with audit trail",
      outcomes: ["time to evidence", "authorized systems", "sources preserved", "manual re-keying"],
    },
  },
  finance: {
    label: "Finance",
    description: "Material service impact, coordination effort, avoided handoffs, and accountable completion.",
    hero: "Less incident overhead.<br><em>More accountable execution.</em>",
    lede: "MCP reduces the coordination tax around operational work. One agent can gather evidence, find the accountable team, avoid a false escalation, and complete the ticket without inventing financial estimates.",
    proofFocus: "measurable workflow",
    agentSystem: ["Operational value agent", "Coordinates evidence, responsibility, and completion"],
    systems: {
      splunk: "Service impact · degradation window · change evidence",
      tickets: "Work queue · accountability · completion record",
      catalog: "Business criticality · ownership · escalation path",
    },
    values: [
      ["Protect the revenue path", "Materiality first", "The workflow connects technical degradation to the affected business service."],
      ["Reduce coordination effort", "One context-preserving path", "Employees stop moving and re-keying evidence between separate systems."],
      ["Avoid false handoffs", "Verify before escalating", "A healthy dependency is cleared before another team absorbs incident work."],
      ["Preserve accountability", "Action lands in the record", "Owner, evidence, recommendation, and status remain reviewable in the ticket."],
    ],
    storyTitle: "From business impact to accountable action",
    story: [
      ["Identify material impact", ["tickets.get_ticket"], "Start with the priority, affected revenue path, requester, and elapsed time."],
      ["Find accountability", ["catalog.get_service_context"], "Resolve the business service, owner, on-call route, and approved response plan."],
      ["Measure the deviation", ["get_service_health", "compare_service_baseline"], "Replace subjective urgency with current and baseline service evidence."],
      ["Reduce investigation labor", ["search_logs", "trace_request"], "Use the same context to locate the failure without another manual handoff."],
      ["Avoid misallocated effort", ["get_service_health(inventory-api)"], "Clear a healthy dependency before consuming another team's capacity."],
      ["Make execution accountable", ["tickets.add_work_note"], "Return the evidence, owner, next action, and status to the business record."],
    ],
    agent: {
      kicker: "Operational value workflow",
      title: "MCP value demonstration",
      welcome: "I can show how MCP reduces incident coordination work across the service desk, catalog, and Splunk. Ask for the business impact, accountable owner, or the complete **INC-1042** workflow.",
      note: "The demo reports observed workflow outcomes and avoids unsupported dollar-value claims.",
      detailLabel: "Supporting inputs",
      prompts: [
        ["Business impact", "Summarize the material business impact and accountable owner for INC-1042."],
        ["Avoided handoff", "What evidence prevents an unnecessary escalation to the inventory-api team?"],
        ["Workflow value", "Explain which manual coordination steps MCP removes in the INC-1042 investigation."],
        ["Investigate + update", "Investigate INC-1042 and update the ticket"],
      ],
    },
    toolSectionTitle: "Value-enabling capabilities",
    relevantTools: ["get_ticket", "list_my_tickets", "get_service_context", "splunk_run_query", "add_work_note", "assign_ticket", "escalate_ticket"],
    toolLens: "Explain which manual handoff or re-keying step this capability removes and where accountability remains.",
    connections: "Three systems remain independently owned while MCP reduces the labor required to coordinate evidence and action between them.",
    ticket: {
      kicker: "MCP-powered execution",
      title: "Reduce coordination overhead",
      description: "Connect business impact, evidence, ownership, and completion without adding unsupported financial claims.",
      primary: "Run accountable workflow",
      outcomes: ["time to decision evidence", "systems coordinated", "audit-ready sources", "manual re-keying"],
    },
  },
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

function audienceProfile() {
  return audienceProfiles[state.audience] || audienceProfiles.executive;
}

function renderPromptRow() {
  const profile = audienceProfile();
  $("#prompt-row").innerHTML = profile.agent.prompts
    .map(
      ([label, prompt]) =>
        `<button type="button" data-prompt="${escapeHtml(prompt)}">${escapeHtml(label)}</button>`,
    )
    .join("");
  $$('[data-prompt]', $("#prompt-row")).forEach((button) =>
    button.addEventListener("click", () => sendChat(button.dataset.prompt)),
  );
}

function renderAudience(audience, { resetChat = false } = {}) {
  state.audience = audienceProfiles[audience] ? audience : "executive";
  const profile = audienceProfile();
  document.body.dataset.audience = state.audience;
  document.title = `MCP Service Demo · ${profile.label}`;
  $("#audience-badge").textContent = `${profile.label} audience`;
  $("#briefing-title").innerHTML = profile.hero;
  $("#hero-lede").textContent = profile.lede;
  $("#hero-proof-focus").innerHTML = `<b>1</b> ${escapeHtml(profile.proofFocus)}`;
  $("#agent-system-title").textContent = profile.agentSystem[0];
  $("#agent-system-description").textContent = profile.agentSystem[1];
  $("#splunk-system-description").textContent = profile.systems.splunk;
  $("#desk-system-description").textContent = profile.systems.tickets;
  $("#catalog-system-description").textContent = profile.systems.catalog;
  $("#value-proof").innerHTML = profile.values
    .map(
      ([kicker, title, description]) =>
        `<article><span>${escapeHtml(kicker)}</span><b>${escapeHtml(title)}</b><small>${escapeHtml(description)}</small></article>`,
    )
    .join("");
  $("#story-title").textContent = profile.storyTitle;
  $("#story-steps").innerHTML = profile.story
    .map(
      ([title, tools, description], index) => `
        <div class="story-step">
          <span>${String(index + 1).padStart(2, "0")}</span>
          <div><b>${escapeHtml(title)}</b>${tools.map((tool) => `<code>${escapeHtml(tool)}</code>`).join("")}<small>${escapeHtml(description)}</small></div>
        </div>`,
    )
    .join("");
  $("#tool-section-title").textContent = profile.toolSectionTitle;
  $("#agent-kicker").textContent = profile.agent.kicker;
  $("#agent-title").textContent = profile.agent.title;
  $("#composer-note").textContent = profile.agent.note;
  $("#connections-description").textContent = profile.connections;
  $("#audience-active-status").textContent = profile.label;
  $("#audience-description").textContent = profile.description;
  const audienceInput = $(`input[name="demo-audience"][value="${state.audience}"]`);
  if (audienceInput) audienceInput.checked = true;
  if (resetChat) {
    state.chat = [{ role: "agent", text: profile.agent.welcome, mode: `${profile.label.toLowerCase()} lens` }];
  } else if (state.chat.length === 1 && state.chat[0].mode === "ready") {
    state.chat[0].text = profile.agent.welcome;
    state.chat[0].mode = `${profile.label.toLowerCase()} lens`;
  }
  renderPromptRow();
  renderToolCatalog();
  renderChat();
  if (state.activeTicket) renderTicket();
}

async function saveAudience(audience) {
  if (!audienceProfiles[audience] || state.busy || audience === state.audience) return;
  const previous = state.audience;
  renderAudience(audience, { resetChat: true });
  try {
    const result = await api("/api/settings/demo", {
      method: "PUT",
      body: JSON.stringify({ audience }),
    });
    state.demoSettings = result.settings;
    toast(`${audienceProfile().label} audience applied · scenario and connections unchanged`);
  } catch (error) {
    renderAudience(previous, { resetChat: true });
    toast(`Audience could not be saved: ${error.message}`, true);
  }
}

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
    .replace(/^(?:•|-) (.+)$/gm, "<span class=\"bullet-line\">• $1</span>")
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
  const relevant = audienceProfile().relevantTools;
  const tools = state.tools
    .slice()
    .sort((left, right) => {
      const leftIndex = relevant.indexOf(left.name);
      const rightIndex = relevant.indexOf(right.name);
      return (leftIndex < 0 ? 999 : leftIndex) - (rightIndex < 0 ? 999 : rightIndex);
    });
  $("#tool-count").textContent = state.tools.length || "—";
  $("#hero-tool-count").textContent = state.tools.length || "—";
  $("#mini-tool-list").innerHTML = tools.length
    ? tools
        .map(
          (tool) =>
            `<button type="button" class="mini-tool ${escapeHtml(tool.server)} ${relevant.includes(tool.name) ? "audience-relevant" : ""}" data-tool-server="${escapeHtml(tool.server)}" data-tool-name="${escapeHtml(tool.name)}" title="${relevant.includes(tool.name) ? `Relevant to the ${audienceProfile().label} narrative` : "Discovered MCP capability"}">${escapeHtml(tool.server)}.${escapeHtml(tool.name)}</button>`,
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
    <div class="tool-audience-lens"><span>${escapeHtml(audienceProfile().label)} lens</span><p>${escapeHtml(audienceProfile().toolLens)}</p></div>
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
  $("#connections-overview").innerHTML = `<div class="connection-audience-lens"><span>${escapeHtml(audienceProfile().label)} lens</span>${escapeHtml(audienceProfile().connections)}</div>` + state.connections
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

function renderDemoSettings(settings) {
  state.demoSettings = settings;
  renderAudience(settings?.audience || "executive");
}

async function openSetup(tab = "splunk") {
  const dialog = $("#setup-dialog");
  $("#connection-result").hidden = true;
  $("#llm-connection-result").hidden = true;
  switchSetupTab(tab);
  if (!dialog.open) dialog.showModal();
  try {
    const [splunkSettings, llmSettings, demoSettings] = await Promise.all([
      api("/api/settings/splunk"),
      api("/api/settings/llm"),
      api("/api/settings/demo"),
    ]);
    renderSplunkSettings(splunkSettings);
    renderLLMSettings(llmSettings);
    renderDemoSettings(demoSettings);
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

function toolAccessLabel(event) {
  if (event.server === "agent") return "Agent selection";
  if (
    event.server === "tickets" &&
    ["add_work_note", "update_ticket_status", "assign_ticket", "escalate_ticket"].includes(event.tool)
  ) {
    return "Controlled write";
  }
  return "Read only";
}

function renderTimeline(events) {
  const profile = audienceProfile();
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
            <div class="tool-event-identity"><div class="tool-server">${escapeHtml(event.server)}.${escapeHtml(event.tool)}</div><span class="tool-access">${escapeHtml(toolAccessLabel(event))}</span></div>
            <p class="tool-summary">${escapeHtml(event.summary)}</p>
            <details class="tool-args-disclosure">
              <summary>${escapeHtml(profile.agent.detailLabel)}</summary>
              <div class="tool-args">${escapeHtml(JSON.stringify(event.arguments, null, 2))}</div>
            </details>
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
      body: JSON.stringify({
        message: message.trim(),
        ticket_id: state.activeTicket?.id || null,
        audience: state.audience,
      }),
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
  const ticketProfile = audienceProfile().ticket;
  const outcomes = state.investigation?.outcomes;
  const outcomeStrip = outcomes
    ? `<div class="outcome-strip" aria-label="Investigation outcomes">
        <div><b>${escapeHtml(outcomes.elapsed_seconds ?? "—")}s</b><span>${escapeHtml(ticketProfile.outcomes[0])}</span></div>
        <div><b>${escapeHtml(outcomes.systems_coordinated)}</b><span>${escapeHtml(ticketProfile.outcomes[1])}</span></div>
        <div><b>${escapeHtml(outcomes.evidence_refs_preserved)}</b><span>${escapeHtml(ticketProfile.outcomes[2])}</span></div>
        <div><b>${escapeHtml(outcomes.manual_rekeying)}</b><span>${escapeHtml(ticketProfile.outcomes[3])}</span></div>
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
        <button class="button primary ask-splunk ${state.busy ? "loading" : ""}" id="ask-splunk-button" ${state.busy ? "disabled" : ""}>${state.busy ? "Investigating…" : escapeHtml(ticketProfile.primary)}</button>
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
          <span class="workspace-kicker">${escapeHtml(ticketProfile.kicker)}</span>
          <h4>${escapeHtml(ticketProfile.title)}</h4>
          <p>${escapeHtml(ticketProfile.description)}</p>
          <div class="agent-actions">
            <button class="button ${state.busy ? "loading" : ""}" id="ask-splunk-side" ${state.busy ? "disabled" : ""}>${state.busy ? "Investigating…" : escapeHtml(ticketProfile.primary)}</button>
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
      body: JSON.stringify({ write_back: true, audience: state.audience }),
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
      {
        role: "agent",
        text: `The demo has been reset for the **${audienceProfile().label}** audience. **INC-1042** is ready for a fresh investigation.`,
        mode: "scenario ready",
      },
    ];
    await refreshTickets("INC-1042");
    renderChat();
    renderConnectionStatus();
    toast(`Demo scenario restored · ${audienceProfile().label} audience and connections preserved`);
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
  $("#audience-badge").addEventListener("click", () => openSetup("demo"));
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
  $$('input[name="demo-audience"]').forEach((input) =>
    input.addEventListener("change", () => saveAudience(input.value)),
  );
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
    const [health, toolPayload, ticketPayload, splunkStatus, splunkSettings, demoSettings] = await Promise.all([
      api("/api/health"),
      api("/api/mcp/tools"),
      api("/api/tickets"),
      api("/api/splunk/status").catch((error) => ({ ready: false, error: error.message })),
      api("/api/settings/splunk"),
      api("/api/settings/demo"),
    ]);
    state.health = health;
    state.splunkStatus = splunkStatus;
    state.connections = toolPayload.servers;
    state.tools = toolPayload.tools;
    state.tickets = ticketPayload.tickets;
    renderSplunkSettings(splunkSettings);
    renderDemoSettings(demoSettings);
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
