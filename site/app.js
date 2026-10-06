"use strict";
const $ = (selector) => document.querySelector(selector);
const state = { data: null, papers: [], category: "all", journal: "all", scope: "all", query: "", days: 30, page: 1, pageSize: 10 };
const scopeLabel = (id) => ({ all: tr("All journals", "全部期刊"), featured: tr("Spotlight journals", "Spotlight 期刊"), other: tr("Other journals", "其他期刊") })[id];
const dateLabel = (id) => ({ "publisher.accepted": tr("Accepted date — not publication", "接收日期，非发表日期"), "published-online": tr("Online publication", "在线发表"), "published-print": tr("Print publication", "纸刊发表"), published: tr("Publication date", "发表日期"), issued: tr("Issue date", "出版日期") })[id] || id;
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
  const node = element("time", "", paper.publication_status === "accepted" ? tr(`Accepted ${paper.date}`, `接收 ${paper.date}`) : paper.date);
  node.dateTime = paper.date;
  node.title = dateLabel(paper.date_source);
  return node;
}
function readingNote(paper) {
  return element("p", "reading-note", tr(paper.note_en, paper.note_zh));
}
function journalLabel(paper) {
  return paper.journal_short === "PNAS" || paper.short === "PNAS" ? "PNAS" : paper.journal || paper.name;
}
function renderSuggestion() {
  const entry = state.data.daily_suggestions?.[0];
  const paper = entry && state.papers.find(p => p.doi === entry.doi);
  $("#suggestion").hidden = !paper;
  $("#suggestion-content").replaceChildren();
  if (!paper) return;
  $("#suggestion-date").textContent = tr(`Recommended ${entry.recommended_on}`, `推荐于 ${entry.recommended_on}`);
  const card = element("article", "suggestion-card");
  const body = element("div", "suggestion-body");
  const intro = element("div", "suggestion-intro");
  const meta = element("div", "feature-top");
  const journal = element("span", "journal-badge", journalLabel(paper));
  journal.title = paper.journal;
  meta.append(journal, timeNode(paper));
  if (paper.publication_status === "accepted") meta.append(statusBadge(paper));
  const title = element("h3"); title.append(link(paper.title, paper.url));
  intro.append(meta, title, element("p", "authors", paper.authors.join(" · ")),
    element("p", "suggestion-question", tr(entry.question.en, entry.question.zh)),
    link(tr("Read paper ↗", "阅读原文 ↗"), paper.url, "suggestion-link"));
  const reasons = element("div", "suggestion-reasons");
  reasons.append(element("h4", "", tr("Why read it", "为什么值得读")));
  entry.reasons.forEach((reason, index) => {
    const row = element("div", "suggestion-reason");
    const text = element("div");
    text.append(element("h5", "", tr(reason.heading.en, reason.heading.zh)),
      element("p", "", tr(reason.text.en, reason.text.zh)));
    row.append(element("span", "reason-number", String(index + 1).padStart(2, "0")), text);
    reasons.append(row);
  });
  reasons.append(element("p", "suggestion-audience", tr("For: ", "适合读者：") + tr(entry.audience.en, entry.audience.zh)));
  body.append(intro, reasons);
  const footer = element("div", "suggestion-footer");
  footer.append(element("p", "", entry.selection === "from_archive" ? tr("From the collection · original paper date shown above", "馆藏回选 · 原文日期如上") : tr("Newly added in this update", "本轮新收录")));
  const details = element("details");
  details.append(element("summary", "", tr("Reading basis & limitations", "审读依据与阅读提示")),
    element("p", "", tr(entry.reading_caveat.en, entry.reading_caveat.zh)));
  footer.append(details); card.append(body, footer);
  $("#suggestion-content").append(card);
}
function statusBadge(paper) {
  return element("span", "badge accepted-badge", tr("Accepted · publication pending", "已接收 · 待正式发表"));
}
function articleBadge(paper) {
  const types = { Commentary: tr("Commentary", "评论"), Perspective: tr("Perspective", "观点"), Comment: tr("Comment", "评论"), Review: tr("Review", "综述"), "Review Article": tr("Review", "综述") };
  return types[paper.article_type] ? element("span", "badge type-badge", types[paper.article_type]) : null;
}
function hasOtherJournals() {
  return state.papers.some((paper) => !paper.featured) || state.data.journals.some((journal) => !state.data.featured_journals.includes(journal.short));
}
function featureCard(paper) {
  const card = element("article", "feature-card");
  const top = element("div", "feature-top");
  const journal = element("span", "journal-badge", journalLabel(paper));
  journal.title = paper.journal;
  top.append(journal, timeNode(paper));
  if (paper.publication_status === "accepted") top.append(statusBadge(paper));
  const type = articleBadge(paper);
  if (type) top.append(type);
  const title = element("h3");
  title.append(link(paper.title, paper.url));
  const bottom = element("div", "feature-bottom");
  bottom.append(element("span", "", categoryLabel(paper.categories[0])), link(tr("Read paper ↗", "阅读原文 ↗"), paper.url));
  card.append(top, title, readingNote(paper), bottom);
  return card;
}
function paperCard(paper) {
  const card = element("article", "paper-card");
  const top = element("div", "paper-top");
  const journal = element("span", "journal-name", journalLabel(paper) || tr("Journal unavailable", "期刊名称缺失"));
  journal.title = paper.journal;
  top.append(journal);
  top.append(timeNode(paper));
  if (paper.publication_status === "accepted") top.append(statusBadge(paper));
  const type = articleBadge(paper);
  if (type) top.append(type);
  const title = element("h3");
  title.append(link(paper.title, paper.url));
  const authors = paper.authors.filter(Boolean);
  const byline = element("p", "authors", authors.slice(0, 4).join(" · ") + (authors.length > 4 ? " · et al." : "") || tr("Author information awaiting verification — see publisher", "作者信息待核验，请查看出版方"));
  if (paper.author_metadata_status === "partial") byline.append(element("span", "", tr(" · Author list incomplete — see publisher", " · 作者名单不完整，请查看出版方")));
  const bottom = element("div", "paper-bottom");
  const tags = element("div", "tags");
  paper.categories.forEach((id) => tags.append(element("span", "tag", categoryLabel(id))));
  bottom.append(tags, link(tr("Read paper ↗", "原文 ↗"), paper.url, "paper-link"));
  const details = element("details", "evidence");
  details.append(element("summary", "", tr("Details", "详细信息")));
  if (authors.length) details.append(element("p", "full-authors", tr("All authors: ", "全部作者：") + authors.join(" · ")));
  if (paper.article_type) details.append(element("p", "", tr("Article type: ", "文章类型：") + paper.article_type));
  if (paper.type_provenance?.basis_kind === "explicit_abstract_research_inference") details.append(element("p", "", tr("Original research supported by the abstract; exact publisher subtype not specified.", "摘要支持其研究性质；未指定出版方的精确文章子类型。")));
  if (paper.publication_status === "accepted") details.append(element("p", "", tr("Accepted manuscript; publication date and available publisher subtype will be rechecked after publication.", "已接收，待正式发表；届时补核发表日期及可获得的出版方文章子类型。")));
  if (paper.review_evidence_kind === "online_short_comment") details.append(element("p", "", tr("Reading note based on the accessible text of a no-abstract scientific commentary.", "阅读说明依据在线审读的无摘要科学评论正文。")));
  if (paper.review_evidence_kind === "abstract_excerpt") details.append(element("p", "", tr("Reading note based on the publisher's Abstract excerpt; the full article was not reviewed.", "阅读说明依据出版方的摘要摘段，未审读全文。")));
  details.append(element("p", "", `${dateLabel(paper.date_source)} · ${paper.date} · DOI: ${paper.doi}`));
  if (paper.entry_kind === "editorial_related_reading") details.append(element("p", "", tr("Related reading selected by the editor for its relevance to network-science readers; network science is not its main subject.", "编辑选入的延伸阅读，供网络科学读者参考；网络科学并非其主要主题。")));
  else if (paper.scope_class === "transferable_application") details.append(element("p", "", tr("Included for its transferable network-science method or theory.", "收录理由：具有可迁移的网络科学方法或理论。")));
  if (paper.author_metadata_status !== "available") details.append(element("p", "", tr("Author information is incomplete; consult the publisher.", "作者信息尚不完整，请查看出版方。")));
  if (paper.has_update) details.append(element("p", "", tr("Check the publisher for corrections or retractions.", "请查看出版方的更正或撤稿信息。")));
  details.append(link(tr("Publisher page ↗", "出版方页面 ↗"), paper.url));
  card.append(top, title, byline, readingNote(paper), bottom, details);
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
function resetFilters(scope = "all", days = 30) {
  Object.assign(state, { category: "all", journal: "all", scope, query: "", days, page: 1 });
  $("#search").value = ""; $("#period").value = String(days);
  $("#journal").value = "all"; $("#scope").value = scope;
  renderCategories(); renderResults();
}
function renderResults() {
  const end = new Date(state.data.window_end + "T00:00:00Z");
  const cutoff = state.days === 0 ? state.data.window_start : new Date(end.getTime() - (state.days - 1) * 86400000).toISOString().slice(0, 10);
  const query = state.query.trim().toLowerCase();
  const results = state.papers.filter((paper) =>
    paper.date >= cutoff && (state.category === "all" || paper.categories.includes(state.category)) &&
    (state.journal === "all" || paper.journal_short === state.journal) &&
    (state.scope === "all" || (state.scope === "featured" ? Boolean(paper.featured) : !paper.featured)) &&
    (!query || [paper.title, paper.journal, paper.journal_short, paper.doi, ...paper.authors].join(" ").toLowerCase().includes(query))
  );
  $("#latest-title").textContent = state.scope === "featured" ? tr("Spotlight papers", "Spotlight 文献") : state.scope === "other" ? tr("Other journal papers", "其他期刊文献") : tr("All papers", "全部文献");
  const journalName = state.data.journals.find((j) => j.short === state.journal)?.name;
  $("#result-count").textContent = `${results.length} ${tr(results.length === 1 ? "paper" : "papers", "篇文献")}${journalName ? " · " + journalName : ""}${state.category === "all" ? "" : " · " + categoryLabel(state.category)}`;
  const pages = Math.max(1, Math.ceil(results.length / state.pageSize));
  if (state.page > pages) state.page = pages;
  const start = (state.page - 1) * state.pageSize;
  $("#paper-list").replaceChildren(...results.slice(start, start + state.pageSize).map(paperCard));
  if (!results.length) $("#paper-list").append(element("p", "empty", tr("No matching papers. Clear filters or expand the date range.", "当前条件下没有匹配文献。可以清除筛选或扩大时间范围。")));
  renderPagination(pages);
  $("#clear").hidden = [state.category, state.journal, state.scope].every((v) => v === "all") && !state.query && state.days === 30;
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
  // Keep the original Spotlight order; append the other journals in source order.
  const journals = [...state.data.journals].sort((a, b) => {
    const rank = (journal) => {
      const index = state.data.featured_journals.indexOf(journal.short);
      return index < 0 ? state.data.featured_journals.length : index;
    };
    return rank(a) - rank(b);
  });
  journals.forEach((journal) => {
    const node = element("option", "", journalLabel(journal)); node.value = journal.short; $("#journal").append(node);
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
    resetFilters(hasOtherJournals() ? "featured" : "all", 0); $("#latest").scrollIntoView({ behavior: "auto" });
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
  renderSuggestion();
  $("#journal").setAttribute("aria-label", tr("Journal", "期刊"));
  $("#period").setAttribute("aria-label", tr("Dates", "日期"));
  $("#scope").setAttribute("aria-label", tr("Journal scope", "期刊范围"));
  const featured = state.papers.filter((p) => p.featured);
  $("#featured-all").textContent = tr(`View all ${featured.length} Spotlight ${featured.length === 1 ? "paper" : "papers"} →`, `查看全部 ${featured.length} 篇 Spotlight 文献 →`);
  $("#date-cutoff").textContent = tr(`Data through ${data.window_end}`, `数据截至 ${data.window_end}`);
  const month = new Date(data.window_end + "T12:00:00Z").toLocaleDateString(language === "zh" ? "zh-CN" : "en-GB", { year: "numeric", month: "long", timeZone: "Asia/Shanghai" });
  const firstMonth = new Date(data.window_start + "T12:00:00Z").toLocaleDateString(language === "zh" ? "zh-CN" : "en-GB", { year: "numeric", month: "long", timeZone: "Asia/Shanghai" });
  $("#edition").textContent = `${firstMonth === month ? month : firstMonth + " – " + month} · ${state.papers.length} ${tr("papers", "篇文献")}`;
  $("#scope-control").hidden = !hasOtherJournals();
  const updated = new Date(data.generated_at).toLocaleDateString(language === "zh" ? "zh-CN" : "en-GB", { timeZone: "Asia/Shanghai", year: "numeric", month: "long", day: "numeric" });
  $("#updated").textContent = tr(`Updated ${updated}`, `更新于 ${updated}`);
  $("#featured-list").replaceChildren(...featured.slice(0, 6).map(featureCard));
  if (!featured.length) $("#featured-list").append(element("p", "empty", tr("No spotlight papers passed this snapshot's screening. This does not mean no relevant papers were published.", "本次快照没有通过筛选的 Spotlight 文献；这不代表近期没有相关论文。")));
  const counts = data.screening_counts;
  const pending = counts.review + counts.deferred_unassessed;
  $("#status").hidden = pending === 0;
  $("#status").textContent = tr(`${pending} candidates awaiting evidence.`, `${pending} 篇候选待补证。`);
  $("#coverage-summary").textContent = tr(`${data.window_start} – ${data.window_end}: ${data.published_count} published papers and ${data.accepted_count} accepted manuscripts.`, `${data.window_start} 至 ${data.window_end}：已发表 ${data.published_count} 篇，已接收 ${data.accepted_count} 篇。`);
  if (!state.attempt?.ok) {
    $("#status").hidden = false;
    $("#status").textContent += state.attempt ? tr(" The latest collection failed; the previous valid snapshot is retained.", " 最近一次采集未完整成功，当前保留上次有效快照。") : tr(" Latest collection status unavailable.", " 最近采集状态不可用。");
    $("#status").classList.add("warning");
  }
  renderCategories(); renderResults();
}
function renderUnavailable() {
  $("#suggestion").hidden = true;
  $("#status").hidden = false;
  $("#status").textContent = tr("Paper list unavailable or incompatible. Please try again later.", "文献列表暂不可用或为旧版快照，请稍后重试。");
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
    if (!Array.isArray(data.papers) || !data.window_end || !Array.isArray(data.coverage) || data.screening_version !== "newflow-1" || !data.featured_journals || !data.journals) throw new Error("Invalid or outdated snapshot");
    if (!data.screening_counts || data.papers.some(p => !p.note_en || !p.note_zh || !["published", "accepted"].includes(p.publication_status))) throw new Error("Missing reading notes or publication status");
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
