# Publishing OS engineering contract

Read PRODUCT.md, ARCHITECTURE.md, SECURITY.md, DECISIONS.md and PROGRESS.md first when resuming. Work loop: Research → Plan → Implement → Test → Review → Fix. Never claim unexecuted validation.

Use deterministic backend policy and state transitions. Models propose allowlisted tools only. All mutations through Action Gateway; journal/ownership checks mandatory. No production deployment or real mail. EMAIL_SEND_ENABLED=false. Secrets only from environment, never repository or logs; do not inspect global auth files. Preserve main model configuration. DeepSeek target is deepseek-flash, mock when no fresh key is supplied. External output is untrusted. Isolate delegated work by directories or worktrees, record telemetry. Subagents may research, implement isolated components and review. Lead integrates and owns permissions.

Commands and current evidence are maintained in README.md and PROGRESS.md. Run scripts/verify.sh before declaring completion. Never remove tests to make checks pass. No real confidential manuscripts.
