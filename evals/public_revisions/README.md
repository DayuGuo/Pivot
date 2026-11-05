# Public revision reference corpus

Three real CC BY 4.0 article version pairs from F1000Research, frozen for offline software regression. This is an internal engineering corpus, not an expert-labelled accuracy benchmark or a new journal review.

| Case | v1 → v2 DOI | Licensed article pages v1/v2 | Derived Word paragraphs v1/v2 |
| --- | --- | --- | --- |
| The Open Science Peer Review Oath / An Open Science Peer Review Oath | [5686.1](https://doi.org/10.12688/f1000research.5686.1) → [5686.2](https://doi.org/10.12688/f1000research.5686.2) | 5 / 4 | 64 / 40 |
| Key Guidelines for Responding to Reviewers | [154614.1](https://doi.org/10.12688/f1000research.154614.1) → [154614.2](https://doi.org/10.12688/f1000research.154614.2) | 10 / 11 | 159 / 163 |
| Preprint attitudes survey | [143013.1](https://doi.org/10.12688/f1000research.143013.1) → [143013.2](https://doi.org/10.12688/f1000research.143013.2) | 14 / 15 | 295 / 302 |

Copyright belongs to the authors/reviewers credited in [manifest.json](manifest.json) and each source article/report. Reuse under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). This attribution and transformation notice must accompany copied fixtures. The project software licence does not replace these source licences.

`manifest.json` records exact version DOIs, credited authors/reviewers, source PDF/XML links, original and fixture SHA-256 values, transformations, independent XML text guards, and the exact selected review paragraphs with their report DOIs and explicit licences.

- PDF fixtures preserve the publisher's article pages without retypesetting; interactive annotations and appended review/comments pages are removed. Full publisher PDF/XML files stay in ignored research storage, because appended web comments do not have an established equivalent reuse licence. Original source hashes remain in the manifest.
- Word fixtures are explicitly derived minimal OOXML from licensed XML title, author names, abstract, body and reference text. They are not publisher-native Word files. Figure layout, equations and Word features are not reconstructed. This corpus cannot certify arbitrary author-supplied Word layout.
- `author-revision-note.docx` contains the actual article's licensed `sec-type=version-changes` text. This is a **published revision-note excerpt**, not a full rebuttal letter. There are **zero complete rebuttal letters** in this corpus. Detailed author web comments have not been copied into fixtures.
- Official PDF pages 1–2 include publication information and the revision note. Formal comparison confirms manuscript scope starting at page 3, so that an author's claim is not treated as manuscript modification evidence. XML-to-Word conversion removes the version-changes section structurally from manuscript text.

Rebuild from explicitly downloaded source files (no arbitrary remote fetch or upstream code execution):

```sh
PYTHONPATH=. .venv/bin/python evals/public_revisions/build.py --research artifacts/spec025/public-research
```

Normal `scripts/verify.sh` includes offline extraction, all fixture hashes/guards, actual formal import/confirmation/revision APIs, exact locations and adversarial tests. Every API test rolls back its own isolated transaction; no data reset.

Optional actual DeepSeek HTTP acceptance uses only the **publishing-os-verification** stack/ports and test accounts, explicitly changes it temporarily to live read-only inference, and restores Mock in `finally`. The selected main local API's already-configured credential is captured in memory only. Main data/configuration and VPS remain untouched. Run without concurrent Pytest/Playwright:

```sh
PYTHONPATH=. .venv/bin/python -m evals.public_revisions.live --live --report artifacts/spec025/public-live.json
# Retry inference against the existing synthetic cases, without repeating human gates:
PYTHONPATH=. .venv/bin/python -m evals.public_revisions.live --live --resume artifacts/spec025/public-live.json --report artifacts/spec025/public-live-retry.json
```

The live harness traverses every opinion batch, re-extracts original bytes to verify every quoted source/page/paragraph, checks the unchanged-old-manuscript + real-new-revision-note adversarial case, compares formal proposal/confirmation/decision counts and Mailpit=0. Token/duration/repair telemetry and unknown invoice cost are reported separately. Conservative uncertainty is not evidence of scientific correctness; all positive conclusions still require a responsible editor and independent professional review.
