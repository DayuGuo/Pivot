# Design skill workflow

Installed and checked on 2026-11-02 under `/home/dayu/.codex/skills`. Global skill installation was explicitly requested by the user. No existing skill or Codex global configuration was overwritten; no Impeccable hooks, permission bypass or live automatic apply were enabled. Skill discovery becomes available on the next user turn; their local entry points were directly inspected and tested in this session.

| Responsibility | Skill | Official upstream path |
| --- | --- | --- |
| Aesthetic direction | frontend-design | https://github.com/anthropics/skills/tree/main/skills/frontend-design |
| Design knowledge | ui-ux-pro-max | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/main/.claude/skills/ui-ux-pro-max |
| Refinement | impeccable | https://github.com/pbakaus/impeccable/tree/main/.agents/skills/impeccable |
| Acceptance review | web-design-guidelines | https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines |

Installation used the bundled skill-installer's GitHub downloader and copied complete skill directories. UI/UX includes its local Python scripts, reference documents and CSV knowledge base. Impeccable includes its references and official launcher; its checksum-verified engine initialized successfully. The four SKILL.md file checksums are recorded in design-skills.json; these are content checksums, not claims of a pinned upstream Git commit.

Use the exact reference and product constraints in DESIGN.md before applying any general recommendation. For this product, current Hermes official-site visual evidence outranks generic palette suggestions. An initial UI/UX broad search produced a mismatched marketing/purple recommendation, which was rejected; targeted UX/Next.js queries are used for implementation knowledge.

Project context remains PRODUCT.md, ARCHITECTURE.md, SECURITY.md and PROGRESS.md. Impeccable notes that PRODUCT.md is not in its proprietary newer record format; no automatic schema rewrite was performed. Its engine and Web Design Guidelines are review aids, not substitutes for real browser and workflow tests.

No paid model API is required by the four installed skill texts. DeepSeek delegated work is a separate, explicitly live model process. Never include secrets or private manuscript data in a design task.
