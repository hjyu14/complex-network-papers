# Complex Network Papers

- Purpose: a public, registration-free literature board about complex network structure and dynamics on networks.
- Scope: journal articles in the last 90 calendar days (including today), not preprints. Never fabricate papers or dates.
- Scientific scope and journal whitelist are configured in `config/sources.json`. Change these explicitly, not to improve apparent results.
- Crossref is the initial metadata source. Store metadata and DOI links, never PDFs or full abstracts. Abstracts may be processed transiently for screening.
- Screening is heuristic, not an expert assessment. Preserve match evidence, date provenance, query coverage and limitations. Featured journals do not bypass screening.
- Publication dates: online first, then print, then published/issued. If the preferred available date is incomplete, exclude rather than invent a day or silently use another date. Exclude future dates.
- `site/` is the public deployment directory. No credentials, private notes or research datasets may be committed. No runtime dependencies are required.
- Verify changes with `python -m unittest discover -s tests -v`, `node --check site/app.js`, and browser inspection for UI changes.
- Collector: `python scripts/collect.py`. Preview: `python -m http.server 8000 --directory site`.
- Failed or partial collection must not replace the last complete snapshot. Publish attempt status separately. All queries have explicit, reported limits.
- GitHub Actions and Pages are authorized for this project. Keep scheduled runs bounded; do not enable paid services. Repository: hjyu14/complex-network-papers.
