# 资料区模块维护地图

资料区继续采用模块化单体，接口和事务保持在同一应用内。分文件是为了隔离变更原因，不引入微服务、事件总线或另一套权限。

| 模块 | 修改它的理由 | 边界 |
| --- | --- | --- |
| `domain/dossier_models.py` | 持久字段、复合外键与不可变版本模型 | 不导入路由、模型供应商或执行数据库IO |
| `domain/dossier_schemas.py` | 输入类型、作者必填项、负责人显式true | 不依赖数据库/HTTP/模型；不认证ORCID身份 |
| `domain/dossier_access.py` | 身份/角色/期刊/所有者、版本和CAS完整性读取 | 不调用模型、不注册路由 |
| `domain/dossier_actions.py` | 幂等回执适配和业务审计 | 所有修改继续走core.run_action；不把确认交给LLM |
| `domain/pagination.py` | 有界游标与排序条件 | 位置不授予权限，SQL仍独立限定访问范围 |
| `work_limits.py` | 单worker重任务准入 | 正文/DB前429，无队列；不代替对象权限 |
| `domain/dossier_queries.py` | 列表读取、批量查询与所有者过滤 | 不按每份资料逐条查版本，不扩大主编访问范围 |
| `domain/dossier_views.py` | 版本/消息投影、历史来源标签 | 保留旧版引用，不能把旧核对移给新版本 |
| `domain/document_sources.py` | 原件/审批摘要、继承来源、页/段定位 | 不能给手改字段伪造原件证据，不依赖路由/模型调用 |
| `domain/document_candidates.py` | 自动提取与候选证据 | 只生成候选，不能最终确认 |
| `domain/dossiers.py` | 资料HTTP路由与兼容导出 | 组合服务；旧模块导入路径保持可用 |
| `domain/document_imports.py` | 导入/独立确认接口 | 审批路径、版本、digest和回执重放逐项校验 |
| `domain/dossier_chat.py` | 只读工具循环和对话接口 | 已发放来源、有限预算、提交前再授权；无危险工具 |

路径相对 `apps/api/publishing`。`packages/document_ingest`负责无服务凭据解析；`packages/model_gateway`负责受控传输，不获得业务权限。正式出版的core/stages/reviews/decisions/production仍独立；本轮未重写1423行core或460行部署管理器。

改表时同时改迁移、研究字段映射、不可变/跨刊约束测试；只移动文件时先比较字段和约束声明，再更新 `docs/research/library/comparison/source-to-implementation.json` 的路径/行号，禁止重写历史迁移或重置库。旧回执JSON是已持久化协议，不因整理代码而随意修改指纹算法。

验证入口：`scripts/check-boundaries.py`限制显式导入方向，`scripts/check-research-library.py`核对全部字段/约束，`scripts/verify.sh`跑完整回归。边界脚本只检查直接Python导入，不证明所有动态依赖或授权安全；真正权限和重放由PostgreSQL/API测试负责。

排查顺序：先用合成材料复现，检查具体版本、revision、request_id和来源hash，再修最小职责模块、追加失败回归。不要删除旧成功/失败记录，不能因模型偶尔给出合理答案而跳过后端契约。

尚存边界：dossier_chat仍复用正式chat的failure_code/sanitized_telemetry/tool_schema三个协议辅助函数；本轮没有触碰其正式流程，可在下一批抽成共享协议模块。客户端请求状态与部署管理器也按各自真实问题分批整理，不能把资料区拆分说成全项目已模块化完成。

前端`use-history-pages.ts`复用版本/导入分页，调用组件须随对象、版本/revision或核对快照变化重建；workspace保留路由/操作隔离，代理透传Retry-After并在缓冲上传前限重任务。spec019记录恢复协议和单进程范围。
