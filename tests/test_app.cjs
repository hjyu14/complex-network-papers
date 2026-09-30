// Minimal DOM double: deterministic UI logic tests, not a browser/layout substitute.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class Node {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.attrs = {}; this.events = {};
    this.textContent = ''; this.value = ''; this.hidden = false;
    this.classList = { add() {} };
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this.attrs[key] = value; }
  getAttribute(key) { return this.attrs[key]; }
  addEventListener(event, listener) { this.events[event] = listener; }
  scrollIntoView() {}
}
const config = JSON.parse(fs.readFileSync(path.join(__dirname, '../config/sources.json'), 'utf8'));
const localeSource = fs.readFileSync(path.join(__dirname, '../site/i18n.js'), 'utf8');
const source = fs.readFileSync(path.join(__dirname, '../site/app.js'), 'utf8');
function setup(version = 6) {
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, new Node());
    return nodes.get(id);
  };
  const base = { url: 'https://doi.org/10.1234/test', authors: [], journal: 'Physical Review E', journal_short: 'PRE', featured: null, categories: ['network_structure'], screening_basis: 'network', evidence: ['complex networks'], date_source: 'published-online', retrieved_by: ['journal: PRE'], metadata_url: 'https://api.crossref.org/works/10.1234/test' };
  const papers = Array.from({ length: 35 }, (_, i) => ({ ...base, doi: `10.1234/${i}`, title: `Synthetic test ${i}`, date: i < 10 ? '2026-09-29' : '2026-07-02' }));
  for (let i = 0; i < 8; i++) papers[i] = { ...papers[i], categories: ['network_collective'], journal_short: 'PNAS', journal: 'Proceedings of the National Academy of Sciences', featured: 'PNAS' };
  papers[8].categories = ['other'];
  const data = { papers, generated_at: new Date().toISOString(), window_start: '2026-07-02', window_end: '2026-09-29', screening_version: version, coverage: [], candidate_count: 35, categories: [...config.network_categories, {id:'other',label:'其他'}], featured_journals: config.featured_journals, featured_order_year: config.featured_order_year, journals: config.journals };
  const context = vm.createContext({ URL, Date, console, document: { documentElement: {}, querySelector: node, createElement: (tag) => new Node(tag), querySelectorAll: (selector) => selector === 'select' ? ['#period', '#scope', '#journal'].map(node) : [] }, fetch: async (url) => ({ ok: true, json: async () => url.includes('status') ? { ok: true } : data }) });
  vm.runInContext(localeSource, context);
  vm.runInContext(source, context);
  return { node, context, data };
}
const ready = () => new Promise(setImmediate);

test('spotlight can exit through scope, journal, return and reset', async () => {
  const { node, context } = setup(); await ready();
  assert.equal(node('#paper-list').children.length, 30);
  node('#load-more').events.click();
  assert.equal(node('#paper-list').children.length, 35);
  node('#featured-all').events.click();
  assert.match(node('#result-count').textContent, /^8 papers/);
  assert.equal(node('#scope').value, 'featured');
  assert.equal(node('#back-all').hidden, false);
  node('#scope').events.change({target:{value:'other'}});
  assert.match(node('#result-count').textContent, /^27 papers/);
  node('#scope').events.change({target:{value:'all'}});
  assert.match(node('#result-count').textContent, /^35 papers/);
  node('#featured-all').events.click();
  node('#journal').events.change({target:{value:'PRE'}});
  assert.match(node('#result-count').textContent, /^27 papers/);
  assert.equal(vm.runInContext('state.scope', context), 'all');
  node('#featured-all').events.click();
  node('#back-all').events.click();
  assert.match(node('#result-count').textContent, /^35 papers/);
  node('#featured-all').events.click();
  node('#clear').events.click();
  assert.equal(node('#clear').hidden, true);
});

test('search, dates, theme intersection and other', async () => {
  const { node } = setup(); await ready();
  node('#search').events.input({ target: { value: 'PNAS' } });
  assert.match(node('#result-count').textContent, /^8 papers/);
  node('#clear').events.click();
  node('#period').events.change({ target: { value: '7' } });
  assert.match(node('#result-count').textContent, /^10 papers/);
  node('#categories').children.at(-1).events.click();
  assert.match(node('#result-count').textContent, /^1 papers/);
  node('#journal').events.change({target:{value:'PNAS'}});
  assert.match(node('#result-count').textContent, /^0 papers/);
  assert.equal(node('#paper-list').children[0].className,'empty');
});

test('six newest cards, full journal names, ordered caption and other last', async () => {
  const {node} = setup(); await ready();
  const cards = node('#featured-list').children;
  assert.equal(cards.length,6);
  assert.equal(cards[0].children[0].children[0].textContent,'Proceedings of the National Academy of Sciences');
  assert.equal(cards[0].children[1].children[0].textContent,'Synthetic test 7');
  assert.equal(node('#featured-journals').textContent,'Nature Communications · Physical Review X · Science Advances · PNAS · Physical Review Letters');
  assert.equal(node('#categories').children[0].children[0].textContent,'All topics');
  assert.equal(node('#categories').children.at(-1).children[0].textContent,'Other');
});

test('old snapshot is blocked, not mislabeled as whitelist results', async () => {
  const { node } = setup(2); await ready();
  assert.match(node('#status').textContent, /incompatible/);
  assert.equal(node('#search').disabled, true);
  assert.equal(node('#scope').disabled, true);
});

test('titles are text and non-HTTPS links are rejected', async () => {
  const { context } = setup(); await ready();
  assert.throws(() => vm.runInContext('link("test", "javascript:alert(1)")', context), /不安全/);
  const n = vm.runInContext('element("h3", "", "<img src=x onerror=alert(1)>")', context);
  assert.equal(n.textContent, '<img src=x onerror=alert(1)>');
  assert.equal(n.children.length, 0);
});

test('language switch preserves filters, paper titles and authors', async () => {
  const {node, context} = setup(); await ready();
  assert.equal(vm.runInContext('language',context),'en');
  node('#journal').events.change({target:{value:'PRE'}});
  node('#period').events.change({target:{value:'7'}});
  const title = node('#paper-list').children[0].children[1].children[0].textContent;
  node('#language-toggle').events.click();
  assert.match(node('#result-count').textContent,/^2 篇文献/);
  assert.equal(node('#paper-list').children[0].children[1].children[0].textContent,title);
  assert.equal(vm.runInContext('state.journal', context),'PRE');
  assert.equal(vm.runInContext('state.days', context),7);
  assert.match(node('#paper-list').children[0].children[2].textContent,/作者元数据暂缺/);
  node('#language-toggle').events.click();
  assert.match(node('#result-count').textContent,/^2 papers/);
  assert.match(node('#paper-list').children[0].children[2].textContent,/Author metadata unavailable/);
  const card = vm.runInContext('paperCard({...state.papers[0], authors:["Ada Example"], author_metadata_status:"partial"})', context);
  assert.equal(card.children[2].textContent,'Ada Example');
  assert.match(card.children[2].children[0].textContent,/incomplete/);
});

test('journal options use only full names', async () => {
  const {node} = setup(); await ready();
  assert.deepEqual(node('#journal').children.map((n)=>n.textContent),config.journals.map((j)=>j.name));
});

test('failure UI also switches language', async () => {
  const {node} = setup(4); await ready();
  node('#language-toggle').events.click();
  assert.match(node('#status').textContent,/旧版快照/);
  assert.equal(node('#scope').disabled,true);
});

test('public rules article is linked and bilingual', () => {
  const home = fs.readFileSync(path.join(__dirname,'../site/index.html'),'utf8');
  const rules = fs.readFileSync(path.join(__dirname,'../site/rules.html'),'utf8');
  assert.match(home, /href="rules.html"/);
  assert.match(home, /<html lang="en">/);
  assert.match(rules, /data-language="en"/);
  assert.match(rules, /data-language="zh" hidden/);
  assert.match(rules, /Screening v6/);
});

test('pending candidates are disclosed separately in both languages', async () => {
  const { node, data } = setup();
  data.screening_counts = { included: 35, review_context: 4, review_missing_abstract: 3, missing_or_partial_date: 2, notice: 5 };
  await ready();
  assert.match(node('#coverage-summary').textContent, /9 candidates awaiting review/);
  assert.match(node('#result-count').textContent, /^35 papers/);
  node('#language-toggle').events.click();
  assert.match(node('#coverage-summary').textContent, /9 条候选待核查/);
});

test('published artifact has consistent rules, date bounds, counts and unique DOIs', () => {
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../site/data/papers.json'), 'utf8'));
  const audit = JSON.parse(fs.readFileSync(path.join(__dirname, '../site/data/screening-report.json'), 'utf8'));
  assert.equal(data.screening_version, config.version);
  assert.equal(audit.config_sha256, data.config_sha256);
  assert.equal(audit.window_end, data.window_end);
  assert.equal(audit.window_start, data.window_start);
  assert.equal(audit.collection_complete, true);
  assert.equal(data.papers.length, data.screening_counts.included);
  assert.equal(data.candidate_count, audit.decisions.length);
  assert.equal(new Set(data.papers.map(p => p.doi)).size, data.papers.length);
  assert.ok(data.papers.every(p => p.date >= data.window_start && p.date <= data.window_end && !('abstract' in p)));
  assert.equal((Date.parse(data.window_end) - Date.parse(data.window_start)) / 86400000 + 1, 90);
  assert.ok(data.coverage.every(q => !q.truncated && !q.failed));
});
