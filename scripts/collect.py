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


def author_metadata(item):
    """Do not present deposit placeholders as verified personal names."""
    names, placeholders = [], []
    for author in item.get("author", []) or []:
        name = clean(" ".join(filter(None, [author.get("given"), author.get("family")])) or author.get("name", ""))
        if name.casefold().strip(" .") in {"anonymous", "unknown", "n/a", "not available", "author unknown"}:
            placeholders.append(name)
        elif name:
            names.append(name)
    status = "partial" if names and placeholders else "placeholder" if placeholders else "available" if names else "missing"
    return {"authors": names, "author_metadata_status": status, "author_placeholders": placeholders}


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
    issns = set(item.get("ISSN", []))
    journal = next((j for j in config["journals"] if issns.intersection(j["issns"])), None)
    if journal is None:
        return None, "journal_not_whitelisted"
    abstract = clean(item.get("abstract", ""))
    # Editorial scope, not a judgment that biological network analysis is invalid.
    # An organism-specific model needs a core research-task signal in its title;
    # generic structure/community vocabulary in an abstract cannot rescue it.
    if (matches(rules["application_model_title"], title)
            and matches(rules["biomedical_context"], title)
            and not matches(rules["core_contribution_title"], title)):
        return None, "application_led_biomedical_model"
    if matches(rules["materials_title"], title) and matches(rules["network_object"], title) and not matches(rules["graph_evidence"], title + " " + abstract):
        return None, "material_network_without_graph_evidence"
    if matches(rules["ml_title"], title) and not matches(rules["ml_core_exception"], title):
        return None, "general_machine_learning"
    network_direct = matches(rules["network_explicit"], title)
    network_object = matches(rules["network_object"], title)
    network_mechanism = matches(rules["network_mechanism"], title)
    text = title + " " + abstract
    network_abstract = matches(rules["network_explicit"], abstract)
    is_network = bool(network_direct or (network_object and network_mechanism) or (network_object and network_abstract and matches(rules["network_mechanism"], abstract)))
    if not is_network:
        return None, "not_core"
    categories = []
    for c in config["network_categories"]:
        if matches(c["pattern"], text):
            categories.append(c["id"])
    evidence = sorted(set(network_direct + network_object + network_mechanism + network_abstract))
    return {
        "doi": doi, "url": "https://doi.org/" + quote(doi, safe="/"),
        "title": title,
        **author_metadata(item),
        "journal": journal["name"],
        "issns": sorted(issns), "date": published.isoformat(), "date_source": date_source,
        "categories": categories or ["other"],
        "featured": journal["short"] if journal["short"] in config["featured_journals"] else None, "journal_short": journal["short"], "evidence": evidence,
        "screening_basis": "network", "source": "Crossref", "abstract_available": bool(abstract),
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
    jobs = [("journal: " + j["name"], "https://api.crossref.org/journals/" + j["issns"][0] + "/works", j) for j in config["journals"]]
    candidates, coverage, errors = {}, [], []
    for label, endpoint, query in jobs:
        report = {"label": label, "query": query, "retrieved": 0, "total_results": None, "truncated": False, "urls": []}
        try:
            # Crossref rejects publication-date sorting with cursor pagination.
            # This bounded collection stays below the 10,000 offset limit.
            for page in range(config["max_pages_per_journal"]):
                params = {"filter": f"type:journal-article,from-pub-date:{start},until-pub-date:{today}",
                          "rows": config["rows_per_page"], "offset": page * config["rows_per_page"], "sort": "published", "order": "desc"}
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
                if not items or report["retrieved"] >= report["total_results"]:
                    break
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
                   "categories": [{"id": c["id"], "label": c["label"]} for c in config["network_categories"]] + [{"id": "other", "label": "其他"}],
                   "featured_journals": config["featured_journals"], "featured_order_year": config["featured_order_year"], "journals": config["journals"], "coverage": coverage,
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
