# NetSci Observatory

English | [中文](README.zh-CN.md)

A public, registration-free reading list for network science. Discover research on network structure, dynamics on networks, and transferable network-science theory and methods, without searching each journal separately.

**[Explore the papers →](https://netsciobs.com/)**

## What you can do

- Browse relevant papers from thirteen journals in one place.
- Filter by research topic, journal, date, or Spotlight journal scope; search titles, authors, journals, and DOIs.
- Read short English or Chinese notes explaining each paper's connection to network science.
- Follow links to the original papers, with accepted manuscripts and special article types identified.
- Switch the website between English and Chinese without changing paper titles, author names, or active filters.

The website starts in English and remembers your language choice.

## Research scope

We focus on how networks form and evolve, how their structure can be inferred, and how interactions shape spreading, synchronization, collective behavior, robustness, and control.

Studies of specific systems are included when network organization is a central research question or the work contributes theory or methods transferable to other systems. Routine use of network measures for domain analysis, or nonlinear dynamics without a clear network-science contribution, is outside the scope. Relevant reviews, perspectives, and scientific commentaries may also be included.

## Journals and Spotlight

Spotlight displays included papers from the following nine journals. The homepage shows the latest six; the Spotlight link opens the full Spotlight list. This is a display grouping, not a quality ranking, and all papers follow the same inclusion criteria.

- Nature
- Science
- Nature Communications
- Nature Machine Intelligence
- Nature Computational Science
- Physical Review X
- Physical Review Letters
- Science Advances
- Proceedings of the National Academy of Sciences

The complete list also includes papers from:

- Communications Physics
- Physical Review Research
- Physical Review E
- Chaos: An Interdisciplinary Journal of Nonlinear Science

## Current coverage and limitations

The current list covers **1 September–5 October 2026**, with **146 papers: 108 published papers and 38 accepted manuscripts**. Of these, 22 belong to the Spotlight group.

Date filters are relative to the displayed data cutoff, not today's date. Choose “All collected dates” to browse the entire collection. Updates are currently published in reviewed batches, not automatically every day. Publication dates prioritize first online publication; accepted manuscripts awaiting publication are marked separately and shown by acceptance date. Preprints are excluded.

Selection is based mainly on abstracts and bibliographic evidence, with AI assistance and editorial decisions on scope questions. Reading notes support discovery; they are not quality ratings or full-text expert reviews. Coverage is not guaranteed to be exhaustive. The site provides metadata, short notes, and original-paper links, not full abstracts or article text.

Read the [selection policy and limitations](https://netsciobs.com/rules.html) for details.

## Feedback

Found a missing paper, an incorrect record, or a reading note that needs correction? [Open an issue](https://github.com/hjyu14/complex-network-papers/issues), preferably with the DOI or publisher link and a brief explanation. Suggestions for improving the website are welcome too.

## For contributors

The site is a static website hosted on GitHub Pages, with no registration or runtime dependencies. To preview it locally from the repository root:

```sh
python -m http.server 8003 --directory site
```

Open `http://localhost:8003/`. Collection, selection, and publication procedures are documented separately:

- [Collection and coverage checks](docs/collection-workflow.md)
- [Selection protocol](docs/screening-protocol.md)
- [Evidence requirements and known pitfalls](docs/evidence-data-features.md)
- [Publication and verification](docs/publication.md)
- [Review records](reports/) and [contributor constraints](AGENTS.md)
