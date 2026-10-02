"""Merge the two normally verified ScienceDirect records into a new v9 trial snapshot.

The earlier round-2 files are historical inputs and are never overwritten.  The
publisher's exact online-first dates are stored separately from the old Crossref
date fields, then used as the effective v9 screening date with explicit provenance.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "reports" / "v9-2026-09"
SOURCE = "material-after-browser-round2.json"
EVIDENCE = "browser-elsevier-verification-2-evidence.json"


def read(name: str):
    return json.loads((TRIAL / name).read_text(encoding="utf-8"))


def main() -> None:
    previous = read(SOURCE)
    evidence = read(EVIDENCE)
    rows = {r["doi"]: dict(r) for r in previous["results"]}
    observations = {r["doi"]: r for r in evidence["results"]}
    assert set(observations) == {
        "10.1016/j.chaos.2026.118533",
        "10.1016/j.chaos.2026.118552",
    }
    assert all(doi in rows for doi in observations)

    # Make the old source explicit on every record before any publisher date is
    # promoted to the effective v9 field.
    for row in rows.values():
        row.setdefault("crossref_preferred_date", row.get("preferred_date"))
        row.setdefault("crossref_date_source", row.get("date_source"))

    for doi, note in observations.items():
        row = rows[doi]
        assert note["status"] == "verified_normally"
        assert note["material_obtained"]
        assert note["available_online"] == note["version_of_record"]
        # Preserve what Crossref previously said before adding the publisher signal.
        row["crossref_preferred_date"] = row.get("crossref_preferred_date")
        row["crossref_date_source"] = row.get("crossref_date_source")
        row["metadata_sources"] = list(dict.fromkeys(row["metadata_sources"] + [EVIDENCE]))
        row["abstract_sources"] = list(dict.fromkeys(row["abstract_sources"] + [EVIDENCE]))
        row["abstract_level_material"] = True
        row["abstract_and_complete_preferred_date"] = True
        row["preferred_date"] = note["available_online"]
        row["date_source"] = "publisher-available-online"
        row["publisher_date_evidence"] = {
            "source_url": note["source_url"],
            "journal_issue_label": note["journal_issue_label"],
            "available_online": note["available_online"],
            "version_of_record": note["version_of_record"],
            "date_semantics": "Online first is the effective v9 publication date; issue label is month-only.",
        }
        row["publisher_type_evidence"] = {
            "label": note["article_type"],
            "source_url": note["source_url"],
            "note": "ScienceDirect labels the item as a Research article.",
        }
        row["round3_evidence_reference"] = {"file": EVIDENCE, "doi": doi}
        row["round3_date_reconciliation"] = "publisher_online_date_precedes_issue_month"
        row["screening_evidence"] = note["screening_evidence"]
        row["classification_deferred"] = True

    # The two records leave the abstract queue and the date queue because their
    # exact publisher online-first dates are now available.  The Crossref-only
    # counters are retained to make the source transition auditable.
    missing = [r for r in rows.values() if not r["abstract_level_material"]]
    date_gaps = [r for r in rows.values() if r["abstract_level_material"] and not r["preferred_date"]]
    actionable = [r for r in missing if r.get("further_abstract_collection_required", True)]
    counts = dict(previous["counts"])
    counts.update({
        "elsevier_verification_processed": 2,
        "elsevier_verification_succeeded": 2,
        "elsevier_verification_session_reused_for_second_page": True,
        "abstract_level_material": sum(r["abstract_level_material"] for r in rows.values()),
        "abstract_and_complete_preferred_date": sum(r["abstract_and_complete_preferred_date"] for r in rows.values()),
        "abstract_but_missing_preferred_date": len(date_gaps),
        "still_missing_abstract": len(missing),
        "still_requiring_abstract_collection": len(actionable),
        "missing_abstract_or_preferred_date": len(missing) + len(date_gaps),
        "remaining_material_collection_records": len(actionable) + len(date_gaps),
        "material_including_previously_retained": 25 + sum(r["abstract_level_material"] for r in rows.values()),
        "abstract_and_complete_crossref_preferred_date": sum(
            bool(r.get("abstract_level_material") and r.get("crossref_preferred_date"))
            for r in rows.values()
        ),
        "abstract_but_missing_crossref_preferred_date": sum(
            bool(r.get("abstract_level_material") and not r.get("crossref_preferred_date"))
            for r in rows.values()
        ),
    })
    assert counts["abstract_level_material"] == 2685
    assert counts["still_missing_abstract"] == 1165
    assert counts["still_requiring_abstract_collection"] == 1159
    assert counts["abstract_and_complete_preferred_date"] == 2580
    assert counts["abstract_but_missing_preferred_date"] == 105
    counts["missing_abstract_or_crossref_preferred_date"] = (
        counts["still_missing_abstract"] + counts["abstract_but_missing_crossref_preferred_date"]
    )
    assert counts["remaining_material_collection_records"] == 1264

    out_material = {
        "version": "v9",
        "created_at": evidence["recorded_on"],
        "window": previous["window"],
        "counts": counts,
        "classification_deferred": True,
        "input_sha256": {
            SOURCE: hashlib.sha256((TRIAL / SOURCE).read_bytes()).hexdigest(),
            EVIDENCE: hashlib.sha256((TRIAL / EVIDENCE).read_bytes()).hexdigest(),
        },
        "missing_abstract_by_journal": dict(Counter(r["retrieved_by"][0] for r in actionable)),
        "notes": [
            "Two ScienceDirect pages were verified through the normal CAPTCHA checkbox flow; no bypass or token manipulation was used.",
            "The second page opened in the same browser session without another CAPTCHA prompt, so session reuse is recorded but not assumed for other sites.",
            "Publisher Available online and Version of Record dates are stored separately from the former Crossref fields and determine the effective v9 date.",
            "Both records show a September 2026 issue label but June 2026 online-first dates; they are outside a September online-first cohort.",
            "Abstract evidence is paraphrased; full abstracts, HTML, DOM, and screenshots are not stored.",
        ],
        "results": sorted(rows.values(), key=lambda r: r["doi"]),
    }
    out_pending = {
        "counts": counts,
        "missing_abstract": sorted(actionable, key=lambda r: r["doi"]),
        "missing_preferred_date_with_abstract": sorted(date_gaps, key=lambda r: r["doi"]),
        "historical_round2_access_blocked": previous.get("round2_access_blocked", []),
        "round3_access_blocked_remaining": [],
        "resolved_by_round3": sorted(observations),
    }
    material_name = "material-after-elsevier-verification-corrected.json"
    pending_name = "material-pending-after-elsevier-verification-corrected.json"
    for name in (material_name, pending_name):
        if (TRIAL / name).exists():
            raise FileExistsError(name)
    (TRIAL / material_name).write_text(json.dumps(out_material, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (TRIAL / pending_name).write_text(json.dumps(out_pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
