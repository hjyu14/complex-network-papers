"""Low-rate DOI metadata fallback APIs for v9; no abstracts are stored."""
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "reports/v9-2026-09"
UA = "ComplexNetworkPapers/0.1 (https://github.com/hjyu14/complex-network-papers)"


def get_json(url, accept="application/json"):
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": accept})
            with urlopen(req, timeout=18) as r:
                return r.status, json.load(r)
        except Exception as exc:
            code = getattr(exc, "code", None)
            if code not in (429, 500, 502, 503, 504) or attempt == 2:
                return code or type(exc).__name__, None
            time.sleep(1.5 * (attempt + 1))
    return "error", None


def one(doi):
    out = {"doi": doi, "sources": [], "abstract_available": False,
           "metadata_available": False}
    # DataCite descriptions can contain an abstract for a minority of records.
    status, data = get_json("https://api.datacite.org/dois/" + quote(doi, safe=""))
    if data and isinstance(data.get("data"), dict):
        attrs = data["data"].get("attributes") or {}
        desc = attrs.get("descriptions") or []
        abstract = any((d.get("descriptionType", "").lower() == "abstract" and d.get("description"))
                       for d in desc if isinstance(d, dict))
        out["abstract_available"] |= abstract
        out["metadata_available"] = True
        out["sources"].append({"source": "datacite", "status": "ok", "abstract_available": abstract})
    else:
        out["sources"].append({"source": "datacite", "status": str(status)})
    # OpenAIRE is public and occasionally mirrors repository abstracts.
    url = "https://api.openaire.eu/search/publications?doi=" + quote(doi, safe="") + "&format=json"
    status, data = get_json(url)
    abstract = False
    if isinstance(data, dict):
        entries = ((data.get('response') or {}).get('results') or {}).get('result') or []
        if isinstance(entries, dict): entries = [entries]
        for entry in entries:
            product = entry.get('metadata', {}).get('oaf:entity', {}).get('oaf:result', {})
            descriptions = product.get('description') or []
            if isinstance(descriptions, (str, dict)): descriptions = [descriptions]
            for desc in descriptions:
                value = desc.get('$', '') if isinstance(desc, dict) else desc
                abstract |= isinstance(value, str) and len(value.split()) >= 40
    if abstract:
        out["abstract_available"] = True
    out["sources"].append({"source": "openaire", "status": "ok" if data is not None else str(status),
                           "abstract_available": abstract})
    # Unpaywall requires a contact email and supplies no abstract.  The current
    # experiment does not invent a contact identity or request credentials.
    out["sources"].append({"source": "unpaywall", "status": "not_requested_contact_email_missing"})
    return out


def run(out, workers=6):
    report = json.loads((TRIAL / "screening-report.json").read_text(encoding="utf-8"))
    rows = {x["doi"].lower() for x in report["decisions"] if x["decision"] == "review"}
    known = set()
    for fn in ("crossref-fallback.json", "crossref-batch-refresh.json",
               "europepmc-fallback.json", "openalex-fallback.json"):
        data = json.loads((TRIAL / fn).read_text(encoding="utf-8"))
        known |= {x["doi"].lower() for x in data.get("results", []) if x.get("abstract_available")}
    targets = sorted(rows - known)
    counts = {"target": len(targets), "processed": 0, "abstract_found": 0,
              "metadata_found": 0, "errors": 0}
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, doi) for doi in targets]
        for idx, future in enumerate(as_completed(futures), 1):
            result = future.result()
            counts["processed"] = idx
            counts["abstract_found"] += bool(result["abstract_available"])
            counts["metadata_found"] += bool(result["metadata_available"])
            results.append(result)
            if idx % 50 == 0 or idx == len(targets):
                print(json.dumps({"phase": "api_batch", **counts}, ensure_ascii=False), flush=True)
    results.sort(key=lambda x: x["doi"])
    payload = {"version": "v9", "counts": counts, "results": results,
               "note": "API responses and abstracts processed transiently; no abstracts or full text stored."}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return counts


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--out", required=True); p.add_argument("--workers", type=int, default=6)
    a = p.parse_args(); print(json.dumps(run(a.out, a.workers), ensure_ascii=False))
