"use strict";
const $ = (selector) => document.querySelector(selector);
const state = { data: null, papers: [], category: "all", journal: "all", scope: "all", query: "", days: 90, page: 1, pageSize: 10 };
const scopeLabel = (id) => ({ all: tr("All journals", "全部期刊"), featured: tr("Spotlight journals", "重点期刊"), other: tr("Other journals", "其他期刊") })[id];
const dateLabel = (id) => ({ "published-online": tr("Online publication", "在线发表"), "published-print": tr("Print date (fallback)", "纸刊日期（回退）"), published: tr("Publication date (fallback)", "出版日期（回退）"), issued: tr("Issued date (fallback)", "issued 日期（回退）") })[id] || id;
const englishCategories = { network_structure: "Structure & formation", network_inference: "Community detection, inference & reconstruction", network_spreading: "Spreading, diffusion & percolation", network_collective: "Synchronization, games & collective behavior", network_resilience: "Robustness, cascades & control", other: "Other" };

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function link(text, url, className = "") {
  const node = element("a", className, text);
  // External data never becomes HTML or an arbitrary executable URL.
  const parsed = new URL(url);
  if (parsed.protocol !== "https:") throw new Error("Unsafe link protocol / 不安全的链接协议");
  node.href = parsed.href;
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}
function categoryLabel(id) {
  return tr(englishCategories[id] || "Other", state.data.categories.find((c) => c.id === id)?.label || "其他");
}
function timeNode(paper) {
  const node = element("time", "", paper.date);
  node.dateTime = paper.date;
  node.title = dateLabel(paper.date_source);
  return node;
}
function featureCard(paper) {
  const card = element("article", "feature-card");
  const top = element("div", "feature-top");
  top.append(element("span", "journal-badge", paper.journal), timeNode(paper));
  const title = element("h3");
  title.append(link(paper.title, paper.url));
  const bottom = element("div", "feature-bottom");
  bottom.append(element("span", "", categoryLabel(paper.categories[0])), link(tr("Read paper ↗", "阅读原文 ↗"), paper.url));
  card.append(top, title, bottom);
  return card;
}
function paperCard(paper) {
  const card = element("article", "paper-card");
  const top = element("div", "paper-top");
  const journal = element("span", "journal-name", paper.journal || tr("Journal unavailable", "期刊名称缺失"));
  journal.title = paper.journal;
  top.append(journal);
  if (paper.featured) top.append(element("span", "badge", scopeLabel("featured")));
  top.append(timeNode(paper));
  const title = element("h3");
  title.append(link(paper.title, paper.url));
  const authors = paper.authors.filter(Boolean);
  const byline = element("p", "authors", authors.slice(0, 4).join(" · ") + (authors.length > 4 ? " · et al." : "") || tr("Author metadata unavailable — see publisher", "作者元数据暂缺，请查看出版方"));
  if (paper.author_metadata_status === "partial") byline.append(element("span", "", tr(" · Author list incomplete — see publisher", " · 作者名单不完整，请查看出版方")));
  const bottom = element("div", "paper-bottom");
  const tags = element("div", "tags");
  paper.categories.forEach((id) => tags.append(element("span", "tag", categoryLabel(id))));
  if (paper.scope_class) tags.append(element("span", "tag", paper.scope_class === "core" ? tr("Core network science", "核心网络科学") : tr("Transferable application", "可迁移应用研究")));
  bottom.append(tags, link(tr("Read paper ↗", "原文 ↗"), paper.url, "paper-link"));
  const details = element("details", "evidence");
  details.append(element("summary", "", tr("Inclusion evidence & date source", "收录依据与日期来源")));
  details.append(element("p", "", tr("Scope assessment: ", "收录范围判定：") + paper.evidence.join(" / ")));
  details.append(element("p", "", `${dateLabel(paper.date_source)} · ${paper.date} · DOI: ${paper.doi}`));
  details.append(element("p", "", tr("Query: ", "检索路径：") + paper.retrieved_by.join("; ") + tr(". AI title/abstract assessment; not full-text expert review.", "。AI 标题／摘要审读，非全文专家审定。")));
  if (paper.author_metadata_status !== "available") details.append(element("p", "", tr("Crossref author metadata is missing or contains placeholders. This does not establish publication status; check the publisher. Metadata is reread on each collection.", "Crossref 作者信息缺失或包含占位值，不能据此判断出版状态；请核对出版方。每次采集会重新读取元数据。")));
  if (paper.has_update) details.append(element("p", "", tr("An update is linked in the metadata. Check the publisher for corrections or retractions.", "元数据存在更新关联，请查看出版方最新更正或撤稿说明。")));
  details.append(link(tr("Check Crossref metadata ↗", "核对 Crossref 元数据 ↗"), paper.metadata_url));
  card.append(top, title, byline, bottom, details);
  return card;
}
function renderCategories() {
  const nav = $("#categories");
  nav.replaceChildren();
  [{ id: "all" }, ...state.data.categories].forEach((category) => {
    const count = state.papers.filter((p) => category.id === "all" || p.categories.includes(category.id)).length;
    const button = element("button", "category-button");
    button.type = "button";
    button.setAttribute("aria-pressed", String(state.category === category.id));
    button.append(element("span", "", category.id === "all" ? tr("All topics", "全部主题") : categoryLabel(category.id)), element("span", "", String(count)));
    button.addEventListener("click", () => {
      state.category = category.id;
      state.page = 1;
      renderCategories();
      renderResults();
    });
    nav.append(button);
  });
}
function resetFilters(scope = "all") {
  Object.assign(state, { category: "all", journal: "all", scope, query: "", days: 90, page: 1 });
  $("#search").value = ""; $("#period").value = "90";
  $("#journal").value = "all"; $("#scope").value = scope;
  renderCategories(); renderResults();
}
function renderResults() {
  const end = new Date(state.data.window_end + "T00:00:00Z");
  const cutoff = new Date(end.getTime() - (state.days - 1) * 86400000).toISOString().slice(0, 10);
  const query = state.query.trim().toLowerCase();
  const results = state.papers.filter((paper) =>
    paper.date >= cutoff && (state.category === "all" || paper.categories.includes(state.category)) &&
    (state.journal === "all" || paper.journal_short === state.journal) &&
    (state.scope === "all" || (state.scope === "featured" ? Boolean(paper.featured) : !paper.featured)) &&
    (!query || [paper.title, paper.journal, paper.journal_short, paper.doi, ...paper.authors].join(" ").toLowerCase().includes(query))
  );
  $("#latest-title").textContent = state.scope === "featured" ? tr("Spotlight papers", "重点期刊文献") : state.scope === "other" ? tr("Other journal papers", "其他期刊文献") : tr("Latest papers", "最新文献");
  const journalName = state.data.journals.find((j) => j.short === state.journal)?.name;
  $("#result-count").textContent = `${results.length} ${tr("papers", "篇文献")} · ${journalName || scopeLabel(state.scope)} · ${state.category === "all" ? tr("All topics", "全部主题") : categoryLabel(state.category)} · ${tr("through", "截至")} ${state.data.window_end}`;
  const pages = Math.max(1, Math.ceil(results.length / state.pageSize));
  if (state.page > pages) state.page = pages;
  const start = (state.page - 1) * state.pageSize;
  $("#paper-list").replaceChildren(...results.slice(start, start + state.pageSize).map(paperCard));
  if (!results.length) $("#paper-list").append(element("p", "empty", tr("No matching papers. Clear filters or expand the date range.", "当前条件下没有匹配文献。可以清除筛选或扩大时间范围。")));
  renderPagination(pages);
  $("#clear").hidden = [state.category, state.journal, state.scope].every((v) => v === "all") && !state.query && state.days === 90;
  $("#back-all").hidden = state.scope === "all";
}
function renderPagination(pages) {
  const nav = $("#pagination");
  nav.replaceChildren();
  if (pages <= 1) return;
  const previous = element("button", "page-button", tr("← Previous", "← 上一页"));
  previous.disabled = state.page === 1;
  const go = (page) => { state.page = page; renderResults(); $("#latest").scrollIntoView({behavior:"auto"}); };
  previous.addEventListener("click", () => go(state.page - 1));
  nav.append(previous);
  for (let page = 1; page <= pages; page += 1) {
    if (pages > 7 && page !== 1 && page !== pages && Math.abs(page - state.page) > 1) {
      if (page === 2 || page === pages - 1) nav.append(element("span", "page-gap", "…"));
      continue;
    }
    const button = element("button", `page-button${page === state.page ? " active" : ""}`, String(page));
    button.setAttribute("aria-label", tr(`Page ${page}`, `第 ${page} 页`));
    if (page === state.page) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => go(page));
    nav.append(button);
  }
  const next = element("button", "page-button", tr("Next →", "下一页 →"));
  next.disabled = state.page === pages;
  next.addEventListener("click", () => go(state.page + 1));
  nav.append(next);
}
function bindControls() {
  state.data.journals.forEach((journal) => {
    const node = element("option", "", journal.name); node.value = journal.short; $("#journal").append(node);
  });
  $("#journal").addEventListener("change", (event) => {
    state.journal = event.target.value;
    // Selecting a journal must not leave an incompatible hidden spotlight filter.
    if (state.journal !== "all") { state.scope = "all"; $("#scope").value = "all"; }
    state.page = 1; renderResults();
  });
  $("#scope").addEventListener("change", (event) => {
    state.scope = event.target.value;
    state.journal = "all"; $("#journal").value = "all";
    state.page = 1; renderResults();
  });
  $("#search").addEventListener("input", (event) => { state.query = event.target.value; state.page = 1; renderResults(); });
  $("#period").addEventListener("change", (event) => { state.days = Number(event.target.value); state.page = 1; renderResults(); });
  $("#featured-all").addEventListener("click", () => {
    resetFilters("featured"); $("#latest").scrollIntoView({ behavior: "auto" });
  });
  $("#clear").addEventListener("click", () => {
    resetFilters();
  });
  $("#back-all").addEventListener("click", () => resetFilters());
}
async function getJSON(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
function renderSnapshot() {
  if (!state.data) return;
  const data = state.data;
  const featured = state.papers.filter((p) => p.featured);
  $("#featured-journals").textContent = data.featured_journals.map((short) => short === "PNAS" ? short : data.journals.find((j) => j.short === short)?.name || short).join(" · ");
  $("#featured-order").textContent = tr("Network-science research published in these selected leading journals, subject to the same inclusion criteria as the full feed.", "精选上述重点期刊中的网络科学研究，与全站文章采用相同的主题收录标准。");
  $("#total-stat").textContent = String(state.papers.length);
  $("#featured-stat").textContent = String(featured.length);
  const updated = new Date(data.generated_at).toLocaleString(language === "zh" ? "zh-CN" : "en-GB", { timeZone: "Asia/Shanghai", hour12: false });
  $("#updated").textContent = tr(`Last successful update: ${updated} (Beijing)`, `最近成功更新：${updated}（北京时间）`);
  $("#featured-list").replaceChildren(...featured.slice(0, 6).map(featureCard));
  if (!featured.length) $("#featured-list").append(element("p", "empty", tr("No spotlight papers passed this snapshot's screening. This does not mean no relevant papers were published.", "本次快照没有通过筛选的重点期刊文章；这不代表近期没有相关论文。")));
  const truncated = data.coverage.filter((q) => q.truncated).length;
  if (truncated) $("#status").classList.add("warning");
  $("#status").textContent = tr(`90-day feed · journal whitelist · core network science and transferable contributions · reviewed fixed cohort.`, `近 90 天 · 期刊白名单 · 核心网络科学与可迁移贡献 · 已审读固定池。`);
  $("#coverage-summary").textContent = tr(`${data.coverage.length} journal queries; ${data.candidate_count} unique candidates; ${data.papers.length} included. Rules v${data.screening_version}. ${truncated ? `${truncated} queries reached the retrieval budget.` : "All journal queries stayed within the retrieval budget."} Topic counts overlap. Date filters are relative to the snapshot end date.`, `查询 ${data.coverage.length} 本期刊，去重候选 ${data.candidate_count} 条，收录 ${data.papers.length} 篇。规则版本 v${data.screening_version}。${truncated ? `${truncated} 个查询达到采集预算。` : "所有期刊查询均未达到采集预算。"} 主题分类可重叠，时间筛选以快照截止日为基准。`);
  if (data.rescreening?.scope === "existing_papers_only") {
    $("#coverage-summary").textContent = tr(`Rules v${data.screening_version}: re-screened the existing ${data.rescreening.input_count} papers; ${data.papers.length} retained, no new papers added. Earlier unreviewed candidates were not processed in this run. Topics may overlap; date filters use the snapshot end date.`, `规则 v${data.screening_version}：仅重筛原有 ${data.rescreening.input_count} 篇，保留 ${data.papers.length} 篇，未新增文献。此前待核查候选未在本轮处理。主题可重叠，时间筛选以快照截止日为基准。`);
  }
  const pending = Object.entries(data.screening_counts || {}).filter(([reason]) => reason.startsWith("review_") || reason === "missing_or_partial_date").reduce((sum, [, count]) => sum + count, 0);
  $("#coverage-summary").textContent += tr(` ${pending} candidates awaiting review, not displayed as papers.`, ` ${pending} 条候选待核查，未作为论文展示。`);
  if (Date.now() - new Date(data.generated_at).getTime() > 48 * 3600000) {
    $("#status").textContent += tr(" Warning: snapshot is over 48 hours old.", " 注意：快照已超过 48 小时未更新。");
    $("#status").classList.add("warning");
  }
  if (!state.attempt?.ok) {
    $("#status").textContent += state.attempt ? tr(" The latest collection failed; the previous valid snapshot is retained.", " 最近一次采集未完整成功，当前保留上次有效快照。") : tr(" Latest collection status unavailable.", " 最近采集状态不可用。");
    $("#status").classList.add("warning");
  }
  renderCategories(); renderResults();
}
function renderUnavailable() {
  $("#status").textContent = tr("Paper snapshot unavailable or incompatible with current rules. No sample papers are substituted. Please retry later.", "文献快照暂不可用或为旧版快照，不符合当前规则。未使用示例论文，请稍后重试。");
  $("#status").classList.add("warning");
  $("#paper-list").replaceChildren(element("p", "empty", tr("Papers currently unavailable.", "暂时无法展示文献。")));
  $("#featured-list").replaceChildren(element("p", "empty", tr("No valid snapshot available.", "暂无可用文献快照。")));
  $("#updated").textContent = tr("No verifiable update time", "尚无可验证的更新时间");
  $("#result-count").textContent = tr("Data unavailable", "数据不可用");
  $("#featured-all").disabled = true; $("#search").disabled = true;
  document.querySelectorAll("select").forEach((node) => { node.disabled = true; });
}
async function init() {
  try {
    const data = await getJSON("data/papers.json");
    if (!Array.isArray(data.papers) || !data.window_end || !Array.isArray(data.coverage) || data.screening_version !== 8 || !data.featured_journals || !data.journals) throw new Error("Invalid or outdated snapshot");
    state.data = data;
    state.papers = [...data.papers].sort((a, b) => b.date.localeCompare(a.date) || b.doi.localeCompare(a.doi));
    try { state.attempt = await getJSON("data/status.json"); } catch { state.attempt = null; }
    bindControls();
    languageListeners.push(renderSnapshot);
    renderSnapshot();
  } catch (error) {
    console.error(error);
    languageListeners.push(renderUnavailable);
    renderUnavailable();
  }
}
init();
