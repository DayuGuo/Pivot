# Workbench browser acceptance

Scope: local synthetic editorial fixture, private editor state for `demo-001`, Linux Chromium through the Docker Web origin. No real manuscripts, external notifications, official decisions, or mail sends.

Run `npx playwright test tests/e2e/workbench.spec.ts --reporter=list`. Chromium requires a process environment that permits its browser subprocesses. The restricted shell initially rejected Chromium startup; the authorized unsandboxed local test process launches successfully.

| Scenario | Evidence required by the browser test |
| --- | --- |
| Four-page chain | Existing login and navigation → queue → reader → reviewers → revision → original queue |
| Queue | Natural-language synthetic query, empty state, search/stage/sort, server-saved named view after reload, scroll restoration after opening the selected manuscript |
| Reader | Exact quoted text highlighted in the correct version/section, original attachment content and download header, version notes and reading section/paragraph after reload; real mouse-wheel scrolling to paragraph index 2 then exact paragraph visible near the reader viewport top on reload; network-aborted save retained across navigation plus an unrelated successful candidate save, recovery and retry |
| Reading controls | 18 px body text, keyboard panel resizing, focus mode, saved font and panel width |
| Reviewers | Topic/search empty state, previous/next preview, visible fixture provenance and uncertainty, selection across reload, comparison, editable `.test` invitation body/date, complete preview with digest |
| Revision and decision | Both rounds, old/new evidence, persisted verification, blank initial outcome, required-content validation, complete decision preview, private notes, ongoing review task unchanged |
| AI | Explicit synthetic scope, progress, cancellation without a later saved result, failed-save retry, rewritten result and adopted/ignored dispositions after reload; saved results keep their immutable version binding and are hidden when viewing another version |
| Layout and keyboard | 1366×768, 1440×900, 1920×1080; dark/system theme; Ctrl+K visible focus; 200% document CSS zoom; 390×844 narrow reader and Escape navigation close |
| Failure and permissions | Failed initial load with retry; author and reviewer 403 with no manuscript table or fixture identifier exposed |

The zoom check sets `document.documentElement.style.zoom = "2"` in Chromium and exercises the rendered page. It does not claim browser toolbar zoom, OS scaling, or assistive-technology certification. Windows, macOS, Firefox and Safari remain untested. API security/concurrency/CSRF coverage is a separate suite; this browser suite does not substitute for it.

The integrated seven-case run passed in 21.2 seconds. Log: `artifacts/workbench-browser-acceptance.log`. After strengthening failed-note recovery with an unrelated successful candidate save, the focused reader case passed (1 passed, 3.8 seconds); log: `artifacts/workbench-reader-recovery-acceptance.log`. The lead subsequently executed the full verification script successfully: **182 Python tests and 15 browser tests passed**, including this suite's final paragraph-level reading-position case at 18 px (browser test 10, 4.2 seconds). That case used a mouse wheel to save paragraph index 2, reloaded to the exact visible paragraph, and retained the failed-note recovery scenario. Evidence was read from `artifacts/workbench-final-verify.log`; the full browser suite took 30.3 seconds. The initial live run exposed that the Web proxy did not export PATCH/PUT and dropped Content-Disposition; both were fixed by the lead before the passing integrated runs.

Screenshots produced by executed browser checks: `workbench-work-1366.png`, `workbench-reader-1440.png`, `workbench-invitation-1920.png`, `workbench-decision-1920.png`, `workbench-queue-1366.png`, `workbench-queue-1440.png`, `workbench-queue-1920.png`, `workbench-reader-dark.png`, `workbench-reader-zoom200.png`, and `workbench-reader-narrow.png`, all under `artifacts/`. The lead owns final representative screenshot selection.
