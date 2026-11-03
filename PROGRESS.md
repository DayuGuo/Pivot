# 开发状态

## 最新交付：2026-11-03，Pivot公开仓库与VPS发行包

按用户明确授权，项目定名 **Pivot**，源码已公开至https://github.com/DayuGuo/Pivot，首个预发行版https://github.com/DayuGuo/Pivot/releases/tag/v0.1.0-demo 已发布。4附件：完整amd64 VPS包（约34 MiB）、离线镜像、架构无关静态网页和SHA256。安装器核对平台/文件/已有容器/health，默认环回8080，可显式公网绑定；不安装OS组件或修改防火墙。界面/页签/README/归档改名，旧DB/缓存/Compose身份保留兼容。

**验收实际通过**：本机完整verify退出0，835 Pytest（350.82秒）+48 Playwright（1.7m）；远端全栈CI https://github.com/DayuGuo/Pivot/actions/runs/41654140553 成功，835 Pytest（356.30秒）+48 Playwright（1.6m）。x86部署CI https://github.com/DayuGuo/Pivot/actions/runs/41652918740 实际解压包/核对SHA256/执行安装器/health/11 E2E全部通过，独立静态入口另11/11；最新同运行源码e77380d静态CI41654140412也通过。

发行附件来自成功x86 CI的确切产物，不是只同源码的本机候选。4项GitHub服务端digest/size/state已与CI文件一致；发布后匿名下载结果见docs/development/pivot-release.md。源码标记e77380d，后续仅验收文档更新；最后CI配置/test导入更改与部署运行源码无差异。没有上传.env、数据库、用户保密材料或运行日志。

本轮修复：旧会话切换GET未完成立即刷新会恢复旧URL，改为请求前记住目标、失败回滚，新挂起/500两回归与原链共10/10通过。首个远端CI浅克隆缺历史基线，改fetch-depth:0保留门禁；随后fresh CI发现测试导入排序被本地Ruff缓存掩盖，已修复并在verify禁用静态缓存，fresh103文件检查与相关模块4测试通过，最终CI整链成功。保留失败日志，不把它们冒称通过。

GitHub OAuth的workflow scope不足时使用已授权GitHub应用提交CI，再用同账号CLI传源码/二进制；没有修改全局认证或主模型配置。仓库/安装/限制见README、docs/deployment/demo-racknerd.md、docs/development/pivot-release.md。当前仍未连接用户RackNerd，不声称VPS实装/公网部署，邮件与重大决定权限不变。以下均为历史检查点。

## 最新交付：2026-11-03，本机GitHub展示Demo与安装包

用户将优先级调整为先展示思路、再细化真实业务；当前不连接RackNerd或创建GitHub公开仓库。spec012先于spec011。已交付同组件的`/demo`与独立静态首页，`./scripts/demo.sh`健康检查后访问localhost:3110。三栏对话、主/稿件会话、底部截止日日历、原文/作者/证据、资料/全文编辑、新稿录入、有效TXT/MD导入、刷新恢复与重置均可操作；全为明确合成/预设模拟/浏览器本地状态，无业务API、模型、邮件或正式决定。

独立UI审查发现并修复摘要复用截断正文、重复引用不定位和重复eyebrow；旧引用改文后不冒充当前依据，11场景回归通过，reviewer逐项resolved（ship仅这三修复范围）。安装审查发现原生ARM包不能冒称适合amd64 VPS，现`--image`显式生成linux/amd64标签/归档，支持ARM覆盖；架构与校验和复核resolved。静态包约4.7MB，amd64离线镜像约29MB。本机原生Nginx1.28.3初次空闲15.39MiB，不是VPS负载承诺。

完整verify最终**退出0：835 Pytest（326.79秒）+46 Playwright（1.6m）**，静态/迁移/漂移/准确前后端构建通过，1项既有第三方warning，日志artifacts/demo-full-verify-final.log。首次完整回归曾因并行Playwright清理共用trace路径导致1 ENOENT失败（835+45通过）；现静态测试独立目录后重跑全通过，保留失败日志。原生静态包11/11；补充导入/错误/重置/坏缓存/HTTP兼容实际通过，5视口无横向溢出且输入可见，pageerror/API请求0。

amd64包构建/加载/manifest通过，但本机ARM64缺x86仿真，运行报exec format error退出255，3112的11项均连接拒绝，**不能声称amd64运行或VPS安装通过**。已定义x86 GitHub CI加载实际离线包并验收，尚未远端执行。静态归档不依赖CPU架构，已完成本机展示范围；无公网部署、保密材料或真实模型/邮件调用，主业务栈/主模型配置未变。安装说明docs/deployment/demo-racknerd.md，完整交付证据docs/development/demo-delivery.md；下方为历史检查点。

## 最新计划：单人＋Codex单刊审阅第一阶段（2026-11-03）

新增specs/011-single-journal-review-pilot.md，按用户最新要求收敛为一本期刊、3—5编辑、20篇获准非保密/合成样本，完整资料录入→版本化文本解析→只读问答→真实原文/ORCID/DOI证据。暂缓日历、多身份、多刊邀请、注册及正式流程替换；保留现有v0.1与回归。按现有代码确认仍缺PDF/DOCX、编辑内部导入授权与只读入口，不能通过放宽作者私人准备稿权限解决。

规划8周（每周30—40小时，必要时延长），含100题固定评测与专业复核G1数据/权限、G2文件/证据、G3试点环境/恢复及复测，约5专业人日。现金中性约2.4万元，建议准备3万元；不含本人劳动，专业日费/云费为询价前预留。专业复核未进行，不将Codex自评冒称人工签收；仅本地可逆开发不需逐次审批，真实数据试点须通过复核和校方授权。

该轮只形成计划并同步文档入口，没有采购或实施新解析功能；既有verify实际退出0：835 Pytest（367.76秒）+35 Playwright（1.5m），日志artifacts/single-journal-phase-one-plan-verify.log。随后用户将展示Demo列为优先，见顶部。既有真实模型回环不证明本计划中的解析/外部核验功能完成。

## 最新设计修正：完整稿件与可核验证据驱动审阅（2026-11-03）

PRODUCT_DESIGN.md更新为v1.1：稿件对话默认是基于资料的只读审阅，不强制Agent。提前录入完整全文、附件、全部作者顺序/机构/ORCID等元数据，保留版本/hash、解析覆盖及缺项；原文定位与外部ORCID/机构/DOI链接分别标识来源、认证/匹配/可访问状态及获取时间。模型只能引用后台已登记证据，不虚构链接；作者提供、官方记录可访问、OAuth认证与具体条目属实分开，匿名与出域权限不变。稿件普通问答不推进状态；主动保存/准备操作后仍走负责人确认。

本轮只改Markdown设计及状态记录，未实现资料包、PDF/DOCX解析、只读模式或外部证据连接。已查阅ORCID官方登录/FAQ、Crossref、DataCite与ROR官方文档，未抓取作者资料、未执行真实OAuth/模型/邮件调用。文档本地链接与diff检查通过；依AGENTS运行既有完整scripts/verify.sh，实际退出0：835 Pytest（395.57秒）+35 Playwright（1.5m）、静态/边界/研究门禁、迁移/漂移、TypeScript/ESLint及镜像构建启动通过，1项既有第三方warning。日志artifacts/manuscript-evidence-design-verify.log；这些结果不证明新设计已经实现。

## 最新文档：核心产品设计与新增需求（2026-11-03）

已将历次问答和新需求整理为根目录PRODUCT_DESIGN.md：桌面左下角紧凑日历联动真实任务期限；开放主对话与稿件私有对话；单账号多期刊多职责；出版社范围本人全部审稿邀请；邮箱与ORCID注册/关联。明确账号/期刊角色/稿件分派分离、利益冲突和跨期刊匿名投影，日历不单独维护deadline副本；保留AI候选→动态补项→独立负责人确认及真实邮件禁发。ORCID官方登录/认证/邮箱可见性说明已查阅，未创建应用或执行OAuth。

本次只修改Markdown产品文档及入口链接，没有改运行代码/数据库/界面/登录或权限，不声称新增日历、多身份、跨刊邀请中心或注册已经实现。文档9个本地链接与需求覆盖检查通过；依AGENTS实际运行完整scripts/verify.sh，退出0：835 Pytest（364.58秒）+35 Playwright（1.4m），静态/边界/研究门禁、迁移/漂移、TypeScript/ESLint和准确镜像构建启动通过；1项既有第三方warning，日志artifacts/product-design-document-verify.log。这是既有产品回归证据，不证明新增设计已经实现；本轮没有真实模型/邮件/ORCID授权调用。

## 最新进展：2026-11-03，真实新领域对话与工具端到端通过

本轮未改代码的真实重跑6/6通过（29.155秒），此前503/读超时属于间歇性故障，不能推断为schema不兼容。已实际修复本地恢复缺口：同步worker内可取消AsyncClient，新领域从conversation入口共享60秒期限、read idle30秒/其他5秒；跨3轮最多额外1次相同推理重试，重验授权、不重复已执行工具。每attempt独立脱敏计量，无Mock回退。等锁后的apply与成功返回前再次检查期限，迟到候选整体回滚，不宣称数据库锁/COMMIT有硬取消。独立审查提出的该边界已修，新增14 API/12传输回归通过。

主服务已实际更新，三个关键模块源码SHA256与运行容器一致。修复后真实API **6/6，35.178秒**：创建私人稿件、保存未核实候选、读取真实文件随机标记并引用、识别编号/作者角色/步骤、UUID重放、prepare_review只留pending、危险发信/录用不改状态、未分派审稿人详情/chat404。实际Chromium通过主3100同源代理调用真实模型，文件/角色/状态引用、刷新恢复及危险请求拒绝均通过（7.402/3.460秒）；独立审核页对话可见、复核框未勾选、提交disabled、确认POST0、pageerror0、Mailpit前后0。报告artifacts/live-publishing-recovery-final.json及live-publishing-browser.json，详见docs/development/deepseek-recovery.md。

所列四份真实报告（包括未改代码基线及首次/最终浏览器）共16回合/31次供应商请求，返回usage输入156185/输出8835Token，成本null，本轮均无503/timeout；恢复是独立离线故障注入证据，不混称真实503后恢复。每回合数据库恰1Turn/Receipt/完成审计，遥测一致。两篇验收稿author_draft未冻结，人类确认/决定/预览均0；原23用户/49稿件/1437审计/95旧对话ID全部保留。无真实邮件、关键决定、公开发布或生产部署。主模型/全局配置不变，原生跨提供商子Agent仍未验证成功。

最终完整scripts/verify.sh **实际退出0：835 Pytest（371.58秒）+35 Playwright（1.4m）**，含同篇投稿→预审/分派→评审→修回/录用→校样/更正→鉴权本地预览。静态/边界/研究门禁、迁移/漂移、ESLint/TypeScript、浏览器脚本语法及准确前后端构建启动通过；1项既有Starlette/httpx warning。日志artifacts/deepseek-recovery-full-verify.log。本地单期刊合成v0.1的全部验收条件已满足，原生跨模型/多格式解析/真实邮件/公开出版/生产部署仍明确排除；最终Goal状态由工具确认。下方均为历史检查点，旧“未通过/主服务未更新/blocked”等不代表当前验收结果。

## 上一轮复核：2026-11-03，当时真实模型验收未通过

用户要求复核上一轮。主服务已实际升级到新领域F与失败诊断补丁，入口http://localhost:3100/publishing；API/Web/PostgreSQL/Mailpit均healthy，主库head为12e06b9c4f53且alembic check无漂移。下方“主服务未升级”等为历史检查点，不代表当前状态。整个Goal未完成，当前Goal工具状态为blocked；本次复核没有提前标完成。

新领域DeepSeek实际验收仍失败：请求ec75d599-ac2e-4ac7-afa1-d7ebf161e559第一轮成功（1523输入/17输出Token、12013ms），第二轮15367ms读超时；后续30秒read timeout仅进程内实验也遇503（362ms），并未修复可用性。运行服务仍15秒read timeout、3轮/8工具/2048输出限制。密钥能成功调用，不需要重发凭据；不能以旧/workbench或开发委派的成功代替新领域通过。报告artifacts/live-publishing-acceptance-final.json明确live_verified=false。

补齐失败诊断：全业务rollback后，重新检查原身份/会话/角色和上下文，再独立追加publishing.chat_failed；仅固定错误码和脱敏数值遥测，每轮清空并finally收集。新增8项失败审计回归，聚焦108项通过；独立作者代码审查未发现新的可复现P1/P2。最终完整scripts/verify.sh实际退出0：**809 Pytest（346.77秒）+35 Playwright（1.4m）**，静态/边界/研究门禁、迁移/漂移、ESLint/TypeScript及准确API/Web镜像构建启动通过；1项既有第三方Starlette/httpx warning。日志artifacts/v01-review-final-verify.log，未删除旧测试。

主库实际保存检查：升级前23用户/49稿件/1437审计/95旧对话ID全部保留，现25用户/49稿件/1452审计/95旧对话。最近两次失败没有PublishingChatTurn或ActionReceipt；EMAIL_SEND_ENABLED=false，Mailpit总数0。证据artifacts/v01-main-post-update-review.json与v01-review-runtime.json。未发真实邮件或作关键决定。README、架构、安全与路线图已纠正过时状态；详细复核见docs/development/v01-code-review.md。

## 活跃 Goal：OJS / Janeway 数据库研究与 v0.1 完整样本

### F 离线检查点已验收，Goal进入本机集成/真实模型验收

spec010已实施实际校样包/作者回应/鉴权本地预览：FileObject独立于冻结VersionFile，作者逐包确认或要求更正，保留历史且新文件不同于前包；最终preview绑定同包approve响应和制作人确认，status仍accepted，未正式发表。迁移12e06b9c4f53已在独立55433实际升级/check。53组件（37.10s）、10独立安全（33.75s）及实际服务/浏览器链通过；权限回执漏洞先复现再修，原测试未改。来源门禁25类/323字段、148增量列、122命名约束、3迁移/合同、24触发器绑定实际通过，20复制库实验符合预期。

最终完整 `scripts/verify.sh` **实际退出0：797 Pytest（360.97秒）+35 Playwright（1.4m）**，含全部旧回归、11项新UI延迟/权限/角色/未保存恢复回归和实际五角色全链（30.4秒）。Ruff/format、边界、研究门禁、迁移/漂移、ESLint/TypeScript及准确API/Web镜像构建启动全部通过。日志artifacts/v01-f-full-verify.log；1项既有第三方warning。桌面/390px预览实际查看，无overflow/pageerror，正文script为纯文本未执行。

回应用户代码复核时发现并修复历史并发丢消息、迟到200覆盖403、角色变化旧回合、账号入口未保存保护、审核重试、启动空env覆盖等；详见docs/development/v01-code-review.md。主库备份副本已完整迁移演练，原49篇稿件、23用户、1437审计和95旧对话ID保留且无伪审批；19项旧harness临时授权已归档撤销，未删稿件/旧审计。当前主服务还未升级，新领域真实DeepSeek仍待验收，Goal仍活跃。

真实DeepSeek安全API文档子任务已实际1/1通过：561/933 Token、7263ms、成本null，lead修4处表述1轮；不是原生跨模型成功。报告docs/development/v01-deepseek-delegation.md。新启动器保护现有live runtime环境，13个模拟安全检查通过；下一步实际一键本机更新、供应商新领域工具回环及最终文档一致性。无真实邮件或生产部署。

### E 检查点已验收（Goal仍活跃）

spec009已接通编辑建议/主编决定/匿名Release/正式RevisionRequest，独立worktree交付模型迁移与UI，lead整合确定性服务与权限。minor逐条追溯修回到本轮固定版本，major需新轮；共享正文须主编人工检查匿名性，录用绑定制作负责人快照。独立55433已实际升级11d95a8b3e42并check无漂移；17输入约束+4真实PG生命周期+9独立安全测试通过。包括两次minor→V3接受、major R1V1→R2V2→minorV3接受、chief改变建议后reject、跨稿报告拒绝、角色撤权及真实response字节篡改不提交。

完整 `scripts/verify.sh` **实际退出0：686 Pytest（251.01秒）+24 Playwright（1.2m）**，全部旧回归保留，迁移/结构漂移、Ruff/format、依赖边界、ESLint/TypeScript及准确API+Web镜像构建启动通过。日志artifacts/v01-e-full-verify.log。E独立模型44项（26.76秒）含完整新head metadata对比、不可变/跨稿/同版本人类证据及deferred原子bundle。最初raw-model实验发现chief/production历史作者邮箱未link时DDL不拦，而API已拦；已补SQL并在隔离public仅CREATE OR REPLACE对应函数、不删数据/不降级，后续完整回归通过。具体sha见artifacts/v01-e-guard-refresh.json。

聚焦完整浏览器先通过21.4秒；全量中同篇链22.7秒：作者→预审/分派→评审→编辑建议→主编minor/匿名分享→作者V2/声明/response→编辑复核/新建议→chiefaccept→production实际待办。首轮最后两个合法链接导致strict locator失败，现限定左侧本人任务唯一链接后通过，没有删断言。四张桌面/390实际打开复核，对话输入可见、无overflow/pageerror。研究门禁随后独立扩展并实际通过22类/289字段、114个D/E列/93约束、两迁移和2合同指纹；10项复制库实验1正+9负均符合预期，应用代码无后改。证据artifacts/v01-e-research-gate.json和E-research-gate-*。

F规格/制作来源取舍为设计，尚未实施；Goal不完成。下一片实际校样、更正循环、作者确认与鉴权本地预览；随后新领域真实DeepSeek/安全API委派验收及保护主服务环境的本地集成。主3100/8100仍为旧live基线，当前新领域只运行于隔离13100/18100；无真实API/邮件/主库修改。

### D 检查点已验收（2026-11-03，Goal仍活跃）

真实主链继续到：责任编辑确认站内轮次/邀请→审稿人仅见匿名摘要→本人声明无冲突并接受→固定匿名材料/本人草稿→AI未核实文字候选→本人独立确认提交报告→编辑明确结束本轮→编辑汇总建议。拒绝邀请不等于拒稿，重邀保留attempt；报告草稿不向编辑/作者公开，已交报告仍不自动给作者。新角色账号 reviewer2@publishing.test / Reviewer2Demo2026! 为纯合成候选；原账号保持。

迁移10c84f7a2d31已在独立55433升级/漂移验收，4新模型+typed Assignment/WorkItem/VersionFile复合键，初始化seal、不可变文件/表单、邀请/报告/确认强绑定及deferred一致性。50项独立组件含双连接seal/append竞态通过，随机schema已清理，不动public业务记录。研究门禁现19类/248字段、73个D列、57项约束与官方来源绑定；未执行上游代码。

最终完整 `scripts/verify.sh` **实际退出0：612 Pytest（145.91秒）+24 Playwright（1.0m）**，迁移/漂移、研究门禁、Ruff/format、ESLint/TypeScript、准确API+Web镜像构建/启动通过。日志artifacts/v01-d-full-verify.log；唯一第三方Starlette弃用warning。浏览器同篇走author→editor→chief→editor→reviewer→editor，含真实下载匿名文件名、AI不选推荐、报告保存/刷新/本人提交/结轮撤权；新Goal仍未完成。

细粒度权限同时保护模型、消息历史、幂等重放与独立审核快照。不能用“还可看邀请摘要/预审稿件”恢复已撤销全文/私密报告权限；同version原稿ID不能绕匿名白名单。独立审查实际复现的请求锁等待重放与稿件锁等待终答两处竞态已修，新增6例全通过；历史proposal GET/receipt也重验内容权限。最近6条授权消息可进入模型记忆，权限增加保留安全摘要历史，收窄屏蔽不再授权内容。Node代理给新chat75秒预算并保留下载hash头。所有新增供应商测试均Mock/离线，无新真实API调用、发信、主库迁移或生产部署。

下一片E：编辑建议、主编独立确认决定/匿名作者反馈、作者修回及新版本复核；之后F制作/作者校样/本地鉴权预览与新领域真实DeepSeek验收。主服务仍是旧真实模型基线，当前新领域只在独立13100/18100运行。


### C 检查点已验收（Goal仍活跃）

规范化主链已实际贯通：作者投稿→材料预审→真实报告人工复核→匿名材料筛选→主编范围→责任编辑分派→质量评估→寻找审稿人。每关独立负责人确认；退回生成V2、重置声明、保留V1和旧检查，并从预审重做。历史共同作者作为自审冲突信号，绝不按邮箱授予访问。

新工具可读取本稿实际私有复核报告、保存未核实检查意见候选；不能选择检查结果、写人工声明或确认。采用候选也不代勾。新增完整三角色浏览器链含这项断言。最终隔离 `scripts/verify.sh` **退出0：532 Pytest（58.27秒）+24 Playwright（56.7秒）**；Ruff/format、研究门禁、TypeScript/ESLint、迁移/漂移、API+Web准确镜像构建及启动通过。日志artifacts/v01-c-full-verify.log。独立C安全9项通过；没有未修复已证实P1/P2。所有模型传输为Mock/离线脚本，本片没有真实供应商验收。

验证Harness现在会在任何数据库写入/构建前拒绝已运行的live Compose API；实际对主服务退出1保护通过（artifacts/v01-live-stack-protection.log），不会重建成Mock。独立Mock栈会重新构建并启动API/Web后再跑浏览器，避免验收旧镜像。主库/真实模型进程未更改。浏览器修复已填textarea标签混入值的问题。D/E设计研究已保存review-revision-design.md；实际邀请/报告/决定/修回/制作/预览尚待实施。


2026-11-02 新 Goal 已建立，持续执行中，**尚未完成整个目标**。恢复先读 goals/publishing-v0.1.md、specs/007-* 和 docs/research/library/README.md。分支 codex/publishing-v01；旧版已验收基线354c930保留。

已实际归档 OJS3.5.0-6/其PKP固定gitlink 与 Janeway1.8.4 的官方源码/指南证据、字段表、许可/摘要；研究门禁验证39+35来源及18基线文件，59表/412字段与61模型/553字段为静态索引，非上游运行数据库导出。比较取舍见 docs/research/library/comparison/database-decisions.md。

A/B 已写入真实领域基础、13张规范化子表、作者/版本/实际UTF8文件、任务/分派/不可变提案与独立人工确认、同源对话工具及常驻三栏新路由 /publishing。迁移f8a12d4c6e90在独立55433数据库upgrade/check通过，24项随机schema迁移/回退/冻结约束重演通过；旧UUID/历史不变，真实新投稿出现后拒绝破坏性降级。C的CheckRun与09b73e6a1c22已接通并完成本节最终验收。

新A/B接口、文件安全与聊天测试已运行；基础全后端一轮426通过，随后安全/聊天聚焦35通过，最终完整验证仍待执行。浏览器首轮暴露旧并发测试给共享作者留下多期刊授权；已仅撤销隔离库4项Pytest临时授权、保留稿件/审计，并修复测试finally清理。其他修复：旧审计隐藏私人领域事件、准备/确认检查实际CAS字节、锁/模型等待后重新授权、人工默认值候选保护、聊天历史及重放访问依赖检查。对应回归继续运行。

A/B检查点最终完整 `scripts/verify.sh` 已实际退出0：**508 Pytest（40.41秒）+24 Playwright（含新增作者→编辑真实投稿链）通过**；研究门禁、Ruff/format、TypeScript/ESLint、PostgreSQL迁移/漂移与Docker生产构建均通过。日志 artifacts/v01-ab-checkpoint-verify.log。另四条独立数据库连接的相同人工确认重试只生成一条确认、一次修订和一项预审待办；24项基础迁移演练通过。已修下拉框标签语义、浏览器脚本的历史对象定位和登录等待；保留旧记录未清空数据库。此检查点仅证明A/B及C独立组件，不代表完整v0.1已完成。

当前主服务仍为此前真实模型版本，**新领域尚未部署至主库或进行真实供应商验收**。新代码在独立Mock验证栈18100/13100运行，上传用独立持久volume。新UI静态检查通过，浏览器交互和全量verify尚待最终证据。后续站内邀请/评审/修回/决定/制作/本地预览仍未实现；不得从已写表/页面推断已完成。邮件始终禁用，无生产部署。


更新：2026-11-02。首个编辑初筛纵向原型已实现并通过本地自动化验收。未真实发信、未生产部署、未更改主模型或全局 Codex 配置。

## 当前验证：真实DeepSeek对话与受控工具已通过

用户在本机安全配置有效密钥后，实际DeepSeek deepseek-flash模型回环成功。最终live验收6/6通过（26.719秒）：主编角色/ENV-2026-0129-v3状态与原文引用、问题依据、UUID响应/审计幂等、危险发信/正式录用指令明确拒绝且工作区不变、作者/审稿人403、私有邀请主题/正文真实保存与人工收件人保留。Mailpit前后0，正式状态未改变；未发信/未作关键决定。

实际Chromium主界面对话也使用真实DeepSeek，工具/引用/角色标记和刷新恢复通过；见artifacts/live-deepseek-browser.json/.png。最终live报告artifacts/live-model-acceptance.json：10次供应商请求、输入43694/输出3543Token，成本未知为null，仅该轮统计。先前401凭据已解决，历史失败未当作成功。

实际调用修复了自由终答丢引用与引用ID漂移：required工具选择、最终回合respond、后端来源枚举/无来源空数组、原预算内一次来源纠正；坏来源仍拒绝，草稿最终校验后才提交。独立代码复审通过；最终隔离 `scripts/verify.sh` 实际退出0：322 Pytest（28.28秒）+23 Playwright（45.4秒）、静态检查、迁移/漂移和生产构建通过，1项第三方弃用警告。日志artifacts/live-supplier-final-verify.log；无新迁移，head e7b24c91a603。配置/平台限制和运行命令见docs/development/live-editorial-model.md；当前运行时真实供应商验证不代表原生跨提供商Codex子Agent已验证。

## 当前更新：真实模型与安全工具循环

按spec006实现独立DeepSeek工作台adapter、角色/期刊/版本上下文、最多3轮/8工具/1草稿的真实工具协议。草稿整轮成功后才提交，等待期间复核人工修改和权限；来源ID、请求幂等、审计与Mock历史供应商标记保留。邮件批准/发送、重大决定均无Agent工具。安全本地启动器就绪，不落盘密钥。

以下为接入代码初次交付的历史证据；当时真实DeepSeek调用0、未提供新凭据。当前真实验收见上节，聊天公开的旧密钥未使用。最终 `./scripts/start.sh` 与 `./scripts/verify.sh` 退出0：**316 Pytest（27.91秒）+23 Playwright（49.8秒）通过**，Ruff/format、依赖边界、ESLint、TypeScript、迁移/漂移、Docker生产构建通过；1项第三方弃用警告。新增47离线传输、35真实PostgreSQL工具循环安全集成、7启动器测试及2浏览器UI契约场景；日志artifacts/live-model-final-verify.log。审查补强明确目标/否定指令、等待期间人工修改/撤权和固定执行边界。无新迁移，head仍e7b24c91a603。只读smoke实际退出2并记录live_verified=false/fresh_live_model_configuration_required，不把假HTTP回环冒称真实供应商验证。详细启用、平台限制及委派记录见docs/development/live-editorial-model.md和live-model-delegation.json。

## 最新用户修正：对话为主，材料随行

按spec005将原弹出助手改为四页常驻主体对话，左任务/中对话/右材料；自动白名单筛选与导航、真实私有聊天历史、当时上下文快照、原文引用和安全邀请/决定草稿准备已接入。新增回合表e7b24c91a603，旧真实投稿链保留。人工未保存内容有准备前同步及冲突候选恢复；纯查询不因未完表单阻断。

最终实际运行 `scripts/start.sh` 和 `scripts/verify.sh`：**227 Pytest（22.39秒）+21 Playwright（46.6秒）全部通过**，含45个聊天API用例及6个新增对话浏览器场景；Ruff/format、依赖边界、ESLint、TypeScript、PostgreSQL迁移/漂移、Docker生产构建通过。另13个工作台场景阶段复测通过（38.2秒）。日志artifacts/conversation-final-verify.log；迁移head e7b24c91a603。1项第三方Starlette/httpx弃用警告。实际修正CSS200输入/发送裁切、窄屏正文不足、人工草稿保存竞态和字体偏好恢复时序；20种页面布局检查正文与发送按钮实际可见区域。仅Linux Chromium及CSS缩放，未实测其他OS/浏览器/原生缩放/手机软键盘。交付与限制见docs/development/conversation-first-delivery.md，委派证据conversation-delegation.json；截图artifacts/conversation-*。

## 已完成Goal：任务工作台、长稿阅读、选人及修回核验

已读取用户目标文件goal-objective.md并按spec004增量开发。新路由/workbench保留原投稿/邮件链，四页共用6篇合成稿件，其中主案例3个版本、2轮修回、多审稿人、长中英文正文与历史。私有草稿、阅读位置、候选选择、核验、AI建议处置及常用视图经真实API/PostgreSQL保存；迁移c81b8c41b016只增加两个隔离状态表，未修改正式出版状态机。

所有指定参考的9个官方URL已实际读取，取舍见docs/research/workbench-design.md；统一规范已补入DESIGN。独立审查发现并修复版本阅读误删核验历史、失败笔记导航恢复及局部滚动引起外层空白；浏览器首轮暴露代理缺PATCH/PUT及下载头，现已补齐。原型不发送、不取消评审、不发布正式决定、不改变关键权限，模拟材料有明确披露。

最终 `scripts/start.sh` + `scripts/verify.sh` 实际退出0：**182 Pytest +15 Playwright**（原8+新7），Ruff/format、依赖边界、ESLint、TypeScript、迁移/漂移、Docker生产构建通过。日志artifacts/workbench-start.log、artifacts/workbench-final-verify.log；head c81b8c41b016；1项第三方Starlette/httpx弃用警告。段落级恢复、字体18下刷新定位和失败草稿经过无关保存后恢复均实际通过。12个四页桌面布局（1366/1440/1920）无横向溢出，主要主题文字色对表面最低5.55:1；实际Linux Chromium，含深色/系统、键盘、CSS200%与窄屏。其他OS/浏览器、原生工具栏缩放未实测。截图、来源、模拟/待接入项及精确审查范围见docs/development/workbench-delivery.md；委派记录workbench-delegation.json不可用Token/成本/耗时留null。不得把新界面推断成spec003完整业务已实现。

## 最新规划：数据库、三栏任务工作区与负责人审核

用户本轮要求已固化到 specs/003-editorial-workflow-and-assisted-intake.md：核心步骤与标签分层、逐关负责人、版本/作者/文件/分派/任务/检查/提案/确认/轮次实体、约束索引、并发幂等、角色待办排序、AI提取与缺项表单、独立审核页、历史迁移和分批验收。复核了现有models/workflow/policy，记录了单status、必填editor_id、单author_id、任务唯一键和单role的结构缺口。实际读取OJS/Janeway官方工作流资料，来源记录在规格末尾。

PRODUCT、ARCHITECTURE、SECURITY、DESIGN、DECISIONS与ROADMAP同步区分“后续设计”和“已运行能力”。本轮只更新规划文档，没有修改运行代码、数据库schema或权限，不声称三栏/作者辅助投稿/新审核页已实现。下一次优先A+B纵向切片；现有完整原型验收见下方。

本轮文档变更后已实际运行 `scripts/verify.sh` 并退出0：145 Pytest、8 Playwright、Ruff/ESLint/TypeScript、PostgreSQL迁移/漂移检查与Docker生产构建通过。日志 artifacts/workflow-planning-verify.log。这仅证明现有原型回归通过，不证明新规格中的后续功能已实现。

## 当前更新：截图工作台、真实会话与邮箱绑定

本节覆盖下方历史蓝色外框设计。视觉权威改为用户直接提供的 Hermes 工作台截图，详见 DESIGN.md 和 ADR-011。浅灰侧栏、白色对话阅读区、细蓝色选中线、底部输入框、可收起侧栏/手机抽屉均已实现；真实会话支持新建、搜索、切换、URL恢复和草稿隔离。历史消息已迁移到真实会话，回执保持旧请求重试兼容。

邮箱配置支持自建 SMTP、Gmail、Outlook，具备持久状态、验证、断开与重新绑定审计。凭据只读服务器专用环境变量，并校验期刊所有权。探测与发信分离，无发信能力。实际 Mailpit EHLO 验证通过，捕获消息总数为0；真实 Gmail/Outlook 和远程 SMTP 无授权凭据，未验证。OAuth consent/refresh 与收件箱尚未实现。

最终完整 `scripts/verify.sh` 退出0：**145 Pytest + 8 Playwright**，含56适配器用例及37新增会话/邮箱API用例；生产容器构建、Ruff、ESLint、TypeScript、迁移/漂移通过。实际 head 为 a99d14733f66，包含旧消息回填。日志 artifacts/final-screenshot-start.log、artifacts/final-screenshot-verify.log，JUnit artifacts/pytest.xml。Pytest有1项第三方 Starlette/httpx 弃用警告，不影响通过。

独立后端安全审查未发现需处理的实质问题。独立视觉审查确认布局与配色，要求统一实际中文字体；已增加自托管 Noto Sans SC Variable 5.3.1（OFL-1.1），最终截图复核对这项修复给出 scoped ship。Chromium CDP实际报告品牌、会话名、输入区使用 NotoSansSC-Thin 的自定义变量字体（isCustomFont=true）；不是从CSS声明推断。最终截图 artifacts/hermes-desktop-chat.png、artifacts/hermes-mobile-chat.png、artifacts/hermes-mobile-drawer.png、artifacts/mail-settings.png 和 artifacts/mail-setup-guide.png。没有真实云账号或DeepSeek供应商调用、邮件发送或生产部署。

## 后续界面与设计 Harness 更新

- 用户要求参考新版 Hermes Agent、与当前官网相近，明确排除旧版风格。已实际读取 2026-11-02 当前官网、官方桌面预览、源码设计文档和最新发布 v0.22.5；旧 v0.16 PR 截图不再作为视觉权威。当前官网的蓝白视觉被适配为蓝色产品外框/侧栏、安静阅读区、自托管 Barlow Condensed 字体；没有复制 Hermes 商标、商业字体或插画。证据与限制见 DESIGN.md。
- AGENTS.md 原样加入用户规则：Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining. 已删除重复标语、无用英文 eyebrow 和多余说明。
- Frontend Design、UI/UX Pro Max、Impeccable、Web Design Guidelines 四个技能已从官方上游安装至全局技能目录。UI/UX 数据库检索、Impeccable context 和检测器已实际运行；没有启用 hooks/live 自动应用或改写 Codex 全局配置。来源和内容校验见 docs/development/design-skills.md / .json。
- 新增可显隐的稿件上下文面板和响应式状态；独立 Codex 视觉审查发现的残余英文标签及手机面板显示不一致已修复，手机导航点击区域达到 44px。独立复查对列出的修复给出 scoped ship；验收范围与限制见 docs/development/design-acceptance.md。保留真实状态、角色、Mock 披露及邮件禁用提示。
- 最新完整验证：**52 个 Pytest（39 API + 13 模型/CLI）、5 个 Playwright**通过；Ruff、ESLint、TypeScript、Next.js 构建、PostgreSQL 迁移和漂移检查通过。日志 artifacts/hermes-verify.log，截图 artifacts/editorial-workspace.png、artifacts/hermes-login.png、artifacts/hermes-mobile.png。Impeccable 源码检测实际返回空数组；这不等于浏览器可访问性全面认证。
- DeepSeek 新增无回显本地启动器、具体的公开/合成 UI 审查任务文件、CLI --task-file 及 6 个边界测试。聊天中提供的凭据未使用、未写入文件或日志；没有新的环境凭据，因此真实供应商调用仍为 0，仍不可声称原生跨 provider 成功。

## 初始交付基线（4dfbc2d）

| 项目 | 实际结果 |
| --- | --- |
| 一键启动 | `./scripts/start.sh` 实际成功；PostgreSQL、Mailpit、FastAPI、Next.js 均 healthy |
| 真实数据库与迁移 | PostgreSQL 17；Alembic `0002_audit_guards (head)`；`alembic check` 无 schema 漂移 |
| 完整验证脚本 | `./scripts/verify.sh` 退出 0；日志 `artifacts/verify.log` |
| 后端与模型契约 | Pytest **46 passed**：39 个 API/业务/安全用例 + 7 个网关离线契约用例；JUnit `artifacts/pytest.xml` |
| 浏览器 | Playwright Chromium **4 passed**，运行于完整 Docker 产品；编辑登录/真实创建/刷新/审计/注销，作者与审稿人 403，错误密码，CSRF/跨站登录保护 |
| 静态检查 | Ruff check + format，模型依赖边界，ESLint 与 TypeScript 全通过 |
| 前端工件 | Next.js 生产构建通过（本机与 Docker）；清空本机 `.next` 后 `next typegen && tsc --noEmit` 也通过 |
| 生产依赖 | `npm audit --omit=dev` 为 0 vulnerabilities；开发工具链仍有 16 项 moderate 的 minimatch 传递依赖公告，未盲目执行破坏性降级 |
| 独立 Codex 协议实验 | CLI 0.165.0 + 隔离 CODEX_HOME + loopback 假 Responses 服务，2 次模型请求、真实无副作用 shell 工具执行及结果回传；`evals/model_probe_result.json` |
| 真实 DeepSeek | **0 次调用，未验证**：未提供新 DEEPSEEK_API_KEY；原生跨提供商 Subagent 也未建立可靠验证。已保留可测试的安全 API 委派器与报告 |
| 邮件安全 | 无 SMTP 外发传输器；默认 false，环境强行 true 仍返回 403。完整快照绑定、修订撤销、跨期刊拒绝及数据库不可篡改测试通过 |

浏览器报告：`artifacts/playwright-report/index.html`；截图：`artifacts/editorial-workspace.png` 和 `artifacts/editorial-intake.png`。测试证据为本机实际结果；GitHub Actions 工作流已定义，远端运行未触发，不声称远端 CI 已通过。

## 已完成实现

- 官方研究：OpenAI Goals/Subagents/Harness、Spec Kit、Anthropic 长周期 Harness、OJS、Janeway、Craft Anything、DeepSeek 官方集成，来源和取舍在 docs/research。
- 八个模块边界；Next.js/React/TypeScript/Tailwind、FastAPI、SQLAlchemy、真实 PostgreSQL、Alembic、Docker Compose。
- Bootstrap 真实写入期刊、四类用户、成员角色和审计；命令以事务完成稿件创建、draft → submitted → screening、编辑待办、对话、审计和幂等回执。
- 随机可撤销会话、scrypt、CSRF、期刊/角色/归属检查、数据库审计追加保护；四连接并发重复请求只创建一次，失败不留下部分稿件。
- UI 可操作登录、对话、快捷指令、稿件查看、审计、刷新与注销；明确 Mock 标记，无未实现业务假按钮。
- 安全模型 API 委派、UUID 隔离草稿、成功率/Token/成本/耗时/返工遥测；Mock 样本 1/1、0 Token/$0，未知真实成本保留 null；Ollama/vLLM 仅接口未实测。
- setup/dev/start/stop/verify、本地浏览器证据与 CI；Git 仓库保存可恢复的产品、架构、安全、决策、进度与规格。

## 本轮修复与审查

独立审查发现并修复：邮件禁发入口缺期刊检查、邮件快照类型约束不足；PostgreSQL JSON 比较改为 jsonb，保护触发器已实测。前端改用运行时 API 代理，避免构建时 localhost 固化；保留 Sec-Fetch-Site，使跨站登录防护经代理仍生效。浏览器测试定位器冲突已修复，并提高文字可读性。最终检查补齐 Next 冷启动 typegen 和开发脚本 npm 参数转发。

## 限制与下一步

本期是本地、单期刊、合成数据原型，非生产系统。原投稿链保持Mock；工作台真实模型工具回环已通过本地验收；完整评审/修回/决定/制作/出版尚未实现，OJS/Janeway 只有适配契约。邮件审批为后端不变量，没有真实邀请 UI、附件存储或发送 outbox。真实API运行时已验证，原生跨提供商Codex子Agent仍未验证；不能从产品API回环推断开发助手兼容性。后续顺序见 ROADMAP.md：完整状态/权限 → Agent/多模型 → 邮件审批/邀请 → 评审/决定/修回 → 制作/发布 → 评测/部署/加固。

## 恢复入口

读 AGENTS.md、README.md、ARCHITECTURE.md、SECURITY.md、DECISIONS.md 和 specs/001-editorial-intake.md。Web 3100 / API 8100 / DB 55432 / Mailpit 8025；不要操作已有 8000 端口模型服务，不读全局认证、不真实发信、不自动生产部署。运行 `./scripts/start.sh`，安装测试环境 `./scripts/setup.sh`，验证 `./scripts/verify.sh`。
