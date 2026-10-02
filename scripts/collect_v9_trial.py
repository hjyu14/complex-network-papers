"""Isolated v9 September 2026 trial; never writes the public snapshot."""
import argparse, hashlib, json, re, time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from collect import (ROOT, clean, default_collection_date, publication_date,
                     relevance, request_json, write_json)

SOURCE = ROOT / "config/sources.json"
POLICY = ROOT / "config/screening-policy-v9.json"


def classify_v9(item, config, end):
    title = clean(" ".join(item.get("title", [])))
    if item.get("type") != "journal-article" or not title:
        return None, "not_article"
    if re.match(r"^(correction|erratum|corrigendum|retraction|author correction|publisher correction|editorial|addendum)\b", title, re.I) or item.get("update-to"):
        return None, "notice"
    published, date_source = publication_date(item)
    if published is None:
        return None, "missing_or_partial_date"
    start = date(2026, 9, 1)
    if not start <= published <= end:
        return None, "outside_window"
    doi = item.get("DOI", "").strip().lower()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        return None, "missing_doi"
    issns = set(item.get("ISSN", []))
    journal = next((j for j in config["journals"] if issns.intersection(j["issns"])), None)
    if journal is None:
        return None, "journal_not_whitelisted"
    abstract = clean(item.get("abstract", ""))
    if not abstract:
        return None, "review_missing_abstract"
    decision, routes, evidence = relevance(title, abstract, config["screening"])
    if decision != "included":
        return None, decision
    # This is a bounded trial label, not a claim of expert editorial review.
    application_words = re.compile(r"\b(soil|pollution|disease|health|medical|biology|ecology|climate|traffic|financial|agricultur|urban|material|protein|brain|social)\b", re.I)
    cls = "transferable_application" if application_words.search(title + " " + abstract) else "core"
    route_names = [r["route"] for r in routes]
    summary = (f"The study examines {title}; it uses {', '.join(route_names)} evidence to make a network contribution central to the work.")
    return {
        "doi": doi, "url": "https://doi.org/" + doi, "title": title,
        "journal": journal["name"], "journal_short": journal["short"],
        "issns": sorted(issns), "date": published.isoformat(), "date_source": date_source,
        "class": cls, "screening_summary": summary, "evidence": evidence,
        "screening_routes": routes, "abstract_available": True,
        "metadata_url": "https://api.crossref.org/works/" + doi,
    }, "included"


def run(end, out):
    config = json.loads(SOURCE.read_text(encoding="utf-8"))
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    config["screening_version"] = policy["version"]
    jobs = [("journal: " + j["name"], "https://api.crossref.org/journals/" + j["issns"][0] + "/works", j) for j in config["journals"]]
    candidates, coverage, errors = {}, [], []
    for index, (label, endpoint, journal) in enumerate(jobs, 1):
        report = {"label": label, "retrieved": 0, "total_results": None, "truncated": False, "urls": []}
        try:
            params = {"filter": f"type:journal-article,from-pub-date:2026-09-01,until-pub-date:{end}", "rows": 1000, "offset": 0, "sort": "published", "order": "desc", "select": "DOI,title,type,ISSN,abstract,author,published-online,published-print,published,issued,update-to,updated-by"}
            url = endpoint + "?" + urlencode(params)
            message = request_json(url)
            report["urls"].append(url); report["total_results"] = message["total-results"]
            for item in message["items"]:
                doi = item.get("DOI", "").lower()
                if doi:
                    candidates.setdefault(doi, {"item": item, "queries": []})["queries"].append(label)
            report["retrieved"] = len(message["items"]); report["truncated"] = report["retrieved"] < report["total_results"]
            if report["truncated"]: errors.append({"query": label, "error": "retrieval_budget_truncated"})
        except Exception as exc:
            report["failed"] = True; errors.append({"query": label, "error": type(exc).__name__ + ": " + str(exc)[:300]})
        coverage.append(report)
        print(json.dumps({"phase":"collection","journal_index":index,"journal_total":len(jobs),"journal":label,"retrieved":report["retrieved"],"candidates":len(candidates)}, ensure_ascii=False), flush=True)
        time.sleep(0.25)
    decisions, papers, counts = [], [], Counter()
    total = len(candidates)
    for idx, candidate in enumerate(candidates.values(), 1):
        paper, reason = classify_v9(candidate["item"], config, end)
        counts[reason] += 1
        item = candidate["item"]
        row = {"doi": item.get("DOI", "").lower(), "title": clean(" ".join(item.get("title", []))), "decision": "included" if paper else "review" if reason.startswith("review_") or reason == "missing_or_partial_date" else "excluded", "reason": reason, "abstract_available": bool(clean(item.get("abstract", ""))), "retrieved_by": sorted(set(candidate["queries"]))}
        decisions.append(row)
        if paper:
            paper["retrieved_by"] = row["retrieved_by"]; papers.append(paper)
        if idx % 100 == 0 or idx == total:
            print(json.dumps({"phase":"screening","processed":idx,"total":total,"included":len(papers),"counts":dict(counts)}, ensure_ascii=False), flush=True)
    papers.sort(key=lambda p: (p["date"], p["doi"]), reverse=True)
    config_hash = hashlib.sha256(json.dumps({"source":config,"policy":policy}, sort_keys=True).encode()).hexdigest()
    status = {"attempted_at": datetime.now(timezone.utc).isoformat(), "ok": not errors, "errors": errors, "coverage": coverage}
    report = {"attempted_at": status["attempted_at"], "screening_version": policy["version"], "config_sha256": config_hash, "window_start": "2026-09-01", "window_end": end.isoformat(), "collection_complete": not errors, "counts": dict(counts), "decisions": decisions}
    write_json(out / "screening-report.json", report); write_json(out / "status.json", status)
    if not errors:
        write_json(out / "papers.json", {"generated_at": status["attempted_at"], "window_start":"2026-09-01", "window_end":end.isoformat(), "screening_version":policy["version"], "config_sha256":config_hash, "candidate_count":total, "coverage":coverage, "screening_counts":dict(counts), "papers":papers})
    print(json.dumps({"phase":"complete","ok":not errors,"candidates":total,"included":len(papers),"counts":dict(counts)}, ensure_ascii=False), flush=True)
    return not errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--date", type=date.fromisoformat, default=date(2026, 9, 30)); parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(); raise SystemExit(0 if run(args.date, args.out) else 1)
