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


def default_collection_date(today=None):
    """Temporary baseline freeze; explicit --date enables the later daily trial."""
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    return min(today, date(2026, 9, 29))


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value or ""))).strip()


def matches(pattern, text):
    return sorted({m.group(0).lower() for m in re.finditer(pattern, text, re.I)})


def classify_methods(text, rules):
    """Return conservative, orthogonal method labels and their evidence.

    Method labels describe how a paper studies its network question; they do
    not establish network-science relevance and never create a green lane.
    """
    definitions = [
        ("theory", "method_theory"),
        ("empirical", "method_empirical"),
        ("simulation", "method_simulation"),
        ("ai_ml", "method_ai_ml"),
    ]
    labels, evidence = [], {}
    for label, key in definitions:
        hits = matches(rules.get(key, r"(?!)"), text)
        if hits:
            labels.append(label)
            evidence[label] = hits
    return labels, evidence


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


def relevance(title, abstract, rules):
    """Evidence routes, not semantic certainty. No signal remains reviewable.

    Match within a title or sentence: unrelated words in distant abstract
    sentences must not jointly manufacture a network argument.
    """
    units = [("title", title)] + [("abstract", s) for s in re.split(r"(?<=[.!?])\s+", abstract) if s]
    routes, evidence = [], set()
    for source, text in units:
        direct = matches(rules["network_explicit"], text)
        objects = matches(rules["network_object"], text)
        mechanisms = matches(rules["network_mechanism"], text)
        methods = matches(rules["network_methods"], text)
        # Modularity also describes software/protein design. Require relational
        # context before treating that lone word as network-method evidence.
        if methods == ["modularity"] and not (objects or matches(rules["graph_evidence"], text)):
            methods = []
        relations = matches(rules["implicit_relations"], text)
        processes = matches(rules["implicit_processes"], text)
        specific = matches(rules["specific_network_mechanism"], text)
        graph = matches(rules["graph_evidence"], text)
        structural_graph = [hit for hit in graph if not re.fullmatch(r"complex networks?|network science", hit)]
        research = matches(rules.get("research_action", r"(?!)"), text)
        background = matches(rules.get("background_context", r"(?!)"), text)
        # A network mentioned as motivation, future applicability or a
        # biological/material metaphor is not evidence of an analysis.
        if source == "abstract" and background and not methods:
            continue
        # ML/material terminology alone is not negative evidence about a paper.
        # Explicit methods and mechanism evidence can establish relevance there.
        ambiguous_ml = matches(rules["ml_title"], title) or matches(rules.get("ml_representation", r"(?!)"), text)
        ambiguous_material = matches(rules["materials_title"], title + " " + text)
        graph_application = matches(rules.get("graph_application_title", r"(?!)"), title)
        incidental_domain = matches(rules.get("incidental_network_domain", r"(?!)"), title)
        core = matches(rules["ml_core_exception"], text)
        if ambiguous_material and not (structural_graph or methods):
            continue
        if ambiguous_ml and not (methods or core or (relations and processes)):
            continue
        # A graph is often only a representation in molecular/biomedical
        # design.  Do not treat cross-graph modelling as network science
        # unless an explicit network method or network mechanism is present.
        if graph_application and not (methods or specific or direct):
            continue
        # In quantum-device papers, "network" can name the communication
        # setting without being a network-science object.  Require explicit
        # topology/graph/network-analysis evidence before using generic
        # network + device language as a route.
        if incidental_domain and objects and not (methods or direct or graph):
            continue
        if matches(rules.get("food_web", r"(?!)"), text) and not (methods or graph or matches(rules.get("relational_analysis", r"(?!)"), text)):
            continue
        # Generic "complex network" and "higher-order interactions" can be
        # metaphors or descriptions of prior tools. Stronger network concepts
        # remain independent evidence; routine network methods always count.
        if source == "abstract" and direct and all(re.fullmatch(r"complex networks?|higher.order interactions?", hit) for hit in direct):
            if not (research or structural_graph or specific):
                direct = []
        if relations == ["interacting agents"] and not matches(rules.get("collective_process", r"(?!)"), text):
            relations = []
        route, hits = None, []
        if methods:
            route, hits = "network_method", methods
        elif direct:
            route, hits = "explicit_network_concept", direct
        elif objects and (mechanisms or processes) and (source == "title" or graph or (specific and research)):
            route, hits = "network_structure_or_dynamics", objects + mechanisms + processes
        elif relations and processes:
            route, hits = "implicit_interaction_dynamics", relations + processes
        if route:
            routes.append({"route": route, "source": source, "matches": hits})
            evidence.update(hits)
    if routes:
        return "included", routes, sorted(evidence)
    # Missing abstracts cannot support a definitive content exclusion.
    if not abstract:
        return "review_missing_abstract", [], []
    if matches(rules["ml_title"], title) and matches(rules["ml_application"], title):
        return "general_machine_learning", [], []
    if matches(rules["network_object"], title + " " + abstract) or matches(rules["implicit_processes"], title + " " + abstract):
        return "review_context", [], []
    return "review_no_signal", [], []


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
    text = title + " " + abstract
    scope_review = None
    if config['version'] >= 8:
        scope_path = ROOT / config['scope_policy']['review_file']
        registry = json.loads(scope_path.read_text(encoding='utf-8'))
        scope_review = registry['decisions'].get(doi)
        if scope_review is None:
            return None, 'review_unassessed_scope'
        if clean(scope_review['title']).casefold() != title.casefold():
            return None, 'review_changed_title'
        if scope_review['v8_category'] == 'review':
            return None, 'review_scope'
        if scope_review['v8_category'] == 'excluded':
            return None, 'outside_editorial_scope'
        if scope_review['v8_category'] not in config['scope_policy']['classes']:
            raise ValueError('Invalid scope-review category')
        decision = 'included'
        routes = [{'route': 'approved_scope_review', 'source': scope_review['evidence_level'],
                   'matches': [scope_review['reason']]}]
        evidence = [scope_review['reason']]
    else:
        decision, routes, evidence = relevance(title, abstract, rules)
    if decision != "included":
        return None, decision
    categories = []
    for c in config["network_categories"]:
        if matches(c["pattern"], text):
            categories.append(c["id"])
    annotations = {}
    if config['version'] < 8:
        methods, method_evidence = classify_methods(text, rules)
        annotations = {'methods': methods, 'method_evidence': method_evidence}
    else:
        annotations = {'scope_class': scope_review['v8_category'],
                       'scope_evidence_level': scope_review['evidence_level'],
                       'scope_review_sha256': hashlib.sha256(scope_path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()}
    return {
        "doi": doi, "url": "https://doi.org/" + quote(doi, safe="/"),
        "title": title,
        **author_metadata(item),
        "journal": journal["name"],
        "issns": sorted(issns), "date": published.isoformat(), "date_source": date_source,
        "categories": categories or ["other"],
        **annotations,
        "featured": journal["short"] if journal["short"] in config["featured_journals"] else None, "journal_short": journal["short"], "evidence": evidence,
        "screening_basis": "network", "screening_routes": routes, "source": "Crossref", "abstract_available": bool(abstract),
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
    if config["rows_per_page"] < 1 or config["rows_per_page"] > 1000 or not 1 <= config["max_pages_per_journal"] <= 10000 // config["rows_per_page"]:
        raise ValueError("Pagination must stay within the 10,000-record offset budget")
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
                          "rows": config["rows_per_page"], "offset": page * config["rows_per_page"], "sort": "published", "order": "desc",
                          "select": "DOI,title,type,ISSN,abstract,author,published-online,published-print,published,issued,update-to,updated-by"}
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
            if report["truncated"]:
                errors.append({"query": label, "error": "Collection limit or early empty page: incomplete coverage"})
            print(f"{label}: {report['retrieved']}/{report['total_results']}", flush=True)
        except Exception as exc:
            errors.append({"query": label, "error": type(exc).__name__ + ": " + str(exc)[:300]})
            report["failed"] = True
            print(f"FAILED {label}: {type(exc).__name__}", flush=True)
        coverage.append(report)
        time.sleep(0.25)
    stats, papers, decisions = Counter(), [], []
    for candidate in candidates.values():
        paper, reason = screen(candidate["item"], config, today)
        stats[reason] += 1
        item = candidate["item"]
        decisions.append({"doi": item.get("DOI", "").lower(), "title": clean(" ".join(item.get("title", []))),
                          "decision": "included" if paper else "review" if reason.startswith("review_") or reason == "missing_or_partial_date" else "excluded",
                          "reason": reason, "abstract_available": bool(clean(item.get("abstract", ""))),
                          "retrieved_by": sorted(set(candidate["queries"]))})
        if paper:
            paper["retrieved_by"] = sorted(set(candidate["queries"]))
            papers.append(paper)
    papers.sort(key=lambda p: (p["date"], p["doi"]), reverse=True)
    status = {"attempted_at": timestamp, "ok": not errors, "errors": errors, "coverage": coverage}
    # Separate audit artifact: never silently discard unmatched candidates.
    write_json(out / "screening-report.json", {"attempted_at": timestamp, "screening_version": config["version"],
               "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
               "window_start": start.isoformat(), "window_end": today.isoformat(),
               "collection_complete": not errors, "counts": dict(stats), "decisions": decisions})
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
    parser.add_argument("--date", type=date.fromisoformat, default=default_collection_date(),
                        help="Window end; temporarily defaults to no later than 2026-09-29")
    parser.add_argument("--out", type=Path, default=OUT, help="Separate trial output directory (does not replace the public snapshot)")
    args = parser.parse_args()
    success = collect(json.loads(CONFIG.read_text(encoding="utf-8")), args.date, args.out)
    raise SystemExit(0 if success else 1)
