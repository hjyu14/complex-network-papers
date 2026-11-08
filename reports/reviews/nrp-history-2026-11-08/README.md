# Nature Reviews Physics historical review import

Status: the user approved the local preview for Git commit, push and production deployment on 2026-11-08. Deployment results are verified separately after the release.

The user approved the NRP history collection and local website integration on 2026-11-08. Existing PR/RMP sources remain immutable. This change adds 12 NRP selections to the existing 84, for a local preview of 96 reviews. It does not change the ordinary daily collection, Spotlight or recommendation.

All-types official yearly directories from 2018 through 2026 register 1,002 unique records. The primary assistant assessed 354 articles in the Review Article, Technical Review, Perspective, Roadmap and Expert Recommendation formats: 12 included, 342 excluded, no unresolved or unassessed articles. The remaining 648 records are outside this substantive review-format import; their original types and explicit genre boundary are recorded separately. These exclusions do not claim that scientific comments are unscientific.

Included records comprise seven Review Articles, two Technical Reviews and three Perspectives. All included notes follow actual reading of complete explicit publisher abstracts. Some clearly unrelated excluded records were assessed using explicitly identified opening/closing abstract excerpts; actual reading scopes are recorded per event. No full text or PDF was downloaded or reviewed. Complete abstracts remain only in the ignored shared abstract cache.

`evidence/inputs/` freezes the starting configuration, screening rules and the approved NRP import scope. `directory-YYYY.json` preserves all-type pagination and bibliography; `crossref-bibliography.json` preserves the database comparison; `articles/` preserves publisher bibliography and distinct supplementary observations; `screening-log.jsonl` retains authored decisions and corrections. The publisher's official format definitions are at https://www.nature.com/natrevphys/content.

Crossref returned 1,002 rows but only 1,001 unique DOIs: the biological model-discovery DOI appeared twice across offset pages. The cause is unconfirmed. The official-only Non-line-of-sight imaging record was verified directly on the publisher and excluded after abstract reading. Official directories are the coverage basis; API row counts alone are not taken as proof of completeness.

`evidence/check.json` binds coverage and log hashes. `evidence/collection.json` contains the 12 selected records and necessary evidence, pinned independently in `config/review-collection.json`. NRP was checked through 2026-11-08; PR/RMP retain their previous 2026-11-02 cutoff. Reproducible collection/assembly helpers and local preview outputs are in `.private/work/nrp-history-2026-11-08/`.

Release scope: the user explicitly approved this version, a bilingual changelog entry, related repository documentation and verified cleanup of redundant files from this task. The changelog entry is dated 2026-11-08. Deployment and cleanup receipts are retained privately; original bibliography, screening records and abstract-cache versions remain protected.
