"""Merge existing and retry reports into a Springer/Nature coverage summary."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / "reports/v9-2026-09"


def read(name: str) -> dict:
    return json.loads((TRIAL / name).read_text(encoding="utf-8"))


def run(out: Path) -> None:
    canonical = {row["doi"]: row for row in read("publisher-canonical-v2.json")["results"]}
    audit = {row["doi"]: row for row in read("springer-nature-type-audit.json")["records"]}
    backfill = {row["doi"]: row for row in read("springer-nature-backfill-v1.json")["results"]}
    material = read("material-after-elsevier-verification-corrected.json")["results"]
    # The Nature audit intentionally covers the 282 records already selected
    # for the Springer/Nature type review, rather than every 10.1038 record in
    # the broader pending material file.
    material = [
        row for row in material
        if row["doi"].startswith("10.1007/") or row["doi"] in audit
    ]
    records = []
    for row in sorted(material, key=lambda item: item["doi"]):
        doi = row["doi"]
        existing = canonical.get(doi, {})
        fields = existing.get("bibliographic_metadata") or {}
        retry = backfill.get(doi, {})
        audit_row = audit.get(doi, {})
        abstract = bool(existing.get("abstract_available") or retry.get("abstract_available"))
        article_type = retry.get("article_type") or fields.get("citation_article_type") or audit_row.get("publisher_article_type")
        online_date = retry.get("online_date") or fields.get("citation_online_date") or audit_row.get("publisher_online_date")
        publication_date = retry.get("publication_date") or fields.get("citation_publication_date") or audit_row.get("publisher_publication_date")
        canonical_source_url = ((existing.get("sources") or [{}])[0].get("url"))
        nature_classification = audit_row.get("classification") if doi.startswith("10.1038/") else None
        if doi.startswith("10.1038/") and nature_classification == "type_unresolved" and article_type:
            # All 13 retry targets resolved to News, News Feature, News &
            # Views, Correspondence, or Nature Index on the publisher page.
            nature_classification = "publisher_non_research_type"
        record = {
            "doi": doi,
            "title": row.get("title"),
            "publisher_group": "Springer" if doi.startswith("10.1007/") else "Nature",
            "preferred_date": row.get("preferred_date"),
            "preferred_date_source": row.get("date_source"),
            "abstract_available": abstract,
            "abstract_source": (
                "springer-nature-backfill-v1.json" if retry.get("abstract_available")
                else "publisher-canonical-v2.json" if existing.get("abstract_available") else None
            ),
            "article_type": article_type,
            "article_type_source": (
                retry.get("article_type_source") or retry.get("source_url") if retry.get("article_type")
                else canonical_source_url or "springer-nature-type-audit.json" if audit_row.get("publisher_article_type") else None
            ),
            "publisher_online_date": online_date,
            "publisher_publication_date": publication_date,
            "publisher_source_url": retry.get("source_url")
            or canonical_source_url
            or audit_row.get("publisher_type_source"),
            "nature_type_classification": nature_classification,
        }
        records.append(record)
    counts = {
        "records": len(records),
        "springer_10_1007_records": sum(r["publisher_group"] == "Springer" for r in records),
        "springer_10_1007_abstract_available": sum(r["publisher_group"] == "Springer" and r["abstract_available"] for r in records),
        "nature_10_1038_records": sum(r["publisher_group"] == "Nature" for r in records),
        "nature_10_1038_article_type_available": sum(r["publisher_group"] == "Nature" and bool(r["article_type"]) for r in records),
        "nature_10_1038_standard_research_type": sum(
            r["publisher_group"] == "Nature" and r["nature_type_classification"] == "publisher_standard_research_type"
            for r in records
        ),
        "nature_10_1038_non_research_type": sum(
            r["publisher_group"] == "Nature" and r["nature_type_classification"] == "publisher_non_research_type"
            for r in records
        ),
        "nature_10_1038_unresolved_type": sum(
            r["publisher_group"] == "Nature" and not r["article_type"] for r in records
        ),
        "retry_access_limited": sum(r["doi"] in backfill and backfill[r["doi"]]["status"] == "access_limited" for r in records),
    }
    payload = {
        "version": "v9-springer-nature-coverage-1",
        "window_start": "2026-09-01",
        "window_end": "2026-09-30",
        "counts": counts,
        "input_sha256": {
            name: hashlib.sha256((TRIAL / name).read_bytes()).hexdigest()
            for name in (
                "material-after-elsevier-verification-corrected.json",
                "publisher-canonical-v2.json",
                "springer-nature-type-audit.json",
                "springer-nature-backfill-v1.json",
            )
        },
        "notes": [
            "Abstract text and page bodies are not stored.",
            "Nature records classified as publisher_non_research_type are not standard research articles; absence of a standard abstract is expected for those types.",
            "Preferred dates remain the existing material date provenance; publisher dates are reported separately.",
        ],
        "records": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    run(TRIAL / "springer-nature-coverage-v1.json")
