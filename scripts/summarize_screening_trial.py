"""Compare trial decisions to the deployed snapshot without changing either."""
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", type=Path, default=ROOT / "reports/v6-trial")
    args = parser.parse_args()
    trial = args.trial
    status = json.loads((trial / "status.json").read_text(encoding="utf-8"))
    audit = json.loads((trial / "screening-report.json").read_text(encoding="utf-8"))
    print("Collection complete:", status["ok"])
    config = json.loads((ROOT / "config/sources.json").read_text(encoding="utf-8"))
    current_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    print("Matches current config:", audit.get("config_sha256") == current_hash)
    print("Decisions:", dict(Counter(x["decision"] for x in audit["decisions"])))
    print("Reasons:", audit["counts"])
    if not status["ok"]:
        print("Incomplete collection; do not interpret an older trial snapshot as this run.")
        return
    data = json.loads((trial / "papers.json").read_text(encoding="utf-8"))
    previous = json.loads((ROOT / "site/data/papers.json").read_text(encoding="utf-8"))
    old_ids = {p["doi"] for p in previous["papers"]}
    new_ids = {p["doi"] for p in data["papers"]}
    print("Included:", len(new_ids), "Previously:", len(old_ids))
    print("Added:", len(new_ids - old_ids), "Removed:", len(old_ids - new_ids))
    print("Included by journal:", dict(Counter(p["journal_short"] for p in data["papers"])))
    for p in data["papers"]:
        if p["journal_short"] == "Science" or any(r["route"] == "implicit_interaction_dynamics" for r in p["screening_routes"]):
            print(json.dumps({"doi": p["doi"], "title": p["title"], "routes": p["screening_routes"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
