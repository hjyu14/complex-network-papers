"""Batch public publisher structured metadata for v9 review records.

Only short structured fields and availability flags are written.  HTML/XML and
abstract text are processed in memory and discarded.  This deliberately does
not bypass paywalls, login, CAPTCHA, or access controls.
"""
import argparse
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from collect import relevance

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "reports/v9-2026-09"
UA = "ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)"


def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def meta(page, names):
    fields = parse_meta(page)
    return next((clean(fields.get(n.lower(), '')) for n in names if fields.get(n.lower())), '')


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.fields = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            attrs = dict(attrs)
            key = attrs.get('name') or attrs.get('property')
            if key and attrs.get('content'):
                self.fields[key.lower()] = attrs['content']


def parse_meta(page):
    parser = MetadataParser(); parser.feed(page)
    return parser.fields


def page_fetch(url):
    req = Request(url, headers={"User-Agent": UA,
                                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"})
    with urlopen(req, timeout=12) as response:
        # Meta tags and JSON-LD occur near the head; cap the in-memory page.
        body = response.read(160_000)
        return response.geturl(), response.headers.get("content-type", ""), body


def parse_elsevier(body):
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        text = body.decode("utf-8", "ignore")
        return bool(re.search(r"<(?:abstract|ce:abstract)", text, re.I)), "", ""
    texts = []
    title = ""
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1].lower()
        if tag in {"title", "article-title"} and not title:
            title = clean("".join(el.itertext()))
        if tag == "abstract":
            texts.append(clean("".join(el.itertext())))
    return bool(" ".join(texts)), title, " ".join(texts)


def parse_page(url, content_type, body):
    host = urlparse(url).netloc.lower()
    if "api.elsevier.com" in host or "xml" in content_type:
        has_abs, title, abstract = parse_elsevier(body)
        return has_abs, title, abstract, "elsevier_xml"
    page = body.decode("utf-8", "ignore")
    title = meta(page, ["citation_title", "og:title", "twitter:title"])
    abstract = meta(page, ["citation_abstract", "dc.description", "description"])
    if not abstract:
        # JSON-LD often carries the abstract while remaining structured metadata.
        m = re.search(r'"abstract"\s*:\s*"((?:\\.|[^"\\])*)"', page, re.I | re.S)
        if m:
            try:
                abstract = clean(json.loads('"' + m.group(1) + '"'))
            except json.JSONDecodeError:
                abstract = clean(m.group(1))
    # A short teaser or generic website slogan is not an abstract.
    if len(abstract.split()) < 40 or any(s in abstract.lower() for s in
        ['enable javascript', 'access denied', 'verify you are human', 'please log in']):
        abstract = ''
    return bool(abstract), title, abstract, "publisher_html_meta"


def choose_links(row):
    links = row.get("links") or []
    chosen = []
    for link in links:
        url = (link.get("url") or "").strip()
        host = urlparse(url).netloc.lower()
        if not url:
            continue
        if url.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        # Public structured endpoints confirmed by a small probe.  Other links
        # are retained as access-limited evidence and are not requested here.
        if ("link.springer.com/article/" in url or "www.nature.com/articles/" in url or
                "api.elsevier.com/content/article/" in url):
            if 'api.elsevier.com' in host:
                if 'httpAccept=text/plain' in url:
                    continue
                url += '&view=META_ABS'
            if url not in chosen:
                chosen.append(url)
    if not chosen:
        doi = row['doi'].lower()
        if doi.startswith('10.1038/'):
            chosen.append('https://www.nature.com/articles/' + doi.split('/', 1)[1])
        elif doi.startswith('10.1007/'):
            chosen.append('https://link.springer.com/article/' + doi)
    return chosen


def fetch_row(row):
    doi = row["doi"]
    links = choose_links(row)
    result = {"doi": doi, "attempted_links": len(links), "sources": [],
              "abstract_available": False, "title_available": False,
              "status": "no_public_structured_link" if not links else "processed"}
    for url in links[:3]:
        try:
            final_url, ctype, body = page_fetch(url)
            has_abs, title, abstract, parser = parse_page(final_url, ctype, body)
            result["sources"].append({"url": final_url, "parser": parser,
                                      "status": "ok", "title_available": bool(title),
                                      "abstract_available": bool(abstract)})
            result["abstract_available"] |= bool(abstract)
            result["title_available"] |= bool(title)
            if abstract:
                rules = json.loads((ROOT / 'config/sources.json').read_text(encoding='utf-8'))['screening']
                reason, routes, evidence = relevance(title, abstract, rules)
                result['material_observations'] = {'heuristic_reason': reason, 'routes': routes,
                    'evidence': evidence, 'abstract_word_count': len(abstract.split()),
                    'classification_deferred': True}
            if parser == 'publisher_html_meta':
                page_fields = parse_meta(body.decode('utf-8', 'ignore'))
                result['bibliographic_metadata'] = {k: page_fields.get(k) for k in
                    ['citation_doi', 'citation_journal_title', 'citation_online_date',
                     'citation_publication_date', 'citation_article_type', 'dc.type'] if page_fields.get(k)}
                identity = (page_fields.get('citation_doi') or '').lower().replace('doi:', '')
                if identity and identity != doi.lower():
                    result['abstract_available'] = False
                    result['status'] = 'doi_mismatch'
                    break
            if has_abs:
                result["status"] = "abstract_found"
                break
        except Exception as exc:
            result["sources"].append({"url": url, "status": "error",
                                      "error": type(exc).__name__, 'http_status': getattr(exc, 'code', None)})
            result["status"] = "access_limited"
        time.sleep(0.25)
    return result


def run(out, workers=4, limit=0, offset=0):
    report = json.loads((TRIAL / "screening-report.json").read_text(encoding="utf-8"))
    rows = {x["doi"].lower(): x for x in report["decisions"] if x["decision"] == "review"}
    # Restrict this experiment to records still lacking an abstract from the
    # completed API runs.  Their abstract flags are deliberately not inferred
    # from the presence of a publisher link.
    known = set()
    for fn in ("crossref-fallback.json", "crossref-batch-refresh.json",
               "europepmc-fallback.json", "openalex-fallback.json"):
        data = json.loads((TRIAL / fn).read_text(encoding="utf-8"))
        known |= {x["doi"].lower() for x in data.get("results", []) if x.get("abstract_available")}
    crossref = json.loads((TRIAL / "crossref-fallback.json").read_text(encoding="utf-8"))
    cr = {x["doi"].lower(): x for x in crossref["results"]}
    targets = []
    for doi, row in rows.items():
        if doi in known:
            continue
        enriched = dict(row)
        enriched["links"] = cr.get(doi, {}).get("links", [])
        targets.append(enriched)
    if offset > 0:
        targets = targets[offset:]
    if limit > 0:
        targets = targets[:limit]
    counts = {"target": len(targets), "processed": 0, "abstract_found": 0,
              "title_found": 0, "access_limited": 0, "no_link": 0}
    results = []
    if Path(out).exists():
        saved = json.loads(Path(out).read_text(encoding='utf-8'))
        results = saved.get('results', [])
        done = {r['doi'] for r in results}
        targets = [t for t in targets if t['doi'] not in done]
        counts.update({'processed': len(results),
            'abstract_found': sum(bool(r['abstract_available']) for r in results),
            'title_found': sum(bool(r['title_available']) for r in results),
            'access_limited': sum(r['status'] == 'access_limited' for r in results),
            'no_link': sum(r['status'] == 'no_public_structured_link' for r in results)})
    initial_count = len(results)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_row, row) for row in targets]
        for idx, future in enumerate(as_completed(futures), 1):
            result = future.result()
            counts["processed"] = initial_count + idx
            counts["abstract_found"] += bool(result["abstract_available"])
            counts["title_found"] += bool(result["title_available"])
            counts["access_limited"] += result["status"] == "access_limited"
            counts["no_link"] += result["status"] == "no_public_structured_link"
            results.append(result)
            if idx % 25 == 0 or idx == len(targets):
                partial = {'version': 'v9', 'complete': idx == len(targets), 'counts': counts,
                           'results': sorted(results, key=lambda x: x['doi']),
                           'note': 'Abstracts and page bodies processed transiently, never stored; classification deferred.'}
                temp = Path(out).with_suffix('.tmp')
                temp.write_text(json.dumps(partial, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                temp.replace(out)
                print(json.dumps({"phase": "publisher_structured", **counts}, ensure_ascii=False), flush=True)
    results.sort(key=lambda x: x["doi"])
    payload = {"version": "v9", "window_start": "2026-09-01", "window_end": "2026-09-30",
               "counts": counts, "results": results,
               "note": "Publisher HTML/XML and abstracts processed transiently; no page HTML, full text, or abstracts stored."}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run(args.out, args.workers, args.limit, args.offset), ensure_ascii=False))
