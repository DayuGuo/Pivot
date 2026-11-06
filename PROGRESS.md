# 当前执行：spec028 统一设置

按用户要求将模型API、邮箱和当前账号集中到真实工作区侧栏的统一设置面板。保留工作区挂载、对话与文件选择；模型密钥仍由服务器安全环境提供，邮箱使用既有授权API，真实发送禁用。无新后端工具、表或迁移。[范围](specs/028-unified-settings.md)。

初轮111项三引擎专项已通过；独立审查随后发现底层Ctrl/Cmd+K可穿透设置，已在旧镜像真实复现并补阻断与回归。修复后117项专项已全部通过（193.73秒、三引擎各39项、0重试）；完整scripts/verify.sh仍需完成，不能将专项当最终门禁。当前只操作独立Mock验证项目，主服务/数据与VPS未更新，最终实际结果将替换本段。

# 已完成：PR #8 最后一轮CI复核

用户要求检查4bf09e7的CI，失败修复并更新PR/文档，不合并或部署VPS。应用源码仍为3307df6，CI工具/专项测试/工作流修复为6f76d7d；本轮不更新本机主服务、数据库、原件或模型配置。[完整复核](docs/development/spec027/ci-followup.md)与[结构化证据](docs/development/spec027/ci-followup.json)优先于下方历史快照。

完整[push 42119052986](https://github.com/DayuGuo/Pivot/actions/runs/42119052986)与[PR 42119062980](https://github.com/DayuGuo/Pivot/actions/runs/42119062980)均顶层及全部步骤success：各1559后端（10条提醒，579.79/667.98秒）＋399浏览器（三引擎各133，13.8/16.1分钟），0失败/跳过/flaky/浏览器重试。各依赖首次28/80秒成功。静态push42119052972/PR42119062915各17步骤success、各33＋33项；PR首次300秒超时后实际官方HTTPS回退、第二次成功（总357秒），push首次27秒。37项离线专项、静态/迁移/准确构建通过，不累计重叠覆盖。

原生amd64包42119052983全部20步骤success，官方HTTPS预检后Chromium依赖14秒完成。302150234字节归档外/七内部SHA及实际镜像ID匹配；preview.4原48表62行4CAS全部保留，测试后55表72行5CAS在新项目恢复全等，PDF/DOCX引用定位/刷新、重启、4并发200/429与同UUID恢复通过；旧cookie/引文可读，邮件/正式决定0，其他服务ID不变。仅候选CI artifact，不发布Release或部署。

原失败不覆盖：4bf原生42115429481两次300秒/124，共602秒，未构建且后续跳过；原完整push成功，PR因新提交concurrency取消。6f本机会话143中断，1559后端/390浏览器已过但无完整结束，不计exit0；最终完整结论依据远端两轮实际verify.sh。原日志/中断回执保留，未删测试或通过清库掩盖问题。

本机只读API200、EMAIL_SEND_ENABLED=false/Mailpit0，本轮DeepSeek0请求，关键决定仍由负责人确认。未合并、未Release、未连接VPS。实际编辑评价及专业复核尚未执行，见[交接](docs/development/spec027/external-handoff.md)。

# spec027 工程候选交付（3307历史验收，最新CI见顶部）

已按[用户执行建议](docs/consultation/Pivot-candidate-execution-brief-2026-11-05.txt)完成任务A/B工程候选，草稿[PR #8](https://github.com/DayuGuo/Pivot/pull/8)叠加未合并#7/#6。应用运行源码冻结3307df676cc64a84c0ab6a591f66c2e9d2901582；后续CI工具、专项测试和工作流修复为6f76d7d，最新结果见顶部复核记录，不合并main、不更新VPS、不发布Release。[操作指南](docs/development/spec027/operating-guide.md) · [交付记录](docs/development/spec027/review.md) · [精确结果](docs/development/spec027/results.json) · [合同](specs/027-internal-revision-contract.md)。以下保留3307当时的验收快照，最新CI以顶部为准。

历史3307本机scripts/verify.sh实际exit0、1246.54秒：**1530后端474.58秒（10条提醒）＋399浏览器12.2m**，Chromium/Firefox/WebKit各133项、0失败/跳过/重试。全仓语法、Ruff/format、研究完整性/模块边界、18条离线引文、PostgreSQL迁移无漂移、ESLint/TypeScript与准确镜像构建/启动通过。证据artifacts/spec027/verify-final.log、verify-final-exit.json、pytest-final.xml。迁移175、资料/导入/来源/兼容/安装器132、三引擎专项57与全量重叠，不累加。

任务A：缺项PDF/DOCX可先保存材料并正文审阅，不建完整DossierCheck；首次上传前/后人工字段保留，显式切换候选；资料与缺项按精确版本导出。新增可选文章类型、基金、声明原文及来源，空扩展不改旧序列化/指纹；声明不代签。类型须明确标识、基金/声明完整有界，拒绝已覆盖的他文/限定语截断反例；模型候选和纠正提示均限实际14k窗口，完整摘要/联系人规则补充分开。具体归属和语义仍由编辑核对。

任务B：私人真实原/新版本＋编辑预拆要求/原上下文＋来源明确的粘贴回复及四项完整度，生成冻结核对包；三层人判和理由追加、并发头/同UUID恢复、导出/历史不转当前批准。新增28a7c1e09462两表27字段，旧表/迁移/回执不改。已修多标签重读仍旧头、读取恢复误要求再签、人工草稿丢失及新元数据边界问题，Codex交叉审查不等于外部专业审核。

6篇独立许可论文/42项工程问题（A27/B15）、9项后续保留题及空白人评/净耗时模板已准备，原件/快照/许可/逐字位置离线校验通过。语料此前用于调试，非未知盲测；完整逐点回复信0、实际编辑评价0人，不报告科学准确率、节时或继续使用结果。

真实DeepSeek合成私有两版核对＋问答6 HTTP/5条精确版本引用通过，最终3307元数据一次请求/三项完整原文和限定语通过。全部实验11 HTTP、输入21623/输出1741Token，按当日官方峰值未缓存口径估价0.0085761美元，账单未知。原10次预算末次非法根字段被拒且预算挡纠正；另立2次/0.02美元小额补测，实际1次成功，失败保留。无签署/业务确认/邮件/决定请求；key只在安全环境内存传递。合成供应商协议不替代许可论文专业评价，原生跨供应商Codex子Agent仍未验证。

历史3307原生amd64 [CI42110416671](https://github.com/DayuGuo/Pivot/actions/runs/42110416671)全部步骤成功：3307包302151650字节，SHA及七内部文件/运行镜像ID一致；实际preview.4升级保留48表62行4CAS，累计新增7表空，新增核对/人判后55表72行5CAS在新项目恢复全等，旧cookie/引文可读。4并发200/429、同UUID恢复、原件/引用/刷新/重启通过，1472MiB容器总硬限下无OOM，非用户VPS容量认证。仅CI artifact，不Release。中间ARM64/amd64实验另列，不替代最终源。静态push同源两轮33项通过；重复PR安装卡下载已取消，不记成功。

CI依赖失败保留：5ded两次完整门禁在Ubuntu26慢镜像超时，用户timeout无法杀root apt；固定Ubuntu24并把timeout置于提权内部，3307主CI安装35秒完成。后续静态/打包入口同样改用已验证helper，下载5m/依赖12m、保留日志，YAML解析和离线8项通过；新入口远端状态与已成功的应用验收分列。同应用源码完整[push CI42110416792](https://github.com/DayuGuo/Pivot/actions/runs/42110416792)与[PR CI42110424097](https://github.com/DayuGuo/Pivot/actions/runs/42110424097)均全部作业/步骤success：1530后端641.00/650.29秒＋399浏览器15.4m，0重试；新caller配置是其后的独立增量，精确状态以results快照和Actions为准，不借用旧步骤成功冒称新入口已远端执行。

**本机已更新且旧数据完整保留**：0600 DB/CAS备份已验证pg_restore目录及tar全文件；原53表3560行的主键/全部字段SHA与24CAS路径/长度/字节SHA全部相同，新两表空，schema f592→28a7。API/Web健康200，DeepSeek/deepseek-flash配置保留。更新验收仅GET，业务POST/新模型调用0；EMAIL_SEND_ENABLED=false、Mailpit0。未覆盖恢复/删除/重置，不改Codex主模型/全局配置，不连接VPS或改变公开静态站。

实际Linux三引擎，最终原生包桌面Word引用/375px图及中间真实DeepSeek修回/引文图已人工查看，页面无错误/横溢出，Impeccable源码检测[]。真实Edge/Safari/Android、IME/软键盘未测。下一阶段需要负责人安排两名获授权编辑及许可完整修回包，按净耗时/有效覆盖/严重错误评价；专业工程师复核文件、权限、版本确认、模型出域、备份恢复、部署维护。自动复合拆解/完整回复文件导入/结构化外部投稿来源仍未做，日历等长期目标按反馈推进。工程候选通过不等于报告全部试用条件或生产放行完成。

# 当前增量：2026-11-05，spec026已完成代码逻辑与三浏览器复核

交付[PR #7](https://github.com/DayuGuo/Pivot/pull/7)，依赖尚未合并的PR #6，均不自动合并、不部署VPS。[范围](specs/026-browser-and-logic-audit/spec.md) · [完整审计报告](docs/development/spec026-review.md) · [结构化结果](docs/development/spec026-results.json) · [兼容性边界](docs/development/browser-compatibility.md) · [模块维护地图](docs/development/module-map.md)。运行/测试/脚本固定提交168f7d6e72257e03f1aefda180e6c0c52898e7d2，其后仅文档调整。

最终scripts/verify.sh**实际退出0**，独立退出记录1186.23秒：**1395后端通过470.66秒（7条第三方提醒）＋366浏览器通过11.4m**，每引擎122项，0失败/跳过/重试；语法、Ruff、研究完整性、模块边界、18条离线引文、迁移无漂移、ESLint/TypeScript和生产构建/启动均通过。GitHub同源码[push verify42088173082](https://github.com/DayuGuo/Pivot/actions/runs/42088173082)全部作业及已执行步骤成功，实际1395后端414.26秒＋366浏览器11.5m，0重试。static push42088173400/PR42088185044均所有实际步骤通过，静态站和原生amd64离线安装后各33项三引擎通过；与完整回归有重叠，不累加。重复PR verify42088185015卡在官方浏览器系统依赖安装，已取消，不计为测试成功；准确终态见结构化结果。

修复实际复现的问题：撤权刷新保留旧材料、邮箱probe等待期间角色/期刊/会话失效仍保存状态；旧写回合清空后稿草稿、解除新表单保护或跳回旧稿；最近200篇遗漏较旧本人待办、历史重复权限投影和连接池拥塞；禁止存储/缺较新UUID与Abort API、IME229、拖动中断和短视口；导入页短暂切入期刊主对话并重建文件框；确认成功提示早于快照重载导致快速返回可能丢失。复用ensure_actor，拆出work_queue与browser能力，权限缓存仅一次历史GET，通用准入8进行中/16等待/2秒且不占DB等待，重任务单名额不排队保持。工作队列不授予材料权限，POST未知结果仍按原UUID主动恢复。只删除重复次级说明，保留模拟、来源和人工确认信息。

保留所有失败证据：首次完整门禁1385后端过、Chromium110过/5失败后停止，后续队列/历史修复；f135126完整1395后端过/358浏览器过2失败（Firefox滚轮截断与WebKit夹具可用等待）；62f7697子项1395/360全过但工具会话退出143，不冒称exit0，同源码CI359过/1重试揭示导入上下文问题；fc2451f1395后端过/362浏览器过1失败，随后受控红测定位确认提示竞态。新夹具按钮名称错误单独记录，未算产品红测；没有删除测试或放宽权限/摘要/精确位置断言。最终168f7d6全量通过后没有再改运行代码。详报告，不用中间检查点代替最终验收。

**本机主服务已更新且数据完整保留**：启动前已做0600本地DB/CAS备份；53张应用表3560行逐行主键与全部字段内容SHA全部相同，24原件路径、长度和字节SHA全部相同。无新迁移，schema head仍f59230d88725；API/Web健康200，现有DeepSeek/deepseek-flash配置保留。EMAIL_SEND_ENABLED=false、Mailpit0封；本轮真实模型调用0/新模型API费用0，未重新验证凭据可用性。负责人确认、旧批准/历史指纹不变，没有恢复覆盖、删除数据或更改Codex全局/主模型。

实际Linux引擎Chromium156.0.8078.4、Firefox157.0、WebKit27.2。公开历史DeepSeek回答只读回放逐字定位、续批第9项草稿、0业务POST/错误，6张桌面/深色375px截图已检查（fc2451f；最后补丁只改审核成功时序，截图相关模块未改）。Impeccable源码检查[]。不代表真实Edge/macOS或iOS Safari、Android、历史最低版本、真实IME/软键盘与物理多指认证；2.5GB VPS新容量/完整应用发行包未在本轮重验。下一步按ROADMAP补真机与专业安全/备份/资源复核，继续单刊试点，不自动上线。

# 当前增量：2026-11-05，spec025本机与最终远端验收通过

PR #4/#5已按授权合并main（ecc884d6d8ab443969bfccecd77e935ee25773ea、eae5e2f137fda928751a6601efd4594a277e0f2f）。新交付[PR #6](https://github.com/DayuGuo/Pivot/pull/6)不自动合并，不连接VPS。详细[审查记录](docs/development/spec025-review.md)、[精确结果](docs/development/spec025-results.json)、[许可语料](evals/public_revisions/README.md)。以下旧切片“尚未合并”等均为当时状态，以本段为准。

最终运行源码4995bb15d2e3673dfa79ccf088c8de0794b126f2；比较/模型协议与f12fe0a一致，后续为迁移夹具、来源定位、请求完成等待和批次提示修复。scripts/verify.sh exit0：**1382后端448.52秒、7条第三方提醒＋103浏览器4.3m**，静态/研究映射/模块边界/离线18引文/迁移无漂移/构建启动全部通过。同源码分支[verify42054578463](https://github.com/DayuGuo/Pivot/actions/runs/42054578463)顶层/全部步骤success，实际1382后端557.73秒＋103浏览器2.8m；push/PR static42054578663/42054588474全部步骤success。同源码PR预览[verify42054588405](https://github.com/DayuGuo/Pivot/actions/runs/42054588405)也顶层/全部步骤success，实际1382后端649.11秒＋103浏览器3.2m。此后仅交付文档变化，运行/测试/脚本冻结不改。

正式PDF/DOCX准备→独立全文/原件/范围人审→当前草稿正式文件→正式修回逐项比较→原件页/Word段＋已核对全文高亮已贯通。新增f59230d88725两表32字段；旧表/旧指纹不改。批准绑定本人会话、版本/revision和不可变原件/提取/范围，替换与继承保留来源，不冒充新确认。作者元数据保持原关联，不自动按文中姓名认领账号。

公开许可固定3组真实版本对、6份文章页PDF、9份XML转制Word（含3份作者修订说明节选）和9段有独立CC BY许可的评审意见。完整回复信0、出版社原生Word0。真实DeepSeek最终4组（含未改正文＋新版回复反例）8批/16工具，40处理项、68引文逐文件SHA/重新提取/原件定位通过，输入158313/输出4158 Token、104286ms、成本未知。35项不确定、5项非修改要求、完成0；处理项含长段片段/程序性指令，不是40条独立科学要求，不报告专业准确率。只读推理前后proposal/确认/决定825/825/72相同，Mailpit0，结束恢复隔离Mock。

发现并修复WinAnsi控制槽误读（原件不变，parser text-v3，fonttools4.68.0）、合法revision0误拒、长段截断、确认范围刷新丢失、Unicode偏移、重抄引文和跨窗口/重复歧义、待核实批次提示从头重来。五轮模型部分协议失败均保留并拒绝输出，最终后端证据编号避免重抄；六轮39 HTTP/29个200及Token/返工记录见报告，不能当准确率。全量先行4旧迁移夹具失败和1浏览器提前等待失败已修复，没有删测试或改旧迁移。

本机已用保留现有模型环境的scripts/start.sh升级；原全部51应用表3560行、其中35业务表956行，逐行摘要前后相同，新两表0行；24个CAS字节不变，0600数据库/原件备份已校验。主服务审阅DeepSeek/deepseek-flash可用，基础创建演示仍Mock。最终隔离浏览器复核已保存的真实模型回合与原文，提示从第9项继续、POST0/错误0，桌面/375px深色截图已查看。没有重置/删除/恢复覆盖旧数据。

EMAIL_SEND_ENABLED=false、Mailpit0、关键决定仍由负责人独立确认；未部署VPS、未发布新Release、不改Codex全局或主模型配置。下一步优先明确许可的完整回复信/原生Word、双人编辑复合要求金标准和专业安全工程师复核，不自动扩大正式试点。

# 当前增量：2026-11-05，spec024本机与末版远端验收通过

当前稿件建议栏与正式修回逐项对照已在本机更新。规格见spec024；完整边界/失败修复见[验收报告](docs/development/spec024-review.md)，精确状态见[结果](docs/development/spec024-results.json)。可审查交付[PR #5](https://github.com/DayuGuo/Pivot/pull/5)，新分支codex/contextual-guidance依赖仍未合并的PR #4；两者均未自动合并，不部署VPS。

最终界面源码aadccc358f573333e8d687d40aedc3f174505e56；后端与116ca1f完全相同。scripts/verify.sh exit0，1344后端596.84秒＋93浏览器3.5m，静态/迁移无漂移/准确构建启动通过。最后版本提示的界面改动在后端测试阶段完成，后端/模型/其测试/verify脚本对象与d45223c一致，随后全部界面检查和浏览器覆盖最终版本。前一全量90浏览器通过/3夹具失败已修复，恢复/建议13项专项8.6秒通过；失败和中止记录不算成功。

真实DeepSeek合成两工具实验3.288秒：实际修改有证据、承诺稍后补链接为部分回应；输入2667/输出283 Token，成本未知。首次分类误将已有回复称为未回应，先失败回归后修复，四次实际调用合计输入5318/输出568、分类返工1次。不能称真实论文修回或真实模型正式流程E2E已验收。所有判断待负责人核对，大修仍需重审。

前一d45223c远端verify42018557800成功：1344＋93；最后aadccc3静态42019900851和完整42019900996均成功，实际1344后端400.63秒＋93浏览器2.0m，顶层及全部步骤已核对。后续只提交文档，运行/测试/验收脚本不再改变。

建议只填草稿，真实权限/当前版本/任务及已有薄弱证据驱动，无推理或业务写入。作者/责任编辑/主编修回比较只读作者已获分享的要求与实际原/新/回复文本，审稿人不获跨报告权限。引文唯一逐字、实际改动、覆盖不足和独立AI检查约束；历史分析标记版本与进度变化，不能替代当前复核。纯规则/比较与鉴权来源/路由/对话集成分离，无新迁移，head17d51aeb9408。

本机35表956行更新前后逐表摘要相同，24个CAS文件与内容地址匹配。当前用户占位资料未填全文/作者，实际浏览器仅填补资料问题，POST0、投影不变、页面错误0；桌面/375px/深色与历史警告截图已查看。EMAIL_SEND_ENABLED=false、Mailpit0，关键决定独立负责人确认；未发布新VPS包或部署VPS，不改全局配置。后续真实样本/专业复核计划见spec024-revision-evaluation-plan.md。

# 开发状态

## 当前增量：2026-11-05，spec023已完成本机与远端验收

可审查交付：[PR #4](https://github.com/DayuGuo/Pivot/pull/4)，未自动合并。冻结运行源码c81df74以后仅交付文档变化。

PR #3获用户明确授权，已于2026-11-05T09:18:52Z合并main **3e8729a0003a93514592fc0696bd33ef0c95cb4d**；main verify42001351711/static42001351668/既有原生amd64包42001351533均success（不含本批新功能，不是VPS部署）。本批分支codex/evaluation-returns，不自动合并新PR、不连接VPS。

已实现登记v2包、无写入预览、独立页逐项原文定位/人工核对、追加回传、幂等/并发/分页历史和最新意见分歧。EvaluationPackage/EvaluationReturn共26字段、17d51aeb9408迁移，原33表/旧迁移/指纹不改；角色/归属/期刊/历史版本与digest由后端和SQL守卫控制。私有随机ID映射不外露，旧v1包不可直接回传，代号未认证身份；不共享给外部reviewer账号，不多数决定，不创建DossierCheck/正式决定/邮件。

冻结运行源码 **c81df74b6e0d07da185288772c28fbadca118cb4**，本机scripts/verify.sh **exit0：1319后端437.43秒＋91浏览器2.5m**，静态/研究/模块/离线引文18/迁移零漂移/准确构建启动全部通过。远端同源码[verify42005578631](https://github.com/DayuGuo/Pivot/actions/runs/42005578631)顶层及全部步骤success，实际1319后端519.74秒＋91浏览器2.5m；[static42005578299](https://github.com/DayuGuo/Pivot/actions/runs/42005578299)两轮11项10.8/7.7秒通过。6条第三方弃用提醒，未删除测试。细节见[报告](docs/development/spec023-review.md)与[结构化结果](docs/development/spec023-results.json)。

专项32新API11.19秒、相关81API22.19秒、81迁移/资料46.55秒（集合重叠不累加）；相关35浏览器22.1秒，新实际链最终3项4.8秒，含真实并发200/409、确认回执丢失同UUID恢复、等待下载时换身份。初次迁移因SQLAlchemy把SQL内JSON冒号当绑定参数失败，已修正；静态检查发现旧作者贡献可能缺失，改为空数组兼容；重复勾选夹具先误交合法单项再改body导致409，改为一开始真正重复ID，未放宽后端422断言。失败记录保留。桌面/375px截图已查看，Impeccable[]，不是专家或完整辅助技术认证。

本机更新前DB/CAS0600备份仅在忽略目录。scripts/start.sh保留选定DeepSeek环境，增量升级后旧33表940行摘要完全一致、新两表空。两份已有公开授权资料共5条结论，经实际浏览器登记两组模拟相反意见、上传/定位/逐项确认/刷新，4包＋4回传＋8网关回执，分歧2/3正确；理由明确不代表专家。新模型调用、邮件/关键决定请求、页面错误0，原资料投影不变。最终35表956行；精确排除8条新类型且响应ID匹配的回执后旧940行摘要相同，原24个CAS文件逐一hash相同。未重置/删除/恢复旧数据。

主服务现可体验新流程；EMAIL_SEND_ENABLED=false、Mailpit0，重大决定独立负责人确认。没有新供应商推理或凭据重新鉴权，不把health.available当真实调用成功。未发布新Release或部署VPS，Codex全局配置/主模型不改。后续先由真实获授权编辑确定评价标准，再规划实际评价者账号/分派/签署与扩大许可样本；真实受控资料之前须专业安全/隐私复核。

## 当前增量：2026-11-04，spec022已完成本机与远端验收

可审查交付：[PR #3](https://github.com/DayuGuo/Pivot/pull/3)，未自动合并。运行源码冻结18d2391，后续只有交付文档更新。

用户明确授权PR #2，已合并main **42f720c1e83a8a4ddb9ac5e93f93a1d9e65fc145**（2026-11-04T22:39:04Z）；合并后main verify41927132915实际1260＋84通过，既有amd64隔离包CI41927132953也success并生成CI artifact，不是VPS部署。原PR #2未合并的记载为上一阶段历史。本批分支codex/evidence-review-integrity，不自动合并新PR、不部署VPS。

本批修复两项P2：反馈历史head/page双查询竞态；评价包等待期间切换登录仍可能下载旧响应。来源/查询移入独立共享服务，历史以单SQL快照读取，浏览器请求前和实际下载前双重身份核对；保留原指纹、写入CAS和所有人类关口。新增本人可下载、隐藏AI判定与旧人工意见、含准确历史全文/作者/引文的独立评价JSON包。无新表/迁移/真实模型调用，没有专家盲评、匿名化或评价回传。

冻结运行源码 **18d23910c59e0837e4fbcd8208faca4b9754aa8d**，本机scripts/verify.sh **exit0：1287后端381.43秒＋88浏览器2.3m**，静态/研究/依赖/离线引文18/迁移零漂移/准确构建启动全部通过。远端同源码[verify41929773512](https://github.com/DayuGuo/Pivot/actions/runs/41929773512)顶层及全部步骤success，实际1287后端419.64秒＋88浏览器2.0m；[静态41929773645](https://github.com/DayuGuo/Pivot/actions/runs/41929773645)两轮11项11.4/10.9秒通过。5条既有第三方弃用提醒，无删测试。专项49API9.80秒＋32浏览器18.1秒；桌面/375px截图已查看，Impeccable检测[]。详[复核报告](docs/development/spec022-review.md)和[结构化结果](docs/development/spec022-results.json)。

先失败后修复的历史交错用例和等待中身份变化用例均保留。前次尚未完成的完整回归主动停止exit143，旧源码verify41928749895已取消，不计成功；其后重新冻结完整重跑。首轮浏览器的登录夹具等待问题也保留记录，不以重复运行掩盖原因。

本机已使用保留选定模型环境的scripts/start.sh更新。两份既有公开授权历史回答真实浏览器下载，共5条候选，正文/作者/原件位置/摘要一致，旧人工意见未导出，原资料不变，模型调用/业务写/页面错误0。最终更新与只读验收前后33张publishing_*表940行逐表摘要完全一致（登录/会话审计另计），无需迁移或恢复。主服务仍DeepSeek配置、EMAIL_SEND_ENABLED=false、Mailpit0；本阶段未重新验证供应商凭据，不把health.available当真实调用成功。关键决定仍由负责人独立确认。

下一阶段先与实际编辑确定独立评价标准，再设计受鉴权的结果回传与分歧汇总，扩充独立原生Word/多栏PDF许可样本；真实受控试点前仍需专业工程师安全/隐私复核。未发布新Release、未操作用户VPS。

## 当前增量：2026-11-04，spec021人工证据反馈（本机与远端已验收）

下一阶段可审查交付：[PR #2](https://github.com/DayuGuo/Pivot/pull/2)，未自动合并。main当前f67f24e仅包含用户明确授权的PR #1；新功能已在本机开发服务运行，VPS未改变。

最终冻结源码21f10f9已完成scripts/verify.sh：**1260后端381.97秒＋84浏览器2.3m**，静态/研究/依赖/迁移漂移/准确构建启动全部通过，5条同类第三方弃用提醒。完整交付docs/development/spec021-review.md及结构化spec021-results.json；同一源码远端完整CI41922935042实际1260后端383.22秒＋84浏览器1.9m、全部步骤success；静态41922935021为11＋11通过。后续仅文档更新，不改运行源码，VPS未部署。

用户明确授权PR #1合并，已合并main f67f24e0dc2fef8639d122cc0e545ccdfe73332f。先前main授权阻塞已解除，不再适用PR #1；用户明确要求不部署VPS。本阶段分支codex/review-feedback，未推送下一阶段到main，也不自动合并后续PR。

已实现逐条结论人工复核入口、追加式反馈、精确版本/claim来源、负责人勾选和理由、冲突/幂等、历史分页与摘要下载；模型和原回答不改，邮件/正式决定/资料核对不被反馈自动触发。迁移16c40fda8397增加独立ClaimReview16字段；原表/旧指纹不变。OJS/Janeway官方指南本轮实际读取，源字段与约束在静态研究映射中完整绑定。

失败先行2接口用例失败；初轮后端发现严格UUID导致后续复核422，已沿RequestID兼容输入修复；后端19项通过。完整head测试先有115过/1漂移（夹具仅迁移到15b），保留历史D/E夹具边界并为真正完整head加入16c，81schema/资料测试通过。production53实际JUnit已重绑，旧观测不覆盖。浏览器初轮24过/3失败来自选择框标签定位和Next双alert范围，已修复可访问名称与定位；第二轮27通过16.4秒，含真实DB保存、同UUID恢复、刷新、撤权和375px。

完整检查点scripts/verify.sh实际退出0：1257 Pytest（377.23秒）＋83 Playwright（2.2m）、全部静态/迁移/准确构建启动通过，5条既有类别弃用警告。最后发现翻旧记录会采用并发新前置ID，失败先行已复现，前端改为保持原提交基准；28相关浏览器16.3秒及两个实际HTTP并发1成功/1冲突通过，第二个完整检查点1257后端381.41秒＋84浏览器2.3m通过。随后复现大归档结论触发32KiB约束，已改前置精确容量检查返回413，并拒绝空白/空字符理由422；22专项通过6.04秒，最终整链已按本节首段通过；保留旧失败和检查点日志，不用重跑掩盖已发现问题。

主服务升级前已生成仅本机、忽略且0600的DB/CAS备份。实际增量迁移16c后原32表936行摘要完全相同，新表空；随后2条公开许可历史回答由测试驱动模拟负责人标为无依据/待核对，原回答/版本/资料核对投影均不变、原文高亮及实际摘要下载/刷新通过，模型/邮件/决定/资料确认调用0、页面错误0。三次重放后反馈仍2条；排除2个新网关回执后旧32表936行摘要仍一致。专家盲评/更多原生样本/ORCID OAuth未实现。专家盲评/更多原生样本/ORCID OAuth均未实现。

## 当前增量：2026-11-04，spec020第三批已交付

代码与文档已在[PR #1](https://github.com/DayuGuo/Pivot/pull/1)形成可审查交付。自动审批拒绝本轮直接更新默认main，认为默认分支发布需明确授权；main仍a898a02，未自动合并、不绕过拦截。预发行preview.4已授权发布且可下载。

第三批最终交付：本机**1238后端＋81浏览器**和全部静态/迁移/构建通过；真实DeepSeek公开语料、作者归属与原文支持实测见下方。已发布[preview.4](https://github.com/DayuGuo/Pivot/releases/tag/v0.2.0-preview.4)，原生包安装/并发/恢复/浏览器通过。远端完整执行1238＋81、静态11＋11及全部步骤成功；发行记录时部分顶层仍in_progress/null，详spec020报告，不冒称顶层已success。使用原--state更新，开发者未连接或自动更新VPS。

已实现作者正向机构/邮箱/ORCID关联、未确认来源留空与定位、不确定性/重复信息提示、同一导入作者换序来源跟随，以及独立上下文AI原文支持检查。失败候选折叠待核对，旧回答不追溯认证；录入元数据与原件来源分开。共享协议辅助函数抽至model_gateway/protocol，正式chat兼容导出保留。无新迁移，head15b39ecf7286，既有回执/人工确认/邮件禁用不变。

真实DeepSeek新建6份公开评测资料：26作者位次与独立金标准比对，姓名、机构、邮箱无错配/列出字段无缺失；6次浏览器模拟负责人独立核对建新版本、12问答/定位/刷新通过。初轮保留23条、待核对5条。检查发现录入摘要冒称原件Summary，新增明确来源类型后该类2候选均安全保留待核对（有用回答断言失败，历史保留）；进一步明确全文来源的2问返回3条original_text结论，浏览器精确定位/刷新通过，0额外确认。不是专家/作者签署，不代表一般语义正确率。

36个冻结公开来源支持正反例首轮34完成/2协议失败；一次有界检查纠正修复后36/36正确。来源类型最终版重跑36/36、误放0/误拒0/错误0，36attempt、输入44,644/输出2,027Token，费用null。离线CI仅3随库小样本18个精确引文＋金标准作者proposal回放，不冒充真实提取质量。真实自动提取另外6/6已比对。

完整verify首轮1231通过/1失败，失败是新缺失机构提示使“issues[0]为邮箱”的测试顺序假设失效；保留无错误关联及未认证等原断言，改为按字段/原因核对具体issue。新增来源类型3参数回归，最后专项40通过。来源类型修复检查点scripts/verify.sh实际退出0：**1235 Pytest（378.70秒）＋81 Playwright（2.2m）**，Ruff/format、ESLint/TypeScript、研究/依赖门禁、18离线引文、PostgreSQL迁移/漂移与准确镜像构建启动均通过。4项第三方弃用警告；日志artifacts/spec020/full-verify-final.log。未删测试。

最终复查24条旧采用候选，22保留/2待核对，原断言不够直接的临床Word补问2/2通过；不把非金标准重查算作误拒率。最终12问选集（8初轮＋4补问）23条采用均有原文件引用、3条待核对；共17个新问答，历史不改。所有模型实测196attempt、416,186输入/26,470输出Token，费用null。结构化结果docs/development/spec020-results.json。

最后代码复核发现作者贡献仍仅校验值存在于全文，已补正向归属及过滤后来源下标：失败先行1过/1失败，修复后78相关测试与六文件离线回放通过。真实公开候选本次贡献均为空，不据此声称模型贡献提取已实测。上述1235+81为修复前检查点；最终scripts/verify.sh已实际退出0：**1238 Pytest（378.50秒）＋81 Playwright（2.2m）**，全部静态/研究/边界/迁移漂移/准确构建启动通过，4项同类第三方弃用警告；日志artifacts/spec020/full-verify-delivery.log。最终本机服务已安全更新，32表全部现存936行摘要与更新前相同，provider仍deepseek、EMAIL_SEND_ENABLED=false。

本机安全更新前后32张publishing_*表825行摘要一致；公开评测后排除明确新资料/回执再比对原825行仍相同，不扩大为全库证明。仅新增公开评测资料/版本/导入/人工资料核对/问答及相应回执；正式流程与邮件未改变，Mailpit0、EMAIL_SEND_ENABLED=false。无VPS连接/自动部署，无全局模型配置修改。详见[第三批交付](docs/development/spec020-review.md)及[研究记录](docs/research/author-association-and-source-support.md)。

## 当前增量：2026-11-04，spec019第二批已验收

修复主动同UUID断线/429/503/不完整响应恢复、已知写成功后仅读取、路由与操作代次隔离、返回旧表单/迟到跳转、撤权后并行回复恢复私有数据、保存后的旧列表覆盖新搜索及改问题仍保留旧重试。资料/消息/版本/导入均有明示keyset分页，搜索覆盖本人全部有权资料且不清空当前编辑表单；批量关联限定本页。API/Web在重任务正文前单名额非排队429/Retry-After，私人包单worker/1472MiB硬限额。无新表/迁移/删除数据，权限与人类关口保留。

最终本机scripts/verify.sh退出0：**1194 Pytest（379.62秒）＋78 Playwright（2.1m）**，研究/分层/Ruff/ESLint/TypeScript、迁移/漂移、实际前后端镜像构建启动通过。最终源码4b4c933c2ec428ebdc00cc14272273918d6a5e28的[远端verify脚本](https://github.com/DayuGuo/Pivot/actions/runs/41859417633)也通过1194（501.87秒）＋78（2.3m），四项既有第三方warning；全部作业步骤含Complete job为success，但采集时GitHub顶层workflow/check仍in_progress/结论null，**不将汇总字段冒称success**。验收依据是实际完成的命令/全部步骤与独立原生包；发行JSON保留差异。[amd64安装包CI](https://github.com/DayuGuo/Pivot/actions/runs/41859417258)和[静态Demo CI](https://github.com/DayuGuo/Pivot/actions/runs/41859417506)顶层均success。

原生包实装两格式/独立核对/引用/重启/隔离恢复/实际浏览器通过；四路上传1执行、3返回429，同UUID顺序恢复与重放成功，完整资料投影不变，确认/邮件/决定请求0。后续观测峰值API115310592/Web61452288/DB91537408字节，各无OOM；不是用户2.5GB VPS整机压测。本机从旧版实际更新：32张出版业务表最终825行数量/内容摘要一致，alembic无漂移，DeepSeek环境保留。真实DeepSeek同一合成稿5条全文/字段引用、3次有效attempt、7694输入/478输出tokens/供应商4978ms，费用null；原UUID11ms重放无额外推理且仍未核对。最终页面精确高亮/刷新/375px/200%通过，浏览器新增模型/确认/邮件/决定请求0。主Codex配置不改，原生委派0/消耗未知。

[preview.3](https://github.com/DayuGuo/Pivot/releases/tag/v0.2.0-preview.3)五附件已公开并核对服务端digest/大小，归档283310602字节，SHA256 `ad8de2c6a7411be9d1a3aa164542ea9b5a16ce4b76063104ce983ce54cfed6b0`。包来自成功原生CI的确切产物，内层七哈希/八条目校验，无运行密钥/数据库/用户文件；旧发行保留。升级沿用原安装用户/--state，管理器先备份DB/CAS，不重新init。未连接或更新用户VPS、原静态站保持不动。邮件始终禁用，关键决定继续人工确认。

失败均保留：最初两条浏览器重现重复POST/跨稿件忙碌残留；1190后Lead修改运行中验证脚本造成shell错位，未计整链通过；1194后的浏览器发现空搜索URL兼容/核对选择器范围问题，修复后资料29专项通过19.6秒，最终新增改问题回归并全量78通过。游标布尔/对象等类型500已改422；时间戳夹具被不可变guard拒绝、UTC命名错误均修正，保护未放宽。真实驱动先误要求元数据引用在全文，纠正后恢复同一回答无新增推理；浏览器baseURL修正后通过。日志artifacts/spec019-full-verify-accepted.log、spec019-gh-full-verify.log与spec019-final-amd64；未删除测试。规格spec019、审查报告spec019-review、维护地图与升级指南同步。下一批为作者关联不确定性及句子级证据评测。

## 当前增量：2026-11-04，spec018逻辑审查与模块维护（第一批已验收）

用户报告VPS已安装，本轮不连接或更新服务器。已重现确认回执跨import_id/不存在ID串用及损坏原件仍返回成功；追加不可变Approval和来源重验，保留v1指纹。重现列表4份资料10次内容查询和6条旧规则消息6次Answer查询，改为一次列表/一次批量历史。模型/DTO/访问/动作/查询/投影/原件来源分离，路由兼容导出，数据库四模型字段/约束AST逐项相同，无新迁移；来源映射和Alembic导入已更新。分层门禁正向通过、临时副本反向导入实验被拒绝。资料专项133项通过37.95秒，兼容专项3项通过1.34秒；本机完整verify实际退出0：1180 Pytest（371.77秒）＋66 Playwright（2.0m），远端同源1180（402.43秒）＋66（1.7m）及原生包/静态站CI均成功。旧发行后端逐字节匹配a408b63，实际三资料备份升级到809552d后完整快照/原件/会话与旧回执保留，错import重放409、schema无漂移。新后端真实DeepSeek4.101秒通过，输入5229/输出230tokens，费用null、原生子Agent0，正式邮件/决定0。[preview.2](https://github.com/DayuGuo/Pivot/releases/tag/v0.2.0-preview.2)五附件已公开，包/服务端SHA已核对；用户自行选择原状态路径update，本轮未更新VPS。本机主服务也已安全更新，旧模型环境保留为deepseek、邮件false，ORM门面与新模型同一类且主DB无漂移。计划spec018、维护地图module-map、审查报告spec018-review记录范围。邮件/关键决定权限不变。

## 当前增量：2026-11-04，完整VPS私人体验包（已发布预发行包）

spec017已实现独立离线镜像/Compose/私密初始化/保留卷启动/备份与隔离恢复，默认SSH环回3210，1472MiB总容器硬上限。无默认可用演示密码、邮件固定false，关键决定仍为负责人确认。16项部署配置测试与前端静态检查通过；包级真实演练发现并修复管理器文件创建、Compose参数及恢复属主权限问题。完整verify实际退出0：1173 Pytest（520.72秒）＋66 Playwright（2.0m）；修复后ARM64包Mock/真实DeepSeek两格式、独立核对/引用/重启/隔离恢复及两组实际浏览器均通过。补测八作者Word/25页公开PDF，真实提取/问答核心9份CPG/62条声明与原文一致，API峰值约136MiB，无OOM；不等于整机或全面语义证明。GitHub workflow授权已完成，最终源码a408b63原生amd64包CI41817314184、静态站CI41817314161、完整CI41817314556均成功；远端1173 Pytest（364.28秒）＋66 Playwright（1.7m）。最终包283307112字节、外层/内层SHA核对、三镜像amd64及487份依赖/字体许可已核对。[v0.2.0-preview.1](https://github.com/DayuGuo/Pivot/releases/tag/v0.2.0-preview.1)四附件已公开发布，仍未部署VPS。报告docs/development/private-vps-preview.md，用户VPS未连接，原静态站/资料未改。

## 当前增量：2026-11-04，公开真实论文评测与修复（已本机验收）

spec016使用3篇许可明确论文/6份文件：公开未发表8作者原生Word+明确转制PDF，两篇PLOS已发表editorial/essay的出版社PDF+明确JATS转制Word。文件/许可/金标准及复现入口见evals/public_documents，下载原件、失败回合和测试日志留artifacts/public-papers。不能冒称6份作者原件或3篇已审实验研究。独立署名审计26位次/38项机构链接无错误，原四作者PDF有1邮箱未自动提取而留空待补；ORCID不认证。

已修复：Word内部部件URI/EndNote缓存字段/PDF打开页误拒绝、多作者2048输出上限（提取6144、对话仍2048）、完整标签摘要、原样空白/字形间距证据恢复、明确机构编号错配及地址数字误判、姓名隔离邮箱补全。真实问答发现NBSP逐字失败已修复、存储仍为原文精确跨度；已完成第一轮6文件/12问答及独立浏览器确认/新版本/定位/刷新。语义复核发现重复历史回答、限定语强化、缺项断言、人名改写John/Johnson与规模/数量混淆，已新增上下文/终轮提醒、覆盖与窄范围姓名/比较校验；最终受影响实测回合已通过，历史错误保留不篡改。最终77项专项通过（19质量＋58对话）；完整scripts/verify.sh通过：**1157 Pytest（611.58秒）＋66 Playwright（2.9m）**，研究/边界门禁、Ruff/format、ESLint/TypeScript、迁移/结构漂移及准确API/Web镜像构建启动通过。4项第三方弃用warning与上一轮类别相同。证据artifacts/public-papers/full-verify-final-accepted.log、pytest.xml，不把中断旧运行算通过。交付报告见[真实论文评测](docs/development/public-paper-evaluation.md)。

独立文本检查：PDF25/4/6页，与Poppler最差逐页字符召回100%/99.911%/99.986%；Word正文105/70/80行对照LibreOffice，两转制Word无缺行，原Word11个自动项目符号未重建（去掉符号后0缺正文行），保留原差异并明确提示。指标不证明视觉顺序、公式、图片或科学结论正确。全迭代45个仅用于评测的公开论文资料包、26完成导入/36问答、19失败导入/2失败问答，147供应商attempt（134有效完成、13无效协议）、747,100输入/110,615输出tokens，费用null待账单；详见telemetry-summary.json，没有读取主模型密钥或全局认证。实际核对由浏览器脚本模拟演示编辑，不是专家/作者本人签收；6次确认后各v2已核对，后续问答重测0额外确认。最终12问选集在final-six-case-acceptance.json，实际重启6资料含完整历史/原件逐字节相等，同会话恢复provider仍deepseek。邮件/正式决定/正式稿件计数未变、Mailpit0、EMAIL_SEND_ENABLED=false，未部署公网。


2026-11-04推送前真实DeepSeek再检：3962ms完成inspect_manuscript/list_tasks只读工具回环，1条引用、state_changed=false；服务provider=deepseek/live_enabled=true/EMAIL_SEND_ENABLED=false，证据artifacts/live-model-smoke.json（忽略、不推送）。新增[保留资料的更新说明](docs/deployment/update-preserving-data.md)，区分静态Demo与完整栈，提供停写后数据库＋原件备份、快进更新、沿用原卷/模型环境及增量迁移命令；未连接VPS、未验证其完整栈容量或部署。此前GitHub main停留046b70d，本轮同步包含其后资料区、真实问答、文档导入和实测修复四个已验收提交。

## 最新增量：2026-11-03，PDF/Word导入、人工核对与原件定位

spec015已本地实现：文本层PDF/.docx原件私有CAS、完整提取和页/段映射、DeepSeek或明确Mock元数据候选、独立负责人补齐核对后一次建立新Version/Approval/Source/DossierCheck；上传不升版，模型没有确认工具。三新表36字段13命名约束、15b迁移、不可变历史与来源映射已登记；主库及隔离库已升级且check无漂移。只改元数据继承原件而新版本待核对，换TXT脱离来源；手改字段不伪造旧来源。

71解析、42导入API、54问答、18相关UI专项实际通过，最新迁移相关81项实际通过48.55秒。**最终串行scripts/verify.sh实际退出0：1112 Pytest（381.04秒）＋66 Playwright（2.0m）**。研究映射/架构边界、Ruff/ESLint/TypeScript、完整迁移/结构及准确前后端构建通过，证据artifacts/document-import-full-verify-delivery.log、pytest.xml。4条警告为Starlette兼容、恶意fixture add_js弃用、两条Alembic配置弃用；不影响通过，未删测试。此前1109+66为历史检查点。

真实DeepSeek PDF/DOCX各完整API通过（4.198/4.388秒）：2作者/14候选来源、原字节准确、上传未升版、测试驱动模拟演示负责人确认v2、幂等重放、QA尾标记PDF页2与Word提取段23。另真实Chromium两格式均通过精确引用/刷新/375px，页面错误0、发信/决定/确认请求0。实际重启API/Web后同登录会话完整投影/导入/原件逐字节相等，provider仍deepseek。证据artifacts/document-import-live.json、document-import-live-browser.json及document-import-live-restart.json。

首轮PDF2次HTTP成功但候选校验失败未落库；补安全诊断/更明确原文规则后两格式成功，不推断原先唯一错误字段。浏览器实测模型空终答曾存1条历史无结论，新增一次预算内纠正、再次空则明确失败/不存回合，3回归覆盖；历史不篡改。遥测含失败与脚本重试：16 attempts均HTTP成功，32,911输入/3,255输出tokens，费用null；3合成资料中2完成导入/6问答（含上述历史空回合）/1失败导入。原生委派未知消耗留null，未宣称DeepSeek原生子Agent。

最终阶段旧布尔测试因Lead重叠运行同验证栈E2E，全局回执/审计计数受其他期刊写入干扰，1111过/1失败；改为按测试期刊隔离计数，保留全部422/业务状态断言，28项重新通过后全量串行重跑。没有删除测试或已有数据。真实邮件和编辑决定计数未变，EMAIL_SEND_ENABLED=false；仅合成授权材料，不改主模型/全局认证，不连接VPS，公网静态Demo未更新。文本层限制/无OCR/复杂结构拒绝/专业复核关口见docs/development/document-import-review.md；此为私有资料区增量，不等于正式投稿也支持多格式。

## 最新增量：2026-11-03，资料区真实DeepSeek与逐字证据已验收

spec014已落地并更新本机`/library`：以当前保存版本的全文/作者信息为范围，通过read_dossier/search_dossier/lookup_reference/respond四个只读工具生成结论；每条claim至少有一条后端逐字校验的本轮来源引用，可点击定位原文行/作者字段，Unicode码点、版本digest与原文件SHA256均复核。长稿完整索引、有限读取，明确显示实际覆盖；未完整覆盖拒绝明确虚假的“已通读”句，无全文只按元数据回答。结论仍须人工复核，不把准确引用当作科学结论已被证实。

**最终scripts/verify.sh退出0：996 Pytest（387.65秒）＋59 Playwright（1.8m）**。研究映射/架构边界、Ruff/ESLint/TypeScript、完整迁移与结构检查、前后端构建通过，证据artifacts/grounded-full-verify-final.log。新增51项chat、82项外部协议；旧历史迁移范围按新表适配，最新完整Base结构不排除任何表。DossierAnswer与人类DossierCheck分开，数据库防嫁接/UPDATE/DELETE/TRUNCATE，有历史拒绝回退。

**真实DeepSeek API 4/4（3.228/6.369/6.717/2.989秒）**：全文+作者/贡献、真实Crossref DOI书目、危险操作不改变状态、新版本36条替换旧24条；逐字引文、当前版本、幂等重放无重复推理、刷新恢复全部实际检查。邮件草稿/批准、编辑决定、人类确认及资料核对计数前后相等。入口实际走deepseek-flash，不是Mock，不读取主机密钥；使用全新合成资料，没有调用用户既有稿件做外发验收。报告artifacts/dossier-live-acceptance.json。

**真实Chromium端到端通过**：输入问题→实际DeepSeek→响应→点击引用精确高亮→刷新→真实DOI链接保留，375px无横向溢出、页面错误0、确认/发信/决定请求0。报告artifacts/dossier-live-browser.json及桌面/手机截图。随后实际重启本机API/Web，同一登录会话恢复7条成功回合、完整作者/原文件/版本和全部引文逐项相等；provider仍deepseek，当前v3仍未人工核对。报告artifacts/dossier-live-restart.json。

首轮完整离线993+59通过后，真实首轮2次模型HTTP正常但终答参数未过校验，业务全部回滚；新增已读来源后的终答参数纠正最多1次，仍限3轮/8工具，最终完整校验不放宽。后续实测观察到citations过多/结论文本带URL，纠正后成功；51专项和最终全量覆盖该行为。安全诊断仅已知字段路径/固定类型，不含input/原始供应商输出。历史旧规则问题中的疑似密钥被排除，全部待发上下文再次检查。畸形Crossref HTML安全转unavailable。

真实遥测包含初次失败和浏览器脚本重复定位检查造成的全部调用：18个provider attempts均HTTP成功，业务成功回合7、失败回合1，输入38,724/输出3,667 tokens，2次工具参数纠正；费用未知为null，未把成功HTTP冒称成功业务，也不宣称实际发生过供应商503恢复。浏览器脚本曾修正同名引用按钮与重复DOI链接的选择器，追加模型回合已计入统计。artifacts/dossier-live-telemetry-summary.json；原生委派Token/费用不可获得见docs/development/dossier-grounded-delegation.json。

本机已安全更新且保持原DeepSeek模型环境，主Codex全局模型/认证配置未改，EMAIL_SEND_ENABLED=false。公网静态Demo未更新，不部署VPS。README/架构/安全/ADR-024/spec014及docs/development/dossier-grounded-review.md与实际行为同步。外部目前仅对资料或问题已提供的DOI做Crossref书目匹配，不读取外部全文、不做全网检索或ORCID认证；真实验收为合成短稿，长稿检索/预算/权限由自动测试覆盖。下一步为多样化公开稿件评测和人工反馈、外部全文授权/版本证据；正式受控试点仍须专业工程师复核。

## 最新增量：2026-11-03，真实内部审阅资料包已本地验收

用户同意先试第一切片，合同见spec013。`/library`提供左侧私有资料、中心规则对话、右侧完整录入/原文/版本；独立核对位于`/library/review/[versionId]?dossier=...`。四张真实PostgreSQL表保存全文CAS引用、有序作者/机构/通讯邮箱/ORCID/贡献/来源快照、不可变版本与人工核对、规则回合；复用登录、Action Gateway与审计。仅录入者且当前仍为本刊editor/chief_editor可访问，主编无默认全局权限；不创建正式稿件、不改author_draft，不冒充已认证ORCID。

**完整验收实际退出0：863 Pytest（339.01秒）＋53 Playwright（1.8m）**。`scripts/verify.sh`在publishing-os-verification独立Mock栈执行，研究映射/架构边界、Ruff/ESLint/TypeScript、迁移/结构一致性、前后端构建均通过。局部资料包28项覆盖严格布尔授权、空白正文拒绝、CSRF/幂等重放/撤权、跨刊/他人访问拒绝、精确核对digest、历史SQL防改/删除/TRUNCATE、完整base→13f迁移和安全回退。53项生产模型另实际重跑通过（34.96秒）。首轮全量7失败/854通过已修复：4个测试空库计数假设、3个历史迁移比较范围；没有删测试或清理已有资料。

**实际重启隔离DB/API/Web后恢复通过**：同登录会话读取完整元数据、原文逐字节及SHA256、相同版本/digest、2个版本/1个核对/1个规则回合和4条审计。证据artifacts/dossier-restart-acceptance.json；完整日志artifacts/dossier-full-verify-final.log。纯规则对话未调用模型，不作科学审阅，也没有邮件/正式决定工具；测试仅用合成资料，真实邮件0。

本机主服务已通过安全`./scripts/start.sh`更新到新代码，原DeepSeek选择前后均为deepseek；主DB结构check通过，未调用真实模型。3100实际Chromium从登录点“内部审阅资料”进入表单成功，375px无横向溢出、页面错误0，仅登录POST，无资料或模型变更。入口http://localhost:3100/library；账号editor@publishing.test / EditorDemo2026!。公网https://pivot.anotherdayu.com/仍为原静态Demo，本轮未连接或更新VPS。

源码/设计取舍及限制见docs/development/internal-dossiers.md，委派任务与不可获得Token/费用测量见dossier-delegation.json。本轮未读取全局认证文件、未改主模型配置、未使用暴露密钥。下一步是与确切版本绑定并可定位真实原文的只读模型问答；正式受控试点前仍需独立专业工程师复核权限、隐私、备份恢复与部署。spec011整体及真实模型可信引用尚未完成，不能把第一切片通过等同整个产品完成。

## 最新部署：2026-11-03，用户已上线公网Demo

用户已自行完成部署：https://pivot.anotherdayu.com/ 。本轮未登录或修改VPS，仅对公开页面使用正常TLS校验的HTTP客户端和隔离Chromium验证。HTTPS返回200，标题Pivot · 产品演示；页面/资源错误0、脚本错误0，375px无横向溢出。

现有Demo 11项浏览器回归在该公网域名实际全部通过（34.5秒）：会话切换与刷新、日历、作者/正文编辑、新稿录入、来源定位及变更失效、长正文保留、键盘/窄屏、HTML纯文本和危险请求边界。测试拦截全部业务API请求，实际API请求0；改动仅位于一次性浏览器的合成资料/localStorage，不写服务器业务数据。证据artifacts/pivot-public-site-e2e.log、pivot-public-site-smoke.json及桌面/窄屏截图。

README和GitHub homepage同步在线入口。本轮没有应用代码修改或真实模型/邮件操作，不以网页可访问替代SSH级OS/容器/防火墙/备份/生产安全验收；下方VPS未实装等为前次发行时的历史状态。

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
