"""Small publisher-page pilot for the v9 missing-material queue.

The pilot fetches DOI landing pages for ten records from each of APS,
Elsevier, PNAS, and Science.  Only short field availability and provenance
are written; abstract text and page bodies are discarded.
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
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "reports/v9-2026-09"
UA = "ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)"
GROUPS = {
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
        content = values.get("content")
        if key and content:
            self.fields[key.lower()] = content


def parse_meta(page: str) -> dict[str, str]:
    parser = MetaParser()
    parser.feed(page)
    return parser.fields


def jsonld_values(page: str) -> list[dict]:
    values: list[dict] = []
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.I | re.S):
        try:
            parsed = json.loads(html.unescape(match.group(1).strip()))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            values.append(parsed)
        elif isinstance(parsed, list):
            values.extend(x for x in parsed if isinstance(x, dict))
    return values


def first_jsonld(values: list[dict], key: str) -> str:
    for value in values:
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return clean(item)
        if isinstance(item, dict):
            for subkey in ("value", "name", "@value"):
                if isinstance(item.get(subkey), str) and item[subkey].strip():
                    return clean(item[subkey])
    return ""


def select_dois(limit: int) -> list[dict]:
    source = json.loads((TRIAL / "material-pending-after-elsevier-verification-corrected.json").read_text(encoding="utf-8"))
    queue = source["missing_abstract"] + source["missing_preferred_date_with_abstract"]
    result = []
    for group, prefix in GROUPS.items():
        rows = [row for row in queue if row["doi"].startswith(prefix)]
        result.extend({"group": group, "doi": row["doi"], "title": row["title"]} for row in rows[:limit])
    return result


def fetch_one(row: dict) -> dict:
    doi = row["doi"]
    result = {
        "group": row["group"],
        "doi": doi,
        "requested_url": "https://doi.org/" + doi,
        "status": "processed",
        "final_url": None,
        "title_available": False,
        "abstract_available": False,
        "abstract_word_count": 0,
        "article_type": None,
        "online_date": None,
        "publication_date": None,
        "doi_match": None,
    }
    try:
        request = Request(
            result["requested_url"],
            headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9"},
        )
        with urlopen(request, timeout=20) as response:
            body = response.read(320_000)
            result["final_url"] = response.geturl()
        page = body.decode("utf-8", "ignore")
        meta = parse_meta(page)
        ld = jsonld_values(page)
        title = clean(meta.get("citation_title") or meta.get("og:title") or first_jsonld(ld, "headline") or first_jsonld(ld, "name"))
        abstract = clean(meta.get("citation_abstract") or meta.get("dc.description"))
        if not abstract:
            abstract = first_jsonld(ld, "abstract")
        article_type = clean(meta.get("citation_article_type") or meta.get("dc.type") or first_jsonld(ld, "@type"))
        online = clean(meta.get("citation_online_date") or first_jsonld(ld, "datePublished"))
        publication = clean(meta.get("citation_publication_date") or first_jsonld(ld, "dateCreated"))
        identity = clean(meta.get("citation_doi") or meta.get("dc.identifier"))
        if not identity:
            identity = first_jsonld(ld, "identifier")
        result.update({
            "title_available": bool(title),
            "abstract_available": len(abstract.split()) >= 10,
            "abstract_word_count": len(abstract.split()) if len(abstract.split()) >= 10 else 0,
            "article_type": article_type or None,
            "online_date": online or None,
            "publication_date": publication or None,
            "doi_match": (doi.lower() in identity.lower()) if identity else None,
        })
        if not any((result["title_available"], result["abstract_available"], result["article_type"], result["online_date"])):
            result["status"] = "structured_empty"
    except HTTPError as exc:
        result["status"] = "http_error"
        result["http_status"] = exc.code
    except Exception as exc:
        result["status"] = "error"
        result["error"] = type(exc).__name__
    return result


def run(out: Path, per_group: int = 10, workers: int = 4) -> dict:
    targets = select_dois(per_group)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, row): row for row in targets}
        for idx, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if idx % 10 == 0 or idx == len(targets):
                print(json.dumps({"phase": "publisher_page_pilot", "processed": idx, "target": len(targets)}, ensure_ascii=True), flush=True)
            time.sleep(0.25)
    results.sort(key=lambda row: (row["group"], row["doi"]))
    counts = {
        "target": len(targets),
        "processed": len(results),
        "title_found": sum(r["title_available"] for r in results),
        "abstract_found": sum(r["abstract_available"] for r in results),
        "article_type_found": sum(bool(r["article_type"]) for r in results),
        "online_date_found": sum(bool(r["online_date"]) for r in results),
        "doi_match_confirmed": sum(r["doi_match"] is True for r in results),
        "http_errors": sum(r["status"] == "http_error" for r in results),
        "structured_empty": sum(r["status"] == "structured_empty" for r in results),
    }
    by_group = {}
    for group in GROUPS:
        group_rows = [r for r in results if r["group"] == group]
        by_group[group] = {
            "target": len(group_rows),
            "title_found": sum(r["title_available"] for r in group_rows),
            "abstract_found": sum(r["abstract_available"] for r in group_rows),
            "article_type_found": sum(bool(r["article_type"]) for r in group_rows),
            "online_date_found": sum(bool(r["online_date"]) for r in group_rows),
            "doi_match_confirmed": sum(r["doi_match"] is True for r in group_rows),
            "http_errors": sum(r["status"] == "http_error" for r in group_rows),
        }
    payload = {
        "version": "v9-publisher-page-pilot-1",
        "per_group": per_group,
        "counts": counts,
        "by_group": by_group,
        "results": results,
        "note": "Only field availability and provenance are stored; page bodies and abstract text are discarded.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(TRIAL / "publisher-page-pilot-v1.json"))
    parser.add_argument("--per-group", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(run(Path(args.out), args.per_group, args.workers), ensure_ascii=True))
