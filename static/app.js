const presets = [
  "What breaks if the ledger service goes down?",
  "Next time the ledger fails, page Rohan first",
  "Who on the team has worked on payments-api before?",
  "Who on the team has worked on notifications before?",
  "Which accounts are linked to flagged transaction TX-1042?",
  "What did Mira Shah ask for last month, and was it resolved?",
  "What did we decide the last time ledger failed?",
  "What did we decide in earlier sessions?",
];

const log = document.querySelector("#log");
const trace = document.querySelector("#trace");
const question = document.querySelector("#question");
const user = document.querySelector("#user");
const sessionEl = document.querySelector("#session");
const health = document.querySelector("#health");
let sessionId = newSession();

sessionEl.textContent = sessionId;

document.querySelector("#presets").innerHTML = presets
  .map((text) => `<button type="button">${escapeHtml(text)}</button>`)
  .join("");

document.querySelector("#presets").addEventListener("click", (event) => {
  if (event.target.tagName === "BUTTON") ask(event.target.textContent);
});

document.querySelector("#form").addEventListener("submit", (event) => {
  event.preventDefault();
  ask(question.value);
});

document.querySelector("#new-session").addEventListener("click", () => {
  sessionId = newSession();
  sessionEl.textContent = sessionId;
  push("note", `New session ${sessionId}. Memory for this operator stays.`);
});

document.querySelector("#reset").addEventListener("click", async () => {
  if (!confirm("Reset Harbor Pay and every operator memory graph?")) return;
  const response = await fetch("/api/reset", { method: "POST" });
  const body = await response.json();
  if (!response.ok) {
    push("note", body.detail || "Reset failed");
    return;
  }
  log.innerHTML = "";
  trace.innerHTML = "<div class='empty'><h2>Demo data reset</h2><p>The company graph is back to the September incident, and every memory graph is gone.</p></div>";
  checkHealth();
});

checkHealth();

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const body = await response.json();
    health.className = body.ok ? "ok" : "bad";
    health.textContent = body.ok ? "FalkorDB connected" : `FalkorDB down: ${body.error}`;
  } catch (error) {
    health.className = "bad";
    health.textContent = "API not reachable";
  }
}

async function ask(text) {
  text = (text || "").trim();
  if (!text) return;
  question.value = "";
  push("you", text);
  const response = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: text,
      user_id: user.value.trim() || "aditya",
      session_id: sessionId,
    }),
  });
  const body = await response.json();
  if (!response.ok) {
    push("clearpath", body.detail || "The request failed");
    return;
  }
  push("clearpath", body.answer);
  renderTrace(body);
}

function push(kind, text) {
  const item = document.createElement("div");
  item.className = "bubble" + (kind === "you" ? " user" : "");
  item.innerHTML = `<div class="who">${kind}</div><p></p>`;
  item.querySelector("p").textContent = text;
  log.appendChild(item);
  log.scrollTop = log.scrollHeight;
}

function renderTrace(data) {
  const actions = (data.actions || [])
    .map((action) => `<span>${escapeHtml(actionLabel(action))}</span>`)
    .join("");
  const hops = (data.handoffs || [])
    .map((hop) => `${hop.from} → ${hop.to} (${hop.reason})`)
    .join(" · ");
  const paths = (data.paths || []).map(renderPath).join("");
  const cypher = (data.cypher || []).map((query) => `<pre>${escapeHtml(query)}</pre>`).join("");
  const memory = data.memory || { episodes: [], procedures: [] };
  const episodes = (memory.episodes || [])
    .map((row) => `<li>${escapeHtml(row.ts)} · ${escapeHtml(row.session_id)} · ${escapeHtml(row.question)}</li>`)
    .join("");
  trace.innerHTML = `
    <p class="eyebrow">${escapeHtml(data.tool || "")} · ${escapeHtml(data.planner || "")}</p>
    <h2>How this answer was reached</h2>
    <p class="meta">${escapeHtml(hops || "No handoff")}</p>
    <div class="actions">${actions || "<span>No write</span>"}</div>
    ${paths || "<p>No path was returned.</p>"}
    <h3>This operator's memory</h3>
    <ul>${episodes || "<li>No episodes yet.</li>"}</ul>
    ${(memory.procedures || []).map((row) => `<p class="meta">Standing order: page ${escapeHtml(row.person_id)} when ${escapeHtml(row.service_id)} fails.</p>`).join("")}
    <details open>
      <summary>Cypher and algorithms</summary>
      ${cypher || "<p>No query.</p>"}
    </details>
  `;
}

function renderPath(path) {
  const nodes = (path.nodes || [])
    .map((node, index) => {
      const arrow = index < path.nodes.length - 1 && path.kind !== "graph"
        ? `<span class="arrow">${escapeHtml(path.edges?.[index]?.type || "→")}</span>`
        : "";
      return `<div class="node"><small>${escapeHtml(node.label || "")}</small>${escapeHtml(node.name || node.id)}</div>${arrow}`;
    })
    .join("");
  const edges = path.kind === "graph"
    ? `<ul class="edges">${(path.edges || []).map((edge) => `<li>${escapeHtml(edge.source)} —${escapeHtml(edge.type)}→ ${escapeHtml(edge.target)}</li>`).join("")}</ul>`
    : "";
  return `<div class="path"><h3>${escapeHtml(path.title || "Path")}</h3><div class="row">${nodes}</div>${edges}</div>`;
}

function actionLabel(action) {
  if (action.type === "PAGE") return `Page ${action.person_id} (${action.reason})`;
  if (action.type === "FREEZE") return `Freeze ${action.account_ids.join(", ")}`;
  if (action.type === "OPEN_INCIDENT") return `Open ${action.id} ${action.severity}`;
  if (action.type === "RECORD_DECISION") return `Write ${action.id}`;
  if (action.type === "HANDOFF") return `Hand ${action.ticket_id} to ${action.person_id}`;
  if (action.type === "WRITE_PROCEDURE") return `Remember: page ${action.person_id}`;
  return action.type;
}

function newSession() {
  return "s" + Math.random().toString(36).slice(2, 8);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
