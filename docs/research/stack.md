# 实现用官方接口依据

调研日期：2026-11-02，以下官方页面均已实际读取。项目锁定版本见 uv.lock 与 package-lock.json，页面的 latest 不能代替锁文件。

- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)：使用依赖注入解析认证身份与拒绝请求；本项目选择可撤销数据库会话，不把示例 JWT 作为必需架构。
- [SQLAlchemy 2.0 事务文档](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)：应用命令同事务，测试使用外部事务/savepoint 隔离。
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)：schema 通过版本化迁移而非应用启动 create_all 管理；检查 metadata 漂移。
- [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)：事务级 advisory lock 为 actor/request 提供跨工作进程序列化，唯一约束作为补充保护。
- [Next.js 安装](https://nextjs.org/docs/app/getting-started/installation)、[CSS](https://nextjs.org/docs/app/getting-started/css)：App Router 与 Tailwind 集成，当前项目采用工作区结构。
- [Next CLI](https://nextjs.org/docs/app/api-reference/cli/next)：使用 next typegen 再 tsc，在无构建缓存的全新环境中也可类型检查；npm CLI 参数需经 -- 转发，开发/生产端口显式设置。

这些页面支撑技术选择；实际工程行为由本地构建、数据库、HTTP、Pytest 与 Playwright 验证，而非文档推断。
