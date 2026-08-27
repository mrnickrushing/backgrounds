const state = {
  meta: null,
  templates: null,
  me: null,
  cases: [],
  queue: null,
  current: null,
  tab: "overview",
  reportSection: null,
  dashboard: {
    filters: { q: "", stage: "all", due: "all" },
    views: [],
  },
};
const DASHBOARD_STATE_PREFIX = "backgrounds.dashboard.v1";
let dashboardHotkeyHandler = null;
const app = document.querySelector("#app"),
  modal = document.querySelector("#modal"),
  modalForm = document.querySelector("#modalForm");
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>'"]/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[
        c
      ],
  );
const label = (s) =>
  String(s)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
const fmtDate = (s) =>
  s
    ? (() => {
        const value = new Date(`${s}T12:00:00`);
        return Number.isNaN(value.getTime())
          ? "Invalid date"
          : new Intl.DateTimeFormat(undefined, {
              month: "short",
              day: "numeric",
              year: "numeric",
            }).format(value);
      })()
    : "Not set";
const request = async (path, options = {}) => {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 401) {
    location.href = "/login";
    throw new Error("Session expired");
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
};
function toast(message) {
  const node = document.querySelector("#toast");
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 2200);
}
function storageKey(scope, suffix) {
  return `${DASHBOARD_STATE_PREFIX}.${scope}.${suffix}`;
}
function readJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}
function writeJSON(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}
function normalizeDashboardFilters(filters = {}) {
  const next = {
    q: String(filters.q || "").slice(0, 120),
    stage: String(filters.stage || "all"),
    due: String(filters.due || "all"),
    activeOnly: Boolean(filters.activeOnly),
  };
  if (!["all", "overdue", "due_soon"].includes(next.due)) next.due = "all";
  return next;
}
function dashboardScope() {
  return state.me?.username || state.me?.display_name || "shared";
}
function loadDashboardPrefs(scope) {
  const savedViews = readJSON(storageKey(scope, "views"), []);
  return {
    filters: normalizeDashboardFilters(
      readJSON(storageKey(scope, "filters"), { q: "", stage: "all", due: "all" }),
    ),
    views: Array.isArray(savedViews) ? savedViews : [],
  };
}
function persistDashboardPrefs() {
  const scope = dashboardScope();
  writeJSON(storageKey(scope, "filters"), normalizeDashboardFilters(state.dashboard.filters));
  writeJSON(
    storageKey(scope, "views"),
    (state.dashboard.views || []).slice(0, 12),
  );
}
function saveDashboardFilters(filters) {
  state.dashboard.filters = normalizeDashboardFilters(filters);
  persistDashboardPrefs();
  syncDashboardUrl(state.dashboard.filters);
}
function saveDashboardViews(views) {
  state.dashboard.views = views.slice(0, 12);
  persistDashboardPrefs();
}
function dueLabel(value) {
  return {
    all: "All due states",
    overdue: "Overdue only",
    due_soon: "Due in 7 days",
  }[value] || "All due states";
}
function dashboardFilterSummary(filters) {
  const parts = [];
  if (filters.q) parts.push(`Search “${filters.q}”`);
  if (filters.stage !== "all") parts.push(label(filters.stage));
  if (filters.due !== "all") parts.push(dueLabel(filters.due));
  if (filters.activeOnly) parts.push("Open only");
  return parts.length ? parts.join(" · ") : "All cases";
}
function matchDueFilter(caseItem, due) {
  if (due === "overdue") return caseItem.overdue_follow_ups > 0;
  if (due === "due_soon") {
    if (!caseItem.target_date) return false;
    const target = new Date(`${caseItem.target_date}T12:00:00`);
    if (Number.isNaN(target.getTime())) return false;
    const now = new Date();
    const days = Math.ceil((target.setHours(0, 0, 0, 0) - now.setHours(0, 0, 0, 0)) / 86400000);
    return days >= 0 && days <= 7;
  }
  return true;
}
function filterDashboardCases(cases, filters) {
  const current = normalizeDashboardFilters(filters);
  const q = current.q.toLowerCase();
  return cases.filter(
    (x) =>
      (!q ||
        `${x.case_id} ${x.investigator} ${(x.tags || []).join(" ")}`
          .toLowerCase()
          .includes(q)) &&
      (current.stage === "all" || x.status === current.stage) &&
      (current.activeOnly ? x.status !== "closed" : true) &&
      matchDueFilter(x, current.due),
  );
}
function filtersEqual(a, b) {
  const left = normalizeDashboardFilters(a);
  const right = normalizeDashboardFilters(b);
  return (
    left.q === right.q &&
    left.stage === right.stage &&
    left.due === right.due &&
    left.activeOnly === right.activeOnly
  );
}
function dashboardLensFilters() {
  return {
    all: { q: "", stage: "all", due: "all", activeOnly: false },
    open: { q: "", stage: "all", due: "all", activeOnly: true },
    overdue: { q: "", stage: "all", due: "overdue", activeOnly: true },
    dueSoon: { q: "", stage: "all", due: "due_soon", activeOnly: true },
  };
}
function readRouteState() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [pathPart = "", queryPart = ""] = raw.split("?");
  return {
    parts: pathPart.split("/").filter(Boolean),
    params: new URLSearchParams(queryPart),
  };
}
function dashboardFiltersFromParams(params) {
  const q = params.get("q") || "";
  const stage = params.get("stage") || "all";
  const due = params.get("due") || "all";
  const open = params.get("open") === "1" || params.get("activeOnly") === "1";
  return normalizeDashboardFilters({ q, stage, due, activeOnly: open });
}
function dashboardParamsFromFilters(filters) {
  const current = normalizeDashboardFilters(filters);
  const params = new URLSearchParams();
  if (current.q) params.set("q", current.q);
  if (current.stage !== "all") params.set("stage", current.stage);
  if (current.due !== "all") params.set("due", current.due);
  if (current.activeOnly) params.set("open", "1");
  return params;
}
function dashboardHash(filters) {
  const params = dashboardParamsFromFilters(filters).toString();
  return params ? `#/?${params}` : "#/";
}
function syncDashboardUrl(filters) {
  const target = dashboardHash(filters);
  if (location.hash !== target) history.replaceState(null, "", target);
}
async function copyShareLink() {
  const url = location.href;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(url);
    return;
  }
  const node = document.createElement("textarea");
  node.value = url;
  node.style.position = "fixed";
  node.style.opacity = "0";
  document.body.appendChild(node);
  node.select();
  document.execCommand("copy");
  node.remove();
}
function triggerDownload(filename, content, type = "application/json") {
  const blob = new Blob([content], { type });
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}
function extractDashboardViews(payload) {
  const list = Array.isArray(payload) ? payload : payload?.views;
  if (!Array.isArray(list)) return [];
  return list
    .map((view, index) => {
      const filters = view?.filters ? normalizeDashboardFilters(view.filters) : null;
      const name = String(view?.name || "").trim();
      if (!filters || !name) return null;
      return {
        id: `view-${Date.now().toString(36)}-${index.toString(36)}`,
        name,
        filters,
      };
    })
    .filter(Boolean);
}
function mergeDashboardViews(existing, imported) {
  const next = [...existing];
  for (const view of imported) {
    const duplicate = next.find(
      (item) =>
        item.name.trim().toLowerCase() === view.name.trim().toLowerCase() &&
        filtersEqual(item.filters, view.filters),
    );
    if (!duplicate) next.push(view);
  }
  return next.slice(0, 12);
}
function csvEscape(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}
function downloadCsv(filename, rows, columns = []) {
  const header = columns.length ? columns : Object.keys(rows[0] || {});
  const body = [
    header.join(","),
    ...rows.map((row) => header.map((key) => csvEscape(row[key])).join(",")),
  ].join("\n");
  triggerDownload(filename, `${body}\n`, "text/csv");
}
function isEditableTarget(target) {
  return Boolean(
    target?.closest?.("input, textarea, select, button, [contenteditable='true']"),
  );
}
function bindDashboardHotkeys(actions) {
  if (dashboardHotkeyHandler) {
    document.removeEventListener("keydown", dashboardHotkeyHandler);
  }
  dashboardHotkeyHandler = (event) => {
    if (!(location.hash === "#/" || location.hash.startsWith("#/?"))) return;
    if (isEditableTarget(event.target) && event.key !== "Escape") return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === "/" || event.key === "?") {
      event.preventDefault();
      if (event.key === "?") {
        actions.showShortcuts();
        return;
      }
      actions.focusSearch();
      return;
    }
    if (event.key === "s") {
      event.preventDefault();
      actions.saveView();
      return;
    }
    if (event.key === "e") {
      event.preventDefault();
      actions.exportViews();
      return;
    }
    if (event.key === "i") {
      event.preventDefault();
      actions.importViews();
      return;
    }
    if (event.key === "x") {
      event.preventDefault();
      actions.exportCases();
      return;
    }
    if (event.key === "l") {
      event.preventDefault();
      actions.copyLink();
      return;
    }
    if (event.key === "c") {
      event.preventDefault();
      actions.clearFilters();
      return;
    }
    const lensByKey = {
      "1": "all",
      "2": "open",
      "3": "overdue",
      "4": "dueSoon",
    };
    if (lensByKey[event.key]) {
      event.preventDefault();
      actions.setLens(lensByKey[event.key]);
    }
  };
  document.addEventListener("keydown", dashboardHotkeyHandler);
}
function status(value) {
  return `<span class="status ${esc(value)}">${esc(label(value))}</span>`;
}
function progress(done, total) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return `<div class="progress"><div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div><small>${done} of ${total} complete</small></div>`;
}
function field(name, title, type = "text", opts = {}) {
  const full = opts.full ? " full" : "";
  if (type === "select") {
    return `<div class="field${full}"><label for="f-${name}">${esc(title)}</label><select id="f-${name}" name="${name}" ${opts.required ? "required" : ""}>${opts.options.map((x) => `<option value="${esc(x.value ?? x)}">${esc(x.label ?? label(x))}</option>`).join("")}</select></div>`;
  }
  if (type === "textarea") {
    return `<div class="field${full}"><label for="f-${name}">${esc(title)}</label><textarea id="f-${name}" name="${name}" ${opts.required ? "required" : ""} placeholder="${esc(opts.placeholder || "")}">${esc(opts.value || "")}</textarea></div>`;
  }
  if (type === "file") {
    return `<div class="field${full}"><label for="f-${name}">${esc(title)}</label><input id="f-${name}" name="${name}" type="file" ${opts.required ? "required" : ""} ${opts.accept ? `accept="${esc(opts.accept)}"` : ""}></div>`;
  }
  if (type === "checkbox") {
    return `<label class="check${full}"><input type="checkbox" name="${name}" ${opts.checked ? "checked" : ""}> ${esc(title)}</label>`;
  }
  return `<div class="field${full}"><label for="f-${name}">${esc(title)}</label><input id="f-${name}" name="${name}" type="${type}" value="${esc(opts.value || "")}" ${opts.required ? "required" : ""} placeholder="${esc(opts.placeholder || "")}"></div>`;
}
function openModal({
  title,
  eyebrow = "Add record",
  body,
  submit = "Save",
  success = "Saved",
  onSubmit,
}) {
  document.querySelector("#modalTitle").textContent = title;
  document.querySelector("#modalEyebrow").textContent = eyebrow;
  document.querySelector("#modalBody").innerHTML = body;
  document.querySelector("#modalSubmit").textContent = submit;
  modalForm.onsubmit = async (e) => {
    e.preventDefault();
    const button = e.submitter;
    if (button?.value === "cancel") {
      modal.close();
      return;
    }
    const form = new FormData(modalForm);
    const data = Object.fromEntries(form.entries());
    modal
      .querySelectorAll("input[type=checkbox]")
      .forEach((x) => (data[x.name] = x.checked));
    try {
      button.disabled = true;
      await onSubmit(data);
      modal.close();
      toast(success);
      await route();
    } catch (err) {
      toast(err.message);
    } finally {
      button.disabled = false;
    }
  };
  modal.showModal();
}
function openNoticeModal({
  title,
  eyebrow = "Notice",
  body,
  submit = "Close",
}) {
  document.querySelector("#modalTitle").textContent = title;
  document.querySelector("#modalEyebrow").textContent = eyebrow;
  document.querySelector("#modalBody").innerHTML = body;
  document.querySelector("#modalSubmit").textContent = submit;
  modalForm.onsubmit = (e) => {
    e.preventDefault();
    modal.close();
  };
  modal.showModal();
}
function setChrome(name, routeName) {
  document.querySelector("#crumb").textContent = name;
  document
    .querySelectorAll(".nav-link")
    .forEach((x) =>
      x.classList.toggle("active", x.dataset.route === routeName),
    );
}
async function loadMeta() {
  if (!state.meta) state.meta = await request("/api/meta");
}
async function loadTemplates() {
  if (!state.templates) state.templates = await request("/api/templates");
}
async function dashboard(routeParams = new URLSearchParams()) {
  setChrome("Caseload", "dashboard");
  const [me, cases, queue] = await Promise.all([request("/api/me"), request("/api/cases"), request("/api/queue")]);
  state.me = me;
  state.cases = cases;
  state.queue = queue;
  const persisted = loadDashboardPrefs(dashboardScope());
  const hasUrlFilters = ["q", "stage", "due", "open", "activeOnly"].some((key) => routeParams.has(key));
  state.dashboard = {
    ...persisted,
    filters: hasUrlFilters ? dashboardFiltersFromParams(routeParams) : persisted.filters,
  };
  const filters = state.dashboard.filters;
  const total = state.cases.length,
    open = state.cases.filter((x) => x.status !== "closed").length,
    inq = state.cases.reduce((n, x) => n + x.open_inquiries, 0),
    overdue = state.cases.reduce((n, x) => n + x.overdue_follow_ups, 0),
    roleLabel = state.queue.role === "supervisor" ? "Supervisor view" : "Investigator view";
  const lensFilters = {
    all: { q: "", stage: "all", due: "all", activeOnly: false },
    open: { q: "", stage: "all", due: "all", activeOnly: true },
    overdue: { q: "", stage: "all", due: "overdue", activeOnly: true },
    dueSoon: { q: "", stage: "all", due: "due_soon", activeOnly: true },
  };
  const queueList = (items) =>
    `<div class="record-list">${items.map((item) => `<div class="record"><div><h4>${esc(item.case_id)} · ${esc(item.title)}</h4><p>${esc(item.detail)}${item.due_date ? ` · Due ${fmtDate(item.due_date)}` : ""}</p></div><div class="record-actions">${status(item.priority)}<span class="subtle">${esc(item.kind)}</span></div></div>`).join("") || '<div class="empty"><strong>No items</strong>Nothing is queued for this bucket.</div>'}</div>`;
  app.innerHTML = `<div class="page-head"><div><p class="eyebrow">Caseload command center</p><h1>Active caseload</h1><p>${esc(roleLabel)} · Track required work, follow-ups, and supervisory review.</p></div><div class="page-head-actions"><button class="secondary" data-action="save-view">Save view</button><button class="secondary" data-action="export-views">Export views</button><button class="secondary" data-action="import-views">Import views</button><button class="secondary" data-action="export-cases">Export cases</button><button class="secondary" data-action="copy-link">Copy link</button><button class="secondary" data-action="shortcuts">Shortcuts</button><button class="secondary" data-action="refresh">Refresh</button></div></div><div class="stat-grid"><div class="stat"><div class="stat-label">Assigned cases</div><div class="stat-value">${total}</div><div class="stat-detail">${open} currently active</div></div><div class="stat"><div class="stat-label">Open inquiries</div><div class="stat-value">${inq}</div><div class="stat-detail">Across all cases</div></div><div class="stat"><div class="stat-label">Overdue follow-ups</div><div class="stat-value">${overdue}</div><div class="stat-detail">Needs attention</div></div><div class="stat"><div class="stat-label">Risk flags</div><div class="stat-value">${state.queue.risk.length}</div><div class="stat-detail">${roleLabel}</div></div></div><section class="panel"><div class="panel-head"><div><h2>Command center</h2><p>${esc(state.queue.role_card.detail)}</p></div><span class="subtle">${state.queue.role_card.title}</span></div><div class="stat-grid"><div class="stat"><div class="stat-label">Today</div><div class="stat-value">${state.queue.today.length}</div><div class="stat-detail">Immediate items</div></div><div class="stat"><div class="stat-label">This week</div><div class="stat-value">${state.queue.this_week.length}</div><div class="stat-detail">Near-term items</div></div><div class="stat"><div class="stat-label">Risk</div><div class="stat-value">${state.queue.risk.length}</div><div class="stat-detail">Missing releases, responses, and returns</div></div></div></section><section class="panel"><div class="panel-head"><div><h2>Today</h2><p>Immediate action queue.</p></div><span class="subtle">${state.queue.today.length} queued</span></div>${queueList(state.queue.today)}</section><section class="panel"><div class="panel-head"><div><h2>This week</h2><p>Work due within the next seven days.</p></div><span class="subtle">${state.queue.this_week.length} queued</span></div>${queueList(state.queue.this_week)}</section><section class="panel"><div class="panel-head"><div><h2>Risk watch</h2><p>Missing releases, pending source responses, and supervisor returns.</p></div><span class="subtle">${state.queue.risk.length} queued</span></div>${queueList(state.queue.risk)}</section><section class="panel"><div class="panel-head"><div><h2>Case queue</h2><p data-dashboard-summary>${esc(dashboardFilterSummary(filters))}</p></div><div class="filter-row"><input class="filter" id="caseSearch" value="${esc(filters.q)}" placeholder="Search cases or tags"><select class="filter" id="caseFilter"><option value="all">All stages</option>${state.meta.case_statuses.map((x) => `<option value="${x}" ${filters.stage === x ? "selected" : ""}>${label(x)}</option>`).join("")}</select><select class="filter" id="dueFilter"><option value="all" ${filters.due === "all" ? "selected" : ""}>All due states</option><option value="overdue" ${filters.due === "overdue" ? "selected" : ""}>Overdue only</option><option value="due_soon" ${filters.due === "due_soon" ? "selected" : ""}>Due in 7 days</option></select><label class="check inline"><input type="checkbox" id="activeOnly" ${filters.activeOnly ? "checked" : ""}> Open only</label><button class="secondary" data-action="reset-filters">Reset</button></div></div><div class="filter-toolbar"><div class="chip-row">${[
    ["all", "All cases"],
    ["open", "Open only"],
    ["overdue", "Overdue"],
    ["dueSoon", "Due soon"],
  ]
    .map(
      ([key, text]) =>
        `<button class="chip ${filtersEqual(filters, lensFilters[key]) ? "active" : ""}" data-lens="${key}">${text}</button>`,
    )
    .join("")}</div><div class="saved-view-controls"><span class="subtle">${state.dashboard.views.length} saved locally</span><div class="saved-view-actions"><button class="secondary" data-action="export-views">Export</button><button class="secondary" data-action="import-views">Import</button></div></div></div><div class="saved-view-row">${state.dashboard.views.length ? state.dashboard.views.map((view) => `<div class="saved-view ${filtersEqual(filters, view.filters) ? "active" : ""}"><button class="saved-view-load" data-view-load="${esc(view.id)}"><strong>${esc(view.name)}</strong><span>${esc(dashboardFilterSummary(view.filters))}</span></button><button class="quiet saved-view-delete" data-view-delete="${esc(view.id)}">Delete</button></div>`).join("") : '<div class="empty compact"><strong>No saved views yet</strong>Capture the current filters so this browser can return to them instantly.</div>'}</div><div id="caseTable">${caseTable(state.cases)}</div></section>`;
  const syncDashboardIndicators = () => {
    const current = state.dashboard.filters;
    document.querySelector("[data-dashboard-summary]") &&
      (document.querySelector("[data-dashboard-summary]").textContent =
        dashboardFilterSummary(current));
    document.querySelectorAll("[data-lens]").forEach((button) =>
      button.classList.toggle(
        "active",
        filtersEqual(current, lensFilters[button.dataset.lens]),
      ),
    );
    document.querySelectorAll(".saved-view").forEach((card) => {
      const loadButton = card.querySelector("[data-view-load]");
      const view = state.dashboard.views.find(
        (item) => item.id === loadButton?.dataset.viewLoad,
      );
      card.classList.toggle("active", view ? filtersEqual(current, view.filters) : false);
    });
  };
  syncDashboardIndicators();
  syncDashboardUrl(filters);
  const apply = () => {
    const q = document.querySelector("#caseSearch").value.toLowerCase(),
      stage = document.querySelector("#caseFilter").value,
      due = document.querySelector("#dueFilter").value,
      activeOnly = document.querySelector("#activeOnly").checked;
    saveDashboardFilters({ q, stage, due, activeOnly });
    const rows = filterDashboardCases(state.cases, { q, stage, due, activeOnly });
    document.querySelector("#caseTable").innerHTML = caseTable(rows);
    syncDashboardIndicators();
    bindCaseRows();
  };
  const setFilters = (next) => {
    saveDashboardFilters(next);
    dashboard();
  };
  const dashboardActions = {
    focusSearch: () => document.querySelector("#caseSearch")?.focus(),
    saveView: () => document.querySelector("[data-action=save-view]")?.click(),
    exportViews: () => document.querySelector("[data-action=export-views]")?.click(),
    importViews: () => document.querySelector("[data-action=import-views]")?.click(),
    exportCases: () => document.querySelector("[data-action=export-cases]")?.click(),
    copyLink: () => document.querySelector("[data-action=copy-link]")?.click(),
    clearFilters: () =>
      setFilters({ q: "", stage: "all", due: "all", activeOnly: false }),
    setLens: (lens) =>
      setFilters(
        {
          all: { q: "", stage: "all", due: "all", activeOnly: false },
          open: { q: "", stage: "all", due: "all", activeOnly: true },
          overdue: { q: "", stage: "all", due: "overdue", activeOnly: true },
          dueSoon: { q: "", stage: "all", due: "due_soon", activeOnly: true },
        }[lens] || { q: "", stage: "all", due: "all", activeOnly: false },
      ),
    showShortcuts: () =>
      openNoticeModal({
        title: "Dashboard shortcuts",
        eyebrow: "Caseload command center",
        submit: "Done",
        body: `<div class="shortcut-grid"><div><strong>/</strong><span>Focus the case search</span></div><div><strong>1</strong><span>All cases</span></div><div><strong>2</strong><span>Open only</span></div><div><strong>3</strong><span>Overdue</span></div><div><strong>4</strong><span>Due in 7 days</span></div><div><strong>s</strong><span>Save current view</span></div><div><strong>e</strong><span>Export saved views</span></div><div><strong>i</strong><span>Import saved views</span></div><div><strong>x</strong><span>Export current cases</span></div><div><strong>l</strong><span>Copy share link</span></div><div><strong>c</strong><span>Clear filters</span></div><div><strong>?</strong><span>Open this help</span></div></div>`,
      }),
  };
  document.querySelector("[data-action=refresh]").onclick = route;
  document.querySelector("[data-action=copy-link]").onclick = async () => {
    try {
      await copyShareLink();
      toast("Link copied");
    } catch (err) {
      toast(err.message || "Unable to copy link");
    }
  };
  document.querySelector("[data-action=reset-filters]").onclick = () =>
    setFilters({ q: "", stage: "all", due: "all", activeOnly: false });
  document.querySelector("[data-action=save-view]").onclick = () => {
    const currentFilters = { ...state.dashboard.filters };
    openModal({
      title: "Save current view",
      eyebrow: "Caseload command center",
      body: field("view_name", "View name", "text", {
        required: true,
        placeholder: "Overdue follow-ups",
        value: dashboardFilterSummary(currentFilters),
      }),
      submit: "Save view",
      onSubmit: async (data) => {
        const name = String(data.view_name || "").trim();
        if (!name) throw new Error("Enter a view name");
        const views = [
          ...state.dashboard.views.filter(
            (view) =>
              view.name.toLowerCase() !== name.toLowerCase() &&
              !filtersEqual(view.filters, currentFilters),
          ),
          {
            id: `view-${Date.now().toString(36)}`,
            name,
            filters: currentFilters,
          },
        ];
        saveDashboardViews(views);
      },
    });
  };
  document.querySelectorAll("[data-action=export-views]").forEach(
    (button) =>
      (button.onclick = () => {
    const exportPayload = {
      schema: "backgrounds.dashboard.export/v1",
      app: "backgrounds",
      version: 1,
      exportedAt: new Date().toISOString(),
      scope: dashboardScope(),
      filters: state.dashboard.filters,
      views: state.dashboard.views,
    };
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    triggerDownload(
      `backgrounds-dashboard-${stamp}.json`,
      `${JSON.stringify(exportPayload, null, 2)}\n`,
    );
    toast("Saved views exported");
      }),
  );
  document.querySelectorAll("[data-action=import-views]").forEach(
    (button) =>
      (button.onclick = () => {
        openModal({
      title: "Import saved views",
      eyebrow: "Caseload command center",
      body: `${field("import_file", "Export file", "file", { full: true, accept: ".json,application/json" })}${field("import_json", "Or paste export JSON", "textarea", { full: true, placeholder: "Paste the JSON from another browser or device" })}${field("apply_filters", "Apply exported filters after import", "checkbox", { full: true, checked: true })}<p class="form-note">Imported views merge into local storage. Matching names plus matching filters are skipped.</p>`,
      submit: "Import views",
      success: "Views imported",
      onSubmit: async (data) => {
        let raw = String(data.import_json || "").trim();
        if (!raw) {
          const file = modalForm.querySelector('input[name="import_file"]')?.files?.[0];
          if (file) raw = (await file.text()).trim();
        }
        if (!raw) throw new Error("Choose a JSON file or paste an export");
        let parsed;
        try {
          parsed = JSON.parse(raw);
        } catch {
          throw new Error("The import JSON is not valid");
        }
        const importedViews = extractDashboardViews(parsed);
        if (!importedViews.length) throw new Error("No saved views were found");
        saveDashboardViews(mergeDashboardViews(state.dashboard.views, importedViews));
        if (data.apply_filters && parsed?.filters) {
          saveDashboardFilters(parsed.filters);
        }
      },
    });
      }),
  );
  document.querySelectorAll("[data-action=export-cases]").forEach(
    (button) =>
      (button.onclick = () => {
        const rows = filterDashboardCases(state.cases, state.dashboard.filters).map((c) => ({
          case_id: c.case_id,
          title: c.title,
          investigator: c.investigator || "",
          status: c.status,
          review_status: c.review_status,
          priority: c.priority,
          target_date: c.target_date || "",
          open_inquiries: c.open_inquiries,
          overdue_follow_ups: c.overdue_follow_ups,
          open_discrepancies: c.open_discrepancies,
          open_documents: c.open_documents,
          tags: (c.tags || []).join(" | "),
        }));
        const stamp = new Date().toISOString().replace(/[:.]/g, "-");
        downloadCsv(
          `backgrounds-cases-${stamp}.csv`,
          rows,
          [
            "case_id",
            "title",
            "investigator",
            "status",
            "review_status",
            "priority",
            "target_date",
            "open_inquiries",
            "overdue_follow_ups",
            "open_discrepancies",
            "open_documents",
            "tags",
          ],
        );
        toast(rows.length ? "Case list exported" : "Exported empty case list");
      }),
  );
  document.querySelector("[data-action=shortcuts]").onclick = dashboardActions.showShortcuts;
  document.querySelector("#caseSearch").oninput = apply;
  document.querySelector("#caseFilter").onchange = apply;
  document.querySelector("#dueFilter").onchange = apply;
  document.querySelector("#activeOnly").onchange = apply;
  document.querySelectorAll("[data-lens]").forEach(
    (button) =>
      (button.onclick = () => dashboardActions.setLens(button.dataset.lens)),
  );
  document.querySelectorAll("[data-view-load]").forEach(
    (button) =>
      (button.onclick = () => {
        const view = state.dashboard.views.find((item) => item.id === button.dataset.viewLoad);
        if (!view) return;
        setFilters(view.filters);
      }),
  );
  document.querySelectorAll("[data-view-delete]").forEach(
    (button) =>
      (button.onclick = () => {
        saveDashboardViews(
          state.dashboard.views.filter((item) => item.id !== button.dataset.viewDelete),
        );
        dashboard();
      }),
  );
  bindDashboardHotkeys(dashboardActions);
  bindCaseRows();
}
function caseTable(cases) {
  if (!cases.length)
    return `<div class="empty"><strong>No matching cases</strong>Adjust the queue filters or create a new case.</div>`;
  return `<div class="table-wrap"><table><thead><tr><th>Case</th><th>Stage / review</th><th>Completion</th><th>Open work</th><th>Target</th><th>Priority</th></tr></thead><tbody>${cases.map((c) => `<tr data-case="${esc(c.case_id)}"><td><span class="case-id">${esc(c.case_id)}</span><span class="subtle">${(c.tags || []).map((x) => "· " + esc(x)).join(" ") || "No tags"}</span></td><td>${status(c.status)}<span class="subtle">${esc(label(c.review_status))}</span></td><td>${progress(c.areas_complete, c.areas_total)}</td><td>${c.open_inquiries} inquiries<span class="subtle">${c.overdue_follow_ups} overdue · ${c.open_discrepancies} discrepancies · ${c.open_documents} documents</span></td><td>${fmtDate(c.target_date)}</td><td>${status(c.priority)}</td></tr>`).join("")}</tbody></table></div>`;
}
function bindCaseRows() {
  document
    .querySelectorAll("[data-case]")
    .forEach(
      (x) =>
        (x.onclick = () =>
          (location.hash = `#/case/${encodeURIComponent(x.dataset.case)}`)),
    );
}
async function caseView(id) {
  setChrome(id, "dashboard");
  await loadTemplates();
  state.current = await request(`/api/cases/${encodeURIComponent(id)}`);
  const c = state.current,
    a = c.audit.metrics,
    pct = Math.round((a.areas_complete / a.areas_total) * 100);
  app.innerHTML = `<div class="case-hero"><div class="case-title"><button class="back" aria-label="Back to caseload">←</button><div><p class="eyebrow">Background investigation</p><h1>${esc(c.case_id)}</h1><div class="case-meta">${esc(c.investigator || "Unassigned investigator")} · Target ${fmtDate(c.target_date)}</div></div></div><div class="case-controls"><select id="caseStatus" aria-label="Case stage">${state.meta.case_statuses.map((x) => `<option value="${x}" ${x === c.status ? "selected" : ""}>${label(x)}</option>`).join("")}</select><button class="primary" data-action="add-inquiry">Add inquiry</button></div></div><div class="case-grid"><section class="panel"><div class="tabs">${[
    ["overview", "Overview"],
    ["inquiries", "Inquiries"],
    ["discrepancies", "Discrepancies"],
    ["interviews", "Interviews"],
    ["sources", "Sources"],
    ["trace", "Trace"],
    ["phs", "PHS"],
    ["timeline", "Timeline"],
    ["documents", "Documents"],
    ["attachments", "Files"],
    ["review", "Review"],
    ["report", "Report workspace"],
  ]
    .map(
      ([x, y]) =>
        `<button class="tab ${state.tab === x ? "active" : ""}" data-tab="${x}">${y}</button>`,
    )
    .join(
      "",
    )}</div><div class="tab-content" id="tabContent"></div></section><aside class="side-column"><section class="panel side-panel"><h3>Readiness</h3><div class="audit-score"><div class="ring" style="--pct:${pct}%"><strong>${pct}%</strong></div><div><strong>${a.areas_complete} / ${a.areas_total} areas</strong><p>${c.audit.errors.length ? "Review required before close" : pct === 100 ? "No blocking errors" : "Complete required coverage"}</p></div></div><div class="issues">${[...c.audit.errors.slice(0, 3).map((x) => `<div class="issue error">${esc(x)}</div>`), ...c.audit.warnings.slice(0, 2).map((x) => `<div class="issue">${esc(x)}</div>`)].join("") || (pct === 100 ? '<div class="issue">No current audit warnings.</div>' : '<div class="issue">Full closeout checks activate at quality review.</div>')}</div></section><section class="panel side-panel"><h3>Recent activity</h3><div class="activity">${c.activity
    .slice(-6)
    .reverse()
    .map(
      (x) =>
        `<div class="activity-item"><div><strong>${esc(label(x.action))}</strong>${esc(x.detail)}<span class="subtle">${new Date(x.at).toLocaleString()}</span></div></div>`,
    )
    .join("")}</div></section></aside></div>`;
  document.querySelector(".back").onclick = () => (location.hash = "#/");
  document.querySelector("#caseStatus").onchange = async (e) => {
    await request(`/api/cases/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ status: e.target.value }),
    });
    toast("Case stage updated");
    caseView(id);
  };
  document.querySelectorAll("[data-tab]").forEach(
    (x) =>
      (x.onclick = () => {
        state.tab = x.dataset.tab;
        caseView(id);
      }),
  );
  document.querySelector("[data-action=add-inquiry]").onclick = addInquiry;
  renderTab();
}
function renderTab() {
  const c = state.current,
    node = document.querySelector("#tabContent");
  if (state.tab === "overview")
    node.innerHTML = `<div class="section-toolbar"><div><p class="eyebrow">Required coverage</p><h3>Twelve areas of investigation</h3></div><span class="subtle">Select an area to write its narrative</span></div><div class="area-grid">${Object.entries(
      state.meta.areas,
    )
      .map(
        ([key, name], i) =>
          `<div class="area-card ${c.areas[key].status}" data-area="${key}"><span class="area-num">${String(i + 1).padStart(2, "0")}</span><div><strong>${esc(name)}</strong><small>${label(c.areas[key].status)}</small></div></div>`,
      )
      .join("")}</div>`;
  else if (state.tab === "inquiries")
    node.innerHTML = templateBatchWorkspace(c) + records(
      "Inquiries",
      "Track every request, response, and follow-up.",
      c.inquiries,
      "add-inquiry",
      (x) =>
        `<div class="record"><div><h4>${esc(x.source_label)} <span class="subtle">${esc(x.id)} · ${esc(state.meta.areas[x.area])}</span></h4><p>${esc(label(x.source_type))} · Follow-up ${fmtDate(x.follow_up_due)}${x.response_summary ? `<br>${esc(x.response_summary)}` : ""}</p></div><div class="record-actions">${status(x.status)}<button class="quiet" data-edit-inquiry="${x.id}">Update</button></div></div>`,
    );
  else if (state.tab === "discrepancies")
    node.innerHTML = `<div class="section-toolbar"><div><p class="eyebrow">Discrepancy comparer</p><h3>Candidate statement matrix</h3><p>Compare the candidate account, contrary information, response, corroboration, and resolution in one view.</p></div><button class="secondary" data-action="add-discrepancy">Add</button></div>${discrepancyMatrix(c.discrepancies)}<div class="section-toolbar"><div><h3>Discrepancy log</h3><span class="subtle">Keep the full evidentiary trail attached to each conflict.</span></div></div><div class="cards">${c.discrepancies.map((x) => `<div class="record"><div><h4>${esc(x.title)} <span class="subtle">${esc(x.id)} · ${esc(state.meta.areas[x.area])}</span></h4><p><strong>Candidate:</strong> ${esc(x.candidate_statement)}<br><strong>Contrary:</strong> ${esc(x.contrary_information)}</p></div><div class="record-actions">${status(x.status)}<button class="quiet" data-edit-discrepancy="${x.id}">Update</button></div></div>`).join("") || '<div class="empty"><strong>No discrepancies recorded</strong>Add the first conflict when it appears.</div>'}</div>`;
  else if (state.tab === "interviews")
    node.innerHTML = interviewPlanWorkspace(c) + records(
      "Interviews",
      "Document the event and approved recording locator.",
      c.interviews,
      "add-interview",
      (x) =>
        `<div class="record"><div><h4>${esc(label(x.kind))} <span class="subtle">${esc(x.id)} · ${fmtDate(x.date)}</span></h4><p>${esc(x.participant_role)}${x.notes ? ` · ${esc(x.notes)}` : ""}${x.recording_locator ? `<br>${esc(x.recording_locator)}` : ""}</p></div><div>${x.uploaded_to_esoph ? status("complete") : status("planned")}</div></div>`,
    );
  else if (state.tab === "sources")
    node.innerHTML = records(
      "Source register",
      "Reference approved-system records without duplicating sensitive contents.",
      c.sources,
      "add-source",
      (x) =>
        `<div class="record"><div><h4>${esc(x.label)} <span class="subtle">${esc(x.id)} · ${esc(label(x.kind))}</span></h4><p>${esc(x.location)}${x.notes ? ` · ${esc(x.notes)}` : ""}</p></div></div>`,
    );
  else if (state.tab === "trace")
    node.innerHTML = traceWorkspace(c);
  else if (state.tab === "phs")
    node.innerHTML = records(
      "PHS change ledger",
      "Track every changed field, what it used to say, and how the change was dispositioned.",
      c.phs_changes,
      "add-phs-change",
      (x) =>
        `<div class="record"><div><h4>${esc(x.field_label)} <span class="subtle">${esc(x.id)}</span></h4><p><strong>Prior:</strong> ${esc(x.prior_value || "Not entered")}<br><strong>Current:</strong> ${esc(x.current_value || "Not entered")}<br><strong>Reported:</strong> ${esc(x.reported_at || "Not entered")}<br>${esc(x.disposition || "No disposition yet")}</p></div><div class="record-actions">${status(x.disposition ? "recorded" : "pending")}<button class="quiet" data-edit-phs-change="${x.id}">Update</button></div></div>`,
    );
  else if (state.tab === "timeline")
    node.innerHTML = records(
      "Life history timeline",
      "Keep employment, residence, education, military, relationship, and legal history in order.",
      c.timeline,
      "add-timeline",
      (x) =>
        `<div class="record"><div><h4>${esc(x.label)} <span class="subtle">${esc(x.id)} · ${esc(label(x.category))}</span></h4><p>${esc(fmtDate(x.start_date))} - ${esc(x.end_date ? fmtDate(x.end_date) : "Open-ended")}${x.notes ? `<br>${esc(x.notes)}` : ""}<br>${esc((x.source_ids || []).join(" · ")) || "No source identifiers"}</p></div><div class="record-actions"><button class="quiet" data-edit-timeline="${x.id}">Update</button></div></div>`,
    );
  else if (state.tab === "documents")
    node.innerHTML = records(
      "Document control",
      "Track requests, receipts, and verification dates without hiding what is still missing.",
      c.documents,
      "add-document",
      (x) =>
        `<div class="record"><div><h4>${esc(x.title)} <span class="subtle">${esc(x.id)} · ${esc(label(x.status))}</span></h4><p>${x.due_date ? `Due ${fmtDate(x.due_date)} · ` : ""}${x.required_original ? "Original required · " : ""}${x.source_locator ? esc(x.source_locator) : "No locator"}${x.notes ? `<br>${esc(x.notes)}` : ""}${x.received_at ? `<br>Received ${fmtDate(x.received_at)}` : ""}${x.verified_at ? ` · Verified ${fmtDate(x.verified_at)}` : ""}${x.returned_at ? ` · Returned ${fmtDate(x.returned_at)}` : ""}</p></div><div class="record-actions"><button class="quiet" data-edit-document="${x.id}">Update</button></div></div>`,
    );
  else if (state.tab === "attachments") attachmentsWorkspace();
  else if (state.tab === "review") reviewWorkspace();
  else reportWorkspace();
  bindTabActions();
  if (state.tab === "overview") renderChecklist(c);
}

function renderChecklist(c) {
  const items = c.audit.checklist || [];
  const incomplete = items.filter((item) => !item.complete).length;
  document
    .querySelector("#tabContent")
    ?.insertAdjacentHTML(
      "afterbegin",
      `<section class="readiness-plan"><div><p class="eyebrow">Guided case plan</p><h3>${incomplete ? `${incomplete} steps still need attention` : "Case is ready for final review"}</h3><p>Use this sequence to keep the file reviewable. It does not replace agency policy or supervisor direction.</p></div><div class="checklist">${items.map((item) => `<div class="check-item ${item.complete ? "complete" : ""}"><span>${item.complete ? "✓" : "○"}</span><div><strong>${esc(item.label)}</strong>${item.detail ? `<small>${esc(item.detail)}</small>` : ""}</div></div>`).join("")}</div></section>${(c.audit.timeline_findings || []).length || (c.audit.document_findings || []).length || (c.audit.phs_findings || []).length || (c.audit.interview_plan_findings || []).length || (c.audit.source_trace_map?.orphan_source_ids || []).length ? `<section class="readiness-plan"><div><p class="eyebrow">Review prompts</p><h3>Timeline, interviews, traceability, and document follow-up</h3><p>These are neutral prompts for review, not conclusions.</p></div><div class="issues">${(c.audit.timeline_findings || []).map((item) => `<div class="issue">${esc(item.message)}</div>`).join("")}${(c.audit.phs_findings || []).map((item) => `<div class="issue">${esc(item.message)}</div>`).join("")}${(c.audit.document_findings || []).map((item) => `<div class="issue">${esc(item.message)}</div>`).join("")}${(c.audit.interview_plan_findings || []).map((item) => `<div class="issue">${esc(item.message)}</div>`).join("")}${(c.audit.source_trace_map?.orphan_source_ids || []).map((item) => `<div class="issue">Unregistered source identifier referenced: ${esc(item)}</div>`).join("")}</div></section>` : ""}`,
    );
}
async function attachmentsWorkspace() {
  const c = state.current,
    node = document.querySelector("#tabContent");
  node.innerHTML =
    '<div class="empty"><strong>Loading controlled files…</strong></div>';
  const items = await request(
    `/api/cases/${encodeURIComponent(c.case_id)}/attachments`,
  );
  node.innerHTML = `<div class="section-toolbar"><div><p class="eyebrow">Controlled records</p><h3>Attachments and exports</h3><p>Allowed: PDF, PNG, JPEG, and UTF-8 text · 10 MB maximum.</p></div><label class="secondary">Upload file<input id="attachmentInput" type="file" accept="application/pdf,image/png,image/jpeg,text/plain" hidden></label></div><div class="editor-actions"><a class="secondary" href="/api/cases/${encodeURIComponent(c.case_id)}/export?format=docx">Export DOCX</a><a class="secondary" href="/api/cases/${encodeURIComponent(c.case_id)}/export?format=pdf">Export PDF</a><a class="secondary" href="/api/cases/${encodeURIComponent(c.case_id)}/export?format=json">Export JSON package</a></div><div class="record-list">${items.map((x) => `<div class="record"><div><h4>${esc(x.filename)} <span class="subtle">${esc(x.id)}</span></h4><p>${esc(x.media_type)} · ${(x.size / 1024).toFixed(1)} KB · SHA-256 ${esc(x.sha256.slice(0, 16))}…</p></div><a class="quiet" href="/api/cases/${encodeURIComponent(c.case_id)}/attachments/${encodeURIComponent(x.id)}">Download</a></div>`).join("") || '<div class="empty"><strong>No attachments</strong>Store only records permitted in this environment.</div>'}</div>`;
  document.querySelector("#attachmentInput").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      toast("File exceeds 10 MB");
      return;
    }
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    await request(`/api/cases/${encodeURIComponent(c.case_id)}/attachments`, {
      method: "POST",
      body: JSON.stringify({
        filename: file.name,
        media_type: file.type,
        content_base64: content,
      }),
    });
    toast("File uploaded and verified");
    await attachmentsWorkspace();
  };
}
function reviewWorkspace() {
  const c = state.current,
    r = c.review || { status: "not_submitted", comments: [] },
    node = document.querySelector("#tabContent");
  node.innerHTML = `<div class="section-toolbar"><div><p class="eyebrow">Supervisory workflow</p><h3>Review and disposition</h3><p>Current status: ${status(r.status)}</p></div></div><div class="report-editor"><div class="field-row"><label>Priority<select id="reviewPriority">${["low", "normal", "high", "urgent"].map((x) => `<option value="${x}" ${x === (c.priority || "normal") ? "selected" : ""}>${label(x)}</option>`).join("")}</select></label><label>Tags<input id="reviewTags" value="${esc((c.tags || []).join(", "))}" placeholder="region, expedited"></label></div><label>Review comment<textarea id="reviewComment" placeholder="Document the review decision or requested correction"></textarea></label><div class="editor-actions"><button class="secondary" data-review="save">Save details</button><button class="secondary" data-review="submit">Submit for review</button><button class="secondary" data-review="return">Return for correction</button><button class="primary" data-review="approve">Approve</button></div></div><div class="record-list">${
    (r.comments || [])
      .slice()
      .reverse()
      .map(
        (x) =>
          `<div class="record"><div><h4>${esc(x.by)} <span class="subtle">${new Date(x.at).toLocaleString()}</span></h4><p>${esc(x.text)}</p></div></div>`,
      )
      .join("") ||
    '<div class="empty"><strong>No review comments</strong>Comments remain attached to the case.</div>'
  }</div>`;
  document.querySelectorAll("[data-review]").forEach(
    (button) =>
      (button.onclick = async () => {
        const action = button.dataset.review,
          body = {
            priority: document.querySelector("#reviewPriority").value,
            tags: document
              .querySelector("#reviewTags")
              .value.split(",")
              .map((x) => x.trim())
              .filter(Boolean),
          };
        if (action !== "save") {
          body.review_action = action;
          body.review_comment = document.querySelector("#reviewComment").value;
        }
        await request(`/api/cases/${encodeURIComponent(c.case_id)}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        toast("Review workflow updated");
        await caseView(c.case_id);
      }),
  );
}
function records(title, subtitle, items, action, render) {
  return `<div class="section-toolbar"><div><h3>${title}</h3><span class="subtle">${subtitle}</span></div><button class="secondary" data-action="${action}">Add</button></div><div class="cards">${items.map(render).join("") || `<div class="empty"><strong>No ${title.toLowerCase()} recorded</strong>Add the first record when work begins.</div>`}</div>`;
}
function templateBatchWorkspace(c) {
  const templates = state.templates?.inquiries || [];
  const existing = new Set((c.inquiries || []).map((item) => item.template_id).filter(Boolean));
  return `<section class="readiness-plan"><div><p class="eyebrow">Batch inquiry builder</p><h3>Create standard requests from templates</h3><p>Select the likely requests once, preview the resulting queue, then create them in one step.</p></div><div class="field-row"><label>Follow-up date<input id="batchFollowUp" type="date"></label><button class="primary" data-action="batch-inquiries">Create selected</button></div><div class="template-grid">${templates.map((item) => `<label class="check full ${existing.has(item.id) ? "disabled" : ""}"><input type="checkbox" class="template-select" value="${esc(item.id)}" ${existing.has(item.id) ? "checked disabled" : ""}> <strong>${esc(item.label)}</strong><small>${esc(label(item.area))} · ${esc(item.method)}${item.release_required ? " · release required" : ""}${existing.has(item.id) ? " · already added" : ""}</small></label>`).join("") || '<div class="empty"><strong>No templates available</strong>Load the inquiry template catalog first.</div>'}</div><div class="record-list" id="batchPreview"></div></section>`;
}
function refreshBatchPreview() {
  const node = document.querySelector("#batchPreview");
  if (!node) return;
  const templates = state.templates?.inquiries || [];
  const due = document.querySelector("#batchFollowUp")?.value || "";
  const selected = [...document.querySelectorAll(".template-select:checked")].map((x) => x.value);
  const existing = new Set((state.current?.inquiries || []).map((item) => item.template_id).filter(Boolean));
  const preview = selected.map((id) => templates.find((item) => item.id === id)).filter(Boolean).map((item) => ({
    ...item,
    follow_up_due: due || fmtDateISOPlus(item.follow_up_days),
    skipped: existing.has(item.id),
  }));
  node.innerHTML = preview.length
    ? preview.map((item) => `<div class="record"><div><h4>${esc(item.label)} <span class="subtle">${esc(label(item.area))}</span></h4><p>${esc(item.method)}${item.release_required ? " · release required" : ""}<br>Follow-up ${fmtDate(item.follow_up_due)}</p></div><div class="record-actions">${item.skipped ? status("planned") : status("ready")}</div></div>`).join("")
    : '<div class="empty"><strong>No templates selected</strong>Choose one or more inquiry templates to preview the batch.</div>';
}
function fmtDateISOPlus(days) {
  const date = new Date();
  date.setDate(date.getDate() + Number(days || 0));
  return date.toISOString().slice(0, 10);
}
function listOrNone(items) {
  return items && items.length ? items.map((x) => esc(x)).join(" · ") : "None linked";
}
function interviewPlanWorkspace(c) {
  return `<section class="readiness-plan"><div><p class="eyebrow">Interview planning</p><h3>Planning packets</h3><p>Link the topic, the source identifiers, any related discrepancies, and the approved recording locator before the interview happens.</p></div><div class="section-toolbar"><span class="subtle">${c.interview_plans.length} packets</span><button class="secondary" data-action="add-interview-plan">Add packet</button></div><div class="cards">${c.interview_plans.map((x) => `<div class="record"><div><h4>${esc(x.subject)} <span class="subtle">${esc(x.id)}</span></h4><p>${esc(x.question)}<br><strong>Sources:</strong> ${listOrNone(x.source_ids || [])}<br><strong>Discrepancies:</strong> ${listOrNone(x.discrepancy_ids || [])}<br><strong>Locator:</strong> ${esc(x.recording_locator || "Not entered")}${x.notes ? `<br>${esc(x.notes)}` : ""}</p></div><div class="record-actions">${status(x.status || "planned")}<button class="quiet" data-edit-interview-plan="${x.id}">Update</button></div></div>`).join("") || '<div class="empty"><strong>No interview plans recorded</strong>Add a packet before interviewing or clarifying discrepancies.</div>'}</div></section>`;
}
function traceWorkspace(c) {
  const trace = c.audit.source_trace_map || { sources: [], orphan_source_ids: [] };
  return `<section class="readiness-plan"><div><p class="eyebrow">Traceability</p><h3>Source-to-finding map</h3><p>Every registered source should show where it is cited. Unregistered identifiers are surfaced separately so they can be corrected.</p></div><div class="stat-grid"><div class="stat"><div class="stat-label">Registered sources</div><div class="stat-value">${trace.sources.length}</div></div><div class="stat"><div class="stat-label">Unregistered refs</div><div class="stat-value">${trace.orphan_source_ids.length}</div></div></div><div class="record-list">${trace.sources.map((x) => `<div class="record"><div><h4>${esc(x.source_id)} <span class="subtle">${esc(x.label)}</span></h4><p>${esc(x.kind || "Source")}${x.location ? ` · ${esc(x.location)}` : ""}<br><strong>References:</strong> ${listOrNone(x.references || [])}</p></div></div>`).join("") || '<div class="empty"><strong>No registered sources</strong>Add a source before expecting trace links.</div>'}</div>${trace.orphan_source_ids.length ? `<div class="issues">${trace.orphan_source_ids.map((id) => `<div class="issue">Unregistered source identifier referenced: ${esc(id)}</div>`).join("")}</div>` : ""}</section>`;
}
function discrepancyMatrix(items) {
  if (!items.length)
    return '<div class="empty"><strong>No discrepancies recorded</strong>Add the first conflict when it appears.</div>';
  return `<div class="table-wrap"><table><thead><tr><th>Issue</th><th>Candidate</th><th>Contrary</th><th>Response</th><th>Corroboration</th><th>Resolution</th><th>Status</th></tr></thead><tbody>${items.map((item) => `<tr><td><strong>${esc(item.id)}</strong><div class="subtle">${esc(item.title)}<br>${esc(label(item.area))}</div></td><td>${esc(item.candidate_statement || "Not entered")}</td><td>${esc(item.contrary_information || "Not entered")}</td><td>${esc(item.candidate_response || "Not entered")}</td><td>${esc(item.corroboration || "Not entered")}</td><td>${esc(item.resolution || "Not entered")}</td><td>${status(item.status)}</td></tr>`).join("")}</tbody></table></div>`;
}
function reportWorkspace() {
  const c = state.current,
    sections = [
      ...Object.entries(state.meta.dimensions).map(([key, name]) => ({
        type: "dimensions",
        key,
        name,
      })),
      {
        type: "bias",
        key: "bias_relevant_findings",
        name: "Bias-Relevant Findings",
      },
      ...Object.entries(state.meta.areas).map(([key, name]) => ({
        type: "areas",
        key,
        name,
      })),
    ];
  if (!state.reportSection) state.reportSection = sections[0];
  const s =
      sections.find(
        (x) =>
          x.type === state.reportSection.type &&
          x.key === state.reportSection.key,
      ) || sections[0],
    data = s.type === "bias" ? c.bias_relevant_findings : c[s.type][s.key],
    complete = Object.values(c.areas).filter(
      (x) => x.status === "complete",
    ).length;
  document.querySelector("#tabContent").innerHTML =
    `<section class="report-hero"><div><p class="eyebrow">Report draft</p><h3>Build a review-ready case report</h3><p>Write source-grounded sections here, then open the finished print layout for supervisory review or export.</p></div><div class="report-hero-stats"><span><b>${complete}/12</b> areas complete</span><span><b>${c.sources.length}</b> registered sources</span></div><div class="report-hero-actions"><a class="secondary" href="/api/cases/${encodeURIComponent(c.case_id)}/report" target="_blank">Open print preview</a><a class="primary" href="/api/cases/${encodeURIComponent(c.case_id)}/export?format=pdf">Download PDF</a></div></section><div class="report-layout"><div class="report-nav"><p class="eyebrow">POST dimensions</p>${sections.map((x, i) => `${i === 10 ? '<p class="eyebrow">Bias assessment information</p>' : ""}${i === 11 ? '<p class="eyebrow">Required areas</p>' : ""}<button class="${x.key === s.key && x.type === s.type ? "active" : ""}" data-report-type="${x.type}" data-report-key="${x.key}">${esc(x.name)}</button>`).join("")}</div><div class="editor"><div class="editor-heading"><div><p class="eyebrow">Narrative section</p><label>${esc(s.name)}</label></div>${s.type === "areas" ? `<select id="sectionStatus" class="filter"><option value="not_started">Not started</option><option value="in_progress">In progress</option><option value="complete">Complete</option><option value="not_applicable">Not applicable</option></select>` : ""}</div><textarea id="sectionNarrative" placeholder="Enter source-grounded investigative narrative…">${esc(data.narrative)}</textarea><div class="editor-help">Source identifiers, comma separated. Every material finding should be traceable.</div><input id="sectionSources" class="filter" style="width:100%" value="${esc(data.source_ids.join(", "))}" placeholder="SRC-0001, SRC-0002"><div class="editor-actions"><a class="secondary" href="/api/cases/${encodeURIComponent(c.case_id)}/report" target="_blank">Open print preview</a><button class="primary" data-action="save-section">Save section</button></div></div></div>`;
  if (s.type === "areas")
    document.querySelector("#sectionStatus").value = data.status;
  document.querySelectorAll("[data-report-key]").forEach(
    (x) =>
      (x.onclick = () => {
        state.reportSection = {
          type: x.dataset.reportType,
          key: x.dataset.reportKey,
        };
        reportWorkspace();
      }),
  );
  document.querySelector("[data-action=save-section]").onclick = async () => {
    const body = {
      narrative: document.querySelector("#sectionNarrative").value,
      source_ids: document
        .querySelector("#sectionSources")
        .value.split(",")
        .map((x) => x.trim())
        .filter(Boolean),
    };
    if (s.type === "areas")
      body.status = document.querySelector("#sectionStatus").value;
    const endpoint = s.type === "bias" ? "bias" : `${s.type}/${s.key}`;
    await request(`/api/cases/${encodeURIComponent(c.case_id)}/${endpoint}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    toast("Report section saved");
    await caseView(c.case_id);
  };
}
function bindTabActions() {
  document
    .querySelectorAll("[data-action=add-inquiry]")
    .forEach((x) => (x.onclick = addInquiry));
  document
    .querySelector("[data-action=add-discrepancy]")
    ?.addEventListener("click", addDiscrepancy);
  document
    .querySelector("[data-action=add-interview]")
    ?.addEventListener("click", addInterview);
  document
    .querySelector("[data-action=add-interview-plan]")
    ?.addEventListener("click", addInterviewPlan);
  document
    .querySelector("[data-action=add-source]")
    ?.addEventListener("click", addSource);
  document
    .querySelector("[data-action=add-phs-change]")
    ?.addEventListener("click", addPhsChange);
  document
    .querySelector("[data-action=add-timeline]")
    ?.addEventListener("click", addTimeline);
  document
    .querySelector("[data-action=add-document]")
    ?.addEventListener("click", addDocument);
  document.querySelectorAll("[data-area]").forEach(
    (x) =>
      (x.onclick = () => {
        state.tab = "report";
        state.reportSection = { type: "areas", key: x.dataset.area };
        caseView(state.current.case_id);
      }),
  );
  document
    .querySelectorAll("[data-edit-inquiry]")
    .forEach((x) => (x.onclick = () => editInquiry(x.dataset.editInquiry)));
  document
    .querySelectorAll("[data-edit-discrepancy]")
    .forEach(
      (x) => (x.onclick = () => editDiscrepancy(x.dataset.editDiscrepancy)),
    );
  document
    .querySelectorAll("[data-edit-phs-change]")
    .forEach((x) => (x.onclick = () => editPhsChange(x.dataset.editPhsChange)));
  document
    .querySelectorAll("[data-edit-timeline]")
    .forEach((x) => (x.onclick = () => editTimeline(x.dataset.editTimeline)));
  document
    .querySelectorAll("[data-edit-document]")
    .forEach((x) => (x.onclick = () => editDocument(x.dataset.editDocument)));
  document
    .querySelectorAll("[data-edit-interview-plan]")
    .forEach((x) => (x.onclick = () => editInterviewPlan(x.dataset.editInterviewPlan)));
  if (state.tab === "inquiries") {
    document.querySelectorAll(".template-select").forEach((x) => (x.onchange = refreshBatchPreview));
    const due = document.querySelector("#batchFollowUp");
    if (due) due.onchange = refreshBatchPreview;
    document.querySelector("[data-action=batch-inquiries]")?.addEventListener("click", batchCreateInquiries);
    refreshBatchPreview();
  }
}
async function batchCreateInquiries() {
  const template_ids = [...document.querySelectorAll(".template-select:checked")].map((x) => x.value);
  const follow_up_due = document.querySelector("#batchFollowUp")?.value || "";
  if (!template_ids.length) {
    toast("Select at least one template");
    return;
  }
  await request(`/api/cases/${encodeURIComponent(state.current.case_id)}/inquiries/batch`, {
    method: "POST",
    body: JSON.stringify({ template_ids, follow_up_due }),
  });
  state.tab = "inquiries";
  await caseView(state.current.case_id);
}
function addCase() {
  openModal({
    title: "Create case workspace",
    eyebrow: "Local case",
    submit: "Create case",
    body:
      field("case_id", "Case identifier", "text", {
        required: true,
        placeholder: "2026-0142",
      }) +
      field("investigator", "Investigator") +
      field("target_date", "Target completion", "date") +
      `<div class="field full"><span class="subtle">Use a non-PII case identifier. Candidate information must remain in approved systems.</span></div>`,
    onSubmit: async (d) => {
      await request("/api/cases", { method: "POST", body: JSON.stringify(d) });
      location.hash = `#/case/${encodeURIComponent(d.case_id)}`;
    },
  });
}
function addInquiry() {
  openModal({
    title: "Add inquiry",
    body:
      field("area", "Investigation area", "select", {
        options: Object.entries(state.meta.areas).map(([value, label]) => ({
          value,
          label,
        })),
      }) +
      field("source_type", "Source type", "text", {
        required: true,
        placeholder: "Employer, court, reference…",
      }) +
      field("source_label", "Source label", "text", {
        required: true,
        placeholder: "Use a safe label",
      }) +
      field("method", "Approved method") +
      field("follow_up_due", "Follow-up date", "date") +
      field("release_required", "Release required", "checkbox") +
      field("release_attached", "Release attached", "checkbox"),
    onSubmit: async (d) => {
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/inquiries`,
        { method: "POST", body: JSON.stringify(d) },
      );
      state.tab = "inquiries";
      await caseView(state.current.case_id);
    },
  });
}
function editInquiry(id) {
  const item = state.current.inquiries.find((x) => x.id === id);
  openModal({
    title: `Update ${id}`,
    body:
      field("status", "Status", "select", {
        options: [
          "planned",
          "sent",
          "received",
          "declined",
          "nonresponsive",
          "not_applicable",
        ].map((x) => ({ value: x, label: label(x) })),
      }) +
      field("follow_up_due", "Follow-up date", "date", {
        value: item.follow_up_due,
      }) +
      field("response_summary", "Response summary", "textarea", {
        full: true,
        value: item.response_summary,
      }) +
      field("release_attached", "Release attached", "checkbox", {
        checked: item.release_attached,
      }),
    onSubmit: async (d) => {
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/inquiries/${id}`,
        { method: "PATCH", body: JSON.stringify(d) },
      );
      await caseView(state.current.case_id);
    },
  });
  document.querySelector("[name=status]").value = item.status;
}
function addDiscrepancy() {
  openModal({
    title: "Record discrepancy",
    body:
      field("title", "Issue title", "text", { required: true }) +
      field("area", "Investigation area", "select", {
        options: Object.entries(state.meta.areas).map(([value, label]) => ({
          value,
          label,
        })),
      }) +
      field("candidate_statement", "Candidate statement", "textarea", {
        required: true,
        full: true,
      }) +
      field("contrary_information", "Contrary information", "textarea", {
        required: true,
        full: true,
      }) +
      field("source_ids", "Source identifiers", "text", {
        full: true,
        placeholder: "SRC-0001, SRC-0002",
      }),
    onSubmit: async (d) => {
      d.source_ids = d.source_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/discrepancies`,
        { method: "POST", body: JSON.stringify(d) },
      );
      state.tab = "discrepancies";
      await caseView(state.current.case_id);
    },
  });
}
function editDiscrepancy(id) {
  const item = state.current.discrepancies.find((x) => x.id === id);
  openModal({
    title: `Resolve ${id}`,
    body:
      field("status", "Status", "select", {
        options: [
          "open",
          "candidate_response_received",
          "corroboration_pending",
          "resolved",
          "unresolved",
        ].map((x) => ({ value: x, label: label(x) })),
      }) +
      field("candidate_response", "Candidate response", "textarea", {
        full: true,
        value: item.candidate_response,
      }) +
      field("corroboration", "Independent corroboration", "textarea", {
        full: true,
        value: item.corroboration,
      }) +
      field("resolution", "Resolution", "textarea", {
        full: true,
        value: item.resolution,
      }),
    onSubmit: async (d) => {
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/discrepancies/${id}`,
        { method: "PATCH", body: JSON.stringify(d) },
      );
      await caseView(state.current.case_id);
    },
  });
  document.querySelector("[name=status]").value = item.status;
}
function addInterview() {
  openModal({
    title: "Document interview",
    body:
      field("kind", "Interview type", "select", {
        options: [
          "pre_investigatory",
          "field",
          "reference",
          "employer",
          "discrepancy",
          "other",
        ],
      }) +
      field("date", "Date", "date", {
        required: true,
        value: new Date().toISOString().slice(0, 10),
      }) +
      field("participant_role", "Participant role", "text", {
        required: true,
      }) +
      field("recording_locator", "Approved recording locator") +
      field("notes", "Notes", "textarea", { full: true }) +
      field("uploaded_to_esoph", "Uploaded to eSOPH", "checkbox"),
    onSubmit: async (d) => {
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/interviews`,
        { method: "POST", body: JSON.stringify(d) },
      );
      state.tab = "interviews";
      await caseView(state.current.case_id);
    },
  });
}
function interviewPlanBody(item = {}) {
  return (
    field("subject", "Packet subject", "text", {
      required: true,
      placeholder: "Pre-Investigatory Interview",
      value: item.subject || "",
    }) +
    field("question", "Planned question or topic", "textarea", {
      required: true,
      full: true,
      placeholder: "What should be covered, verified, or clarified?",
      value: item.question || "",
    }) +
    field("status", "Status", "select", {
      options: Object.entries(state.meta.interview_plan_statuses || {}).map(([value, label]) => ({
        value,
        label,
      })),
    }) +
    field("source_ids", "Source identifiers", "text", {
      full: true,
      value: (item.source_ids || []).join(", "),
      placeholder: "SRC-0001, SRC-0002",
    }) +
    field("discrepancy_ids", "Related discrepancy IDs", "text", {
      full: true,
      value: (item.discrepancy_ids || []).join(", "),
      placeholder: "DSC-0001, DSC-0002",
    }) +
    field("recording_locator", "Approved recording locator", "text", {
      full: true,
      value: item.recording_locator || "",
      placeholder: "eSOPH / secure storage locator",
    }) +
    field("notes", "Notes", "textarea", { full: true, value: item.notes || "" })
  );
}
function addInterviewPlan() {
  openModal({
    title: "Add interview packet",
    body: interviewPlanBody(),
    onSubmit: async (d) => {
      d.source_ids = d.source_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      d.discrepancy_ids = d.discrepancy_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/interview-plans`,
        { method: "POST", body: JSON.stringify(d) },
      );
      state.tab = "interviews";
      await caseView(state.current.case_id);
    },
  });
}
function editInterviewPlan(id) {
  const item = state.current.interview_plans.find((x) => x.id === id);
  openModal({
    title: `Update ${id}`,
    body: interviewPlanBody(item),
    onSubmit: async (d) => {
      d.source_ids = d.source_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      d.discrepancy_ids = d.discrepancy_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/interview-plans/${id}`,
        { method: "PATCH", body: JSON.stringify(d) },
      );
      await caseView(state.current.case_id);
    },
  });
  document.querySelector("[name=status]").value = item.status;
}
function addSource() {
  openModal({
    title: "Register source",
    body:
      field("label", "Source label", "text", {
        required: true,
        placeholder: "Safe descriptive label",
      }) +
      field("kind", "Source type", "text", {
        required: true,
        placeholder: "Correspondence, record, interview…",
      }) +
      field("location", "Approved-system locator", "text", {
        required: true,
        full: true,
        placeholder: "Do not duplicate sensitive contents",
      }) +
      field("notes", "Notes", "textarea", { full: true }),
    onSubmit: async (d) => {
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/sources`,
        { method: "POST", body: JSON.stringify(d) },
      );
      state.tab = "sources";
      await caseView(state.current.case_id);
    },
  });
}
function addPhsChange() {
  openModal({
    title: "Add PHS change",
    body:
      field("field_label", "Field label", "text", {
        required: true,
        placeholder: "Employment, address, education, separation reason…",
      }) +
      field("prior_value", "Prior value", "textarea", {
        required: true,
        full: true,
        placeholder: "What the PHS said before",
      }) +
      field("current_value", "Current value", "textarea", {
        required: true,
        full: true,
        placeholder: "What the PHS says now",
      }) +
      field("reported_at", "Reported date", "date") +
      field("source_ids", "Source identifiers", "text", {
        full: true,
        placeholder: "SRC-0001, SRC-0002",
      }) +
      field("disposition", "Disposition", "textarea", {
        full: true,
        placeholder: "Brief investigator note on the change",
      }),
    onSubmit: async (d) => {
      d.source_ids = d.source_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/phs-changes`,
        { method: "POST", body: JSON.stringify(d) },
      );
      state.tab = "phs";
      await caseView(state.current.case_id);
    },
  });
}
function editPhsChange(id) {
  const item = state.current.phs_changes.find((x) => x.id === id);
  openModal({
    title: `Update ${id}`,
    body:
      field("field_label", "Field label", "text", {
        required: true,
        value: item.field_label,
      }) +
      field("prior_value", "Prior value", "textarea", {
        required: true,
        full: true,
        value: item.prior_value,
      }) +
      field("current_value", "Current value", "textarea", {
        required: true,
        full: true,
        value: item.current_value,
      }) +
      field("reported_at", "Reported date", "date", {
        value: item.reported_at,
      }) +
      field("source_ids", "Source identifiers", "text", {
        full: true,
        value: (item.source_ids || []).join(", "),
      }) +
      field("disposition", "Disposition", "textarea", {
        full: true,
        value: item.disposition,
      }),
    onSubmit: async (d) => {
      d.source_ids = d.source_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/phs-changes/${id}`,
        { method: "PATCH", body: JSON.stringify(d) },
      );
      await caseView(state.current.case_id);
    },
  });
}
function addTimeline() {
  openModal({
    title: "Add timeline entry",
    body:
      field("category", "Category", "select", {
        options: Object.entries(state.meta.timeline_categories).map(([value, label]) => ({
          value,
          label,
        })),
      }) +
      field("label", "Entry label", "text", {
        required: true,
        placeholder: "Employer, school, residence, event…",
      }) +
      field("start_date", "Start date", "date", { required: true }) +
      field("end_date", "End date", "date") +
      field("source_ids", "Source identifiers", "text", {
        full: true,
        placeholder: "SRC-0001, SRC-0002",
      }) +
      field("notes", "Notes", "textarea", { full: true }),
    onSubmit: async (d) => {
      d.source_ids = d.source_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/timeline`,
        { method: "POST", body: JSON.stringify(d) },
      );
      state.tab = "timeline";
      await caseView(state.current.case_id);
    },
  });
}
function editTimeline(id) {
  const item = state.current.timeline.find((x) => x.id === id);
  openModal({
    title: `Update ${id}`,
    body:
      field("category", "Category", "select", {
        options: Object.entries(state.meta.timeline_categories).map(([value, label]) => ({
          value,
          label,
        })),
      }) +
      field("label", "Entry label", "text", {
        required: true,
        value: item.label,
      }) +
      field("start_date", "Start date", "date", {
        required: true,
        value: item.start_date,
      }) +
      field("end_date", "End date", "date", { value: item.end_date }) +
      field("source_ids", "Source identifiers", "text", {
        full: true,
        value: (item.source_ids || []).join(", "),
      }) +
      field("notes", "Notes", "textarea", { full: true, value: item.notes }),
    onSubmit: async (d) => {
      d.source_ids = d.source_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/timeline/${id}`,
        { method: "PATCH", body: JSON.stringify(d) },
      );
      await caseView(state.current.case_id);
    },
  });
  document.querySelector("[name=category]").value = item.category;
}
function addDocument() {
  openModal({
    title: "Add document record",
    body:
      field("title", "Document title", "text", {
        required: true,
        placeholder: "Release, transcript, verification letter…",
      }) +
      field("status", "Status", "select", {
        options: Object.entries(state.meta.document_statuses).map(([value, label]) => ({
          value,
          label,
        })),
      }) +
      field("due_date", "Due date", "date") +
      field("source_locator", "Source locator", "text", {
        full: true,
        placeholder: "Approved system reference",
      }) +
      field("required_original", "Original required", "checkbox") +
      field("notes", "Notes", "textarea", { full: true }),
    onSubmit: async (d) => {
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/documents`,
        { method: "POST", body: JSON.stringify(d) },
      );
      state.tab = "documents";
      await caseView(state.current.case_id);
    },
  });
}
function editDocument(id) {
  const item = state.current.documents.find((x) => x.id === id);
  openModal({
    title: `Update ${id}`,
    body:
      field("title", "Document title", "text", {
        required: true,
        value: item.title,
      }) +
      field("status", "Status", "select", {
        options: Object.entries(state.meta.document_statuses).map(([value, label]) => ({
          value,
          label,
        })),
      }) +
      field("due_date", "Due date", "date", { value: item.due_date }) +
      field("received_at", "Received date", "date", { value: item.received_at }) +
      field("verified_at", "Verified date", "date", { value: item.verified_at }) +
      field("returned_at", "Returned date", "date", { value: item.returned_at }) +
      field("source_locator", "Source locator", "text", {
        full: true,
        value: item.source_locator,
      }) +
      field("required_original", "Original required", "checkbox", {
        checked: item.required_original,
      }) +
      field("notes", "Notes", "textarea", { full: true, value: item.notes }),
    onSubmit: async (d) => {
      await request(
        `/api/cases/${encodeURIComponent(state.current.case_id)}/documents/${id}`,
        { method: "PATCH", body: JSON.stringify(d) },
      );
      await caseView(state.current.case_id);
    },
  });
  document.querySelector("[name=status]").value = item.status;
}
function guide() {
  setChrome("Desk guide", "guide");
  app.innerHTML = `<div class="guide"><div class="page-head"><div><p class="eyebrow">Field reference</p><h1>Investigation desk guide</h1><p>A working aid only. Current CDCR directives, local procedures, supervisor direction, and approved systems control.</p></div></div><section><h2>Open the case deliberately</h2><ol><li>Confirm the assignment and applicable candidate type.</li><li>Use a non-PII case identifier.</li><li>Review the complete eSOPH PHS and releases.</li><li>Create an inquiry for every disclosed source and required verification.</li><li>Register approved-system locators instead of duplicating sensitive records.</li></ol></section><section><h2>Keep discrepancies evidentiary</h2><ol><li>Record the candidate statement and contrary information separately.</li><li>Identify the source and whether knowledge is firsthand.</li><li>Seek independent corroboration.</li><li>Document the candidate response without promising an outcome.</li><li>Resolve the matter or state why it remains unresolved.</li></ol></section><section><h2>Write for review</h2><ul><li>Separate fact, allegation, observation, and explanation.</li><li>Cite every material finding to a registered source.</li><li>Include mitigating and contradictory information.</li><li>Never turn a nonresponse into adverse evidence.</li><li>Run the quality audit before moving a case to review or closed.</li></ul></section></div>`;
}
async function account() {
  setChrome("Account", "account");
  const me = await request("/api/me");
  let system = {},
    users = [],
    audit = [];
  if (me.role === "admin") {
    [system, users, audit] = await Promise.all([
      request("/api/system"),
      request("/api/users"),
      request("/api/audit"),
    ]);
  }
  app.innerHTML = `<div class="page-head"><div><p class="eyebrow">Identity and operations</p><h1>${esc(me.display_name || me.username)}</h1><p>${esc(label(me.role))} · Protected account</p></div></div><div class="stat-grid">${me.role === "admin" ? `<div class="stat"><div class="stat-label">Database</div><div class="stat-value">${esc(system.database)}</div><div class="stat-detail">Version ${esc(system.version)}</div></div><div class="stat"><div class="stat-label">Active users</div><div class="stat-value">${system.active_users}</div><div class="stat-detail">Role-controlled accounts</div></div><div class="stat"><div class="stat-label">Latest backup</div><div class="stat-value" style="font-size:1rem">${esc(system.latest_backup || "Pending")}</div><div class="stat-detail">Integrity-checked snapshot</div></div>` : ""}</div><section class="panel"><div class="panel-head"><div><h2>Account security</h2><p>Manage credentials and multifactor protection.</p></div><div class="filter-row"><button class="secondary" data-account="password">Change password</button><button class="primary" data-account="mfa">Enable MFA</button>${me.role === "admin" ? '<button class="secondary" data-account="backup">Create backup</button><button class="primary" data-account="user">Add user</button>' : ""}</div></div>${me.role === "admin" ? `<div class="table-wrap"><table><thead><tr><th>User</th><th>Role</th><th>MFA</th><th>Status</th></tr></thead><tbody>${users.map((x) => `<tr><td>${esc(x.display_name)}<span class="subtle">${esc(x.username)}</span></td><td>${esc(label(x.role))}</td><td>${x.mfa_enabled ? "Enabled" : "Not enabled"}</td><td>${x.disabled ? "Disabled" : "Active"}</td></tr>`).join("")}</tbody></table></div>` : ""}</section>${
    me.role === "admin"
      ? `<section class="panel"><div class="panel-head"><div><h2>Recent audit activity</h2><p>Append-only operational events.</p></div></div><div class="record-list">${audit
          .slice(0, 20)
          .map(
            (x) =>
              `<div class="record"><div><h4>${esc(label(x.action))} <span class="subtle">${esc(x.username || "System")}</span></h4><p>${esc(x.case_id || "")} ${esc(x.detail || "")} · ${new Date(x.occurred_at).toLocaleString()}</p></div></div>`,
          )
          .join("")}</div></section>`
      : ""
  }`;
  document.querySelector("[data-account=password]").onclick = () =>
    openModal({
      title: "Change password",
      body:
        field("current_password", "Current password", "password", {
          required: true,
        }) +
        field("new_password", "New password", "password", {
          required: true,
          placeholder: "At least 12 characters",
        }),
      submit: "Change password",
      onSubmit: async (d) => {
        await request("/api/change-password", {
          method: "POST",
          body: JSON.stringify(d),
        });
        location.href = "/login";
      },
    });
  document.querySelector("[data-account=mfa]").onclick = async () => {
    const setup = await request("/api/mfa/setup", {
      method: "POST",
      body: "{}",
    });
    openModal({
      title: "Enable authenticator MFA",
      body:
        `<div class="field full"><label>Authenticator secret</label><input readonly value="${esc(setup.secret)}"><span class="subtle">Add this secret to an authenticator app, then enter its six-digit code.</span></div>` +
        field("code", "Verification code", "text", { required: true }),
      submit: "Enable MFA",
      onSubmit: async (d) => {
        await request("/api/mfa/enable", {
          method: "POST",
          body: JSON.stringify({ secret: setup.secret, code: d.code }),
        });
        toast("MFA enabled");
      },
    });
  };
  document
    .querySelector("[data-account=backup]")
    ?.addEventListener("click", async () => {
      await request("/api/backups", { method: "POST", body: "{}" });
      toast("Verified backup created");
      await account();
    });
  document.querySelector("[data-account=user]")?.addEventListener("click", () =>
    openModal({
      title: "Add workbench user",
      body:
        field("username", "Username", "text", { required: true }) +
        field("display_name", "Display name", "text", { required: true }) +
        field("password", "Temporary password", "password", {
          required: true,
          placeholder: "At least 12 characters",
        }) +
        field("role", "Role", "select", {
          options: ["investigator", "supervisor", "reviewer", "admin"],
        }),
      submit: "Create user",
      onSubmit: async (d) => {
        await request("/api/users", {
          method: "POST",
          body: JSON.stringify(d),
        });
        await account();
      },
    }),
  );
  if (me.role === "admin") {
    document
      .querySelector(".filter-row")
      ?.insertAdjacentHTML(
        "beforeend",
        '<label class="secondary">Import case package<input id="casePackageImport" type="file" accept="application/json" hidden></label>',
      );
    document.querySelector("#casePackageImport").onchange = async (event) => {
      const file = event.target.files[0];
      if (!file) return;
      try {
        const payload = JSON.parse(await file.text());
        const data = await request("/api/cases/import", {
          method: "POST",
          body: JSON.stringify({ case: payload }),
        });
        toast(`Imported ${data.case_id}`);
        location.hash = `#/case/${encodeURIComponent(data.case_id)}`;
      } catch (err) {
        toast(`Import failed: ${err.message}`);
      }
    };
  }
}
async function refreshAlertCount() {
  const notices = await request("/api/notifications");
  state.notifications = notices;
  const unread = notices.filter((notice) => !notice.read_at).length;
  const count = document.querySelector("#alertCount");
  count.hidden = unread === 0;
  count.textContent = unread > 99 ? "99+" : String(unread);
}

async function alerts() {
  setChrome("Alerts", "alerts");
  const notices = state.notifications || (await request("/api/notifications"));
  app.innerHTML = `<div class="page-head"><div><p class="eyebrow">Operational awareness</p><h1>Case alerts</h1><p>Review submissions, approvals, and correction requests stay visible here.</p></div></div><section class="panel"><div class="alert-list">${notices.map((notice) => `<article class="alert-item ${notice.read_at ? "read" : ""}"><div><p class="eyebrow">${esc(label(notice.kind))}</p><h3>${esc(notice.message)}</h3><span class="subtle">${new Date(notice.created_at).toLocaleString()}</span></div><div class="record-actions">${notice.case_id ? `<button class="quiet" data-open-case="${esc(notice.case_id)}">Open case</button>` : ""}${!notice.read_at ? `<button class="secondary" data-read-alert="${notice.id}">Mark read</button>` : ""}</div></article>`).join("") || '<div class="empty"><strong>No alerts</strong>Review workflow updates will appear here.</div>'}</div></section>`;
  document.querySelectorAll("[data-read-alert]").forEach(
    (button) =>
      (button.onclick = async () => {
        await request(`/api/notifications/${button.dataset.readAlert}`, {
          method: "PATCH",
          body: "{}",
        });
        await refreshAlertCount();
        await alerts();
      }),
  );
  document.querySelectorAll("[data-open-case]").forEach(
    (button) =>
      (button.onclick = () => {
        location.hash = `#/case/${encodeURIComponent(button.dataset.openCase)}`;
      }),
  );
}

async function route() {
  try {
    if (dashboardHotkeyHandler) {
      document.removeEventListener("keydown", dashboardHotkeyHandler);
      dashboardHotkeyHandler = null;
    }
    await loadMeta();
    await refreshAlertCount();
    const { parts, params } = readRouteState();
    if (parts[0] === "case" && parts[1])
      await caseView(decodeURIComponent(parts[1]));
    else if (parts[0] === "guide") guide();
    else if (parts[0] === "alerts") await alerts();
    else if (parts[0] === "account") await account();
    else await dashboard(params);
  } catch (err) {
    app.innerHTML = `<div class="empty"><strong>Unable to load the workbench</strong>${esc(err.message)}</div>`;
  }
}
document.querySelector("#newCaseButton").onclick = addCase;
document.querySelector("#menuButton").onclick = () =>
  document.querySelector(".sidebar").classList.toggle("open");
document.querySelector("#today").textContent = new Intl.DateTimeFormat(
  undefined,
  { weekday: "short", month: "short", day: "numeric" },
).format(new Date());
window.addEventListener("hashchange", route);
route();
