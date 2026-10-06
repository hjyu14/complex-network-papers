// Minimal DOM double: deterministic UI logic tests, not a browser/layout substitute.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const zlib = require('node:zlib');
function reportText(relative) {
  const file=path.join(__dirname,'..',relative);
  return fs.existsSync(file) ? fs.readFileSync(file,'utf8') : zlib.gunzipSync(fs.readFileSync(file+'.gz')).toString('utf8');
}

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
const collectionConfig = JSON.parse(fs.readFileSync(path.join(__dirname, '../config/sources.json'), 'utf8'));
// The published September fixture remains bound to its frozen nine-journal inputs.
const config = JSON.parse(fs.readFileSync(path.join(__dirname, '../reports/runs/2026-09/inputs/sources.json'), 'utf8'));
const topics = JSON.parse(fs.readFileSync(path.join(__dirname, '../config/publication-notes.json'), 'utf8'));
const localeSource = fs.readFileSync(path.join(__dirname, '../site/i18n.js'), 'utf8');
const source = fs.readFileSync(path.join(__dirname, '../site/app.js'), 'utf8');
function setup(version = 'newflow-1', fixtureConfig = config) {
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, new Node());
    return nodes.get(id);
  };
  const base = { url: 'https://doi.org/10.1234/test', authors: [], note_en:'A factual network reading note.', note_zh:'一条有证据的网络阅读说明。', publication_status:'published', journal: 'Nature Machine Intelligence', journal_short: 'NMI', featured: null, categories: ['network_structure'], screening_basis: 'network', evidence: ['complex networks'], date_source: 'published-online', retrieved_by: ['journal: PRE'], metadata_url: 'https://api.crossref.org/works/10.1234/test' };
  const papers = Array.from({ length: 35 }, (_, i) => ({ ...base, doi: `10.1234/${i}`, title: `Synthetic test ${i}`, date: i < 10 ? '2026-09-30' : '2026-09-01' }));
  for (let i = 0; i < 8; i++) papers[i] = { ...papers[i], categories: ['network_collective'], journal_short: 'PNAS', journal: 'Proceedings of the National Academy of Sciences', featured: 'PNAS' };
  papers[8].categories = ['other'];
  const data = { papers, generated_at: new Date().toISOString(), window_start: '2026-09-01', window_end: '2026-09-30', screening_version: version, coverage: [], candidate_count: 35, published_count:35, accepted_count:0, screening_counts:{included:35, excluded:0, review:0, deferred_unassessed:0}, categories: topics.categories, featured_journals: fixtureConfig.featured_journals, featured_order_year: fixtureConfig.featured_order_year, journals: fixtureConfig.journals };
  const context = vm.createContext({ URL, Date, console, document: { documentElement: {}, querySelector: node, createElement: (tag) => new Node(tag), querySelectorAll: (selector) => selector === 'select' ? ['#period', '#scope', '#journal'].map(node) : [] }, fetch: async (url) => ({ ok: true, json: async () => url.includes('status') ? { ok: true } : data }) });
  vm.runInContext(localeSource, context);
  vm.runInContext(source, context);
  return { node, context, data };
}
const ready = () => new Promise(setImmediate);

test('English is the first-visit default while explicit language choices persist', () => {
  for (const stored of [null, 'en', 'zh', 'invalid', 'storage-unavailable']) {
    const toggle = new Node('button');
    const root = {};
    const writes = [];
    const context = vm.createContext({
      localStorage: {
        getItem(key) { assert.equal(key, 'language'); if (stored === 'storage-unavailable') throw new Error('Storage denied'); return stored; },
        setItem(key, value) { writes.push([key, value]); }
      },
      document: { documentElement: root, querySelector: selector => selector === '#language-toggle' ? toggle : null, querySelectorAll: () => [] }
    });
    vm.runInContext(localeSource, context);
    const expected = stored === 'zh' ? 'zh' : 'en';
    assert.equal(vm.runInContext('language', context), expected);
    assert.equal(root.lang, expected === 'zh' ? 'zh-CN' : 'en');
    assert.equal(toggle.textContent, expected === 'zh' ? 'English' : '中文');
    toggle.events.click();
    assert.deepEqual(writes, [['language', expected === 'zh' ? 'en' : 'zh']]);
  }
});

test('public README defaults to English and offers a reciprocal Chinese version', () => {
  const english = fs.readFileSync(path.join(__dirname, '../README.md'), 'utf8');
  const chinese = fs.readFileSync(path.join(__dirname, '../README.zh-CN.md'), 'utf8');
  assert.match(english, /^# NetSci Observatory\s+English \| \[中文\]\(README\.zh-CN\.md\)/);
  assert.match(chinese, /^# NetSci Observatory\s+\[English\]\(README\.md\) \| 中文/);
  for (const text of [english, chinese]) {
    assert.ok(text.includes('https://netsciobs.com/'));
    assert.ok(text.includes('(docs/screening-protocol.md)'));
    assert.ok(text.includes('(docs/publication.md)'));
  }
});

test('home and rules pages share a local scalable favicon', () => {
  for (const page of ['index.html', 'rules.html']) {
    const html = fs.readFileSync(path.join(__dirname, '../site', page), 'utf8');
    assert.match(html.split('</head>')[0], /<link rel="icon" type="image\/svg\+xml" sizes="any" href="favicon\.svg\?v=1">/);
  }
  const icon = fs.readFileSync(path.join(__dirname, '../site/favicon.svg'), 'utf8');
  assert.match(icon, /<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" viewBox="0 0 64 64">/);
  assert.match(icon, /fill="#1c243c"/);
  assert.match(icon, /fill="#88d8df"/);
  assert.doesNotMatch(icon, /<(?:script|foreignObject|image)\b|\bhref=/i);
});

test('both public pages load one module analytics beacon and disclose it bilingually', () => {
  for (const page of ['index.html', 'rules.html']) {
    const html = fs.readFileSync(path.join(__dirname, '../site', page), 'utf8');
    const beacons = [...html.matchAll(/<script\b[^>]*data-cf-beacon='([^']+)'[^>]*><\/script>/g)];
    assert.equal(beacons.length, 1);
    assert.deepEqual(JSON.parse(beacons[0][1]), { token: '4948fb6be20f4793b65fcc1278d98a40' });
    assert.match(beacons[0][0], /type="module"/);
    assert.match(beacons[0][0], /src="https:\/\/static\.cloudflareinsights\.com\/beacon\.min\.js"/);
    assert.ok(html.indexOf(beacons[0][0]) < html.indexOf('</body>'));
    assert.equal((html.match(/static\.cloudflareinsights\.com/g) || []).length, 1);
  }
  const rules = fs.readFileSync(path.join(__dirname, '../site/rules.html'), 'utf8');
  const english = rules.match(/<article data-language="en">([\s\S]*?)<\/article>/)[1];
  const chinese = rules.match(/<article data-language="zh" hidden>([\s\S]*?)<\/article>/)[1];
  assert.match(english, /<h2>Visit statistics<\/h2>/);
  assert.match(chinese, /<h2>访问统计<\/h2>/);
  for (const text of [english, chinese]) assert.ok(text.includes('https://developers.cloudflare.com/web-analytics/about/'));
});

test('spotlight action counts its whole cohort, not visible cards or filtered results', async () => {
  const { node, context } = setup(); await ready();
  assert.equal(node('#featured-all').textContent, 'View all 8 Spotlight papers →');
  assert.equal(node('#featured-list').children.length, 6);
  assert.match(node('#edition').textContent, /35 papers$/);
  node('#search').events.input({ target: { value: 'no matching title' } });
  node('#language-toggle').events.click();
  assert.equal(node('#featured-all').textContent, '查看全部 8 篇 Spotlight 文献 →');
  assert.match(node('#result-count').textContent, /^0 篇文献/);
  node('#featured-all').events.click();
  assert.equal(node('#latest-title').textContent, 'Spotlight 文献');
  assert.match(node('#result-count').textContent, /^8 篇文献/);
  vm.runInContext('state.papers.forEach((p, i) => p.featured = i === 0 ? "PNAS" : null); renderSnapshot()', context);
  node('#language-toggle').events.click();
  assert.equal(node('#featured-all').textContent, 'View all 1 Spotlight paper →');
});

test('view all Spotlight includes older papers and ordinary reset keeps 30 days', async () => {
  const { node, context } = setup(); await ready();
  vm.runInContext('state.data.window_end = "2026-10-05"; state.papers[0].date = "2026-09-01"; renderSnapshot()', context);
  node('#period').events.change({ target: { value: '7' } });
  node('#search').events.input({ target: { value: 'no match' } });
  node('#featured-all').events.click();
  assert.equal(node('#period').value, '0');
  assert.equal(vm.runInContext('state.days', context), 0);
  assert.equal(node('#search').value, '');
  assert.match(node('#result-count').textContent, /^8 papers/);
  node('#language-toggle').events.click();
  assert.match(node('#result-count').textContent, /^8 篇文献/);
  assert.equal(node('#period').value, '0');
  node('#clear').events.click();
  assert.equal(node('#period').value, '30');
  assert.equal(vm.runInContext('state.days', context), 30);
});

test('relative date labels disclose the snapshot cutoff and retain inclusive seven-day bounds', async () => {
  const home = fs.readFileSync(path.join(__dirname, '../site/index.html'), 'utf8');
  assert.match(home, /aria-describedby="date-cutoff"/);
  assert.match(home, /data-en="Last 30 days" data-zh="最近 30 天"/);
  assert.match(home, /data-en="Last 7 days" data-zh="最近 7 天"/);
  const { node, data, context } = setup();
  ['2026-09-23', '2026-09-24', '2026-09-30'].forEach((date, i) => data.papers[i].date = date);
  await ready();
  assert.equal(node('#date-cutoff').textContent, 'Data through 2026-09-30');
  node('#period').events.change({ target: { value: '7' } });
  assert.match(node('#result-count').textContent, /^9 papers/);
  node('#language-toggle').events.click();
  assert.equal(node('#date-cutoff').textContent, '数据截至 2026-09-30');
  assert.equal(vm.runInContext('state.days', context), 7);
  assert.match(node('#result-count').textContent, /^9 篇文献/);
  data.window_end = '2026-10-01';
  vm.runInContext('renderSnapshot()', context);
  assert.equal(node('#date-cutoff').textContent, '数据截至 2026-10-01');
  assert.match(node('#result-count').textContent, /^8 篇文献/);
});

test('reader-facing journal groups match the configured spotlight scope', () => {
  const rules = fs.readFileSync(path.join(__dirname, '../site/rules.html'), 'utf8');
  const groups = [...rules.matchAll(/<h3>(.*?)<\/h3>\s*<ul class="rules-journals">(.*?)<\/ul>/g)];
  assert.deepEqual(groups.map(g => g[1]), ['Spotlight journals', 'Other included journals', 'Spotlight 期刊', '其他收录期刊']);
  const names = group => [...group[2].matchAll(/<li>(.*?)<\/li>/g)].map(m => m[1]);
  const featured = collectionConfig.journals.filter(j => collectionConfig.featured_journals.includes(j.short)).map(j => j.name).sort();
  const other = collectionConfig.journals.filter(j => !collectionConfig.featured_journals.includes(j.short)).map(j => j.name).sort();
  assert.deepEqual(names(groups[0]).sort(), featured);
  assert.deepEqual(names(groups[1]).sort(), other);
  assert.deepEqual(names(groups[2]).sort(), featured);
  assert.deepEqual(names(groups[3]).sort(), other);
  assert.doesNotMatch(rules, /original nine|additional four|原九刊|新增四刊|尚未开始|have not yet begun/);
  assert.match(rules, /not a quality ranking/);
  assert.match(rules, /不代表质量排名/);
  assert.match(rules, /Date filters are relative to the data cutoff/);
});

test('spotlight can exit through scope, journal, return and reset', async () => {
  const { node, context } = setup(); await ready();
  assert.equal(node('#paper-list').children.length, 10);
  node('#pagination').children.at(-1).events.click();
  assert.equal(node('#paper-list').children.length, 10);
  assert.equal(vm.runInContext('state.page', context), 2);
  node('#featured-all').events.click();
  assert.match(node('#result-count').textContent, /^8 papers/);
  assert.equal(node('#scope').value, 'featured');
  assert.equal(node('#back-all').hidden, false);
  node('#scope').events.change({target:{value:'other'}});
  assert.match(node('#result-count').textContent, /^27 papers/);
  node('#scope').events.change({target:{value:'all'}});
  assert.match(node('#result-count').textContent, /^35 papers/);
  node('#featured-all').events.click();
  node('#journal').events.change({target:{value:'NMI'}});
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
  assert.match(node('#result-count').textContent, /^1 paper/);
  node('#journal').events.change({target:{value:'PNAS'}});
  assert.match(node('#result-count').textContent, /^0 papers/);
  assert.equal(node('#paper-list').children[0].className,'empty');
});

test('six newest cards, full journal names and other last', async () => {
  const {node} = setup(); await ready();
  const cards = node('#featured-list').children;
  assert.equal(cards.length,6);
  assert.equal(cards[0].children[0].children[0].textContent,'Proceedings of the National Academy of Sciences');
  assert.equal(cards[0].children[1].children[0].textContent,'Synthetic test 7');
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
  node('#journal').events.change({target:{value:'NMI'}});
  node('#period').events.change({target:{value:'7'}});
  const title = node('#paper-list').children[0].children[1].children[0].textContent;
  node('#language-toggle').events.click();
  assert.match(node('#result-count').textContent,/^2 篇文献/);
  assert.equal(node('#paper-list').children[0].children[1].children[0].textContent,title);
  assert.equal(vm.runInContext('state.journal', context),'NMI');
  assert.equal(vm.runInContext('state.days', context),7);
  assert.match(node('#paper-list').children[0].children[2].textContent,/作者信息待核验/);
  node('#language-toggle').events.click();
  assert.match(node('#result-count').textContent,/^2 papers/);
  assert.match(node('#paper-list').children[0].children[2].textContent,/Author information awaiting verification/);
  const card = vm.runInContext('paperCard({...state.papers[0], authors:["Ada Example"], author_metadata_status:"partial"})', context);
  assert.equal(card.children[2].textContent,'Ada Example');
  assert.match(card.children[2].children[0].textContent,/incomplete/);
});

test('journal options use only full names', async () => {
  const {node} = setup(); await ready();
  assert.deepEqual(node('#journal').children.map((n)=>n.textContent),config.journals.map((j)=>j.name));
});

test('published expansion adds four filter journals without changing spotlight membership', async () => {
  const data = JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/papers.json'),'utf8'));
  assert.deepEqual(data.journals.map(j=>j.short).sort(),collectionConfig.journals.map(j=>j.short).sort());
  for (const short of ['CP','PRResearch','PRE','Chaos']) {
    assert.ok(collectionConfig.journals.some(j=>j.short===short));
    assert.ok(!collectionConfig.featured_journals.includes(short));
    assert.ok(data.journals.some(j=>j.short===short));
    assert.ok(data.papers.some(p=>p.journal_short===short));
    assert.ok(data.papers.filter(p=>p.journal_short===short).every(p=>p.featured===null));
  }
  const expanded = setup('newflow-1',collectionConfig); await ready();
  assert.deepEqual(expanded.node('#journal').children.map(n=>n.textContent),collectionConfig.journals.map(j=>j.name));
  assert.equal(expanded.node('#scope-control').hidden,false);
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
  assert.equal((rules.match(/<h2>/g) || []).length,10);
  assert.match(rules, /Preprints are excluded/);
  assert.match(rules, /预印本不收录/);
  assert.match(rules, /AI assistance/);
  assert.match(rules, /AI 辅助/);
  for (const journal of config.journals) assert.ok(rules.includes(journal.name));
  assert.match(rules, /docs\/screening-protocol\.md/);
  assert.match(rules, /href="data\/papers\.json">文献数据/);
  assert.match(rules, /href="data\/screening-report\.json">审核汇总/);
  assert.match(rules, /reports\/README\.md">逐篇审核日志/);
  assert.match(rules, /Paper-by-paper review log/);
  assert.equal((rules.match(/blob\/main\//g) || []).length, 12);
  assert.equal((rules.match(/reports\/reviews\/2026-10-05-editorial-revision-01\/README\.md/g) || []).length,2);
  for (const run of ['runs/2026-09-expansion-01','reviews/2026-09-expansion-adjudication-01','runs/2026-10-01-to-05-01']) {
    assert.equal((rules.match(new RegExp(`reports/${run}/README\\.md`, 'g')) || []).length,2);
  }
  assert.doesNotMatch(rules, /codex\/new-workflow/);
});

test('main publishes reviewed snapshots without scheduled collection', () => {
  const workflow = fs.readFileSync(path.join(__dirname, '../.github/workflows/publish-reviewed.yml'), 'utf8');
  assert.match(workflow, /branches: \[main\]/);
  assert.doesNotMatch(workflow, /codex\/new-workflow|schedule:|rescreen_existing\.py|collect\.py/);
  assert.match(workflow, /publish_snapshot\.py --check/);
  assert.match(workflow, /path: site/);
  assert.equal(fs.existsSync(path.join(__dirname, '../.github/workflows/update-site.yml')), false);
});

test('pending candidates are disclosed separately in both languages', async () => {
  const { node, data } = setup();
  data.screening_counts = { included:35, excluded:0, review:4, deferred_unassessed:5 };
  await ready();
  assert.match(node('#status').textContent, /9 candidates awaiting evidence/);
  assert.match(node('#result-count').textContent, /^35 papers/);
  node('#language-toggle').events.click();
  assert.match(node('#status').textContent, /9 篇候选待补证/);
});

test('published artifact has consistent rules, date bounds, counts and unique DOIs', () => {
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../site/data/papers.json'), 'utf8'));
  const audit = JSON.parse(fs.readFileSync(path.join(__dirname, '../site/data/screening-report.json'), 'utf8'));
  // A frozen inclusion snapshot may predate the method-only annotations.
  assert.equal(data.screening_version, 'newflow-1');
  assert.equal(data.screening_version, audit.screening_version);
  assert.equal(audit.config_sha256, data.config_sha256);
  assert.equal(audit.window_end, data.window_end);
  assert.equal(audit.window_start, data.window_start);
  assert.equal(audit.candidate_inventory_complete, false);
  assert.equal(audit.metadata_reconciliation_complete, false);
  assert.equal(data.papers.length, data.screening_counts.included);
  assert.equal(data.candidate_count, 3770);
  assert.equal(audit.included_assessments.length, 152);
  assert.equal(new Set(data.papers.map(p => p.doi)).size, data.papers.length);
  assert.ok(data.papers.every(p => p.date >= data.window_start && p.date <= data.window_end && !('abstract' in p)));
  assert.equal((Date.parse(data.window_end) - Date.parse(data.window_start)) / 86400000 + 1, 36);
  assert.equal(data.coverage.length,13);
  assert.equal(data.coverage.find(q => q.journal === 'NC').candidate_inventory_complete,false);
  assert.equal(data.screening_counts.excluded + data.papers.length + data.screening_counts.review + data.screening_counts.deferred_unassessed, 3770);
  assert.equal(data.published_count,112);
  assert.equal(data.accepted_count,40);
});

test('pagination has ten papers, last page, language persistence and filter reset', async () => {
  const {node, context} = setup('newflow-1'); await ready();
  const firstTitle = node('#paper-list').children[0].children[1].children[0].textContent;
  node('#pagination').children[2].events.click();
  assert.notEqual(node('#paper-list').children[0].children[1].children[0].textContent, firstTitle);
  node('#language-toggle').events.click();
  assert.equal(vm.runInContext('state.page',context),2);
  node('#pagination').children[4].events.click();
  assert.equal(node('#paper-list').children.length,5);
  assert.equal(node('#pagination').children.at(-1).disabled,true);
  node('#search').events.input({target:{value:'PNAS'}});
  assert.equal(vm.runInContext('state.page',context),1);
  assert.equal(node('#pagination').children.length,0);
});

test('research method controls and annotations are absent', () => {
  const home = fs.readFileSync(path.join(__dirname, '../site/index.html'), 'utf8');
  const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../site/data/papers.json'), 'utf8'));
  assert.doesNotMatch(home, /id="method"|Research method \(optional\)/);
  assert.doesNotMatch(source, /state\.method|renderMethods|methodLabel/);
  assert.equal(data.screening_version, 'newflow-1');
  assert.ok(data.papers.every(p => !('methods' in p) && !('method_evidence' in p)));
  assert.equal(data.papers.filter(p => p.scope_class === 'core').length, 138);
  assert.equal(data.papers.filter(p => p.scope_class === 'transferable_application').length, 14);
});

test('fixed September snapshot keeps date bounds without a journal-specific coverage notice', async () => {
  const {node} = setup(); await ready();
  assert.match(node('#edition').textContent,/September 2026/);
  assert.equal(node('#status').hidden,true);
  assert.match(node('#coverage-summary').textContent,/2026-09-01 – 2026-09-30:/);
  assert.doesNotMatch(node('#coverage-summary').textContent,/Nature Communications|coverage remains uncertain/);
  assert.doesNotMatch(node('#edition').textContent,/90-day feed/);
  node('#language-toggle').events.click();
  assert.match(node('#coverage-summary').textContent,/2026-09-01 至 2026-09-30/);
  assert.doesNotMatch(node('#coverage-summary').textContent,/Nature Communications|目录覆盖仍存在不确定性/);
  assert.match(node('#edition').textContent,/2026年9月/);
});

test('accepted date and reading notes are visible and bilingual without changing paper identity', async () => {
  const {context,node} = setup(); await ready();
  vm.runInContext('state.papers[0].publication_status = "accepted"; state.papers[0].date_source = "publisher.accepted"; renderResults()',context);
  const title=node('#paper-list').children[0].children[1].children[0].textContent;
  const card=node('#paper-list').children[0];
  assert.match(card.children[0].children[1].textContent,/Accepted/);
  assert.equal(card.children[3].textContent,'A factual network reading note.');
  const feature=vm.runInContext('featureCard(state.papers[0])',context);
  assert.equal(feature.children[2].textContent,'A factual network reading note.');
  node('#language-toggle').events.click();
  assert.equal(node('#paper-list').children[0].children[3].textContent,'一条有证据的网络阅读说明。');
  assert.equal(node('#paper-list').children[0].children[1].children[0].textContent,title);
});

test('cross-month summary and all-collected-dates filter retain the older papers', async () => {
  const {node,context,data}=setup(); await ready();
  data.window_end='2026-10-05';
  vm.runInContext('renderSnapshot()',context);
  assert.match(node('#edition').textContent,/September 2026 – October 2026/);
  assert.match(node('#coverage-summary').textContent,/2026-09-01 – 2026-10-05/);
  assert.match(node('#result-count').textContent,/^10 papers/);
  node('#period').events.change({target:{value:'0'}});
  assert.match(node('#result-count').textContent,/^35 papers/);
  node('#language-toggle').events.click();
  assert.match(node('#coverage-summary').textContent,/2026-09-01 至 2026-10-05/);
  assert.equal(vm.runInContext('state.days',context),0);
  assert.match(node('#result-count').textContent,/^35 篇文献/);
  node('#period').events.change({target:{value:'7'}});
  assert.match(node('#result-count').textContent,/^10 篇文献/);
});

test('editor-selected related readings are not advertised as core transferable methods', async () => {
  const {node,context}=setup(); await ready();
  const details=vm.runInContext('paperCard({...state.papers[0],scope_class:"transferable_application",entry_kind:"editorial_related_reading"})',context).children.at(-1);
  assert.ok(details.children.some(n=>/Related reading selected by the editor/.test(n.textContent)));
  assert.ok(!details.children.some(n=>/Included for its transferable network-science/.test(n.textContent)));
  node('#language-toggle').events.click();
  const translated=vm.runInContext('paperCard({...state.papers[0],scope_class:"transferable_application",entry_kind:"editorial_related_reading"})',context).children.at(-1);
  assert.ok(translated.children.some(n=>/编辑选入的延伸阅读/.test(n.textContent)));
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/papers.json'),'utf8'));
  const related=data.papers.filter(p=>p.scope_exception);
  assert.deepEqual(related.map(p=>p.doi).sort(),['10.1073/pnas.2611888123','10.1103/kwr4-pzn2','10.1103/qnhv-yp69','10.1103/vxkg-41kp'].sort());
  assert.ok(related.every(p=>p.scope_authority==='human user in current conversation' && p.editorial_support_sha256 && p.entry_kind==='editorial_related_reading'));
});

test('release audit retains all windows and separately pinned October coverage evidence', () => {
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/papers.json'),'utf8'));
  assert.equal(data.run_inputs.length,4);
  const october=data.run_inputs.find(i=>i.run==='reports/runs/2026-10-01-to-05-01');
  assert.equal(october.window_start,'2026-10-01');
  assert.equal(october.window_end,'2026-10-05');
  assert.equal(october.publication_evidence.summary.supplemental_candidate_inventory_complete,true);
  assert.equal(october.publication_evidence.summary.supplemental_metadata_reconciliation_complete,false);
  assert.equal(october.publication_evidence.summary.original_coverage_flags_unchanged,true);
  assert.equal(october.publication_evidence.unidentified_candidate_dispositions[0].category,'excluded');
  const october6=data.run_inputs.find(i=>i.run==='reports/runs/2026-10-06-01');
  assert.equal(october6.window_start,'2026-10-06');
  assert.equal(october6.window_end,'2026-10-06');
  assert.deepEqual(october6.publication_evidence.summary.journals,['Science','SA','PNAS','Chaos']);
  assert.equal(october6.publication_evidence.summary.supplemental_candidate_inventory_complete,true);
  assert.equal(october6.publication_evidence.summary.original_coverage_flags_unchanged,true);
  assert.equal(october6.publication_evidence.summary.not_complete_calendar_day_coverage,true);
  assert.deepEqual(october6.publication_evidence.summary.new_in_window_dois,[]);
  for (const coverage of data.coverage) {
    assert.deepEqual(coverage.windows.map(w=>[w.window_start,w.window_end]),[['2026-09-01','2026-09-30'],['2026-10-01','2026-10-05'],['2026-10-06','2026-10-06']]);
  }
});

test('public export has notes for exactly the current included DOIs and preserves accepted provenance', () => {
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/papers.json'),'utf8'));
  const rows=reportText('reports/runs/2026-09/screening-log.jsonl').trim().split('\n').map(JSON.parse);
  const latest=new Map();
  for (const row of rows) if (['assessment','assessment_corrected'].includes(row.kind)) latest.set(row.data.doi,row.data);
  for (const run of ['runs/2026-09-expansion-01','reviews/2026-09-expansion-adjudication-01','runs/2026-10-01-to-05-01','runs/2026-10-06-01','reviews/2026-10-05-editorial-revision-01']) {
    const events=reportText(`reports/${run}/screening-log.jsonl`).trim().split('\n').map(JSON.parse);
    for (const row of events) if (['assessment','assessment_corrected'].includes(row.kind)) latest.set(row.data.doi,row.data);
  }
  const included=[...latest.values()].filter(d => ['core','transferable_application'].includes(d.category));
  assert.deepEqual(data.papers.map(p => p.doi).sort(),included.map(d => d.doi).sort());
  for (const paper of data.papers) {
    assert.ok(paper.note_en && paper.note_zh);
    assert.equal(paper.scope_class,latest.get(paper.doi).category);
    assert.ok(!JSON.stringify(paper).includes('.private/'));
  }
  const accepted=data.papers.filter(p => p.publication_status === 'accepted');
  assert.equal(accepted.length,40);
  for (const p of accepted) { assert.equal(p.published_date,null); assert.equal(p.accepted_date,p.date); assert.match(p.url,/journals.aps.org.*accepted/); }
  for (const doi of ['10.1126/sciadv.aeg4913','10.1103/21c5-cvnn','10.1038/s41467-026-77405-3']) assert.ok(!data.papers.some(p => p.doi===doi));
});


test('thirteen journals have 152 traced inclusions while only the original nine enter spotlight', () => {
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/papers.json'),'utf8'));
  const metadata=JSON.parse(reportText('reports/runs/2026-09/author-metadata.json'));
  const extra=JSON.parse(reportText('reports/runs/2026-09-expansion-01/author-metadata.json'));
  const october=JSON.parse(fs.readFileSync(path.join(__dirname,'../reports/runs/2026-10-01-to-05-01/author-metadata.json'),'utf8'));
  assert.equal(data.featured_journals.length,9);
  assert.deepEqual([...data.featured_journals].sort(),config.journals.map(j=>j.short).sort());
  assert.equal(data.papers.filter(p=>p.featured).length,25);
  assert.equal(data.author_available_count,152);
  assert.equal(data.journals.length,13);
  assert.deepEqual(data.journals.map(j=>j.short).sort(),collectionConfig.journals.map(j=>j.short).sort());
  assert.equal(data.papers.filter(p=>!p.featured).length,127);
  for(const p of data.papers) {
    const row=metadata.records[p.doi] || extra.records[p.doi] || october.records[p.doi];
    assert.deepEqual(p.authors,row.authors);
    assert.ok(p.authors.length);
    assert.equal(p.author_metadata_status,'available');
    assert.equal(p.author_metadata_sha256,row.metadata_sha256);
    assert.equal(p.author_source_url,row.source_url);
    assert.ok(!p.authors.some(a=>/^(anonymous|unknown|et al\.?)$/i.test(a)));
  }
});

test('explicit editorial revision adds six and preserves three exclusions with bound source views', () => {
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/papers.json'),'utf8'));
  const included=['10.1073/pnas.2620995123','10.1103/mnvf-tq6g','10.1103/m6s5-r1cq','10.1073/pnas.2601203123','10.1038/s41467-026-77850-0','10.1103/vxkg-41kp'];
  for(const doi of included) {
    const p=data.papers.find(p=>p.doi===doi);
    assert.ok(p && p.scope_authority==='human user in current conversation' && p.editorial_support_sha256);
  }
  for(const doi of ['10.1103/xsg5-cb6l','10.1103/g76v-wxz7','10.1103/twww-yj1y']) assert.ok(!data.papers.some(p=>p.doi===doi));
  for(const doi of ['10.1103/m6s5-r1cq','10.1103/vxkg-41kp']) assert.equal(data.papers.find(p=>p.doi===doi).publication_status,'accepted');
  const revisions=data.run_inputs.flatMap(i=>i.assessment_sources?.revisions || []).filter(r=>r.mode==='explicit_revision');
  assert.equal(revisions.length,2);
  assert.equal(revisions.flatMap(i=>i.targets).length,9);
  assert.ok(revisions.every(i=>i.source.run==='reports/reviews/2026-10-05-editorial-revision-01'));
  assert.equal(data.papers.find(p=>p.doi==='10.1103/vxkg-41kp').entry_kind,'editorial_related_reading');
});

test('details preserve all authors and use the paper link instead of evidence APIs', async () => {
  const {context}=setup(); await ready();
  const card=vm.runInContext('paperCard({...state.papers[0], authors:["One", "Two", "Three", "Four", "Five"], author_metadata_status:"available", author_source_url:"https://example.org/authors"})',context);
  assert.equal(card.children[2].textContent,'One · Two · Three · Four · et al.');
  const details=card.children.at(-1);
  assert.ok(details.children.some(n=>n.textContent==='All authors: One · Two · Three · Four · Five'));
  const links=details.children.filter(n=>n.tagName==='a');
  assert.deepEqual(links.map(n=>n.href), ['https://doi.org/10.1234/test']);
  assert.equal(links[0].textContent,'Publisher page ↗');
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/papers.json'),'utf8'));
  for (const paper of data.papers) {
    const rendered=vm.runInContext(`paperCard(${JSON.stringify(paper)})`,context);
    const detailLinks=rendered.children.at(-1).children.filter(n=>n.tagName==='a');
    assert.deepEqual(detailLinks.map(n=>n.href),[paper.url]);
    assert.ok(paper.metadata_url && paper.evidence_url && paper.author_source_url);
  }
});

test('commentary review and abstract excerpt are distinguished in both languages', async () => {
  const {context,node}=setup(); await ready();
  for (const [kind,pattern] of [['online_short_comment',/no-abstract scientific commentary/],['abstract_excerpt',/Abstract excerpt; the full article was not reviewed/]]) {
    const card=vm.runInContext(`paperCard({...state.papers[0],review_evidence_kind:${JSON.stringify(kind)},article_type:"Commentary"})`,context);
    assert.ok(card.children.at(-1).children.some(n=>pattern.test(n.textContent)));
  }
  node('#language-toggle').events.click();
  const card=vm.runInContext('paperCard({...state.papers[0],review_evidence_kind:"online_short_comment",article_type:"Commentary"})',context);
  assert.ok(card.children.at(-1).children.some(n=>/在线审读的无摘要科学评论正文/.test(n.textContent)));
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/papers.json'),'utf8'));
  const comment=data.papers.find(p=>p.doi==='10.1073/pnas.2622915123');
  assert.equal(comment.material_sha256,null);
  assert.equal(comment.review_evidence_kind,'online_short_comment');
  assert.ok(comment.review_evidence_sha256 && comment.evidence_url);
  assert.equal(data.screening_counts.review,0);
  assert.equal(data.screening_counts.deferred_unassessed,0);
});


test('identical spotlight scope is hidden and all-papers action does not create a redundant filter', async () => {
  const {node,data,context}=setup();
  data.papers.forEach(p=>p.featured=p.journal_short);
  await ready();
  assert.equal(node('#scope-control').hidden,true);
  node('#featured-all').events.click();
  assert.equal(vm.runInContext('state.scope',context),'all');
  assert.equal(node('#back-all').hidden,true);
  assert.match(node('#result-count').textContent,/^35 papers$/);
  node('#language-toggle').events.click();
  assert.equal(node('#scope-control').hidden,true);
  assert.match(node('#result-count').textContent,/^35 篇文献$/);
  const mixed=setup(); await ready();
  assert.equal(mixed.node('#scope-control').hidden,false);
});

test('zero pending notice is hidden but failures and real pending records remain visible', async () => {
  const valid=setup(); await ready(); assert.equal(valid.node('#status').hidden,true);
  const pending=setup(); pending.data.screening_counts.review=2; await ready();
  assert.equal(pending.node('#status').hidden,false);
  assert.match(pending.node('#status').textContent,/2 candidates/);
  const failed=setup(2); await ready(); assert.equal(failed.node('#status').hidden,false);
});

test('ordinary inferred research has no subtype badge while verified reviews are marked', async () => {
  const {context,node}=setup(); await ready();
  assert.equal(vm.runInContext('articleBadge({article_type:null})',context),null);
  assert.equal(vm.runInContext('articleBadge({article_type:"Article"})',context),null);
  assert.equal(vm.runInContext('articleBadge({article_type:"Review Article"}).textContent',context),'Review');
  node('#language-toggle').events.click();
  assert.equal(vm.runInContext('articleBadge({article_type:"Review Article"}).textContent',context),'综述');
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../site/data/papers.json'),'utf8'));
  const review=data.papers.find(p=>p.doi==='10.1063/5.0348359');
  assert.equal(review.article_type,'Review Article');
  assert.match(review.note_en,/scoping review/);
});
