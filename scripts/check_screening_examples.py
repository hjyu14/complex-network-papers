"""Read-only live checks against known papers. Store decisions, never abstracts.

Run: python scripts/check_screening_examples.py
These cases validate specific boundaries; they do not estimate overall accuracy.
"""
from datetime import date
import json
import hashlib

from collect import CONFIG, ROOT, request_json, screen, write_json


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    # Fixed historical date for reproducible 90-day eligibility, not today's feed.
    today = date(2026, 9, 29)
    cases = [
        ("10.1126/science.aeg3946", "included", "Network heterogeneity and dynamical stability; title has no network term."),
        ("10.1073/pnas.2620995123", "included", "Empirical neuronal network structure and perturbation propagation."),
        ("10.1103/9y9m-q7qj", "included", "Preferential attachment as a network formation mechanism."),
        ("10.1126/science.adz5300", "review", "Communication networking needs content review; name alone is insufficient."),
        ("10.1126/science.aef8268", "review", "Imaging reconstruction network: topology alone does not establish network science."),
        ("10.1126/science.aei8090", "review", "Neural predictor: reconstruction alone is insufficient evidence."),
    ]
    results = []
    for doi, expected, rationale in cases:
        item = request_json("https://api.crossref.org/works/" + doi)
        paper, reason = screen(item, config, today)
        decision = "included" if paper else "review" if reason.startswith("review_") else "excluded"
        result = {"doi": doi, "title": item.get("title", []), "expected": expected,
                  "decision": decision, "reason": reason, "rationale": rationale,
                  "routes": paper["screening_routes"] if paper else [], "pass": decision == expected}
        results.append(result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    write_json(ROOT / "reports/v6-examples.json", {"evaluation_date": today.isoformat(),
               "screening_version": config["version"],
               "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(), "cases": results})
    return all(r["pass"] for r in results)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
