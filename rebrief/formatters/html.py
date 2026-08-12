from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from rebrief.core.tokens import format_compact_count

if TYPE_CHECKING:
    from rebrief.core.reporter import ReportPayload

COPY_PROMPT_PREFIX = (
    "Read the following REBRIEF.md before starting to understand "
    "the project's architecture and hotspots."
)

_CSS = """
:root {
  --bg: #09090b;
  --surface: #18181b;
  --border: #27272a;
  --text: #fafafa;
  --muted: #a1a1aa;
  --emerald: #10b981;
  --amber: #f59e0b;
  --red: #ef4444;
  --info: #71717a;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, system-ui, -apple-system, Segoe UI, sans-serif;
  font-size: 14px;
  line-height: 1.45;
}
code, .mono, .path, .token-num, pre {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.wrap { max-width: 1120px; margin: 0 auto; padding: 20px 20px 64px; }
header.app {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
h1 { font-size: 20px; font-weight: 650; margin: 0 0 6px; letter-spacing: -0.02em; }
.meta { color: var(--muted); font-size: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
.chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 4px;
  padding: 1px 7px;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.btn {
  appearance: none;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 6px;
  padding: 7px 12px;
  font: inherit;
  cursor: pointer;
}
.btn:hover { border-color: #3f3f46; }
.btn-primary { border-color: #065f46; background: #022c22; color: var(--emerald); }
.btn-float { position: sticky; top: 12px; z-index: 5; white-space: nowrap; }
.tabs { display: flex; gap: 6px; margin: 0 0 16px; }
.tabs .btn[aria-selected="true"] { border-color: var(--emerald); color: var(--emerald); }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 14px;
}
.card h2 { font-size: 12px; font-weight: 600; color: var(--muted); margin: 0 0 10px; text-transform: uppercase; letter-spacing: 0.08em; }
.token-grid { display: grid; grid-template-columns: 1fr 1fr auto; gap: 16px; align-items: end; }
.token-num { font-size: 22px; font-weight: 650; letter-spacing: -0.03em; }
.token-num.saved { color: var(--emerald); }
.label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
.bar { height: 8px; background: #27272a; border-radius: 99px; overflow: hidden; margin-top: 12px; }
.bar > span { display: block; height: 100%; background: var(--emerald); }
.badges { display: flex; flex-wrap: wrap; gap: 6px; }
.badge {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 9px;
  font-size: 12px;
  background: #0c0c0e;
}
.badge.dep { color: var(--muted); }
.group { margin-bottom: 10px; }
.group:last-child { margin-bottom: 0; }
.filters { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.filters .btn[aria-pressed="true"] { border-color: var(--emerald); color: var(--emerald); }
.search {
  width: 100%;
  margin-bottom: 10px;
  background: #0c0c0e;
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 6px;
  padding: 8px 10px;
  font: inherit;
}
.risk-list { display: grid; gap: 8px; }
.risk-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 10px;
  align-items: start;
}
.sev {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 2px 6px;
  border-radius: 4px;
}
.sev-critical { color: var(--red); background: #450a0a; }
.sev-warning { color: var(--amber); background: #451a03; }
.sev-info { color: #d4d4d8; background: #27272a; }
.conf { font-size: 10px; color: var(--muted); }
.empty { color: var(--muted); font-size: 13px; }
table.hotspots { width: 100%; border-collapse: collapse; }
table.hotspots th, table.hotspots td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
table.hotspots th { color: var(--muted); font-size: 11px; font-weight: 600; cursor: pointer; user-select: none; text-transform: uppercase; letter-spacing: 0.06em; }
.path { font-size: 12px; }
.density { height: 6px; background: #27272a; border-radius: 99px; min-width: 80px; overflow: hidden; }
.density > span { display: block; height: 100%; background: var(--amber); }
ol.checklist { margin: 0; padding-left: 18px; }
ol.checklist li { margin: 6px 0; }
.raw-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
pre.raw {
  margin: 0;
  padding: 14px;
  background: #0c0c0e;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: auto;
  white-space: pre-wrap;
  font-size: 12px;
}
.md-h { color: var(--emerald); font-weight: 650; }
.md-code { color: #fbbf24; }
.md-list { color: var(--muted); }
.toast { position: fixed; bottom: 16px; right: 16px; background: #022c22; color: var(--emerald); border: 1px solid #065f46; padding: 8px 12px; border-radius: 6px; display: none; }
#copy-prompt { position: absolute; left: -9999px; width: 1px; height: 1px; }
[hidden] { display: none !important; }
"""

_JS = r"""
(function () {
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.style.display = "block";
    setTimeout(() => { el.style.display = "none"; }, 1400);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast("Copied")).catch(() => fallbackCopy(text));
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); toast("Copied"); } catch (e) { toast("Copy failed"); }
    ta.remove();
  }

  $("#copy-prompt-btn").addEventListener("click", () => {
    copyText($("#copy-prompt").value);
  });
  $("#copy-md-btn").addEventListener("click", () => {
    copyText($("#raw-md").textContent);
  });

  $$(".tabs .btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.getAttribute("data-view");
      $$(".tabs .btn").forEach((b) => b.setAttribute("aria-selected", b === btn ? "true" : "false"));
      $("#view-dashboard").hidden = view !== "dashboard";
      $("#view-raw").hidden = view !== "raw";
    });
  });

  let severity = "all";
  let confidence = "all";
  const search = $("#risk-search");

  function applyRiskFilters() {
    const q = (search.value || "").toLowerCase();
    $$(".risk-card").forEach((card) => {
      const sevOk = severity === "all" || card.dataset.severity === severity;
      const confOk = confidence === "all" || card.dataset.confidence === confidence;
      const qOk = !q || (card.textContent || "").toLowerCase().includes(q);
      card.hidden = !(sevOk && confOk && qOk);
    });
    const visible = $$(".risk-card").filter((c) => !c.hidden).length;
    const empty = $("#risk-empty-filter");
    if (empty) empty.hidden = visible !== 0;
  }

  $$("[data-filter-kind]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const kind = btn.getAttribute("data-filter-kind");
      const value = btn.getAttribute("data-filter-value");
      if (kind === "all") {
        severity = "all";
        confidence = "all";
        $$("[data-filter-kind]").forEach((b) => b.setAttribute("aria-pressed", b.getAttribute("data-filter-kind") === "all" ? "true" : "false"));
      } else if (kind === "severity") {
        severity = value;
        $$("[data-filter-kind='all']").forEach((b) => b.setAttribute("aria-pressed", "false"));
        $$("[data-filter-kind='severity']").forEach((b) => b.setAttribute("aria-pressed", b === btn ? "true" : "false"));
      } else if (kind === "confidence") {
        confidence = value;
        $$("[data-filter-kind='all']").forEach((b) => b.setAttribute("aria-pressed", "false"));
        $$("[data-filter-kind='confidence']").forEach((b) => b.setAttribute("aria-pressed", b === btn ? "true" : "false"));
      }
      applyRiskFilters();
    });
  });
  search.addEventListener("input", applyRiskFilters);

  const tbody = $("#hotspot-body");
  let sortKey = "changes";
  let sortDir = -1;
  function sortHotspots() {
    if (!tbody) return;
    const rows = $$("tr", tbody);
    rows.sort((a, b) => {
      const av = a.dataset[sortKey] || "";
      const bv = b.dataset[sortKey] || "";
      if (sortKey === "changes") return (Number(av) - Number(bv)) * sortDir;
      return av.localeCompare(bv) * sortDir;
    });
    rows.forEach((row) => tbody.appendChild(row));
  }
  $$("th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.getAttribute("data-sort");
      if (sortKey === key) sortDir *= -1;
      else { sortKey = key; sortDir = key === "changes" ? -1 : 1; }
      sortHotspots();
    });
  });

  const raw = $("#raw-md");
  if (raw) {
    const text = raw.textContent || "";
    raw.textContent = "";
    text.split("\n").forEach((line, i, arr) => {
      const span = document.createElement("span");
      if (/^#{1,6} /.test(line)) span.className = "md-h";
      else if (/^\s*[-*] /.test(line) || /^\s*\d+\. /.test(line)) span.className = "md-list";
      const codeRe = /`([^`]+)`/g;
      let last = 0;
      let match;
      let used = false;
      while ((match = codeRe.exec(line))) {
        used = true;
        if (match.index > last) span.appendChild(document.createTextNode(line.slice(last, match.index)));
        const code = document.createElement("span");
        code.className = "md-code";
        code.textContent = match[0];
        span.appendChild(code);
        last = match.index + match[0].length;
      }
      if (used) span.appendChild(document.createTextNode(line.slice(last)));
      else span.textContent = line;
      raw.appendChild(span);
      if (i < arr.length - 1) raw.appendChild(document.createTextNode("\n"));
    });
  }
})();
"""


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _badges(values: list[str], extra_class: str = "") -> str:
    if not values:
        return '<p class="empty">None detected.</p>'
    cls = f"badge {extra_class}".strip()
    return '<div class="badges">' + "".join(
        f'<span class="{cls}">{_e(item)}</span>' for item in values
    ) + "</div>"


def _risk_cards(payload: ReportPayload) -> str:
    cards: list[str] = []
    for severity in ("critical", "warning", "info"):
        for item in payload["risk_map"][severity]:
            sev = severity.upper()
            conf = item["confidence"]
            cards.append(
                '<article class="risk-card" '
                f'data-severity="{_e(sev)}" data-confidence="{_e(conf)}">'
                f'<span class="sev sev-{_e(severity)}">{_e(sev)}</span>'
                f'<div>{_e(item["message"])}</div>'
                f'<span class="conf">{_e(conf)}</span>'
                "</article>"
            )
    if not cards:
        return '<p class="empty" id="risk-none">None detected.</p>'
    return (
        '<div class="risk-list">'
        + "".join(cards)
        + '<p class="empty" id="risk-empty-filter" hidden>No matching risks.</p>'
        + "</div>"
    )


def _hotspots_table(payload: ReportPayload) -> str:
    hotspots = payload["timeline"]["hotspots"]
    if not hotspots:
        return '<p class="empty">None detected.</p>'
    max_changes = max(entry["changes"] for entry in hotspots) or 1
    rows: list[str] = []
    for entry in hotspots:
        width = max(0, min(100, round(entry["changes"] / max_changes * 100)))
        rows.append(
            "<tr "
            f'data-file="{_e(entry["file"])}" data-changes="{entry["changes"]}">'
            f'<td class="path">{_e(entry["file"])}</td>'
            f'<td class="mono">{entry["changes"]}</td>'
            f'<td><div class="density" title="{width}%"><span style="width:{width}%"></span></div></td>'
            "</tr>"
        )
    return (
        '<table class="hotspots">'
        "<thead><tr>"
        '<th data-sort="file">File</th>'
        '<th data-sort="changes">Changes</th>'
        "<th>Density</th>"
        "</tr></thead>"
        f'<tbody id="hotspot-body">{"".join(rows)}</tbody>'
        "</table>"
    )


def _checklist(payload: ReportPayload) -> str:
    items = payload["checklist"]
    if not items:
        return '<p class="empty">None detected.</p>'
    return '<ol class="checklist">' + "".join(f"<li>{_e(item)}</li>" for item in items) + "</ol>"


def render_html(payload: ReportPayload, markdown: str, repo_name: str) -> str:
    stats = payload["summary"]["token_stats"]
    raw = stats["raw_codebase_tokens"]
    brief = stats["brief_tokens"]
    pct = stats["savings_percentage"]
    bar_width = max(0, min(100, pct))
    mode = payload["mode"]
    version = payload["version"]
    diff = payload["diff_ref"]
    stack = payload["tech_stack"]
    prompt = f"{COPY_PROMPT_PREFIX}\n\n---\n{markdown}"
    title = f"REBRIEF — {_e(repo_name)}"
    diff_chip = f'<span class="chip">diff {_e(diff)}</span>' if diff else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<textarea id="copy-prompt">{_e(prompt)}</textarea>
<div class="wrap">
<header class="app">
  <div>
    <h1>{title}</h1>
    <div class="meta">
      <span class="chip">{_e(mode)}</span>
      <span class="chip">v{_e(version)}</span>
      {diff_chip}
    </div>
  </div>
  <button type="button" class="btn btn-primary btn-float" id="copy-prompt-btn">Copy Prompt for AI</button>
</header>
<nav class="tabs" role="tablist">
  <button type="button" class="btn" data-view="dashboard" aria-selected="true">Dashboard View</button>
  <button type="button" class="btn" data-view="raw" aria-selected="false">Raw Markdown View</button>
</nav>
<section id="view-dashboard">
  <section class="card">
    <h2>Token efficiency</h2>
    <div class="token-grid">
      <div>
        <div class="label">Raw tokens</div>
        <div class="token-num mono">{raw:,}</div>
        <div class="label">{_e(format_compact_count(raw))} estimated</div>
      </div>
      <div>
        <div class="label">Brief tokens</div>
        <div class="token-num mono">{brief:,}</div>
      </div>
      <div>
        <div class="label">Saved</div>
        <div class="token-num saved">{pct:.1f}% reduced</div>
      </div>
    </div>
    <div class="bar" title="{pct:.1f}% reduced"><span style="width:{bar_width:.2f}%"></span></div>
  </section>
  <section class="card">
    <h2>Tech stack &amp; manifests</h2>
    <div class="group"><div class="label">Languages</div>{_badges(stack["languages"])}</div>
    <div class="group"><div class="label">Frameworks</div>{_badges(stack["frameworks"])}</div>
    <div class="group"><div class="label">Manifests</div>{_badges(stack["manifests"])}</div>
    <div class="group"><div class="label">Dependencies</div>{_badges(stack["dependencies"], "dep")}</div>
  </section>
  <section class="card">
    <h2>Risk matrix</h2>
    <div class="filters">
      <button type="button" class="btn" data-filter-kind="all" data-filter-value="all" aria-pressed="true">All</button>
      <button type="button" class="btn" data-filter-kind="severity" data-filter-value="CRITICAL" aria-pressed="false">CRITICAL</button>
      <button type="button" class="btn" data-filter-kind="severity" data-filter-value="WARNING" aria-pressed="false">WARNING</button>
      <button type="button" class="btn" data-filter-kind="severity" data-filter-value="INFO" aria-pressed="false">INFO</button>
      <button type="button" class="btn" data-filter-kind="confidence" data-filter-value="HIGH" aria-pressed="false">HIGH</button>
      <button type="button" class="btn" data-filter-kind="confidence" data-filter-value="MEDIUM" aria-pressed="false">MEDIUM</button>
      <button type="button" class="btn" data-filter-kind="confidence" data-filter-value="LOW" aria-pressed="false">LOW</button>
    </div>
    <input class="search" id="risk-search" type="search" placeholder="Filter risks or file paths">
    {_risk_cards(payload)}
  </section>
  <section class="card">
    <h2>Codebase hotspots</h2>
    {_hotspots_table(payload)}
  </section>
  <section class="card">
    <h2>Developer checklist</h2>
    {_checklist(payload)}
  </section>
</section>
<section id="view-raw" hidden>
  <div class="raw-toolbar">
    <button type="button" class="btn" id="copy-md-btn">Copy markdown</button>
  </div>
  <pre class="raw"><code id="raw-md">{_e(markdown)}</code></pre>
</section>
</div>
<div class="toast" id="toast"></div>
<script>{_JS}</script>
</body>
</html>
"""
