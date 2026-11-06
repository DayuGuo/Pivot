# Pivot

真实工作区侧栏下方新增“设置”：模型API状态/安全接入步骤、邮箱绑定和当前账号集中管理，打开面板保留当前稿件与对话草稿。本机已更新，完整1559后端＋429浏览器通过；模型密钥仍由服务器安全环境管理，不在网页录入或存储。[操作与验收](docs/development/settings.md)。

[PR #8 最后一轮CI复核](docs/development/spec027/ci-followup.md)已完成：修复原生包慢镜像超时，6f76d7d完整push/PR各1559后端＋399浏览器通过，静态双轮和原生amd64包验收通过；真实超时回退路径也已验证。未合并、未部署VPS，失败及本机会话中断记录保留。

当前分支提供单刊辅助核对候选版：PDF/Word资料核对、带原文的问答、私人多版本修回核对和三层人工判断。使用说明见[操作指南](docs/development/spec027/operating-guide.md)，准确源码、测试、真实模型、升级恢复及限制见[交付记录](docs/development/spec027/review.md)和[PROGRESS](PROGRESS.md)。应用代码仍为3307df6，CI修复源码为6f76d7d；历史本机完整门禁1530＋399通过，本次本机会话143中断不计完整成功。此前本机更新保留原53表3560行/24原件，本轮不再改主服务或数据；工程通过不等于专家内容验收。

草稿[PR #8](https://github.com/DayuGuo/Pivot/pull/8)叠加未合并#7/#6，本轮不自动合并或更新VPS。公开静态站、已安装preview.4与本分支候选包分开；日历、多身份和完整出版仍按[路线图](ROADMAP.md)后续推进。真实编辑评价尚未执行，不能据工程测试宣称节时或科学准确率。

已发布的[完整应用私人体验包 v0.2.0-preview.4](https://github.com/DayuGuo/Pivot/releases/tag/v0.2.0-preview.4)可与静态站并存：预编译amd64镜像、私人账号、DeepSeek/PDF/Word、受限内存与备份恢复。它不包含本分支全部增量；候选仅提供CI artifact，不自动发布Release。[安装说明](infrastructure/vps/README.md) · [保留数据升级](docs/deployment/private-preview-upgrade.md)。已安装用户不重新init、不删除卷；用户已报告VPS装有旧版，本轮没有连接或更新服务器。

真实邮件继续禁发，关键决定由负责人独立核对。仅使用合成或明确授权的公开非保密材料，模型没有确认/发送/决定工具；ORCID文本不等于认证。历次发布和失败修复记录保留在PROGRESS及docs/development。

以稿件资料为基础的对话式科研出版工作台。编辑从自己的待办进入稿件，在中心对话中审阅，随时在右侧核对原文、作者资料和引用；正式操作保留负责人的确认权。

**[在线体验 Pivot](https://pivot.anotherdayu.com/)**

## 正式稿件 PDF / Word 与修回

作者以 `author@publishing.test` / `AuthorDemo2026!` 登录，打开[出版工作台](http://localhost:3100/publishing)并新建投稿或进入本人修回草稿，在资料栏选择“导入 PDF / Word 并核对”。明确授权与完整/节选范围后提取；独立核对原件、全文和正文起止页/段，三项勾选后才保存为当前正式草稿文件。已有作者元数据/声明保持原样，正式提交仍另行负责人确认。待核对导入可在同页找回；响应丢失重试原请求，不重复保存。

正式修回请求和作者可见报告齐备时，在中心对话发起“逐条对照修回与作者回复”。引用包含新旧版本、原文行号和受控PDF页/Word段位置；点击“定位已核对全文”可展开实际版本并高亮引用，同时保留原件下载；超过8项可点击继续，保留未发送草稿。长意见分段、回复节选、未完整读取与不确定判断明确标注，AI不确认完成、不发邮件、不作编辑决定。

规格：[spec025](specs/025-formal-document-revisions/spec.md)；许可与限制：[公开版本对语料](evals/public_revisions/README.md)。样本包含真实版本文章和真实文章内修订说明节选；Word是明确的许可XML转换，不是出版社原生Word，没有完整rebuttal letter。真实模型实验与完整自动化状态见PROGRESS，不以Mock或小样本推导科学准确率。

## 本地试用真实资料录入

```bash
./scripts/start.sh
```

打开 [内部审阅资料](http://localhost:3100/library)，未登录时先用 `editor@publishing.test` / `EditorDemo2026!` 登录，再从“内部审阅资料”进入。可手动录入完整 TXT/Markdown（UTF-8、≤1 MiB），或在资料右侧点击“导入 PDF / Word”。文本层 PDF 与 `.docx` 原件≤5 MiB，PDF≤60页，提取文字≤1 MiB；系统提取完整文字、页/段位置及作者元数据候选，随后进入独立核对页。上传不改变当前版本；负责人可先勾“先保存材料，作者及其他缺项稍后补齐”，核对后保存待补材料版本并继续正文审阅；资料齐全时再走完整核对。材料保存不冒充完整资料确认或正式投稿。类型、基金、声明原文为可选候选，缺少则未知，录入不等于本人签署。再次提取默认保留人工字段，明确选择才替换。点击对话引用可定位对应 PDF 页或 Word 提取段并下载原件；刷新和重启可恢复。扫描件、加密文件、旧 `.doc` 及不支持的复杂结构明确拒绝，当前没有OCR或图表/公式理解。

这是本地真实 PostgreSQL/CAS 资料功能，与公网静态 Demo 分开。资料对话沿服务端配置使用DeepSeek或明确标记的Mock，基于当前版本的全文/作者字段生成带逐字定位的审阅建议。外部引用目前仅核验资料或问题已给出的DOI书目元数据，不做全网检索或读取外部全文；结论仍须人工复核。ORCID为手工录入、格式检查，不等于身份认证。权限、字段、验收与下一步见 [spec013](specs/013-internal-review-dossiers.md) 、[基础交付记录](docs/development/internal-dossiers.md) 和 [真实问答](docs/development/dossier-grounded-review.md)。

## 内部修回核对

同一资料先保存原稿，再保存修订稿；在右栏选择“修回核对”，明确两版、预拆要求和原上下文、粘贴作者回复/来源及完整度。生成只读AI辅助包，点击新旧原文定位，负责人分别记录作者回应、正文落实、编辑充分性和理由，并显式核对后追加保存。结果及最新人判可导出JSON，历史不自动批准新版本；不存在邮件或出版决定工具。

当前每批1—8条要求由编辑预拆，回复是粘贴文本；不是四份文件自动建整套修回，也未验证完整逐点回复信。[6篇/42项许可评价准备](evals/single_journal_pilot/README.md)与实际编辑评价分开，后者仍0人。中断沿原UUID主动恢复，已知保存后仅读取恢复，不自动重发。

## 先体验产品 Demo

```bash
git clone https://github.com/DayuGuo/Pivot.git
cd Pivot
./scripts/demo.sh
```

打开 **[localhost:3110](http://localhost:3110)**。只需Docker，无需账号、数据库或模型密钥。停止：`./scripts/demo.sh stop`。

![Pivot 产品演示](docs/preview/demo-desktop.png)

- 三栏工作台：本人待办、常驻对话、稿件材料与当前步骤。
- 主对话与稿件会话独立，左下角日历可按截止日筛选工作。
- 问方法、核对作者、点击原文与真实公开文献；编辑资料或录入新演示稿后刷新保留。
- 手机可打开工作/资料抽屉，对话输入始终可达。

**这是明确标记的模拟交互，使用合成稿件与当前浏览器存储，不调用模型或业务API，不发送邮件，不作正式决定。** 新导入资料不冒充已被AI分析，ORCID手填不等于认证；真实可运行的后端样本另见下方 `/publishing`。

已定名 **Pivot**（原Publishing OS）。[GitHub Releases部署包](https://github.com/DayuGuo/Pivot/releases/tag/v0.1.0-demo)已提供`pivot-vps-linux-amd64.tar.gz`，含离线镜像、静态网页、安装器和校验和。解压后：

```bash
tar -xzf pivot-vps-linux-amd64.tar.gz
cd pivot-demo-linux-amd64
bash install.sh
```

前提为Linux amd64与Docker；默认监听环回8080，可通过HTTPS代理访问。明确需要公网IP直接演示时用`PIVOT_BIND=0.0.0.0 PIVOT_PORT=8080 bash install.sh`并自行放行端口。本机构建：`./scripts/build-demo.sh --image && ./scripts/package-vps-demo.sh`，VPS无需编译、数据库或模型密钥。[五分钟演示与完整安装说明](docs/deployment/demo-racknerd.md) · [本阶段范围](specs/012-showcase-demo.md) · [实际验证记录](docs/development/demo-delivery.md)。源码与4个附件已公开发布，本地与远端完整CI均835 Pytest +48 Playwright通过，x86实际解包安装/11 E2E通过；发行报告见[公开发行验收](docs/development/pivot-release.md)。用户已自行部署[公网Demo](https://pivot.anotherdayu.com/)，线上11项浏览器验收通过；本轮仅检查公开网页，未通过SSH审查服务器配置。

核心产品设计：[PRODUCT_DESIGN.md](PRODUCT_DESIGN.md)。日历/双层对话当前只在独立Demo展示；真实数据库中的聚合、多身份、多刊邀请与邮箱/ORCID注册仍待实施，不能从截图推断上线。

Demo反馈后：[单人＋Codex单刊审阅第一阶段](specs/011-single-journal-review-pilot.md)。包含8周计划、约3万元现金准备及真实试点前的专业复核关口；资料包、文本层PDF/DOCX与只读版本证据问答已按切片本地实现；公开样本评测已按spec016完成一轮；更广泛格式覆盖、ORCID认证与专业复核尚待完成。展示Demo沿用现有电脑/Codex/已购VPS，不需要这笔真实试点预算或新增模型消费。

## 可运行的真实出版 v0.1 样本

目标见 [goals/publishing-v0.1.md](goals/publishing-v0.1.md)，资料库见 [docs/research/library](docs/research/library/README.md)。站内评审、正式决定/修回、实际校样/更正及鉴权本地预览已通过完整离线验收并更新至本机主服务；新领域真实DeepSeek API 6/6及实际浏览器已通过，最终Goal状态见PROGRESS。

新真实业务入口 `/publishing`（登录后点“出版工作台”）；现有 `/workbench` 保留演示材料。新入口的作者资料、实际UTF8 txt/md文件、版本/任务和独立人工审核使用规范化数据库。AI只能整理候选/准备审核，不能确认提交、发信或作决定。F检查点完整验证已实际通过 **797后端+35浏览器**；同篇贯通投稿、评审、正式修回、V2录用、实际校样和鉴权本地预览。所有邮件仍禁用，整个Goal的状态以PROGRESS为准。

真实v0.1基线为835 Pytest +35 Playwright；2026-11-03展示增量后的完整验证为 **835 Pytest +48 Playwright**，scripts/verify.sh退出0，静态检查、PostgreSQL迁移/结构检查及前后端构建通过。独立原生静态包另通过11项；amd64包已在真实x86 GitHub CI实际安装并通过11项验收，用户VPS未实装，边界见[展示交付记录](docs/development/demo-delivery.md)。既有新领域真实API **6/6（35.178秒）** 与实际浏览器通过；[恢复验收](docs/development/deepseek-recovery.md)与[代码复核](docs/development/v01-code-review.md)记录此前发现、修复及限制，本轮Demo未调用真实模型。

验证使用独立Mock栈，保护当前主服务中的数据和真实模型环境；启动与完整命令见[自动验证与本地开发](#自动验证与本地开发)。

以对话与 AI Agent 为入口的科研期刊出版操作系统原型。首条业务链真实运行于 PostgreSQL：登录 → 对话创建合成测试稿件 → 提交并分派编辑初筛 → 状态、待办、对话、审计持久化 → 刷新恢复。

**默认无凭据为明确标记的Mock；当前本机 `/publishing` 使用真实DeepSeek，已通过当前稿件/角色/实际文件/候选/待确认提案与危险请求拒绝验收。瞬时故障有限重试，持续失败明确回滚，不静默回退Mock。真实邮件始终禁用，不包含生产部署。**

当前外观依据用户提供的最新 Hermes 工作台截图：浅灰侧栏、白色对话区、细蓝色选中线与底部输入框。参考证据和适配取舍见 [DESIGN.md](DESIGN.md)。原样遵循 AGENTS.md 中的精简标签规则；四个设计技能的来源、分工和安装记录见 [设计技能](docs/development/design-skills.md)，本轮审查与限制见 [设计验收](docs/development/design-acceptance.md)。

## 一键启动

前提：Python 3、Docker Engine + Docker Compose 可用，首次构建可访问公开镜像/依赖仓库。项目默认仅本机可访问，使用公开的合成演示账号。

```bash
./scripts/start.sh
```

脚本启动 PostgreSQL、Mailpit、FastAPI 和 Next.js，等待健康检查；API 启动时自动执行 Alembic 迁移与幂等 demo bootstrap。不需要手工创建表或复制密钥。已有live API时，启动器只从本项目选中容器恢复模型环境并通过子进程环境保留，不落密钥文件/日志/参数；恢复失败会停止，不默认覆盖成Mock。显式 `EDITORIAL_MODEL_PROVIDER=mock ./scripts/start.sh` 才表示主动切回Mock。

- [编辑工作台](http://localhost:3100)
- [API 文档](http://localhost:8100/docs)
- [Mailpit 本地捕获界面](http://localhost:8025)（原型没有外发传输器，通常为空）

端口为 3100 / 8100 / 55432 / 8025，均绑定 loopback。已有 8000 端口服务不受影响。

停止：`./scripts/stop.sh`。该命令保留 PostgreSQL 卷；再次启动仍保留数据。不要使用 `docker compose down -v`，除非明确要删除全部本项目数据。

## 测试账号与真实出版样本

| 角色 | 邮箱 | 密码 | 当前权限 |
| --- | --- | --- | --- |
| 编辑 | editor@publishing.test | EditorDemo2026! | 本稿预审/责任编辑分派任务、送审与编辑建议；不能最终决定 |
| 作者 | author@publishing.test | AuthorDemo2026! | 创建本人投稿、补齐资料、独立确认及正式修回；仅看负责人已分享反馈 |
| 审稿人 | reviewer@publishing.test | ReviewerDemo2026! | 本人邀请响应；接受后看本轮匿名材料、提交本人报告 |
| 第二审稿人 | reviewer2@publishing.test | Reviewer2Demo2026! | 独立合成候选，与第一审稿人权限相同 |
| 主编 | chief@publishing.test | ChiefDemo2026! | 本稿主编任务、范围/分派、独立确认修回/录用/退稿 |
| 制作 | production@publishing.test | ProductionDemo2026! | 实际分派稿件的校样上传/更正、独立确认及鉴权本地预览 |

1. 作者登录后点“出版工作台”，输入“请创建一篇新投稿”；再提供标题、摘要、关键词、作者等合成信息，由AI整理缺项。
2. 核对表单、本人回答声明，上传真实UTF8完整/匿名稿件，准备审核后在独立页确认投稿。
3. 编辑完成材料预审、实际报告上传和人工复核、匿名材料筛选；主编核对范围并分派责任编辑。
4. 编辑核对质量、准备站内审稿邀请并独立确认；审稿人本人接受并声明无冲突，阅读匿名材料、保存和独立提交报告。
5. 编辑结束实际轮次并确认建议；主编选择正式修回、检查拟分享意见匿名性并独立确认。作者修改新版本、上传回复、重新回答声明并本人提交；编辑人工复核后重新建议，主编可确认录用移交制作。录用不等于公开发表。

6. 制作人员上传实际正文校样并独立确认交作者；作者逐包检查、确认通过或要求更正；制作人员最后审核生成本地预览。预览需登录，仍非正式发表。

v0.1交付时新领域更新至主服务 http://localhost:3100/publishing、主库迁移为12e06b9c4f53；当前迁移及完整结果以PROGRESS顶部为准。隔离Mock验证栈为13100/18100/55433。主服务保留真实模型配置，健康检查仅报告配置，不代替实际供应商验收。新领域真实API 6/6、浏览器文件引用/刷新/人类确认边界已通过，详见 [真实出版对话验收](docs/development/deepseek-recovery.md)。

### 保留的旧版初筛演示

1. 用编辑账号登录。
2. 输入 **“创建一篇测试稿件，并交给编辑初筛。”** 并发送，也可使用可操作的快捷指令。
3. 查看标记为“模拟结果”的执行回复，以及真实稿件的“编辑初筛”状态、待处理初筛任务和负责人。
4. 刷新浏览器，在“稿件管理”和“审计记录”中检查同一稿件 ID。
5. 退出后用作者/审稿人登录；尝试相同指令得到服务端 403，无法越权创建。

Mock 只模拟意图识别，稿件/任务/状态/审计不是前端假数据。期刊和四类用户由 bootstrap 真实写入；命令为当前编辑创建稿件与任务。投稿工具当前支持一条明确指令，其他输入会保存解释而不创建稿件。

## 常驻对话与四页工作材料

编辑或主编登录后点击“我的工作”，或打开 [任务工作台](http://localhost:3100/workbench)。左侧是任务导航，中间是始终可见的主体对话，右侧随上下文切换四类工作材料。对话历史、未发送输入和上下文跨页保留；四页使用同一组**明确标记的合成稿件**；筛选视图、阅读位置、候选选择、版本笔记、问题核验和邀请/决定草稿真实保存至当前用户的 PostgreSQL 工作区，原型真实投稿链仍在 `/`。

1. 在中间对话询问“这篇稿件目前的状态和下一步是什么？”；或将对话范围切换到“当前工作队列”，输入“今天有哪些待初筛任务？”。模拟查询形成真实可操作的材料列表。选中稿件后上下文自动对应；历史消息仍标明原稿件与版本。
2. 阅读 ENV-2026-0129 的中英文长稿，切换三份版本、通过问题跳转原文与修回位置；查看图表/计算公式/附件/参考文献/历史，调整字号、面板宽度或专注阅读。
3. 在“审稿人选择”筛选、连续预览并比较候选；选择后准备.test收件人的邀请，编辑主题、期限、正文并查看完整草稿快照。
4. 在“修回核验与决定”查看两轮问题、回复和原文差异，保存人工核验、内部笔记；选择中性的拟定结果、编辑决定信并查看草稿。进行中的评审任务保持不变。
5. 直接对话“列出当前版本尚未解决的问题，并给出原文依据”“准备邀请草稿”“协助准备决定草稿”，可打开来源和对应工作材料。邀请须先人工选人；已有人工正文不覆盖。模拟检查工具仍在对话下方展开，可取消/重试、改写和处置结果。

默认浅色，可选深色/跟随系统。原始文件是可下载的合成文本，与重排版段落一致；不冒称PDF/DOCX解析。候选档案、论文、既往流程与分析均为合成场景，不是真实履历或学术结论。默认分析仍为Mock；主体对话可按文末步骤显式接入DeepSeek。没有发信、正式决定、任务取消或权限变更能力。作者/审稿人目前无此编辑演示工作台访问权。

设计规范见 [DESIGN.md](DESIGN.md)，接口/数据边界见 [spec004](specs/004-workbench-contract.md)，完整验收、截图与未验证平台见 [本轮交付记录](docs/development/workbench-delivery.md)。工作台采用隔离的草稿/视图表和私有对话回合表，尚未实现spec003的完整出版数据库与作者辅助投稿。常驻对话契约见 [spec005](specs/005-conversation-first-workbench.md)，最新截图/验证/模拟边界见 [常驻对话交付记录](docs/development/conversation-first-delivery.md)。

## 会话与邮箱

侧栏支持真实新建/搜索/切换对话，各会话消息独立持久化，刷新恢复选中会话。桌面可收起侧栏，手机使用可关闭抽屉；稿件详情按需打开。

“邮件”支持自建 SMTP、Gmail、Outlook 配置保存、只读连接/身份验证、断开与重新绑定。本地 Mailpit 预设无需凭据且已真实验证。云账号需服务器端 OAuth 访问令牌；当前没有 OAuth 授权跳转、自动刷新、收件箱或发信能力。保存配置不表示已连接，验证成功也不授予发送权限。

配置步骤、凭据环境引用、期刊所有权与 SMTP 允许列表见 [邮箱绑定指南](docs/development/mail-binding.md)，空模板为 `infrastructure/mail.env.example`。真实 Gmail/Outlook 账号未提供凭据，因此未实测，不声称已经连接。

## 自动验证与本地开发

测试工具需Node.js 22、Python 3.12+、uv、Docker与浏览器系统依赖。完整验收使用独立Mock数据库，不能与日常真实模型服务混用：

```bash
./scripts/setup.sh
# Linux首次需要浏览器系统依赖；下载引擎本身不能替代此步
npx playwright install-deps chromium firefox webkit
docker compose -p publishing-os-verification -f compose.yaml -f infrastructure/compose.verify.yaml up -d --build --wait
COMPOSE_PROJECT_NAME=publishing-os-verification COMPOSE_FILE=compose.yaml:infrastructure/compose.verify.yaml DATABASE_URL=postgresql+psycopg://publishing:publishing_local@localhost:55433/publishing E2E_BASE_URL=http://127.0.0.1:13100 ./scripts/verify.sh
```

隔离Web13100、API18100、DB55433、Mailpit18025，无供应商凭据。verify拒绝对真实模型服务运行；不要让Pytest与Playwright共用同一验证库并发。普通Pytest以外部事务回滚，专门并发/E2E保留唯一命名的合成数据，不删除已有演示资料。

门禁先实际启动三个空白浏览器，缺库时在数据库工作前失败；随后包含全仓离线语法、Ruff、研究完整性、模块依赖、引文回归、PostgreSQL迁移/漂移、Pytest、ESLint、TypeScript和Compose生产构建。构建后启动相同镜像，再用Chromium、Firefox、WebKit单worker验收。不会安装测试浏览器到VPS。物理设备/真实发行版边界与按引擎执行方式见[兼容性说明](docs/development/browser-compatibility.md)。

证据写入`artifacts/pytest.xml`、`artifacts/playwright-report/`、`artifacts/playwright-results/`。本轮日志/截图在`artifacts/spec027/`，可分享的结果见[复核报告](docs/development/spec027/review.md)与[PROGRESS](PROGRESS.md)。CI定义在`.github/workflows/ci.yml`和`demo.yml`；报告逐次绑定实际测试SHA，不将取消/失败运行算作通过。

静态子检查可直接执行`npm run lint`、`npm run typecheck`、`.venv/bin/python scripts/check-boundaries.py`。重跑数据库/API/浏览器子集时沿用上述隔离环境，不切回主库。生产构建使用`docker compose build web`，与实际运行环境一致。

热更新开发：停止 Compose 中的 Web/API（`docker compose stop web api`），运行 `./scripts/dev.sh`；该脚本继续使用同一 PostgreSQL，启动本地 API 与 Next 开发服务，退出时停止这两个进程。`DATABASE_URL` 可通过环境覆盖；默认是本机项目数据库。只允许 PostgreSQL，不使用 SQLite 替代验收。

## 模型协作

主模型配置保持不变。DeepSeek目标ID为 **deepseek-flash**。旧工作台、新领域真实回环、安全API文档子任务分别实际通过。开发委派实测见 [v0.1委派报告](docs/development/v01-deepseek-delegation.md)。原生跨提供商子Agent未验证成功；隔离Codex CLI与loopback假Responses实验不能证明真实DeepSeek原生兼容。

可测试替代路径：安全 API 委派器，默认 Mock，草稿仅写入 UUID 隔离目录，由主 Agent 审查集成，不执行生成代码。支持 research/api/react/tests/documentation。只在明确加 `--live` 后从可信环境读取新 `DEEPSEEK_API_KEY`；不要将密钥放进命令参数、Git 或日志。

```bash
.venv/bin/python -m packages.model_gateway.delegate --kind research --task 'Inspect a synthetic editorial API boundary'
.venv/bin/python -m packages.model_gateway.report /tmp/publishing-delegations
.venv/bin/python evals/model_codex_probe.py
```

在本地交互终端运行下面的命令，可使用**新的、未在聊天中公开过的**密钥执行一个具体的 UI 审查子任务。脚本优先读取 DEEPSEEK_API_KEY 环境变量；未设置时无回显提示输入，只传给独立子进程，不改变主 Codex 模型，也不把密钥写入文件。结果与遥测写入 gitignored `artifacts/delegations/<UUID>/`，等待 Lead 审查集成。这是独立 API 协作，不能冒称原生跨供应商 Subagent 已验证。

```bash
./scripts/delegate-deepseek.sh
```

逐任务记录成功、Token、成本、耗时与返工；未知成本为null。Ollama/vLLM预留显式opt-in、仅loopback接口。开发协作与产品运行时独立。原投稿链固定Mock；旧工作台与新领域均已通过各自真实回环，仅允许授权合成材料出域。详见 [DeepSeek协作报告](docs/research/deepseek.md)。

## 后续数据库与产品规划

三栏“我的工作 / 对话协作 / 稿件进度”、分阶段初审、作者辅助投稿、评审、决定、修回与校样已在单期刊合成样本实现。规格与实际边界见 [数据库与工作流规划](specs/003-editorial-workflow-and-assisted-intake.md)、spec007至010、PROGRESS；后续六阶段路线见ROADMAP。

## 项目地图

- `apps/web`：现代紧凑对话工作台、稿件详情、审计、运行时同源代理。
- `apps/api/publishing`：Domain、Runtime、Workflow、Policy、Action、Audit 与可撤销登录会话。
- `packages/mail_adapters`：只读 SMTP/Gmail/Outlook 探测；`packages/model_gateway`：模型边界、安全委派、遥测；`packages/integrations`：未来 OJS/Janeway 契约。
- `infrastructure`：Dockerfiles 与 Alembic 迁移；`specs`：功能/API 契约；`tests`/`evals`：安全与回归验证。
- [PRODUCT.md](PRODUCT.md)、[ARCHITECTURE.md](ARCHITECTURE.md)、[SECURITY.md](SECURITY.md)、[DECISIONS.md](DECISIONS.md)、[ROADMAP.md](ROADMAP.md)、[研究与来源](docs/research/landscape.md)。

安全约束由代码强制：确定性权限/状态、请求幂等、事务审计、审计不可改写、审批快照修订失效、真实邮件无传输器。已实现的站内评审/决定/制作仍是本地合成样本；公开出版未实现，不能据此推断生产能力。

## 工作台真实模型接入

`/workbench` 支持显式启用 DeepSeek `deepseek-flash`：在本机交互终端运行 `python scripts/start-live-model.py`，无回显输入新密钥；也可从安全环境注入 `DEEPSEEK_API_KEY`。不使用聊天中已公开的凭据。然后运行 `.venv/bin/python scripts/smoke-live-model.py` 验证真实工具回环。默认启动仍为Mock，原投稿链不改变。

AI可按真实登录角色与当前合成稿件读取材料、检索任务、定位引用、导航和准备私有邀请草稿。邮件发送/批准和关键决定不进入工具表，负责人审核权限不变。缺配置或供应商错误明确失败，不静默降级。已通过真实供应商稿件/角色/工具/草稿/危险请求拒绝和浏览器验收；独立Mock回归与live证据分别记录。配置、边界和最新证据见 [真实模型接入](docs/development/live-editorial-model.md)。

真实验收可复跑：`.venv/bin/python scripts/accept-live-model.py --draft`。该命令只在空的合成工作区准备内部邀请草稿，留下人工可审核记录；不发送邮件或发布决定。完整回归使用独立Mock栈，避免消耗真实API或覆盖当前模型配置，见接入说明。

新 `/publishing` 使用独立验收命令（会消耗真实API并新建私人合成稿件，不确认提交）：

```bash
.venv/bin/python scripts/accept-live-publishing.py --live --synthetic-writes --output artifacts/live-publishing-recovery-final.json
node scripts/accept-live-publishing-browser.mjs --live
```

新领域共享60秒期限、网络read idle30秒，跨3轮最多额外重试一次推理，不重复业务工具；数据库等锁后迟到的apply回滚，DB锁/COMMIT本身不宣称硬取消。恢复规则、实际报告与验证边界见 [恢复验收](docs/development/deepseek-recovery.md)。

### 独立评价包（spec022）

在`/library`中打开已有回答，点击“下载独立评价包”。JSON保留该回答对应版本的完整正文、作者和可核对引文，隐藏AI判定及已有人工意见；随机排序的每条候选留空评价。文件仅用于获授权内部核对，作者未匿名，暂不支持评价回传或专家签署。无全文/原件或引用不匹配会拒绝下载，原资料不变。旧版本回答不会导出当前新版正文。

接口：`GET /api/dossiers/{dossier_id}/answers/{answer_id}/evaluation-package`，仍需本人编辑/主编登录；不提供公开共享。无数据库迁移，不修改旧历史，不调用真实模型，不发送邮件或作出关键决定。本阶段不在VPS部署；运行与验收以PROGRESS.md为准。
