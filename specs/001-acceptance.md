# 001 验收记录

验收日期：2026-11-02。范围对应 001-editorial-intake.md，执行明细与限制见 PROGRESS.md。

| 用户验收项 | 实现与证据 |
| --- | --- |
| 明确一键启动，前后端正常 | scripts/start.sh；Compose 四服务健康；同源 /api/health 返回 PostgreSQL/Mock/禁发 |
| 数据库与迁移 | PostgreSQL 17 + Alembic 两个修订，初始空库执行成功；alembic check 无漂移 |
| 浏览器登录 | Playwright 编辑账号登录；错误密码无会话；注销撤销 |
| 对话真实创建 | Playwright 与 Pytest 断言 manuscript、pending 初筛任务、screening 状态、唯一 ID |
| 刷新与审计持久化 | Playwright reload 后按同一 ID 查稿件/任务/审计；数据库事务断言完整状态迁移 |
| 角色权限 | author/reviewer403；作者归属、跨期刊与会话/CSRF 用例；恶意模型工具拒绝 |
| 默认禁发 | EMAIL_SEND_ENABLED=false；即便设 true，禁发用例通过；无 SMTP 传输器 |
| 自动 E2E | 4 个真实 Chromium 场景通过，无 API mock；保留截图/HTML 报告 |
| 自动测试与静态检查 | 46 Pytest 通过，Ruff/ESLint/TypeScript/Next build/边界检查通过 |
| DeepSeek 路径 | 无新 Key，真实 API 与原生跨 provider 未验证；独立 CLI loopback 工具往返已验证，安全 API 替代接口有离线契约测试；详见专项报告 |
| 文档与代码一致 | README、PROGRESS、DECISIONS、架构/安全/产品/路线图与实际接口、命令、限制对齐 |

不得将这次验收扩大为完整出版系统、真实模型供应商兼容或生产部署验收。远端 CI 未运行。
