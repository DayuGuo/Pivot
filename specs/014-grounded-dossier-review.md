# 当前资料版本的有证据只读审阅

日期：2026-11-03。状态：实现合同与静态映射；本文件不表示真实供应商、数据库、浏览器或完整验收均已通过。运行结果由Lead记入PROGRESS.md。

## 范围与既有边界

在[spec013](013-internal-review-dossiers.md)的私有资料包之上，接通当前版本的全文与作者元数据问答，保存可追溯的模型结论及证据。本片不增加正式稿件、作者账号、业务状态机或资料共享权限。访问仍须同刊、created_by本人、当前有效会话且仍为editor/chief_editor；其他主编或编辑不能凭角色读取他人的资料。只使用合成或明确授权的公开非保密材料。

模型意见与负责人的独立核对分开。新增Answer不创建、更新或替代DossierCheck，更不能将“已核验书目信息”“模型高置信度”或聊天中的“确认”作为关键权限证据。正式邮件、投稿、录用、拒稿、撤稿及公开出版仍受既有确定性后端与独立负责人确认约束，不在本片工具白名单中；EMAIL_SEND_ENABLED=false保持不变。

OJS/Janeway提供的身份、版本和出版事实分离模式继续作为比较背景。本片的模型结果、引用精确性、阅读覆盖和供应商边界全部是project_governance自有设计，不声称上游存在同名Answer表、模型审阅机制或相同安全保证。研究参考及验证范围见[外部来源记录](../docs/research/dossier-sources.md)和[既有数据库取舍](../docs/research/library/comparison/database-decisions.md)。

## 增量表与字段合同

迁移：`14a28dbe6175`，前序`13f17cad5064`。模块：`apps/api/publishing/domain/dossier_chat_models.py`；来源及AST位置见[来源映射](../docs/research/library/comparison/source-to-implementation.json)。不修改既有四表的字段或约束，保留此前规则回合。

**DossierAnswer / publishing_dossier_answers**

字段：id、dossier_id、journal_id、version_id、result_json、created_at。

- id同时为主键和指向publishing_dossier_turns.id的外键，一次回答的可读对话与结构化证据一一对应，不能另配一个无归属的模型结果。
- dossier_id、journal_id、version_id通过`fk_dossier_answer_version`三列外键绑定同一资料包、期刊与不可变版本。DB插入guard另验Turn的用户/包/刊/版、当前版本和录入者现任编辑角色；它不授予访问权。
- result_json是`dossier_answer.v1`的完整有界结果快照：provider、model、claims、questions、external_references、coverage、telemetry。`ck_dossier_answer_result`要求JSON对象、固定schema、mock或deepseek、claims数组、coverage对象，且JSON文本不超过131072字节；以COALESCE拒绝SQL NULL导致的检查绕过。结构化DTO和逐项引用校验仍在应用层，不把这个基本CHECK称为完整JSON Schema验证。
- created_at保存本次结果事实的时间，不从外部来源或模型文本推断。

claims的每项text必须有至少一项本地citations；每个citation记录本轮已发放source_id、kind、逐字quote、source_text、label、version_id/version_no、content_digest、正文file_sha256、start/end及字段路径或行号。start/end是相应正文或字段值的Unicode码点偏移，不是UTF-8字节位置。模型不能提供任意自选版本、文件、对象身份或访问权限。

external_references仅保存本轮通过固定Crossref适配器确认同一DOI的书目记录和规范链接；不是外部全文证据。coverage记录全文/元数据索引的总块与已发放块、字符覆盖、是否存在全文及是否全部读取。telemetry仅保留固定供应商/模型标签、安全数值和错误码，未知Token/费用为null；不得保存凭据或原始供应商错误。

14a插入guard检查每个claim有非空引文数组、每项citation具有当前版id/digest、有效text或metadata kind与非空quote；正文项另绑定本版实际FileObject的SHA256。它不能读取CAS或证明逐字字符串在正文内，实际字节完整性与精确引用必须由应用复验。UPDATE/DELETE/TRUNCATE沿用13f的不可变保护；有Answer历史时拒绝破坏性downgrade，空增量允许回退。新Answer不会让旧回合脱离原版，也不会改变已核对版本。

## 只读工具与证据校验

`POST /api/dossiers/{id}/chat`接收request_id、expected_revision、version_id和message，CSRF与Action Gateway强制执行。所有完成事实、回执和publishing.dossier_answered审计同事务保存；审计只引用版本/修订，不复制正文或作者邮箱。旧规则assist可以保留，但新资料区的模型对话使用chat而非冒称规则引导。

模型仅有四个工具：

1. read_dossier：按当前版完整索引分页读取有界片段。
2. search_dossier：在当前版全部正文/元数据索引检索，返回实际片段与阅读覆盖。
3. lookup_reference：只接受当前资料或本轮问题中存在的DOI，固定端点查询Crossref。
4. respond：唯一终答入口，提交带本地精确引文的结论、待补问题及本轮核验过的外部DOI。

每项模型引用必须来自本轮工具真正发放的source_id集合，quote逐字包含在该片段中，正文引文至少8个字符；未知ID、改写引文、旧版/他人资料、未核验的外部DOI或模型自行生成网址均拒绝，不保留未经校验的自由文本结论。保存由服务端补入版本、digest、文件hash、位置与原片段，不能信任模型自行宣称的来源。

全文建立完整索引，长文按预算分块读取/检索，不静默把截断前缀当整篇。coverage.complete=false时明确表示只阅读部分材料，不声称已审阅全文；file缺失时明确表示没有全文。缺乏支持的信息转为待补充问题。精确引用仅证明出处和字节/版本一致，不证明模型推理正确、研究结论成立或引文足以支持全部论点，负责人仍需复核。

外部元数据结果必须匹配查询DOI，链接由适配器生成且仅指向doi.org和Crossref固定记录；不直接使用模型网址或远端任意URL。404、限流、超时、响应错误与DOI不符均不能标为核验通过。仅书目元数据不能作为科学全文已读的证据，也不证明作者ORCID身份、查重、研究质量或撤稿状态。出域仅发送所需DOI标识符，不发送全文或作者信息给Crossref。

## 权限、并发、故障与预算

原会话、角色、期刊、录入者、expected_revision/version_id在模型调用、工具读取、外部请求和写锁等待后重新检查。供应商网络不持资料写锁；最终写入前才锁定资料，重读实际CAS字节、长度/SHA256与metadata/file/name/media的快照digest。并发修改、新版本、撤权、注销或文件损坏不得保存旧上下文回答。任何幂等回执重放也必须检查当前对象访问权，不凭旧UUID恢复已撤销权限的数据。

最多3个模型轮次和有界工具次数，共享60秒期限；最后一轮仅暴露respond。传输沿用既有明确启用的DeepSeek模型适配器、固定HTTPS端点、禁止代理/重定向/密钥日志、有限同请求推理重试及脱敏计量。供应商故障或最终无效回答回滚Turn/Answer/Receipt，不静默降级Mock；仍有原权限时可另记固定失败码和计量。Mock仅用于明确选择的隔离测试，界面持续标记模拟。

正文、作者字段、问题、历史与外部记录都为不可信数据，不能改变系统规则、选择其他对象或获取业务操作工具。疑似API密钥在材料或问题中出现时阻止出域，不读取全局认证文件。历史问题仅在同版使用且不能作为原文证据；切换资料/版本后不自动把旧回答当新版本结论。

## 验收目标与未完成范围

下列为必须实际执行的目标，不因静态合同或源码存在而视为通过：

1. 合成当前版全文/作者/贡献问答经真实DeepSeek工具读取，结论附逐字证据；点引用定位本版原文或字段，刷新后结果与核验来源保留。
2. 超出首段的长正文能够检索或翻页读取，覆盖计数真实；全文缺失、阅读不全与无证据问题不伪装完整科学审阅。
3. 外部公开DOI真实查询成功并输出规范可信来源链接；错误DOI/任意URL/重定向/响应超限和伪造外部引用拒绝。
4. 未授权角色、同刊他人、跨刊、旧版请求、模型期间撤权/并发保存、写锁后身份变化及CAS篡改不能落入有效回答；旧回执与历史读取重新鉴权。
5. 注入正文、未知/发送邮件/编辑决定工具、假引文、假source_id、无结构自由文本、超预算及供应商超时/503均失败关闭，不生成DossierCheck、正式稿件、决定或外发邮件。
6. 14a完整升级与metadata一致、空增量可回退、有Answer历史拒绝回退；Answer及引用JSON不可直接改删或TRUNCATE，直接SQL错误kind/包/刊/版绑定拒绝。
7. 后端、浏览器、精确引用/版本隔离、刷新/重启测试与scripts/verify.sh全部实际运行，并另记录真实DeepSeek验收；隔离Mock/模拟HTTP通过不代替真实供应商结果。

未包含任意网页搜索/抓取、外部论文全文获取、ORCID OAuth、自动科学真实性判断、查重/伦理认证、资料共享、真实邮件外发或生产部署。spec011的专业复核与试点放行条件继续有效。

本片已由Lead完成本地验收：scripts/verify.sh退出0，996后端＋59浏览器；真实DeepSeek API4/4、真实浏览器输入/引用定位/刷新、服务重启恢复通过。补充隔离SQL事务实测NULL/未知引用kind拒绝及有Answer历史的14a回退拒绝，事务全部回滚。实际测量、初次协议失败与有界纠正记录见PROGRESS.md及docs/development/dossier-grounded-review.md；不据此宣称科学正确性或生产安全认证。

2026-11-03文档/映射子任务实际运行`python scripts/check-research-library.py`退出0，errors=[]：30类363字段、29个domain Base类完整覆盖，5份additional contract与5份增量迁移指纹一致；DossierAnswer的6字段、2项命名约束及14a guard函数逐项绑定。此前13f四类仅因import偏移机械刷新AST行号，旧字段/约束/来源语义保留。组件证据引用Lead已执行的81项联合JUnit报告，其中53项属于production模型、28项属于intake；production的36.638秒为该53项testcase time属性之和，不是独立墙钟运行。本子任务仅核对既有XML与静态来源，没有重新执行这些数据库测试，也没有执行真实模型或浏览器验收。
