# Public manuscript evaluation corpus

Three real, explicitly reusable papers; six files. This is an import/metadata/evidence evaluation, not an assessment of scientific validity. No confidential submissions, author contact or real mail. The browser driver explicitly simulates the demo responsible editor; model tools cannot confirm anything.

| Paper | Status and permission | PDF | Word |
| --- | --- | --- | --- |
| [Clinical Practice Guidelines recommendations versus Cochrane systematic reviews…](https://zenodo.org/records/19059298) | Public **unpublished** manuscript; record API states CC BY 4.0 | Labelled LibreOffice export from the native Word | Native author Word |
| [Ten Simple Rules for Reproducible Computational Research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003285) | Published editorial; article-specific CC BY statement | Publisher PDF | Labelled text derivative of publisher JATS |
| [Why Most Published Research Findings Are False](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.0020124) | Published essay; article-specific CC BY statement | Publisher PDF | Labelled text derivative of publisher JATS |

The PLOS statements do not specify a CC BY version; we do not invent one. See `manifest.json` for exact URLs, checksums, licence statements, byline/affiliation gold values, and separately marked editor-added summary/keywords. Published 2005/2013 affiliations and email addresses describe those source versions, not authenticated identities or current employment/contact details. Do not send mail.

The small `derived` files are redistributed with attribution to the original authors and sources under their article licences. PLOS Word derivatives retain the article body/back matter and authorship/affiliation markers; they are **not author-supplied Word originals**, page-faithful reproductions, or formula/figure transcriptions. The native Word and publisher PDFs are downloaded only on explicit request into ignored `artifacts/public-papers`. The independent native Word record's metadata contributors/affiliations are not treated as the paper byline.

## Reproduce

With the project Python environment, Docker services and local real DeepSeek already configured:

```bash
.venv/bin/python scripts/evaluate-public-papers.py --fetch
.venv/bin/python scripts/evaluate-public-papers.py --stage --live
.venv/bin/python scripts/evaluate-public-papers.py --audit
node scripts/evaluate-public-papers-browser.mjs --live
```

`--stage --live` creates six new private evaluation dossiers, stages metadata and stops before confirmation. It reads no model key; the local API uses its existing secure configuration. The browser driver deliberately fills reviewed gold forms as `editor@publishing.test`, clicks the independent acknowledgement, saves a new version and asks real questions. It is an **automated simulation of the responsible person**, not real author/reviewer consent or expert scientific review. `--resume` resumes the same staging set without duplicating already reviewed versions or successful answers; do not mix staging files from different runs.

This delivery reused staged cases while fixing actual failures; the exact accepted set is `artifacts/public-papers/selected-final-imports.json`. Use `--staging artifacts/public-papers/selected-final-imports.json` for its audit/browser driver. Raw failed runs remain in ignored artifacts and the immutable local audit history.

Optional independent text comparisons use installed Poppler `pdftotext -raw` per PDF page and an isolated LibreOffice text export for Word. Save the latter under `artifacts/public-papers/independent-word/{paper-id}/*.txt`; the audit reports whether it exists. Character multiset recall, paragraph matching, exact quote positions and source hashes are distinct measurements; none proves complete visual/scientific understanding. Original unmatched paragraph indexes are retained even when a separate bullet-prefix analysis explains them.

Additional stress inputs, not passed off as completed positive cases: [P4 working paper](https://zenodo.org/records/18968737) (CC BY 4.0; missing affiliation/contact blocks confirmation), and [wheat preprint](https://zenodo.org/records/16531112) (CC BY 4.0; native Word exceeds 5MiB, PDF contains undecodable null glyphs). Their downloaded originals remain outside Git. Scans/OCR and complex visual/mathematical layout are outside this test's supported scope.

Results and remaining limitations: [delivery record](../../docs/development/public-paper-evaluation.md).

For focused rechecks of already reviewed versions, use `--qa-only`; `--only-cases case-a,case-b` selects cases and `--question-tag TEXT` creates an explicitly new phrasing while preserving old immutable answers. No additional confirm is made in QA-only mode. `--resume` reuses an existing report only for the same staging set. Narrow name/comparison and incomplete-coverage guards are not complete semantic validation; expert review remains separate.

## Author links and claim support (spec020)

`support_cases.json` freezes 18 manually authored positive/counterfactual cases before scoring. Each paper contributes three direct-support and three deliberately false or overstated statements; applying them to two formats yields 36 cases. Negative statements are **test counterfactuals**, not conclusions attributed to the papers. Attribution and file licences remain those in `manifest.json`. Exact raw quotes preserve PDF hyphenation/ligatures; no fuzzy scientific paraphrase matching is used.

```bash
# Offline CI uses the three small bundled derivatives; no network/model/business writes.
.venv/bin/python scripts/evaluate-evidence-integrity.py
# All six require the verified downloaded originals already in artifacts/public-papers.
.venv/bin/python scripts/evaluate-evidence-integrity.py --all-files --report artifacts/evidence-all.json
# Explicit actual support-stage inference: public data only, no confirmations.
.venv/bin/python scripts/evaluate-evidence-integrity.py --all-files --live --report artifacts/evidence-live.json
# Separate actual automatic import plus independent metadata/text audit.
.venv/bin/python scripts/evaluate-public-papers.py --stage --live --staging artifacts/new-run/staging.json
.venv/bin/python scripts/evaluate-public-papers.py --audit --staging artifacts/new-run/staging.json --report artifacts/new-run/quality-audit.json
node scripts/evaluate-public-papers-browser.mjs --live --staging artifacts/new-run/staging.json --report artifacts/new-run/browser.json
```

The offline author result is **validator replay of independent gold proposals**, not model extraction accuracy. The separate automatic import audit compares actual DeepSeek proposals before the browser driver corrects the form. Keep reports from different stages/runs separate; --report and --staging preserve prior evidence. The support judge uses the same model in a fresh context, so correlated errors remain possible. Small fixed-corpus success is not a general accuracy estimate, scientific certification, ORCID authentication or professional editorial sign-off. Historical answers are immutable and are not retroactively labelled semantically checked.
