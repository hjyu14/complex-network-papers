"""Backfill missing Springer/Nature metadata from public article pages.

This is deliberately narrower than the general publisher batch collector:
it retries only Springer/Nature records whose existing structured report is
missing an abstract or article type.  Page bodies and abstract text are held
in memory only; the report stores short metadata and provenance.
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
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "reports/v9-2026-09"
UA = "ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)"


def clean(value: str | None) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        fields = dict(attrs)
        key = fields.get("name") or fields.get("property")
        content = fields.get("content")
        if key and content:
            self.fields[key.lower()] = content


def parse_meta(page: str) -> dict[str, str]:
    parser = MetadataParser()
    parser.feed(page)
    return parser.fields


def fetch(url: str, cap: int = 240_000) -> tuple[str, str, bytes]:
    last_error: Exception | None = None
    for attempt in range(3):
        req = Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            },
        )
        try:
            with urlopen(req, timeout=20) as response:
                return response.geturl(), response.headers.get("content-type", ""), response.read(cap)
        except Exception as exc:
            last_error = exc
            code = getattr(exc, "code", None)
            if code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def page_url(doi: str) -> str:
    if doi.startswith("10.1007/"):
        return "https://link.springer.com/article/" + doi
    return "https://www.nature.com/articles/" + doi.split("/", 1)[1]


def nature_issue_type(doi: str, page: str) -> tuple[str, str] | tuple[None, None]:
    """Resolve the one Nature immersive page without citation article metadata."""
    if doi != "10.1038/d41586-026-02597-z":
        return None, None
    issue = "https://www.nature.com/nature/volumes/657/issues/8131"
    # The issue page exposes the type in the same card as the DOI link.
    try:
        _, _, body = fetch(issue, cap=520_000)
        text = body.decode("utf-8", "ignore")
        suffix = re.escape(doi.split("/", 1)[1])
        match = re.search(
            rf'href="/articles/{suffix}".*?c-meta__type">\s*([^<]+?)\s*</span>',
            text,
            re.I | re.S,
        )
        if match:
            return clean(match.group(1)), issue
    except Exception:
        pass
    return None, None


def parse_record(doi: str) -> dict:
    url = page_url(doi)
    result = {
        "doi": doi,
        "requested_url": url,
        "status": "processed",
        "parser": "publisher_html_meta",
        "title_available": False,
        "abstract_available": False,
        "abstract_word_count": 0,
        "article_type": None,
        "online_date": None,
        "publication_date": None,
        "source_url": None,
    }
    try:
        final_url, content_type, body = fetch(url)
        result["source_url"] = final_url
        page = body.decode("utf-8", "ignore")
        fields = parse_meta(page)
        title = clean(fields.get("citation_title") or fields.get("og:title") or fields.get("twitter:title"))
        abstract = clean(
            fields.get("citation_abstract")
            or fields.get("dc.description")
            or fields.get("description")
        )
        abstract_from_section = False
        if not abstract:
            match = re.search(r'"abstract"\s*:\s*"((?:\\.|[^"\\])*)"', page, re.I | re.S)
            if match:
                try:
                    abstract = clean(json.loads('"' + match.group(1) + '"'))
                except json.JSONDecodeError:
                    abstract = clean(match.group(1))
        if not abstract:
            # Springer pages sometimes expose the abstract only in the body,
            # under a section labelled Abs1, without a citation_abstract meta
            # tag.  Extract that section transiently and discard its prose.
            section = re.search(
                r'<section[^>]+(?:aria-labelledby=["\']Abs1["\']|data-title=["\']Abstract["\'])[^>]*>(.*?)</section>',
                page,
                re.I | re.S,
            )
            if section:
                abstract = clean(section.group(1))
                abstract = re.sub(r'^Abstract\s*', '', abstract, flags=re.I)
                abstract_from_section = bool(abstract)
        trusted_springer_description = doi.startswith("10.1007/") and bool(
            fields.get("citation_abstract") or fields.get("dc.description")
        )
        if (
            not abstract_from_section
            and not trusted_springer_description
            and len(abstract.split()) < 40
        ) or any(
            phrase in abstract.lower()
            for phrase in ("enable javascript", "access denied", "verify you are human", "please log in")
        ):
            abstract = ""
        result["title_available"] = bool(title)
        result["abstract_available"] = bool(abstract)
        result["abstract_word_count"] = len(abstract.split()) if abstract else 0
        result["article_type"] = clean(
            fields.get("citation_article_type") or fields.get("dc.type")
        ) or None
        result["online_date"] = clean(fields.get("citation_online_date")) or None
        result["publication_date"] = clean(fields.get("citation_publication_date")) or None
        identity = clean(fields.get("citation_doi") or fields.get("dc.identifier"))
        if identity and doi.lower() not in identity.lower():
            result["status"] = "doi_mismatch"
            result["abstract_available"] = False
            result["abstract_word_count"] = 0
        if not result["article_type"] and doi.startswith("10.1038/"):
            article_type, evidence_url = nature_issue_type(doi, page)
            if article_type:
                result["article_type"] = article_type
                result["article_type_source"] = evidence_url
        if doi == "10.1038/d41586-026-02597-z" and not result["article_type"]:
            # The immersive page has no citation_article_type.  Its type is
            # kept unresolved rather than inferred from the title.
            result["status"] = "type_unresolved"
    except Exception as exc:  # keep per-record failure evidence
        result["status"] = "access_limited"
        result["error"] = type(exc).__name__
        code = getattr(exc, "code", None)
        if code is not None:
            result["http_status"] = code
    return result


def load_json(name: str) -> dict:
    return json.loads((TRIAL / name).read_text(encoding="utf-8"))


def choose_targets() -> tuple[list[dict], dict[str, dict]]:
    material = load_json("material-after-elsevier-verification-corrected.json")["results"]
    material_by_doi = {
        row["doi"].lower(): row for row in material if row["doi"].startswith(("10.1007/", "10.1038/"))
    }
    canonical = {row["doi"].lower(): row for row in load_json("publisher-canonical-v2.json")["results"]}
    audit = load_json("springer-nature-type-audit.json")
    nature_unresolved = {
        row["doi"].lower() for row in audit["records"] if row["classification"] == "type_unresolved"
    }
    targets: list[dict] = []
    for doi, row in material_by_doi.items():
        existing = canonical.get(doi, {})
        needs_abstract = doi.startswith("10.1007/") and not existing.get("abstract_available")
        needs_type = doi in nature_unresolved
        if needs_abstract or needs_type:
            targets.append({"doi": row["doi"], "reason": "missing_abstract" if needs_abstract else "missing_article_type"})
    return sorted(targets, key=lambda row: row["doi"]), canonical


def run(out: Path, workers: int = 4) -> dict:
    targets, canonical = choose_targets()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(parse_record, row["doi"]): row for row in targets}
        for idx, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            result = future.result()
            result["target_reason"] = row["reason"]
            existing = canonical.get(row["doi"].lower(), {})
            result["existing_report_abstract_available"] = bool(existing.get("abstract_available"))
            result["existing_report_article_type"] = (existing.get("bibliographic_metadata") or {}).get("citation_article_type")
            results.append(result)
            if idx % 10 == 0 or idx == len(targets):
                print(json.dumps({"phase": "springer_nature_backfill", "processed": idx, "target": len(targets)}, ensure_ascii=True), flush=True)
            time.sleep(0.2)
    results.sort(key=lambda row: row["doi"])
    payload = {
        "version": "v9-springer-nature-backfill-1",
        "window_start": "2026-09-01",
        "window_end": "2026-09-30",
        "counts": {
            "target": len(targets),
            "processed": len(results),
            "abstract_found": sum(bool(row["abstract_available"]) for row in results),
            "article_type_found": sum(bool(row["article_type"]) for row in results),
            "access_limited": sum(row["status"] == "access_limited" for row in results),
            "type_unresolved": sum(row["status"] == "type_unresolved" for row in results),
            "springer_10_1007": sum(row["doi"].startswith("10.1007/") for row in results),
            "nature_10_1038": sum(row["doi"].startswith("10.1038/") for row in results),
        },
        "results": results,
        "note": "Only short metadata and provenance are saved; HTML, full text, and abstract text are discarded.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(out)
    return payload["counts"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(TRIAL / "springer-nature-backfill-v1.json"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    print(json.dumps(run(Path(args.out), args.workers), ensure_ascii=True))
