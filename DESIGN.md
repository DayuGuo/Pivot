# Publishing OS visual direction

Updated 2026-11-02. The user's latest instruction takes priority: reference the current Hermes Agent official website and its current Desktop presentation, not old PR screenshots. Keep Publishing OS as an editorial product, with its own identity and real workflow.

## Reference evidence

- Current official site: https://hermes-agent.nousresearch.com/ — fetched live with Firecrawl on 2026-11-02 (maxAge=0). The site uses a saturated blue visual world, white/blue contrast, condensed display lettering, fine rules and very small corner radii. Branding extraction reports primary #0000f2, background #0000c2, text #f2f2f2; automated extraction is approximate and must be checked against the rendered capture.
- Current homepage's Desktop image: https://web-assets.nousresearch.com/marketing/b6e121e2175ca968d0d566a80c335622b59ea6f9/assets/hermes-agent/desktop-preview.webp — visually inspected. It shows an open, flat conversation workspace, slim navigation and restrained controls. The asset itself says beta preview; it is evidence of what today's site displays, not proof of the exact current shipping Desktop build.
- Latest published release fetched from GitHub releases/latest: v0.22.5, published 2026-10-23. https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.5 . Release notes say the bundled Desktop installer did not change in that patch. Do not claim a pixel-perfect current Desktop replica.
- Current source design contract: https://github.com/NousResearch/hermes-agent/blob/main/apps/desktop/DESIGN.md — flat grouping, shared tokens, conversation first, restrained secondary labels. Source CSS uses accent #0053fd in the light Desktop theme, distinct from the marketing site's #0000f2.
- Earlier v0.16 PR screenshots are excluded as the visual authority for this redesign.

## Binding choices for Publishing OS

Mode: Operate. The editor must read, act and verify state. Apply the current website's blue identity to the shell and login, with quiet reading surfaces for the actual conversation. This is an adaptation combining the requested current brand direction and a usable editorial workspace; it is not a clone of Hermes assets.

Palette: cobalt #0000f2 for shell/primary actions, deep blue #0000c2 for hover/depth, paper #f8faff for reading surfaces, white #f2f2f2 for blue-surface text, ink #17171a for body copy, slate #555860 for secondary reading text. Status colors remain semantic and include text.

Typography: self-host Barlow Condensed 300/500 (OFL-1.1) through @fontsource/barlow-condensed 5.3.0, an openly licensed condensed sans for the Publishing OS display wordmark, using an appropriate system Chinese sans stack for editorial text. Hermes commercial Rules/Aeonik fonts and logo/artwork are not copied. Body 14–16px with comfortable measure; IDs and metadata are subordinate but legible.

Layout: compact blue sidebar, slim toolbar, flexible chat column and bottom composer, optional manuscript context pane. No decorative dashboard cards, nested panels, repeating explanatory captions or invented capabilities. The editor's existing task, status and audit remain real and discoverable. Preserve login, CSRF, roles, persistence, request idempotency and disabled email.

Controls: quiet borders, 3–6px radius, consistent SVG icons, keyboard focus, observable loading and errors, 44px touch targets on narrow screens. Reduced-motion preferences apply. Panel reveal/close is reversible and functional. No fake provider dropdown or simulated subagent activity.

Exact user rule: Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining.

## Skill responsibilities

Frontend Design sets intentional aesthetic direction within the pinned Hermes reference. UI/UX Pro Max supplies accessibility/layout knowledge, not a replacement brand recommendation. Impeccable provides the final refinement pass for this Operate surface. Web Design Guidelines supplies an independent pre-delivery UI audit. Skills never override product security, the user brief or real test evidence.

UI/UX Pro Max’s first broad query returned a marketing-oriented purple palette; it was rejected as mismatched to the pinned Hermes/workspace brief. Use its targeted accessibility and layout results only.

## Verification

Inspect desktop and 390px mobile captures after all changes; check typography, text/control contrast, overflow, keyboard focus, panel controls and complete task execution. Run repository verification plus focused responsive checks. Record actual results in PROGRESS.md. New DeepSeek credentials remain an external prerequisite for live delegated review; Mock results are explicitly identified.
