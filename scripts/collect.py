"""Bounded Crossref collection; standard library only, no full text storage."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/sources.json"
OUT = ROOT / "site/data"


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value or ""))).strip()


def matches(pattern, text):
    return sorted({m.group(0).lower() for m in re.finditer(pattern, text, re.I)})


def publication_date(item):
    for key in ("published-online", "published-print", "published", "issued"):
        parts = item.get(key, {}).get("date-parts", [])
        if not parts or not parts[0]:
            continue
        # Do not convert a month/year-only date to a made-up day.
        if len(parts[0]) != 3:
            return None, key
        try:
            return date(*parts[0]), key
        except (TypeError, ValueError):
            return None, key
    return None, None


def screen(item, config, today):
    title = clean(" ".join(item.get("title", [])))
    rules = config["screening"]
    if item.get("type") != "journal-article" or not title:
        return None, "not_article"
    if matches(rules["non_article_title"], title) or item.get("update-to"):
        return None, "notice"
    published, date_source = publication_date(item)
    if published is None:
        return None, "missing_or_partial_date"
    if not today - timedelta(days=config["window_days"] - 1) <= published <= today:
        return None, "outside_window"
    doi = item.get("DOI", "").strip().lower()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        return None, "missing_doi"
    abstract = clean(item.get("abstract", ""))
    if matches(rules["materials_title"], title) and not matches(rules["graph_evidence"], title + " " + abstract):
        return None, "material_network_without_graph_evidence"
    if matches(rules["ml_title"], title) and not matches(rules["ml_core_exception"], title):
        return None, "general_machine_learning"
    direct = matches(rules["explicit"], title)
    mechanism = matches(rules["mechanism"], title)
    network_title = matches(rules["network"], title)
    abstract_direct = matches(rules["explicit"], abstract)
    if direct:
        evidence, basis = direct, "title_explicit"
    elif network_title and mechanism:
        evidence, basis = network_title + mechanism, "title_network_mechanism"
    elif network_title and abstract_direct and matches(rules["mechanism"], abstract):
        evidence, basis = abstract_direct, "abstract_support"
    else:
        return None, "not_core"
    categories = [c["id"] for c in config["categories"] if matches(c["pattern"], title)]
    if not categories:
        categories = [c["id"] for c in config["categories"] if matches(c["pattern"], abstract)]
    if not categories:
        categories = ["unclassified"]
    issns = set(item.get("ISSN", []))
    featured = next((j["short"] for j in config["featured_journals"] if issns.intersection(j["issns"])), None)
    return {
        "doi": doi, "url": "https://doi.org/" + quote(doi, safe="/"),
        "title": title,
        "authors": [clean(" ".join(filter(None, [a.get("given"), a.get("family")])) or a.get("name", "")) for a in item.get("author", [])],
        "journal": clean(" / ".join(item.get("container-title", []))),
        "issns": sorted(issns), "date": published.isoformat(), "date_source": date_source,
        "categories": categories, "featured": featured, "evidence": evidence,
        "screening_basis": basis, "source": "Crossref", "abstract_available": bool(abstract),
        "metadata_url": "https://api.crossref.org/works/" + quote(doi, safe=""),
        "has_update": bool(item.get("updated-by"))
    }, "included"


def request_json(url):
    for attempt in range(3):
        try:
            request = Request(url, headers={
                "User-Agent": "ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)",
                "Accept": "application/json"
            })
            with urlopen(request, timeout=40) as response:
                return json.load(response)["message"]
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def collect(config, today, out=OUT, fetch=request_json):
    start = today - timedelta(days=config["window_days"] - 1)
    timestamp = datetime.now(timezone.utc).isoformat()
    jobs = [("topic: " + q, "https://api.crossref.org/works", q) for q in config["queries"]]
    jobs += [("journal: " + j["name"], "https://api.crossref.org/journals/" + j["issns"][0] + "/works", "network") for j in config["featured_journals"]]
    candidates, coverage, errors = {}, [], []
    for label, endpoint, query in jobs:
        report = {"label": label, "query": query, "retrieved": 0, "total_results": None, "truncated": False, "urls": []}
        cursor = "*"
        try:
            for _ in range(config["max_pages_per_query"]):
                params = {"query": query, "filter": f"type:journal-article,from-pub-date:{start},until-pub-date:{today}",
                          "rows": config["rows_per_page"], "cursor": cursor, "sort": "relevance", "order": "desc"}
                url = endpoint + "?" + urlencode(params)
                message = fetch(url)
                report["urls"].append(url)
                report["total_results"] = message["total-results"]
                items = message["items"]
                report["retrieved"] += len(items)
                for item in items:
                    key = item.get("DOI", "").lower()
                    if key:
                        if key not in candidates:
                            candidates[key] = {"item": item, "queries": []}
                        candidates[key]["queries"].append(label)
                next_cursor = message.get("next-cursor")
                if not items or report["retrieved"] >= report["total_results"] or not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
                time.sleep(0.25)
            report["truncated"] = report["retrieved"] < report["total_results"]
            print(f"{label}: {report['retrieved']}/{report['total_results']}", flush=True)
        except Exception as exc:
            errors.append({"query": label, "error": type(exc).__name__ + ": " + str(exc)[:300]})
            report["failed"] = True
            print(f"FAILED {label}: {type(exc).__name__}", flush=True)
        coverage.append(report)
        time.sleep(0.25)
    stats, papers = Counter(), []
    for candidate in candidates.values():
        paper, reason = screen(candidate["item"], config, today)
        stats[reason] += 1
        if paper:
            paper["retrieved_by"] = sorted(set(candidate["queries"]))
            papers.append(paper)
    papers.sort(key=lambda p: (p["date"], p["doi"]), reverse=True)
    status = {"attempted_at": timestamp, "ok": not errors, "errors": errors, "coverage": coverage}
    if not errors:
        payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "window_start": start.isoformat(), "window_end": today.isoformat(),
                   "window_days": config["window_days"], "source": "Crossref", "screening_version": config["version"],
                   "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                   "categories": [{"id": c["id"], "label": c["label"]} for c in config["categories"]] + [{"id": "unclassified", "label": "待分类"}],
                   "featured_journals": config["featured_journals"], "coverage": coverage,
                   "candidate_count": len(candidates), "screening_counts": dict(stats), "papers": papers}
        write_json(out / "papers.json", payload)
    write_json(out / "status.json", status)
    print(json.dumps({"ok": not errors, "candidates": len(candidates), "included": len(papers), "screening": dict(stats)}, ensure_ascii=False), flush=True)
    return not errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=datetime.now(timezone(timedelta(hours=8))).date())
    args = parser.parse_args()
    success = collect(json.loads(CONFIG.read_text(encoding="utf-8")), args.date)
    raise SystemExit(0 if success else 1)
