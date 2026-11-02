# Editorial workbench interface research

Retrieved 2026-11-02 using Firecrawl official documentation/page retrieval. All nine supplied reference URLs returned HTTP200. This is a synthesis of product patterns for Publishing OS, not a claim to integrate those products or reproduce their UIs. No Notion visual reference or mixed component libraries.

| Primary source | Observed pattern | Publishing OS adaptation |
| --- | --- | --- |
| [Linear design refresh](https://linear.app/now/behind-the-latest-design-refresh) (March12,2026) | Quieter sidebar/icons, consistent header/action positions, restrained separators | Stable navigation and compact work context; content dominates, one indigo accent |
| [Linear Triage](https://linear.app/docs/triage) | Incoming actionable queue, responsibility and explicit triage actions | My Work groups real synthetic work items by stage, search/sort/savedviews and nextaction |
| [Attio record views](https://attio.com/help/reference/managing-your-data/records/create-and-view-records) | Table/list previews retain object context, unified record detail/activity | Queue selection preview, preserved filter/list position, adjacent candidate navigation |
| [GitHub reviewing changes](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/reviewing-proposed-changes-in-a-pull-request) | Per-change comments, viewed progress and explicit review submission | Round-specific issue/response/before/after units and explicit human verification; decision stays draft |
| [Dovetail highlights](https://docs.dovetail.com/help/projects/highlights) | Findings linked to highlighted original evidence | Immutable version+file+section+quote anchors, exact highlight and original text download |
| [Benchling review processes](https://help.benchling.com/hc/en-us/articles/39952320412685-Create-and-use-review-processes) | Named responsibility stages, sequential/parallel review, significant edits require renewed review | Distinguish model proposal, human verification and formal operation; preserve prior judgments when merely navigating versions |
| [Carbon data tables](https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines) | Table toolbar/search/filter/sort/selection; density sized to content | Compact operational rows, full long titles and separate reading density; candidate comparison without destructive batch actions |
| [Primer progressive disclosure](https://primer.style/product/ui-patterns/progressive-disclosure/) | Reveal details sparingly without losing context; describe toggles | Collapsible TOC/issue panel, real dedicated invitation/decision previews, no hover-only critical facts |
| [Fluent2 typography](https://fluent2.microsoft.design/typography/) | Platform-native typography, explicit hierarchy and contrast | System font with bundled Chinese fallback,14px controls,17px adjustable article reading, consistent lineheight |

The current Carbon page's embedded Storybook preview itself reported No Preview in the retrieved text; its documented behavior/sizing guidance was available. No claim its live demo was exercised. Product screenshots embedded in docs informed the patterns; actual Publishing OS renders are independently captured and reviewed. No source images or commercial assets copied into the app.

Four design skill roles: Frontend Design aesthetic coherence; targeted UI/UX Pro Max lookup returned focus and focus-obscuration rules; Impeccable context/craft floor plus final detector/render review; Web Design Guidelines current official command source checked during independent review. User's explicit goal and autonomy instruction settle surface purpose/composition; no additional design interview or arbitrary concept tournament was needed.

Implementation boundary: synthetic fixture through independent `/api/editorial-demo`, real per-user PostgreSQL draft/verification/view persistence. Existing authenticating/publishing/email code reused, formal outcomes remain blocked. Prototype state is not production academic evidence. Platform/font choices are designed for Windows/macOS/Linux but only actual executed browser/platform evidence may be claimed.
