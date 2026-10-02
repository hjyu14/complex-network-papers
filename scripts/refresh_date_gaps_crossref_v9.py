"""Refresh exact DOI metadata for the 105 records missing a complete date.

This is a read-only Crossref pass.  It stores only date-part metadata and
status, never abstracts or response bodies.  A complete publisher online date
is required; record-created timestamps are retained as diagnostics only.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "reports" / "v9-2026-09"
UA = "ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)"


def parts(value):
    if not isinstance(value, dict):
        return None
    dp = value.get("date-parts")
    if not isinstance(dp, list) or not dp or not isinstance(dp[0], list):
        return None
    return dp[0]


def fetch(doi):
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    try:
        req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urlopen(req, timeout=30) as response:
            item = json.load(response).get("message", {})
        fields = {k: parts(item.get(k)) for k in
                  ("published-online", "published-print", "published", "issued", "created")}
        return {"doi": doi, "status": "ok", "url": url, "dates": fields,
                "type": item.get("type"), "container_title": item.get("container-title", []),
                "publisher_links": [l.get("URL") for l in (item.get("link", []) or []) if l.get("URL")],
                "link_count": len(item.get("link", []) or [])}
    except Exception as exc:
        return {"doi": doi, "status": "error", "url": url,
                "error": type(exc).__name__}


def main(out, workers=4):
    pending = json.loads((TRIAL / "material-pending-after-elsevier-verification-corrected.json").read_text(encoding="utf-8"))
    targets = [r["doi"] for r in pending["missing_preferred_date_with_abstract"]]
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, doi) for doi in targets]
        for idx, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if idx % 10 == 0 or idx == len(targets):
                complete_online = sum(bool((r.get("dates") or {}).get("published-online")) for r in results)
                errors = sum(r["status"] == "error" for r in results)
                print(json.dumps({"phase": "crossref_date_gap_refresh", "processed": idx,
                                  "total": len(targets), "complete_online_dates": complete_online,
                                  "errors": errors}, ensure_ascii=False), flush=True)
    results.sort(key=lambda r: r["doi"])
    payload = {
        "version": "v9",
        "input_count": len(targets),
        "counts": {
            "processed": len(results),
            "complete_published_online": sum(bool((r.get("dates") or {}).get("published-online")) for r in results),
            "complete_published_print": sum(bool((r.get("dates") or {}).get("published-print")) for r in results),
            "record_created_date": sum(bool((r.get("dates") or {}).get("created")) for r in results),
            "errors": sum(r["status"] == "error" for r in results),
        },
        "results": results,
        "note": "Crossref date metadata only; created timestamps are diagnostics and are not publication dates.",
    }
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["counts"], ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    main(args.out, args.workers)
