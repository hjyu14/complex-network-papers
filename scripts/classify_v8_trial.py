"""Rejected keyword prototype; NOT the confirmed v8 scope implementation.

The final trial is an explicit semantic review in build_v8_scope_review.py.
This prototype has known false positives/negatives and must not be promoted.
It is deliberately separate from production screening. It fetches the fixed
181-paper baseline, uses Crossref abstracts transiently, and writes decisions
without abstracts. The two positive classes are ``core`` and
``transferable_application``; the latter is intentionally conservative.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

try:
    from .collect import clean, request_json, write_json, ROOT
except ImportError:
    from collect import clean, request_json, write_json, ROOT


CORE = re.compile(
    r"\b(?:complex network|network science|network topology|network dynamics|"
    r"random graph|scale[- ]free|small[- ]world|multilayer network|multiplex network|"
    r"temporal network|higher[- ]order network|hypergraph|simplicial complex|"
    r"percolation|epidemic|contagion|spreading|diffusion|cascade|synchroni[sz]|"
    r"consensus|evolutionary game|cooperation|oscillator network|kuramoto|"
    r"community detection|link prediction|network reconstruction|network inference|"
    r"network control|controllability|network dismantl|network robustness|"
    r"random walk|degree distribution|preferential attachment|graph topology|"
    r"graph dynamics|network formation|network growth|core[- ]periphery|"
    r"rich[- ]club|modularity|centrality|adjacency matrix|interacting particle)", re.I)

METHOD = re.compile(
    r"\b(?:community detection|link prediction|network reconstruction|network inference|"
    r"network analysis|network control|controllability|network dismantl|"
    r"network robustness|centrality|modularity|rich[- ]club|graph partition|"
    r"network science|network topology)\b", re.I)

BIO_EXCLUDE = re.compile(
    r"\b(?:functional brain|cortical networks?|human cortical|brain network|hippocamp|alzheimer|"
    r"gene regulatory|transcriptional|single[- ]cell|cell cycle|cellular|"
    r"drug repurposing|atherosclerotic|cancer|tumou?r|biomedical|"
    r"mechanosensory|rat nervous|mouse brain|human subject|cognition|stress recovery|"
    r"synaptic|genomic|rna design|auranofin|amygdala|disease stratification|"
    r"mouse model|maternal inflammation|bladder mucosal|amyloid protein|"
    r"neuroimaging|neurophysiological recordings|merkel cell)\b", re.I)

APPLICATION = re.compile(
    r"\b(?:social|financial|bank|trade|road|traffic|transport|climate|"
    r"ecological|ecosystem|food web|wildlife|infrastructure|power grid|"
    r"surveillance|communication|cyber|malware|urban|internet)\b", re.I)

DOMAIN_METHOD = re.compile(
    r"\b(?:network analysis|network science|network reconstruction|network inference|"
    r"community detection|network control|network topology|centrality|modularity|"
    r"network structure|network dynamics|network resilience)\b", re.I)

QUANTUM_DEVICE = re.compile(r"\b(?:quantum key distribution|entanglement|qubit|quantum network)\b", re.I)

MODEL_CORE = re.compile(
    r"\b(?:percolation|epidemic|contagion|spreading|diffusion|cascade|"
    r"synchroni[sz]|oscillator|kuramoto|consensus|evolutionary game|"
    r"cooperation|higher[- ]order interaction|hypergraph|simplicial|"
    r"network topology|network dynamics|random graph|multilayer network|"
    r"complex network|network control|controllability)\b", re.I)

NON_NETWORK = re.compile(
    r"\b(?:image classification|object detection|drug discovery|disease stratification|"
    r"biomarker|gene expression|cell differentiation|molecular design|material design|"
    r"language model|sequence-derived|anomaly detection)\b", re.I)


def classify(title, abstract, doi=""):
    text = f"{title} {abstract}".strip()
    has_core = bool(CORE.search(text))
    has_method = bool(METHOD.search(text))
    bio = bool(BIO_EXCLUDE.search(text))
    app = bool(APPLICATION.search(text))
    non_network = bool(NON_NETWORK.search(text))

    # The confirmed boundary explicitly excludes biomedical/domain papers
    # whose scientific question is outside network science. Generic neuronal
    # oscillator or epidemic models remain eligible as network models.
    if bio:
        return ("exclude_domain_application", "biomedical_or_domain_network", has_core, has_method)
    if not abstract and not has_core:
        return ("review", "missing_abstract", has_core, has_method)
    if non_network and not has_method:
        return ("exclude_domain_application", "non_network_domain_task", has_core, has_method)
    if QUANTUM_DEVICE.search(text):
        return ("exclude_domain_application", "quantum_device_or_communication", has_core, has_method)
    if has_core and (not app or MODEL_CORE.search(title)):
        return ("core", "network_science_question", has_core, has_method)
    if has_method and app:
        return ("transferable_application", "network_method_in_application", has_core, has_method)
    if has_core and app:
        return ("transferable_application", "network_question_in_application", has_core, has_method)
    if has_core:
        return ("core", "network_science_question", has_core, has_method)
    return ("review", "insufficient_network_evidence", has_core, has_method)


def fetch_one(doi):
    item = request_json("https://api.crossref.org/works/" + quote(doi, safe=""))
    return doi, item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "site/data/baseline-v6.json")
    parser.add_argument("--out", type=Path, default=ROOT / "reports/v8-keyword-prototype")
    args = parser.parse_args()
    raw = args.source.read_bytes()
    baseline = json.loads(raw)
    dois = [p["doi"] for p in baseline["papers"]]
    with ThreadPoolExecutor(max_workers=3) as pool:
        fetched = dict(pool.map(fetch_one, dois))
    decisions = []
    for p in baseline["papers"]:
        doi = p["doi"]
        item = fetched[doi]
        title = clean(" ".join(item.get("title", [])))
        abstract = clean(item.get("abstract", ""))
        category, reason, has_core, has_method = classify(title, abstract, doi)
        decisions.append({
            "doi": doi, "title": title, "date": p["date"], "journal": p["journal"],
            "previously_included": True, "v8_category": category, "reason": reason,
            "abstract_available": bool(abstract), "core_signal": has_core,
            "method_signal": has_method,
            "metadata_sha256": hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest(),
            "metadata_url": "https://api.crossref.org/works/" + quote(doi, safe=""),
        })
    decisions.sort(key=lambda x: (x["v8_category"], x["date"], x["doi"]))
    counts = Counter(x["v8_category"] for x in decisions)
    now = datetime.now(timezone.utc).isoformat()
    report = {
        "trial": "v8_scope_classification",
        "attempted_at": now,
        "source_snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "source_screening_version": baseline["screening_version"],
        "window_start": baseline["window_start"], "window_end": baseline["window_end"],
        "input_count": len(decisions), "counts": dict(counts),
        "positive_categories": ["core", "transferable_application"],
        "decisions": decisions,
    }
    write_json(args.out / "classification-report.json", report)
    write_json(args.out / "summary.json", {
        "trial": report["trial"], "attempted_at": now, "input_count": len(decisions),
        "counts": dict(counts), "positive_categories": report["positive_categories"],
        "source_snapshot_sha256": report["source_snapshot_sha256"],
    })
    print(json.dumps({"input": len(decisions), "counts": dict(counts)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
