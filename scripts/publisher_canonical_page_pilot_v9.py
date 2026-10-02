"""Probe canonical publisher pages for a small v9 metadata pilot.

The probe records only access status and short structured-field availability.
It does not save page bodies, abstracts, cookies, credentials, or full text.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "reports/v9-2026-09"
UA = "ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)"
PREFIXES = {
    "APS": "10.1103/",
    "Elsevier": "10.1016/",
    "PNAS": "10.1073/",
    "Science": "10.1126/",
}


def clean(value: str | None) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        values = dict(attrs)
        key = values.get("name") or values.get("property")
        value = values.get("content")
        if key and value:
            self.fields[key.lower()] = value


def parse_meta(page: str) -> dict[str, str]:
    parser = MetaParser()
    parser.feed(page)
    return parser.fields


def jsonld(page: str) -> list[dict]:
    values: list[dict] = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page, re.I | re.S,
    ):
        try:
            item = json.loads(html.unescape(match.group(1).strip()))
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            values.append(item)
        elif isinstance(item, list):
            values.extend(x for x in item if isinstance(x, dict))
    return values


def ld_value(values: list[dict], key: str) -> str:
    for item in values:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return clean(value)
        if isinstance(value, dict):
            for subkey in ("value", "name", "@value"):
                if isinstance(value.get(subkey), str) and value[subkey].strip():
                    return clean(value[subkey])
    return ""


def source_rows(limit: int) -> list[dict]:
    pending = json.loads(
        (TRIAL / "material-pending-after-elsevier-verification-corrected.json")
        .read_text(encoding="utf-8")
    )
    queue = pending["missing_abstract"] + pending["missing_preferred_date_with_abstract"]
    crossref = json.loads((TRIAL / "crossref-fallback.json").read_text(encoding="utf-8"))
    links = {row["doi"].lower(): row.get("links", []) for row in crossref["results"]}
    result = []
    for group, prefix in PREFIXES.items():
        for row in [x for x in queue if x["doi"].lower().startswith(prefix)][:limit]:
            result.append({"group": group, "doi": row["doi"], "title": row["title"],
                           "publisher_url": canonical_url(group, row["doi"], links.get(row["doi"].lower(), []))})
    return result


def canonical_url(group: str, doi: str, links: list[dict]) -> str:
    if group == "APS":
        return "https://link.aps.org/article/" + quote(doi, safe="/")
    if group == "PNAS":
        return "https://www.pnas.org/doi/" + quote(doi, safe="/")
    if group == "Science":
        return "https://www.science.org/doi/" + quote(doi, safe="/")
    # Crossref exposes Elsevier PII in its text-mining link.  Use the public
    # ScienceDirect article page for this pilot, not the API endpoint.
    for link in links:
        url = link.get("url", "")
        match = re.search(r"PII:([^?/&]+)", url, re.I)
        if match:
            return "https://www.sciencedirect.com/science/article/pii/" + match.group(1)
    return "https://www.sciencedirect.com/search?qs=" + quote(doi)


def fetch(row: dict) -> dict:
    result = {
        "group": row["group"], "doi": row["doi"], "publisher_url": row["publisher_url"],
        "status": "processed", "final_url": None, "http_status": None,
        "title_available": False, "abstract_available": False, "abstract_word_count": 0,
        "article_type": None, "online_date": None, "publication_date": None,
        "doi_match": None,
    }
    try:
        request = Request(row["publisher_url"], headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        })
        with urlopen(request, timeout=25) as response:
            result["http_status"] = getattr(response, "status", 200)
            result["final_url"] = response.geturl()
            body = response.read(500_000)
        page = body.decode("utf-8", "ignore")
        meta = parse_meta(page)
        ld = jsonld(page)
        title = clean(meta.get("citation_title") or meta.get("og:title") or meta.get("twitter:title") or ld_value(ld, "headline") or ld_value(ld, "name"))
        abstract = clean(meta.get("citation_abstract") or meta.get("dc.description") or meta.get("description") or ld_value(ld, "abstract"))
        article_type = clean(meta.get("citation_article_type") or meta.get("dc.type") or ld_value(ld, "@type"))
        online = clean(meta.get("citation_online_date") or ld_value(ld, "datePublished"))
        publication = clean(meta.get("citation_publication_date") or ld_value(ld, "dateCreated"))
        identity = clean(meta.get("citation_doi") or meta.get("dc.identifier") or ld_value(ld, "identifier"))
        result.update({
            "title_available": bool(title),
            "abstract_available": len(abstract.split()) >= 10,
            "abstract_word_count": len(abstract.split()) if len(abstract.split()) >= 10 else 0,
            "article_type": article_type or None,
            "online_date": online or None,
            "publication_date": publication or None,
            "doi_match": (row["doi"].lower() in identity.lower()) if identity else None,
        })
        if not any((result["title_available"], result["abstract_available"], article_type, online, publication)):
            result["status"] = "structured_empty"
    except HTTPError as exc:
        result["status"] = "http_error"
        result["http_status"] = exc.code
    except Exception as exc:
        result["status"] = "error"
        result["error"] = type(exc).__name__
    return result


def run(out: Path, per_group: int = 10, workers: int = 4) -> dict:
    targets = source_rows(per_group)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, row): row for row in targets}
        for index, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if index % 10 == 0 or index == len(targets):
                print(json.dumps({"phase": "publisher_canonical_page_pilot", "processed": index, "target": len(targets)}, ensure_ascii=True), flush=True)
            time.sleep(0.2)
    results.sort(key=lambda row: (row["group"], row["doi"]))
    counts = {
        "target": len(targets), "processed": len(results),
        "title_found": sum(r["title_available"] for r in results),
        "abstract_found": sum(r["abstract_available"] for r in results),
        "article_type_found": sum(bool(r["article_type"]) for r in results),
        "online_date_found": sum(bool(r["online_date"]) for r in results),
        "publication_date_found": sum(bool(r["publication_date"]) for r in results),
        "doi_match_confirmed": sum(r["doi_match"] is True for r in results),
        "http_errors": sum(r["status"] == "http_error" for r in results),
        "structured_empty": sum(r["status"] == "structured_empty" for r in results),
    }
    by_group = {}
    for group in PREFIXES:
        rows = [r for r in results if r["group"] == group]
        by_group[group] = {"target": len(rows), "title_found": sum(r["title_available"] for r in rows),
                           "abstract_found": sum(r["abstract_available"] for r in rows),
                           "article_type_found": sum(bool(r["article_type"]) for r in rows),
                           "online_date_found": sum(bool(r["online_date"]) for r in rows),
                           "publication_date_found": sum(bool(r["publication_date"]) for r in rows),
                           "doi_match_confirmed": sum(r["doi_match"] is True for r in rows),
                           "http_errors": sum(r["status"] == "http_error" for r in rows),
                           "structured_empty": sum(r["status"] == "structured_empty" for r in rows)}
    payload = {"version": "v9-publisher-canonical-page-pilot-1", "per_group": per_group,
               "counts": counts, "by_group": by_group, "results": results,
               "note": "Canonical publisher pages only; field availability and provenance are stored, page bodies and abstract text are discarded."}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(TRIAL / "publisher-canonical-page-pilot-v1.json"))
    parser.add_argument("--per-group", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(run(Path(args.out), args.per_group, args.workers), ensure_ascii=True))
