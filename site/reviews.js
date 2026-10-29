"use strict";
// Reuse the canonical card, topic navigation and pagination from app.js.
Object.assign(state, { days: 0, year: "all", order: "newest" });

function resetReviewFilters() {
  Object.assign(state, { category: "all", journal: "all", query: "", year: "all", order: "newest", page: 1 });
  $("#search").value = "";
  $("#journal").value = $("#year").value = "all";
  $("#order").value = "newest";
  renderCategories(); renderReviewResults();
}
function renderReviewResults() {
  const query = state.query.trim().toLowerCase();
  const results = state.papers.filter(p =>
    (state.category === "all" || p.categories.includes(state.category)) &&
    (state.journal === "all" || p.journal_short === state.journal) &&
    (state.year === "all" || p.date.slice(0, 4) === state.year) &&
    (!query || [p.title, p.journal, p.journal_short, p.doi, ...p.authors].join(" ").toLowerCase().includes(query))
  ).sort((a, b) => (state.order === "oldest" ? a.date.localeCompare(b.date) : b.date.localeCompare(a.date)) || a.doi.localeCompare(b.doi));
  $("#latest-title").textContent = tr("Review collection", "综述馆藏");
  $("#result-count").textContent = tr(`${results.length} ${results.length === 1 ? "review" : "reviews"}`, `${results.length} 篇综述`);
  const pages = Math.max(1, Math.ceil(results.length / state.pageSize));
  state.page = Math.min(state.page, pages);
  $("#paper-list").replaceChildren(...results.slice((state.page - 1) * state.pageSize, state.page * state.pageSize).map(paperCard));
  if (!results.length) $("#paper-list").append(element("p", "empty", tr("No matching reviews. Clear filters to browse the collection.", "当前条件下没有匹配综述，可以清除筛选浏览全部馆藏。")));
  $("#clear").hidden = state.category === "all" && state.journal === "all" && state.year === "all" && !state.query && state.order === "newest";
  renderPagination(pages);
}
function renderReviewSnapshot() {
  $("#edition").textContent = tr(`${state.papers.length} selected reviews · 2000 onwards`, `${state.papers.length} 篇精选综述 · 2000 年起`);
  $("#review-summary").textContent = tr(
    `${state.reviewData.selection_count} selected reviews from Physics Reports and Reviews of Modern Physics. This is a selected reading collection, not an exhaustive bibliography.`,
    `收录 Physics Reports 与 Reviews of Modern Physics 的 ${state.reviewData.selection_count} 篇精选综述。这是一份综述选集，不代表完整历史目录。`);
  $("#review-cutoff").textContent = tr(`Selection through ${state.reviewData.cutoff_date}. Original publication dates are shown.`, `选集截至 ${state.reviewData.cutoff_date}，文献显示原始发表日期。`);
  renderCategories(); renderReviewResults();
}
async function initReviews() {
  try {
    const [data, reviews] = await Promise.all([getJSON("data/papers.json"), getJSON("data/reviews.json")]);
    if (reviews.version !== "review-collection-1" || !Array.isArray(reviews.papers) || !Array.isArray(reviews.current_collection_dois)) throw new Error("Invalid review collection");
    const current = new Map(data.papers.map(p => [p.doi, p]));
    const selected = new Map();
    for (const p of reviews.papers) {
      if (current.has(p.doi) || selected.has(p.doi)) throw new Error("Duplicate review DOI");
      selected.set(p.doi, p);
    }
    for (const doi of reviews.current_collection_dois) {
      if (!current.has(doi) || selected.has(doi)) throw new Error("Review reference missing or duplicated");
      selected.set(doi, current.get(doi));
    }
    if (selected.size !== reviews.total_count || [...selected.values()].some(p => !p.note_en || !p.note_zh || !Array.isArray(p.authors) || !Array.isArray(p.categories))) throw new Error("Incomplete review records");
    state.data = data; state.reviewData = reviews; state.papers = [...selected.values()];
    const journals = [...new Map(state.papers.map(p => [p.journal_short, p.journal])).entries()].sort((a,b) => a[1].localeCompare(b[1]));
    for (const [short, name] of journals) {
      const option = element("option", "", name); option.value = short; $("#journal").append(option);
    }
    for (const year of [...new Set(state.papers.map(p => p.date.slice(0, 4)))].sort().reverse()) {
      const option = element("option", "", year); option.value = year; $("#year").append(option);
    }
    for (const [selector, field, eventName] of [["#journal", "journal", "change"], ["#year", "year", "change"], ["#order", "order", "change"], ["#search", "query", "input"]]) {
      $(selector).addEventListener(eventName, event => { state[field] = event.target.value; state.page = 1; renderReviewResults(); });
    }
    $("#clear").addEventListener("click", resetReviewFilters);
    $("#status").hidden = true;
    languageListeners.push(renderReviewSnapshot);
    renderReviewSnapshot();
  } catch (error) {
    console.error(error);
    const unavailable = () => {
      $("#status").hidden = false;
      $("#status").textContent = tr("Review collection unavailable. Please try again later.", "综述馆藏暂不可用，请稍后重试。");
      $("#result-count").textContent = tr("Data unavailable", "数据不可用");
      $("#paper-list").replaceChildren();
      document.querySelectorAll("select, #search").forEach(node => { node.disabled = true; });
    };
    languageListeners.push(unavailable); unavailable();
  }
}
initReviews();
