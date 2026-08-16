const state = {
  scenarios: [],
  agents: [],
  overview: null,
  skills: [],
  selectedScenarioId: null,
  run: null,
  selectedTraceIndex: 0,
  busy: false,
};

const $ = (selector) => document.querySelector(selector);

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Keep the HTTP status when a proxy returns a non-JSON error page.
    }
    throw new Error(detail);
  }
  return response.json();
}

function setBusy(busy, label = "处理中…") {
  state.busy = busy;
  ["#startRunButton", "#approveButton", "#rejectButton", "#runEvalButton"].forEach(
    (selector) => {
      const button = $(selector);
      if (button) button.disabled = busy || (selector === "#startRunButton" && !state.selectedScenarioId);
    },
  );
  if (busy) $("#startRunButton").dataset.loading = "true";
  else delete $("#startRunButton").dataset.loading;
  $("#startRunButton").textContent = busy ? label : "运行主 Demo";
}

function toast(message) {
  const item = node("div", "toast", message);
  $("#toastStack").append(item);
  window.setTimeout(() => item.remove(), 4800);
}

function formatMoney(value) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function shortHash(value, length = 12) {
  if (!value) return "—";
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function selectScenario(scenarioId) {
  state.selectedScenarioId = scenarioId;
  document.querySelectorAll(".scenario-option").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.scenarioId === scenarioId));
  });
  const selected = state.scenarios.find((item) => item.scenario_id === scenarioId);
  renderRequest(selected);
  $("#startRunButton").disabled = state.busy || !selected;
}

function renderScenarios() {
  const target = $("#scenarioList");
  target.replaceChildren();
  state.scenarios.forEach((scenario) => {
    const button = node("button", "scenario-option");
    button.type = "button";
    button.dataset.scenarioId = scenario.scenario_id;
    button.setAttribute("aria-pressed", "false");
    button.append(node("strong", "", scenario.title), node("span", "", scenario.short));
    button.addEventListener("click", () => selectScenario(scenario.scenario_id));
    target.append(button);
  });
  const preferred = state.scenarios.find((item) => item.scenario_id === "over_limit");
  selectScenario((preferred || state.scenarios[0])?.scenario_id || null);
}

function renderRequest(scenario) {
  const target = $("#requestSheet");
  target.replaceChildren();
  if (!scenario) {
    target.append(node("p", "request-placeholder", "没有可用案例。"));
    return;
  }
  target.append(node("p", "request-quote", `“${scenario.request.request_text}”`));
  const facts = node("div", "request-facts");
  const entries = [
    ["总金额", formatMoney(
      Number(scenario.request.transport_amount)
        + Number(scenario.request.hotel_rate) * Number(scenario.request.hotel_nights)
        + Number(scenario.request.meal_amount),
    )],
    ["住宿单价", formatMoney(scenario.request.hotel_rate)],
    ["票据", scenario.request.has_invoice ? "齐全" : "缺失"],
    ["预期", scenario.expected],
  ];
  entries.forEach(([label, value]) => {
    const wrapper = node("span");
    wrapper.append(node("b", "", label), document.createTextNode(value));
    facts.append(wrapper);
  });
  target.append(facts);
}

async function startRun() {
  if (!state.selectedScenarioId || state.busy) return;
  setBusy(true, "正在编排…");
  try {
    state.run = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({ scenario_id: state.selectedScenarioId }),
    });
    state.selectedTraceIndex = Math.max(0, state.run.trace.length - 1);
    renderRun();
    $("#run-title").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    toast(`运行失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

function renderRun() {
  if (!state.run) return;
  const run = state.run;
  $("#runMeta").textContent = `${run.run_id} · ${run.trace_id}`;
  $("#copyRunButton").hidden = false;
  $("#exportAuditLink").hidden = false;
  $("#exportAuditLink").href = `/api/runs/${encodeURIComponent(run.run_id)}/audit.zip`;
  renderDecisionFocal(run);
  renderMetrics(run.metrics);
  renderAgentLanes(run);
  renderPlan(run.plan);
  renderEvidence(run.evidence);
  renderVerdict(run.verification);
  renderTrace(run.trace);
  renderDecisionBar(run);
}

const decisionCopy = {
  waiting_approval: ["WAITING APPROVAL", "写工具已被真实拦住", "草稿已持久化；只有签名审批身份齐全后，expense.submit 才能继续。"],
  verified: ["ACCEPT", "执行结果通过独立验收", "证据、审批身份、参数哈希、权限和工具回执彼此一致。"],
  blocked: ["BLOCK", "制度硬约束阻止了写入", "系统在调用任何企业写工具之前停止，并保留阻断证据。"],
  rolled_back: ["ROLLBACK", "补偿动作已完成", "原写入已被幂等补偿，审计链仍可完整重建。"],
  planned: ["REPLAN", "证据不足，需要重规划", "Verifier 不会在证据不完整时确认结果。"],
  failed: ["FAILED", "运行未完成", "请检查 Trace 中的失败边界。"],
};

function renderDecisionFocal(run) {
  const target = $("#decisionFocal");
  const copy = decisionCopy[run.status] || [run.status.toUpperCase(), "流程正在推进", "状态已持久化。"];
  target.dataset.state = run.status;
  const body = node("div");
  body.append(node("span", "decision-code", copy[0]), node("h3", "", copy[1]), node("p", "", copy[2]));
  target.replaceChildren(body, node("span", "decision-seal", run.status === "verified" ? "✓" : "PF"));
}

function renderMetrics(metrics) {
  const values = [
    [metrics.trace_event_count, "Trace 事件"],
    [metrics.evidence_count, "制度证据"],
    [metrics.policy_gate_count, "策略门"],
    [metrics.tool_call_count, "工具回执"],
  ];
  const target = $("#metricStrip");
  target.replaceChildren();
  values.forEach(([value, label]) => {
    const item = node("div");
    item.append(node("b", "", String(value)), node("span", "", label));
    target.append(item);
  });
}

function renderAgentLanes(run) {
  const target = $("#agentLanes");
  target.replaceChildren();
  const agentOrder = ["policyflow.policy", "policyflow.planner", "policyflow.executor", "policyflow.verifier"];
  const eventsByAgent = new Map();
  run.trace.forEach((event) => eventsByAgent.set(event.agent_id, event));
  agentOrder.forEach((agentId, index) => {
    const identity = state.agents.find((agent) => agent.agent_id === agentId);
    if (!identity) return;
    const event = eventsByAgent.get(agentId);
    const lane = node("article", "agent-lane");
    let phase = event ? "complete" : "idle";
    if (run.status === "waiting_approval" && agentId === "policyflow.executor") phase = "active";
    lane.dataset.state = phase;
    const header = node("header");
    header.append(node("span", "agent-index", String(index + 1).padStart(2, "0")), node("span", "agent-phase", phase.toUpperCase()));
    lane.append(header, node("h3", "", identity.cn_name), node("p", "", event?.summary || identity.mission));
    target.append(lane);
  });
}

function renderPlan(plan) {
  const target = $("#planSteps");
  target.replaceChildren();
  if (!plan) {
    target.append(node("li", "plan-empty", "尚无执行计划。"));
    return;
  }
  plan.steps.forEach((step) => {
    const item = node("li", "plan-step");
    item.dataset.state = step.status;
    const copy = node("div", "step-copy");
    copy.append(node("strong", "", step.title), node("span", "", `${step.agent_id} · ${step.tool_name || step.effect}`));
    item.append(node("span", "step-index", step.step_id), copy, node("span", "step-state", step.status.replaceAll("_", " ").toUpperCase()));
    target.append(item);
  });
}

function renderEvidence(evidence) {
  const target = $("#evidenceList");
  target.replaceChildren();
  if (!evidence.length) {
    target.append(node("p", "empty-copy", "本次未检索到制度证据。"));
    return;
  }
  evidence.forEach((item, index) => {
    const details = node("details", "evidence-item");
    if (index === 0) details.open = true;
    const summary = node("summary");
    summary.append(node("span", "evidence-clause", item.clause_id), node("span", "", item.title), node("span", "evidence-score", item.score.toFixed(2)));
    const quote = node("div", "evidence-quote", item.quote);
    quote.append(node("span", "evidence-hash", `${item.policy_id}@${item.policy_version} · sha256:${shortHash(item.source_hash, 18)}`));
    details.append(summary, quote);
    target.append(details);
  });
}

function renderVerdict(verification) {
  const target = $("#verdictPanel");
  target.replaceChildren();
  const heading = node("div", "pane-heading");
  heading.append(node("h2", "", "独立裁决"), node("span", "mono-tag", "VERIFIER"));
  target.append(heading);
  if (!verification) {
    target.append(node("p", "empty-copy", "Executor 不能给自己验收；等待独立 Agent。"));
    return;
  }
  target.append(node("p", "verdict-summary", `${verification.verdict.toUpperCase()} · ${verification.summary}`));
  const list = node("ul", "check-list");
  Object.entries(verification.checks).forEach(([name, passed]) => {
    const item = node("li");
    item.dataset.pass = String(passed);
    item.append(node("b", "", passed ? "PASS" : "FAIL"), node("span", "", name.replaceAll("_", " ")));
    list.append(item);
  });
  target.append(list);
}

function renderTrace(trace) {
  const target = $("#traceList");
  target.replaceChildren();
  if (!trace.length) {
    target.append(node("li", "trace-empty", "运行案例后可逐步检查。"));
    return;
  }
  trace.forEach((event, index) => {
    const item = node("li");
    const button = node("button", "trace-event-button");
    button.type = "button";
    button.setAttribute("aria-pressed", String(index === state.selectedTraceIndex));
    const center = node("span");
    center.append(node("span", "trace-agent", event.agent_id), node("span", "trace-name", event.name));
    button.append(node("span", "trace-index", String(index + 1).padStart(2, "0")), center, node("span", "trace-time", `${event.latency_ms.toFixed(1)} ms`));
    button.addEventListener("click", () => {
      state.selectedTraceIndex = index;
      renderTrace(state.run.trace);
    });
    item.append(button);
    target.append(item);
  });
  renderTraceInspector(trace[state.selectedTraceIndex] || trace[0]);
}

function renderTraceInspector(event) {
  const target = $("#traceInspector");
  target.replaceChildren(node("span", "mono-tag mono-tag--dark", event.name), node("p", "", event.summary));
  const fields = node("dl", "trace-fields");
  const values = [
    ["state", `${event.state_before} → ${event.state_after}`],
    ["span_id", event.span_id],
    ["parent", event.parent_span_id || "root"],
    ["evidence", event.evidence_ids.join(", ") || "—"],
    ["tool", event.tool_name || "—"],
    ["args hash", event.arguments_hash || "—"],
    ["idempotency", event.idempotency_key || "—"],
    ["previous hash", event.previous_hash || "legacy"],
    ["event hash", event.event_hash || "legacy"],
  ];
  values.forEach(([label, value]) => {
    const wrapper = node("div", "trace-field");
    wrapper.append(node("dt", "", label), node("dd", "", value));
    fields.append(wrapper);
  });
  target.append(fields);
}

function nextApprovalRole(run) {
  if (!run.approval_request) return null;
  const approved = new Set(run.approvals.filter((item) => item.decision === "approve").map((item) => item.actor_role));
  return run.approval_request.required_roles.find((role) => !approved.has(role)) || null;
}

function renderDecisionBar(run) {
  const bar = $("#decisionBar");
  const role = run.status === "waiting_approval" ? nextApprovalRole(run) : null;
  bar.hidden = !role;
  document.body.classList.toggle("has-decision-bar", Boolean(role));
  if (!role) return;
  $("#approvalRole").textContent = role;
  $("#approvalSummary").textContent = run.approval_request.summary;
  $("#approveButton").textContent = role === "Department Manager" ? "经理批准例外" : "财务批准提交";
}

const reviewerByRole = {
  "Department Manager": "manager-chen",
  "Finance Reviewer": "finance-lin",
};

async function decide(decision) {
  if (!state.run || state.busy) return;
  const role = nextApprovalRole(state.run);
  const reviewerId = reviewerByRole[role];
  if (!reviewerId) return toast("没有匹配的签名审批身份。" );
  setBusy(true, decision === "approve" ? "正在验签…" : "正在回滚…");
  try {
    const session = await api("/api/auth/demo-session", {
      method: "POST",
      body: JSON.stringify({
        reviewer_id: reviewerId,
        run_id: state.run.run_id,
        decision,
      }),
    });
    const reason = decision === "approve"
      ? role === "Department Manager"
        ? "客户活动地点临近会展，批准本次住宿例外。"
        : "制度证据、票据与参数哈希一致，批准提交。"
      : "现场演示拒绝：当前例外依据不足。";
    state.run = await api(`/api/runs/${encodeURIComponent(state.run.run_id)}/decisions`, {
      method: "POST",
      body: JSON.stringify({ decision, approval_token: session.approval_token, reason }),
    });
    state.selectedTraceIndex = Math.max(0, state.run.trace.length - 1);
    renderRun();
  } catch (error) {
    toast(`决策失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

function renderIdentities() {
  const target = $("#identityList");
  target.replaceChildren();
  state.agents.forEach((agent, index) => {
    const row = node("article", "identity-row");
    const main = node("div", "identity-main");
    main.append(node("h3", "", agent.cn_name), node("p", "", agent.mission));
    const boundary = node("div", "identity-boundary");
    boundary.append(node("strong", "", "CANNOT"), node("span", "", agent.cannot.join(" · ")));
    row.append(node("span", "identity-number", String(index + 1).padStart(2, "0")), main, boundary);
    target.append(row);
  });
}

function renderEngineering() {
  const skills = $("#skillRows");
  skills.replaceChildren();
  state.skills.forEach((skill) => {
    const row = node("div", "spec-row");
    row.append(node("code", "", skill.name), node("p", "", skill.purpose));
    skills.append(row);
  });
  const requirements = $("#requirementList");
  requirements.replaceChildren();
  const fit = state.overview.official_fit;
  const rows = [
    [fit.agents_at_least_three, "≥3 个身份清晰的 Agent"],
    [fit.agentteams_mapping, "AgentTeams Manager–Workers 映射"],
    [fit.agentteams_manifest_validated, "AgentTeams v1.2.2 官方 CRD 静态校验"],
    [fit.agentteams_live_verified, "真实 Matrix 协作记录（复赛环境待补）"],
    [fit.skills_documented, "六个完整 Skill 契约"],
    [fit.mcp_streamable_http, "MCP Streamable HTTP 门面"],
    [fit.human_approval_and_rollback, "高风险人工审批与补偿回滚"],
    [true, `${fit.context_mechanisms.length} 种 Context 机制：${fit.context_mechanisms.join(" / ")}`],
  ];
  rows.forEach(([passed, label]) => {
    const row = node("div", "requirement-row");
    row.dataset.pass = String(passed);
    row.append(node("b", "", passed ? "PASS" : "GAP"), node("span", "", label));
    requirements.append(row);
  });
}

async function runEvaluation() {
  if (state.busy) return;
  setBusy(true, "评测运行中…");
  const button = $("#runEvalButton");
  button.textContent = "评测运行中…";
  try {
    const report = await api("/api/evaluations/run", { method: "POST", body: "{}" });
    const target = $("#evalReport");
    target.hidden = false;
    target.replaceChildren(
      node("h3", "", "Golden Suite · 真实运行结果"),
      node("div", "eval-score", `${report.passed}/${report.total} PASS`),
      node("p", "", `主动攻击阻断：${report.attack_blocked}/${report.attack_total}`),
    );
    const list = node("ul", "eval-cases");
    report.cases.forEach((testCase) => {
      const item = node("li");
      item.append(node("b", "", testCase.passed ? "PASS" : "FAIL"), node("span", "", testCase.assertion));
      list.append(item);
    });
    target.append(list);
    target.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    toast(`评测失败：${error.message}`);
  } finally {
    button.textContent = "运行评测";
    setBusy(false);
  }
}

function setupNavigation() {
  const sections = ["demo", "identities", "engineering"].map((id) => document.getElementById(id));
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      document.querySelectorAll("[data-rail-link]").forEach((link) => {
        link.setAttribute("aria-current", link.dataset.railLink === visible.target.id ? "location" : "false");
      });
    },
    { rootMargin: "-20% 0px -65% 0px", threshold: [0, 0.2, 0.5] },
  );
  sections.forEach((section) => observer.observe(section));
}

async function initialize() {
  setupNavigation();
  $("#startRunButton").addEventListener("click", startRun);
  $("#approveButton").addEventListener("click", () => decide("approve"));
  $("#rejectButton").addEventListener("click", () => decide("reject"));
  $("#runEvalButton").addEventListener("click", runEvaluation);
  $("#copyRunButton").addEventListener("click", async () => {
    if (!state.run) return;
    try {
      await navigator.clipboard.writeText(state.run.run_id);
      toast("Run ID 已复制。" );
    } catch {
      toast(`Run ID：${state.run.run_id}`);
    }
  });
  try {
    const [scenarios, agents, overview, skills] = await Promise.all([
      api("/api/scenarios"),
      api("/api/agents"),
      api("/api/overview"),
      api("/api/skills"),
    ]);
    Object.assign(state, { scenarios, agents, overview, skills });
    $("#introAgentCount").textContent = String(overview.agent_count);
    renderScenarios();
    renderIdentities();
    renderEngineering();
  } catch (error) {
    $("#scenarioList").replaceChildren(node("p", "empty-copy", "无法读取本地运行服务。"));
    toast(`初始化失败：${error.message}`);
  }
}

initialize();
