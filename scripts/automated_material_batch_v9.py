"""Programmatic first pass for the current v9 missing-material queue.

The batch visits public DOI landing pages and structured publisher pages before
any browser fallback is attempted.  Only field availability, short counts and
access status are retained; page bodies and abstract text are discarded.
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
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "reports/v9-2026-09"
UA = "ComplexNetworkPapers/0.1 (v9 automated metadata pass)"


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
        page,
        re.I | re.S,
    ):
        try:
            parsed = json.loads(html.unescape(match.group(1).strip()))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            values.append(parsed)
        elif isinstance(parsed, list):
            values.extend(item for item in parsed if isinstance(item, dict))
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


def publisher(row: dict) -> str:
    doi = row["doi"].lower()
    if doi.startswith("10.1103/"):
        return "APS"
    if doi.startswith("10.1016/"):
        return "Elsevier"
    if doi.startswith("10.1038/") or doi.startswith("10.1007/"):
        return "Springer/Nature"
    if doi.startswith("10.1073/"):
        return "PNAS"
    if doi.startswith("10.1126/"):
        return "Science"
    return "Other"


APS_JOURNALS = {
    "physical review letters": "prl",
    "physical review a": "pra",
    "physical review b": "prb",
    "physical review c": "prc",
    "physical review d": "prd",
    "physical review e": "pre",
    "physical review research": "prresearch",
    "physical review x": "prx",
    "physical review applied": "prapplied",
    "physical review materials": "prmaterials",
    "physical review fluids": "prfluids",
    "physical review physics education research": "prper",
    "physical review accelerators and beams": "prab",
    "physical review special topics - accelerators and beams": "prstab",
}


def crossref_links() -> dict[str, list[dict]]:
    data = json.loads((TRIAL / "crossref-fallback.json").read_text(encoding="utf-8"))
    return {row["doi"].lower(): row.get("links", []) for row in data.get("results", [])}


def candidate_urls(row: dict, links: dict[str, list[dict]]) -> list[str]:
    doi = row["doi"]
    group = publisher(row)
    urls: list[str] = []
    for link in links.get(doi.lower(), []):
        url = (link.get("url") or "").split("?", 1)[0]
        if not url or url.lower().endswith(".pdf") or '/doi/pdf/' in url.lower() or '/fulltext' in url.lower():
            continue
        if group == "Elsevier":
            match = re.search(r"PII:([^/?&]+)", link.get("url", ""), re.I)
            if match:
                urls.append("https://www.sciencedirect.com/science/article/pii/" + match.group(1))
        elif group in {"APS", "Springer/Nature", "PNAS", "Science"}:
            urls.append(url.replace("http://", "https://", 1))
    if group == "Elsevier" and not urls:
        urls.append("https://www.sciencedirect.com/search?qs=" + quote(doi))
    elif group == "APS" and not urls:
        urls.append("https://link.aps.org/article/" + quote(doi, safe="/"))
    elif group == "Springer/Nature" and not urls:
        if doi.lower().startswith("10.1038/"):
            urls.append("https://www.nature.com/articles/" + doi.split("/", 1)[1])
        else:
            urls.append("https://link.springer.com/article/" + quote(doi, safe="/"))
    elif group == "PNAS":
        urls.append("https://www.pnas.org/doi/" + quote(doi, safe="/"))
    elif group == "Science":
        urls.append("https://www.science.org/doi/" + quote(doi, safe="/"))
    elif group == "Other":
        urls.append("https://doi.org/" + quote(doi, safe="/"))

    # APS accepted papers use a journal-specific path.  Add it only after the
    # normal link so a published page remains the primary evidence.
    if group == "APS":
        journal_text = " ".join(row.get("retrieved_by", []))
        journal = journal_text.lower().replace("journal:", "").strip()
        code = next((code for name, code in APS_JOURNALS.items() if name in journal), None)
        if code:
            urls.append(f"https://journals.aps.org/{code}/accepted/{quote(doi, safe='/')}")
    deduped: list[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped[:4]


def fetch_url(url: str) -> tuple[str, int, str]:
    request = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        },
    )
    with urlopen(request, timeout=22) as response:
        return response.geturl(), getattr(response, "status", 200), response.read(600_000).decode("utf-8", "ignore")


def extract(row: dict, links: dict[str, list[dict]]) -> dict:
    doi = row["doi"]
    urls = candidate_urls(row, links)
    result = {
        "doi": doi,
        "publisher": publisher(row),
        "requested_urls": urls,
        "status": "no_candidate_url" if not urls else "unresolved",
        "title_available": False,
        "abstract_available": False,
        "abstract_word_count": 0,
        "article_type": None,
        "online_date": None,
        "publication_date": None,
        "doi_match": None,
        "access_gate": None,
    }
    for url in urls:
        try:
            final_url, http_status, page = fetch_url(url)
            meta = parse_meta(page)
            ld = jsonld(page)
            title = clean(meta.get("citation_title") or meta.get("og:title") or meta.get("twitter:title") or ld_value(ld, "headline") or ld_value(ld, "name"))
            abstract = clean(meta.get("citation_abstract") or meta.get("dc.description") or meta.get("description") or ld_value(ld, "abstract"))
            article_type = clean(meta.get("citation_article_type") or meta.get("dc.type") or ld_value(ld, "@type"))
            online = clean(meta.get("citation_online_date") or ld_value(ld, "datePublished"))
            publication = clean(meta.get("citation_publication_date") or ld_value(ld, "dateCreated"))
            identity = clean(meta.get("citation_doi") or meta.get("dc.identifier") or ld_value(ld, "identifier"))
            lower_page = page.lower()
            gate = None
            if any(marker in lower_page for marker in ("verify you are human", "access denied", "captcha", "check access", "access the full article")):
                gate = "access_gate"
            result.update({
                "final_url": final_url,
                "http_status": http_status,
                "title_available": result["title_available"] or bool(title),
                "abstract_available": result["abstract_available"] or len(abstract.split()) >= 40,
                "abstract_word_count": max(result["abstract_word_count"], len(abstract.split()) if len(abstract.split()) >= 40 else 0),
                "article_type": result["article_type"] or (article_type or None),
                "online_date": result["online_date"] or (online or None),
                "publication_date": result["publication_date"] or (publication or None),
                "doi_match": result["doi_match"] if result["doi_match"] is not None else ((doi.lower() in identity.lower()) if identity else None),
                "access_gate": result["access_gate"] or gate,
            })
            if result["abstract_available"] or (result["title_available"] and (result["online_date"] or result["publication_date"])):
                result["status"] = "sufficient" if result["abstract_available"] else "partial"
                break
            result["status"] = "access_limited" if gate else "structured_empty"
        except HTTPError as exc:
            result["last_http_status"] = exc.code
            result["status"] = "access_limited" if exc.code in {401, 403, 429} else "http_error"
        except Exception as exc:
            result["last_error"] = type(exc).__name__
            result["status"] = "error"
        time.sleep(0.2)
    return result


def run(out: Path, workers: int = 6, limit: int = 0, offset: int = 0) -> dict:
    pending = json.loads((TRIAL / "material-pending-after-elsevier-verification-corrected.json").read_text(encoding="utf-8"))
    queue = pending["missing_abstract"] + pending["missing_preferred_date_with_abstract"]
    unique: dict[str, dict] = {}
    for row in queue:
        unique.setdefault(row["doi"].lower(), row)
    targets = list(unique.values())[offset:]
    if limit:
        targets = targets[:limit]
    links = crossref_links()
    results: list[dict] = []
    if out.exists():
        try:
            saved = json.loads(out.read_text(encoding="utf-8"))
            results = saved.get("results", [])
        except (OSError, json.JSONDecodeError):
            results = []
    done = {item.get("doi", "").lower() for item in results}
    targets = [row for row in targets if row["doi"].lower() not in done]
    initial_count = len(results)
    counts = {
        "target": initial_count + len(targets),
        "processed": initial_count,
        "sufficient": sum(item.get("status") == "sufficient" for item in results),
        "partial": sum(item.get("status") == "partial" for item in results),
        "access_limited": sum(item.get("status") == "access_limited" for item in results),
        "errors": sum(item.get("status") in {"error", "http_error"} for item in results),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(extract, row, links) for row in targets]
        for index, future in enumerate(as_completed(futures), 1):
            item = future.result()
            results.append(item)
            counts["processed"] = initial_count + index
            counts["sufficient"] += item["status"] == "sufficient"
            counts["partial"] += item["status"] == "partial"
            counts["access_limited"] += item["status"] == "access_limited"
            counts["errors"] += item["status"] in {"error", "http_error"}
            if index % 10 == 0 or index == len(targets):
                payload = {"version": "v9-automated-material-batch-1", "complete": index == len(targets), "counts": counts, "results": sorted(results, key=lambda item: item["doi"]), "note": "Programmatic publisher/DOI pages only; page bodies and abstract text are discarded."}
                tmp = out.with_suffix(".tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                tmp.replace(out)
                print(json.dumps({"phase": "automated_material", **counts}, ensure_ascii=False), flush=True)
    results.sort(key=lambda item: item["doi"])
    payload = {"version": "v9-automated-material-batch-1", "complete": True, "counts": counts, "results": results, "note": "Programmatic publisher/DOI pages only; page bodies and abstract text are discarded."}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run(Path(args.out), args.workers, args.limit, args.offset)['counts'], ensure_ascii=False))
