# 资料区模块维护地图

资料区继续采用模块化单体，接口和事务保持在同一应用内。分文件是为了隔离变更原因，不引入微服务、事件总线或另一套权限。

| 模块 | 修改它的理由 | 边界 |
| --- | --- | --- |
| `domain/dossier_models.py` | 持久字段、复合外键与不可变版本模型 | 不导入路由、模型供应商或执行数据库IO |
| `domain/dossier_schemas.py` | 输入类型、作者必填项、负责人显式true | 不依赖数据库/HTTP/模型；不认证ORCID身份 |
| `domain/dossier_access.py` | 身份/角色/期刊/所有者、版本和CAS完整性读取 | 不调用模型、不注册路由 |
| `domain/dossier_actions.py` | 幂等回执适配和业务审计 | 所有修改继续走core.run_action；不把确认交给LLM |
| `domain/pagination.py` | 有界游标与排序条件 | 位置不授予权限，SQL仍独立限定访问范围 |
| `domain/work_queue.py` | 期刊/归属限定的轻量稿件与本人待办列表 | 不复用材料/动作投影，不发放文件权限；较旧待办与显式有权对话目标不受最近200篇浏览窗口限制 |
| `work_limits.py` | 单worker重任务准入和通用API背压 | 重任务不排队；通用8进行中/16等待/2秒，DB与正文前受限等待；不代替对象权限 |
| `domain/dossier_queries.py` | 列表读取、批量查询与所有者过滤 | 不按每份资料逐条查版本，不扩大主编访问范围 |
| `domain/dossier_views.py` | 版本/消息投影、历史来源标签 | 保留旧版引用，不能把旧核对移给新版本 |
| `domain/document_sources.py` | 原件/审批摘要、继承来源、页/段定位 | 不能给手改字段伪造原件证据，不依赖路由/模型调用 |
| `domain/claim_review_models.py` | 不可变逐条人工反馈模型 | 独立于AI Answer及稿件批准 |
| `domain/claim_review_sources.py` | 历史Answer/版本/所有者/CAS来源校验 | 共享服务，不导入HTTP路由 |
| `domain/claim_review_queries.py` | 反馈历史分页/投影 | head和页同SQL快照；有界，不写入 |
| `domain/claim_reviews.py` | 人工反馈HTTP路由/网关 | 组合共享服务，无模型工具、旧回答不改 |
| `domain/claim_evaluation_package.py` | 独立评价的Unicode校验和白名单投影 | 纯函数，无网络/DB/业务动作 |
| `domain/claim_evaluation.py` | 私人独立评价下载 | 原版本/原件重验，无共享授权/回传写入 |
| `domain/claim_review_metrics.py` | 记录意见与AI判断的一致性 | 纯函数、排除不确定/未检查，不称科学准确率 |
| `domain/author_links.py` | 正向作者关联、局部重复项与原文跨度 | 纯函数，不授予身份或联网 |
| `domain/claim_support.py` | 有界AI原文支持检查 | 新上下文、同一期限；不注册业务工具 |
| `domain/document_candidates.py` | 自动提取与候选证据 | 只生成候选，不能最终确认 |
| `domain/dossiers.py` | 资料HTTP路由与兼容导出 | 组合服务；旧模块导入路径保持可用 |
| `domain/document_imports.py` | 导入/独立确认接口 | 审批路径、版本、digest和回执重放逐项校验 |
| `domain/dossier_chat.py` | 只读工具循环和对话接口 | 已发放来源、有限预算、提交前再授权；无危险工具 |
| `domain/dossier_export.py` | 精确版本的资料与缺项导出 | 当前所有者与原件重验，不导出私人问答/存储路径 |
| `domain/dossier_revision_models.py` / `dossier_revision_schemas.py` | 私人多版本核对包、三层人判和输入 | 不伪造正式投稿或轮次；模型不写人判 |
| `domain/dossier_revision_sources.py` | 两版来源、回复SHA、原件与引文 | 无模型/业务变更，历史不得转为当前批准 |
| `domain/dossier_revisions.py` | 内部核对路由、纯比较器、网关及审计组合 | 复核等待后授权，追加人判/前置头/同UUID恢复 |

路径相对 `apps/api/publishing`。`packages/document_ingest`负责无服务凭据解析；`packages/model_gateway`负责受控传输，不获得业务权限。正式出版的core/stages/reviews/decisions/production仍独立，不为资料整理重写正式状态机或部署管理器。

改表时同时改迁移、研究字段映射、不可变/跨刊约束测试；只移动文件时先比较字段和约束声明，再更新 `docs/research/library/comparison/source-to-implementation.json` 的路径/行号，禁止重写历史迁移或重置库。旧回执JSON是已持久化协议，不因整理代码而随意修改指纹算法。

验证入口：`scripts/check-boundaries.py`限制显式导入方向及HTTP路由互导，`scripts/check-research-library.py`核对全部字段/约束，`scripts/verify.sh`跑完整回归。边界脚本只检查直接Python导入，不证明所有动态依赖或授权安全；真正权限和重放由PostgreSQL/API测试负责。

排查顺序：先用合成材料复现，检查具体版本、revision、request_id和来源hash，再修最小职责模块、追加失败回归。不要删除旧成功/失败记录，不能因模型偶尔给出合理答案而跳过后端契约。

尚存边界：spec020已把sanitized_telemetry/tool_schema移到packages/model_gateway/protocol.py，正式chat保留兼容导出；dossier_chat仍复用正式chat的failure_code，未重写正式流程。客户端请求状态与部署管理器也按各自真实问题分批整理，不能把资料区拆分说成全项目已模块化完成。

前端`use-history-pages.ts`复用版本/导入分页，调用组件须随对象、版本/revision或核对快照变化重建；workspace保留路由/操作隔离，代理透传Retry-After并在缓冲上传前限重任务。spec019记录恢复协议和单进程范围。

登记评价增量spec023：evaluation_models定义两表；evaluation_sources组合原件/全文/引文材料，v1导出与v2登记共用；evaluation_access只做注册包访问/映射/最新记录；evaluation_protocol纯模板校验和分歧；evaluations组合HTTP与网关。前端evaluation-overview按需加载登记/汇总，evaluation-review位于独立路由右栏，中央对话持续可见；evaluation-types明确协议，requireLibrarySession复用会话前置检查。没有把独立评价回传并入ClaimReview或正式同行评审。

正式文档增量spec025：formal_document_models定义两表；formal_document_sources验证原件/提取/继承链并提供来源，formal_documents仅组合HTTP与Action Gateway。packages/document_ingest/locations为无DB的精确原文映射；revision_sources读取正式版本/作者可见要求，revision_compare保持无数据库动作权限。frontend formal-documents包含上传、待核对分页与独立核对三个组件，复用正式workspace/常驻对话；路由保留稿件和导入ID。evals/public_revisions的build/workflow/live是开发验收工具，不进入生产镜像，不获得邮件/关键决定模型工具。

原文内联定位：assistant/citation-source只做受控GET、原件/已核对文本双SHA及Unicode位置校验，载入前后核对用户/期刊/角色，卸载取消迟到响应。只读片段不进入浏览器存储，不调用模型、不确认业务；保留原件下载，PDF另有原页码链接。

兼容与恢复增量spec026（路径相对`apps/web/components`）：

| 模块 | 修改它的理由 | 边界 |
| --- | --- | --- |
| `browser.ts` | 安全UUID、可选存储、受控期限/取消、SHA、离开提示 | 不全局改浏览器原型，不读业务权限，不降级随机数或摘要 |
| `publishing/workspace.tsx` | 实际会话、路径/稿件上下文、GET取消、旧回执和未保存保护 | 导入ID从路由取，仍刷新实际权限；旧POST可能已提交，不自动重放 |
| `library/api.ts` | 资料请求/异常与受控期限 | 不替代资料归属/版本校验；未知结果沿原UUID主动恢复 |
| `editorial/reader.tsx` | 阅读位置、笔记与指针/捕获清理 | 不改变稿件文本、原文引用或正式编辑决定 |

后端正式`domain/chat.py`的历史权限复用仅限单次GET；任何模型等待后的检查仍独立查库，不能把这个优化复制成跨请求授权缓存。

spec027前端：`library/revision-check.tsx`维护材料包、三层人工草稿和已知/未知写入恢复，`revision-types.ts`定义协议，`metadata-export.tsx`保护下载前后身份；不把编辑的人判交给对话工具。`scripts/accept-vps-upgrade.py`只在随机隔离项目验证旧版升级与新卷恢复；`build-vps-app.py`绑定实际源码身份，`install-browser-deps.sh`对CI依赖安装设次数/时限，均不操作用户VPS。改变这些边界时运行相应有意义的失败回归，再统一verify。

可选`DocumentMetadata`属于版本data_json中的原文字符串，不是正式DeclarationsInput。空扩展在Pydantic序列化时省略，旧快照/回执不增键；`document_candidates`只接受类型标识和基金/声明完整区块，模型引文与纠正反馈限定实际发送窗口。`dossier_evidence`通用leaf索引、`document_sources`字段值匹配及`dossier_export`统一使用版本来源；前端evidence保留显式可定位字段白名单。新增字段时必须同时检查此白名单、来源和人工改值不能冒领原件的回归。
