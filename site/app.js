"use strict";
const $ = (selector) => document.querySelector(selector);
const state = { data: null, papers: [], category: "all", featured: false, query: "", days: 90, limit: 30 };
const dateLabels = { "published-online": "在线发表", "published-print": "纸刊日期（回退）", published: "出版日期（回退）", issued: "issued 日期（回退）" };
const basisLabels = { title_explicit: "标题包含明确网络科学信号", title_network_mechanism: "标题同时包含网络对象与结构／动力学信号", abstract_support: "标题中的网络对象得到摘要机制信号支持" };

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
  if (parsed.protocol !== "https:") throw new Error("不安全的链接协议");
  node.href = parsed.href;
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}
function categoryLabel(id) {
  return state.data.categories.find((c) => c.id === id)?.label || "待分类";
}
function timeNode(paper) {
  const node = element("time", "", paper.date);
  node.dateTime = paper.date;
  node.title = dateLabels[paper.date_source] || paper.date_source;
  return node;
}
function featureCard(paper) {
  const card = element("article", "feature-card");
  const top = element("div", "feature-top");
  top.append(element("span", "journal-badge", paper.featured), timeNode(paper));
  const title = element("h3");
  title.append(link(paper.title, paper.url));
  const bottom = element("div", "feature-bottom");
  bottom.append(element("span", "", categoryLabel(paper.categories[0])), link("阅读原文 ↗", paper.url));
  card.append(top, title, bottom);
  return card;
}
function paperCard(paper) {
  const card = element("article", "paper-card");
  const top = element("div", "paper-top");
  top.append(element("span", "journal-name", paper.journal || "期刊名称缺失"));
  if (paper.featured) top.append(element("span", "badge", paper.featured));
  top.append(timeNode(paper));
  const title = element("h3");
  title.append(link(paper.title, paper.url));
  const authors = paper.authors.filter(Boolean);
  const byline = element("p", "authors", authors.slice(0, 4).join(" · ") + (authors.length > 4 ? " · et al." : "") || "作者信息未提供");
  const bottom = element("div", "paper-bottom");
  const tags = element("div", "tags");
  paper.categories.forEach((id) => tags.append(element("span", "tag", categoryLabel(id))));
  bottom.append(tags, link("原文 ↗", paper.url, "paper-link"));
  const details = element("details", "evidence");
  details.append(element("summary", "", "收录依据与日期来源"));
  details.append(element("p", "", `${basisLabels[paper.screening_basis]}；命中：${paper.evidence.join(" / ")}。`));
  details.append(element("p", "", `${dateLabels[paper.date_source]} · ${paper.date} · DOI: ${paper.doi}`));
  details.append(element("p", "", `检索路径：${paper.retrieved_by.join("；")}。规则筛选，未经人工逐篇审定。`));
  if (paper.has_update) details.append(element("p", "", "元数据存在更新关联，请查看出版方最新更正或撤稿说明。"));
  details.append(link("核对 Crossref 元数据 ↗", paper.metadata_url));
  card.append(top, title, byline, bottom, details);
  return card;
}
function renderCategories() {
  const nav = $("#categories");
  nav.replaceChildren();
  [{ id: "all", label: "全部方向" }, ...state.data.categories].forEach((category) => {
    const count = state.papers.filter((p) => category.id === "all" || p.categories.includes(category.id)).length;
    if (category.id === "unclassified" && !count) return;
    const button = element("button", "category-button");
    button.type = "button";
    button.setAttribute("aria-pressed", String(state.category === category.id));
    button.append(element("span", "", category.label), element("span", "", String(count)));
    button.addEventListener("click", () => {
      state.category = category.id;
      state.limit = 30;
      renderCategories();
      renderResults();
    });
    nav.append(button);
  });
}
function renderResults() {
  const end = new Date(state.data.window_end + "T00:00:00Z");
  const cutoff = new Date(end.getTime() - (state.days - 1) * 86400000).toISOString().slice(0, 10);
  const query = state.query.trim().toLowerCase();
  const results = state.papers.filter((paper) =>
    paper.date >= cutoff && (state.category === "all" || paper.categories.includes(state.category)) &&
    (!state.featured || paper.featured) &&
    (!query || [paper.title, paper.journal, paper.doi, ...paper.authors].join(" ").toLowerCase().includes(query))
  );
  $("#latest-title").textContent = state.featured ? "重点期刊文献" : "最新文献";
  $("#result-count").textContent = `${results.length} 篇文献 · ${state.category === "all" ? "全部方向" : categoryLabel(state.category)} · 截至 ${state.data.window_end}`;
  $("#paper-list").replaceChildren(...results.slice(0, state.limit).map(paperCard));
  if (!results.length) $("#paper-list").append(element("p", "empty", "当前条件下没有匹配文献。可以清除筛选或扩大时间范围。"));
  $("#load-more").hidden = results.length <= state.limit;
  $("#load-more").textContent = `加载更多文献（还有 ${Math.max(0, results.length - state.limit)} 篇）`;
  $("#clear").hidden = !state.featured && state.category === "all" && !state.query && state.days === 90;
}
function bindControls() {
  $("#search").addEventListener("input", (event) => { state.query = event.target.value; state.limit = 30; renderResults(); });
  $("#period").addEventListener("change", (event) => { state.days = Number(event.target.value); state.limit = 30; renderResults(); });
  $("#load-more").addEventListener("click", () => { state.limit += 30; renderResults(); });
  $("#featured-all").addEventListener("click", () => {
    state.featured = true; state.category = "all"; state.query = ""; state.days = 90; state.limit = 30;
    $("#search").value = ""; $("#period").value = "90";
    renderCategories(); renderResults(); $("#latest").scrollIntoView({ behavior: "auto" });
  });
  $("#clear").addEventListener("click", () => {
    Object.assign(state, { category: "all", featured: false, query: "", days: 90, limit: 30 });
    $("#search").value = ""; $("#period").value = "90";
    renderCategories(); renderResults();
  });
}
async function getJSON(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
async function init() {
  let data;
  try {
    data = await getJSON("data/papers.json");
    if (!Array.isArray(data.papers) || !data.window_end || !Array.isArray(data.coverage)) throw new Error("数据结构不完整");
  } catch (error) {
    $("#status").textContent = `文献快照暂不可用（${error.message}）。未使用示例论文，请稍后重试或查看项目采集记录。`;
    $("#status").classList.add("warning");
    $("#paper-list").replaceChildren(element("p", "empty", "暂时无法展示文献。"));
    $("#featured-list").replaceChildren(element("p", "empty", "暂无可用文献快照。"));
    $("#updated").textContent = "尚无可验证的更新时间";
    $("#result-count").textContent = "数据不可用";
    $("#featured-all").disabled = true; $("#search").disabled = true; $("#period").disabled = true;
    return;
  }
  state.data = data;
  state.papers = [...data.papers].sort((a, b) => b.date.localeCompare(a.date) || b.doi.localeCompare(a.doi));
  const featured = state.papers.filter((p) => p.featured);
  $("#total-stat").textContent = String(state.papers.length);
  $("#featured-stat").textContent = String(featured.length);
  $("#updated").textContent = `最近成功更新：${new Date(data.generated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })}（北京时间）`;
  $("#featured-list").replaceChildren(...featured.slice(0, 3).map(featureCard));
  if (!featured.length) $("#featured-list").append(element("p", "empty", "本次快照没有通过筛选的重点期刊文章；这不代表这些期刊近期没有相关论文。"));
  const truncated = data.coverage.filter((q) => q.truncated).length;
  $("#status").textContent = `快照范围 ${data.window_start} — ${data.window_end} · Crossref 元数据 · 自动规则筛选，可能误收或漏收${truncated ? ` · ${truncated} 个查询达到采集上限` : ""}。`;
  $("#coverage-summary").textContent = `本次共 ${data.coverage.length} 个查询，${data.candidate_count} 条去重候选，收录 ${data.papers.length} 篇；${truncated} 个查询未取尽结果。规则版本 v${data.screening_version}。分类数量可重叠。时间筛选以快照截止日为基准。`;
  const age = Date.now() - new Date(data.generated_at).getTime();
  if (age > 48 * 3600000) {
    $("#status").textContent += " 注意：快照已超过 48 小时未更新。";
    $("#status").classList.add("warning");
  }
  try {
    const status = await getJSON("data/status.json");
    if (!status.ok) {
      $("#status").textContent += ` 最近一次采集未完整成功（${status.errors.length} 个查询失败），当前保留上次有效快照。`;
      $("#status").classList.add("warning");
    }
  } catch {
    $("#status").textContent += " 最近采集状态不可用。";
    $("#status").classList.add("warning");
  }
  renderCategories(); renderResults(); bindControls();
}
init().catch((error) => {
  $("#status").textContent = `页面数据处理失败：${error.message}。请查看原始快照或反馈问题。`;
  $("#status").classList.add("warning");
});
