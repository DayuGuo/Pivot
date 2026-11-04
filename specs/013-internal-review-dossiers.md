# 编辑内部审阅资料包：TXT/Markdown准备切片

日期：2026-11-03。状态：实现合同；本文件和静态来源映射不代表数据库、浏览器或完整验证已执行。实际结果由负责人记入PROGRESS.md。

## 范围与复用

承接[spec011](011-single-journal-review-pilot.md)的编辑录入缺口，先实现可恢复的内部资料准备：编辑本人录入 → 保存完整TXT/Markdown原件与有序作者资料 → 独立核对当前版本 → 刷新/服务重启恢复。仅使用合成或公开且明确获准使用的非保密材料。

本切片是正式投稿前的私有资料artifact，不修改Manuscript.author_id或workflow_kind，不创建作者账号、Manuscript、SubmissionWorkflow、正式任务、审稿轮次或编辑决定。不扩大author_draft权限。将来转换为正式稿件必须有明确动作、版本及hash映射，并重新执行正式投稿策略；本片没有该转换接口，也没有另一套出版状态机。

复用登录/CSRF、ensure_actor、Action Gateway的run_action与ActionReceipt、现有FileObject和私有CAS、追加审计。每次保存创建不可变版本；资料包本身仅保存当前指针、修订与归属。作者是版本内结构化快照，不是全局Person或账号。

上游比较模式见[数据库取舍](../docs/research/library/comparison/database-decisions.md)：DB03作者与账号分离、DB05原件与用途分离、DB06草稿与人工核对分离、DB07同刊复合关联和DB08幂等审计。这四张新表和本片权限全部是project_governance自有设计；OJS/Janeway固定源码没有被声称提供同名资料包表、相同核对机制或相同幂等保证。既有源码只作比较依据，不导入或执行其运行代码。

## 四张增量表

迁移：`13f17cad5064`，前序`12e06b9c4f53`。实现模块：HTTP兼容入口`apps/api/publishing/domain/dossiers.py`，持久模型已在spec018移至`apps/api/publishing/domain/dossier_models.py`，其余职责见[模块地图](../docs/development/module-map.md)。字段、类型、AST位置与命名约束在[来源映射](../docs/research/library/comparison/source-to-implementation.json)逐项绑定。以下内容是本片自己的字段合同。

**Dossier / publishing_dossiers**

字段：id、journal_id、created_by、revision、current_version_id、created_at、updated_at。

资料包归属创建者及期刊；revision从1开始，只在保存新版本时递增。UNIQUE(id,journal_id)支撑同刊子表；当前版本的三列复合外键绑定version.id/dossier_id/journal_id，并延迟到事务结束校验，使创建包与首版同事务完成。不得只凭裸version UUID指定另一包或另一刊的当前版。

**DossierVersion / publishing_dossier_versions**

字段：id、dossier_id、journal_id、version_no、data_json、file_object_id、file_name、file_media_type、content_digest、created_by、created_at。

version_no从1开始，UNIQUE(dossier_id,version_no)。同包同刊复合外键与同刊FileObject外键必需；UNIQUE(id,dossier_id,journal_id)供核对与对话引用。data_json是严格DossierData的完整有界快照。版本文件名和media type随本版保存，不从共享blob的首个上传名称推断。版本、文件引用与表单快照不可覆盖；保存后总是新版本，即使本次未上传文件，也只在验证旧原件后将其引用带入新版本。

content_digest使用确定性JSON SHA-256，输入为schema=`internal_dossier.v1`、完整data、原件file_sha256、filename和media_type；无文件时对应字段为null。数据库中的digest不替代下载和核对时实际读取CAS并检查字节长度/SHA-256。

**DossierCheck / publishing_dossier_checks**

字段：id、dossier_id、journal_id、version_id、content_digest、checked_by、session_hash、checked_at。

同包同刊版本三列外键；UNIQUE(version_id)保证每版只有一个人工核对事实。记录追加后不可改删；session_hash是注销后仍保留的证据字符串，不依赖可删除登录会话外键。核对提交必须来自当前创建者及当前有效editor/chief角色，携带当前revision、version_id、完整digest和严格布尔acknowledged=true；缺项、旧版本或原件校验失败拒绝。新版本没有旧版核对资格；人工核对只表示录入者检查了资料，不表示ORCID身份认证或科学结论正确。

**DossierTurn / publishing_dossier_turns**

字段：id、dossier_id、journal_id、version_id、user_id、question、answer、created_at。

同包同刊版本三列外键；question最多2000字符，answer最多6000字符。回合记录追加后不可改删，返回固定provider=rules。回答仅说明确定性缺项、资料状态和操作边界，不调用LLM，不声称阅读或理解全文，不修改资料、核对事实、正式状态或deadline。每条回合绑定原版，即使随后保存新版也不改写旧依据。

## 表单与原件合同

严格DTO拒绝未知字段。DossierData包含题名（500字符）、摘要（12000字符）、zh/en语言、最多12个关键词、有序最多20位作者，以及source_kind和source_note。source_kind仅synthetic/public_authorized；来源说明5—2000字符。创建还要求authorized_material=true，不能以默认值代替明确授权材料声明。

作者包含姓名、邮箱、ORCID、最多20项机构、通讯作者标记、贡献和最多1000字符source_note；此说明记录该作者、机构与所提供ORCID的资料来源。来源在每个版本内保存，不能推导为机构或作者身份已由外部核验。未提供ORCID保持null；现有ORCID归一化和格式检查不等于校验位验证、官方记录存在、作者控制iD或OAuth认证。本片不请求ORCID/DOI外部服务。

可保存不完整资料。核对前确定性检查：题名至少3字符、摘要至少40字符、至少1个非空关键词、正文原件、至少1位作者、恰好1位通讯作者；每位作者有姓名、非空机构与来源说明，通讯邮箱符合保守格式。该清单独立于正式作者投稿的原创性/版权/伦理等声明；不伪造作者声明，也不以补齐这些声明作为内部资料核对条件。

原件仅严格UTF-8 TXT/MD，实际字节1—1048576；沿用files.validate_upload的文件名、路径/控制字符和严格base64限制。名称不决定文件授权；CAS去重按journal_id+sha256，上传同hash并发冲突后重查。拒绝PDF/DOCX、超限和非法文本，不截断正文、不宣称病毒扫描或解析覆盖。失败回滚不删除可能由其他资料引用的CAS字节。

## 接口、权限与幂等

- GET `/api/dossiers`：当前创建者本人及当前期刊的资料列表；只读，不初始化业务。
- POST `/api/dossiers`：创建包与V1；输入request_id、题名、来源和authorized_material。
- GET `/api/dossiers/{id}`、GET `/api/dossiers/{id}/versions/{version_id}`：当前或指定历史版的严格投影。
- POST `/api/dossiers/{id}/versions`：expected_revision、完整data和可选原件；保存新版本并移动当前指针。
- GET `/api/dossiers/{id}/versions/{version_id}/file`：重新鉴权并读取实际原件，attachment、no-store、nosniff和SHA响应头。
- POST `/api/dossiers/{id}/confirm`：独立核对当前完整快照；不属于模型工具。
- POST `/api/dossiers/{id}/assist`：绑定当前revision/version的持久规则引导。

创建、保存、核对、规则回合全部通过run_action，在同一事务写业务、ActionReceipt和publishing.dossier_*审计。审计只留版本/修订等最小信息，不复制全文、作者邮箱或原始文件base64。保留publishing.前缀以沿用旧workspace的私人领域审计隔离。

访问必须同时满足当前有效会话/成员身份、同刊、created_by本人及当前editor或chief_editor角色；其他编辑和主编不因角色获得他人的资料。文件、旧版本、回合、旧request_id重放均重新检查同一归属。没有共享或转移所有权接口。创建目标ID由actor+journal+request_id确定，便于回执重放重新鉴权确切私有对象，不从客户端输入获取任意owner。

ActionReceipt按user+journal+request_id唯一，记录action+payload digest；相同请求恢复原响应，不重复新版本/回合/核对，同UUID不同内容409。不同UUID保存通过资料包行锁和expected_revision竞争，旧修订409。等待锁后重新ensure_actor；撤权后不能通过旧响应恢复资料。重复核对同版只保留一个事实，不能用旧版核对令新版已核对。

## 验收与边界

下列是运行时验收目标，不因本文件或静态映射存在而视为通过：

1. 实际创建、上传中英文TXT/MD、录入作者机构ORCID来源、保存V2；V1原件/表单/核对/回合不被改写，V2待核对；刷新与API/Web重启恢复数据库和CAS。
2. 同刊其他编辑/主编、author/reviewer/production_editor、跨刊、注销/角色变化账号，不能访问列表、详情、历史版、原件、规则回合或旧请求重放；旧正式投稿入口和author_draft权限保持不变。
3. 相同request_id重试一次创建/版本/回合事实；不同payload重用409；并发保存仅当前revision成功；同hash去重不混淆各版本名称或授予其他资料访问。
4. 缺必填、未明确核对、旧revision/version/digest、损坏CAS拒绝核对；核对无正式投稿、邮件、决定或作者账号副作用。
5. 直接SQL修改/删除版本、核对和回合，以及TRUNCATE历史失败；跨包跨刊关联失败；空增量可回退，有资料历史时拒绝破坏性downgrade。
6. 规则回合明确provider=rules、未调用模型；危险指令不触发核对或正式动作；旧回合仍指原版。
7. 离线研究门禁检查四模型字段/约束/迁移指纹，数据库与浏览器测试验证运行语义，最后执行scripts/verify.sh。报告必须区分静态绑定、实际数据库测试、浏览器测试和重启证据。

未包含PDF/DOCX解析、全文科学问答、检索/引用质量评测、外部身份核验、多人资料分派、正式投稿转换、真实邮件、LLM调用或部署。完整spec011及G1/G2/G3试点放行条件仍有效；此切片完成不代表真实试点准入。

2026-11-03文档/映射子任务已实际运行`python scripts/check-research-library.py`并退出0：29类357字段、28个domain Base类完整覆盖，4份additional contract及4份增量迁移指纹一致。新增四类34字段、11项命名约束逐项绑定13f迁移；原OJS39/Janeway35来源、18项历史基线及全部旧模型/证据条目保留。该命令仅作offline_static_evidence_only检查，没有重新执行既有53项组件测试，也没有在本子任务执行数据库、浏览器或服务重启。首次检查确实因raw DDL无法被既有AST门禁读取而失败；负责人将迁移改为显式Alembic表/列/约束声明后重新取真实指纹，复跑通过，未修改门禁。
