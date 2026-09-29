# Complex Network Papers

- Purpose: a public, registration-free literature board focused only on complex network structure and dynamics on networks. General nonlinear dynamics alone is out of scope.
- Scope: journal articles in the last 90 calendar days (including today), not preprints. Never fabricate papers or dates.
- Scientific scope and journal whitelist are configured in `config/sources.json`. Change these explicitly, not to improve apparent results.
- Whitelisted journal ISSNs are mandatory for every paper. Query journal works, not global network keyword search. Only `featured_journals` enter the spotlight; never infer membership from historical tier labels. Nature/Science/Nature Physics stay whitelisted but are outside the spotlight.
- Topic taxonomy maps PRE Networks and Complex Systems and journal scopes; see `docs/classification.md`. Allow multiple research themes; use `other` exclusively when no theme matches, last in navigation. Do not force labels to hide uncertainty.
- UI filters: theme, journal, date, and journal scope (all/featured/other). No separate nonlinear direction, network-type or application facets. Show six newest spotlight papers with full journal names; the journal caption alone may abbreviate PNAS.
- Crossref is the initial metadata source. Store metadata and DOI links, never PDFs or full abstracts. Abstracts may be processed transiently for screening.
- Screening is heuristic, not an expert assessment. Preserve match evidence, date provenance, query coverage and limitations. Featured journals do not bypass screening.
- v5 explicitly screens application-led biomedical model/atlas titles; do not blanket-exclude brain networks. Document this editorial boundary and its false-negative risk. Preserve author placeholders separately, never present them as verified names or infer publication status from them.
- English is the initial interface language; allow Chinese switching without translating titles/authors or resetting filters. `site/rules.html` is the public bilingual policy article. Keep it consistent with executable screening rules.
- Publication dates: online first, then print, then published/issued. If the preferred available date is incomplete, exclude rather than invent a day or silently use another date. Exclude future dates.
- `site/` is the public deployment directory. No credentials, private notes or research datasets may be committed. No runtime dependencies are required.
- Verify changes with `python -m unittest discover -s tests -v`, `node --check site/app.js`, `node --test tests/test_app.cjs`, and browser inspection for UI changes.
- Collector: `python scripts/collect.py`. Preview: `python -m http.server 8000 --directory site`.
- Failed or partial collection must not replace the last complete snapshot. Publish attempt status separately. All queries have explicit, reported limits.
- GitHub Actions and Pages are authorized for this project. Keep scheduled runs bounded; do not enable paid services. Repository: hjyu14/complex-network-papers.
