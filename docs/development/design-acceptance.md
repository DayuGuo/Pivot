# Design acceptance — 2026-11-02

Scope: Publishing OS login and editorial workspace, re-styled using the CURRENT official Hermes website's blue/white identity and current Desktop presentation. This is a product adaptation, not a claim that current shipping Hermes Desktop was installed or replicated pixel for pixel. Earlier v0.16 PR screenshots were excluded.

## Four-skill workflow

- Frontend Design: followed the pinned reference and product scene; chose original Publishing OS lettering, a cobalt shell, quiet editorial reading surfaces, flat results, and no copied third-party commercial fonts/artwork.
- UI/UX Pro Max: verified the installed searchable knowledge database. The broad query's marketing/purple recommendation was rejected; a narrower dashboard result still emphasized BI, so it did not replace the reference. The targeted touch query returned a directly relevant web target-size rule; 44px was chosen for mobile controls. Next.js search returned generic Server Action/cache advice, not an authorization to replace the deterministic FastAPI boundary.
- Impeccable: context engine succeeded. Product context was read without rewriting PRODUCT.md into Impeccable's own schema. After UI edits, the source detector ran once on apps/web/app/page.tsx and returned `[]` with exit 0. Source checks cannot establish rendered contrast or full accessibility compliance by themselves.
- Web Design Guidelines: fetched current official command.md, reviewed the changed UI source, fixed form names/email spellcheck, skip link/heading hierarchy, live-result semantics, error focus, branded text translation, explicit motion preferences, visible focus, long-text handling, and mobile control sizing. URL-level tab/detail deep-linking remains an existing prototype limitation, outside this appearance change; no claim of exhaustive guideline compliance.

## Independent visual review

An isolated Codex reviewer (not DeepSeek) inspected actual desktop/login/390px captures and source before detector findings were supplied. It found two material issues: an unnecessary MANUSCRIPT LIBRARY eyebrow and a mobile overview-pane toggle whose pressed state disagreed with visibility. Both were fixed. Mobile navigation targets and duplicate Mock badges were also refined while preserving honest disclosure.

A follow-up review of the named fixes returned `disposition: ship`: all scored fixes resolved, no regressions observed in the refreshed captures. This is a scoped verdict on those fixes, not a new whole-product or full accessibility certification. The reviewer did not rerun tests; the lead executed and inspected the results below.

## Actual verification

- `./scripts/start.sh`: successful; API, Web, PostgreSQL and Mailpit healthy.
- `./scripts/verify.sh`: exit 0; 52 Pytest, 5 Playwright; lint/typecheck/build/Ruff/DB migration and metadata drift checks passed.
- Playwright includes real editor creation/refresh/audit/logout, forbidden roles, bad password, CSRF/cross-site protection, desktop pane controls, mobile overview show/hide before selection, real mobile manuscript detail and close, no horizontal overflow.
- Actual Chromium platform font check: Noto Sans CJK SC Medium renders the Chinese login heading; Barlow Condensed is self-hosted for brand lettering.
- Screenshots: artifacts/editorial-workspace.png, artifacts/hermes-login.png, artifacts/hermes-mobile.png. Full log: artifacts/hermes-verify.log. Source detector result: artifacts/impeccable-source-audit.json.

DeepSeek live delegation remains pending a new unexposed credential. No real API call, email or production deployment occurred in this update.
