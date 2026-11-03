# PDF / Word 导入、候选核对与原件证据

日期：2026-11-03。状态：本地实现及真实合成两格式/浏览器/重启已验收；最终完整回归见PROGRESS.md与交付记录。验收不代表真实试点或生产部署。

## 范围与不变权限

在spec013私有资料包和spec014版本证据问答之上，支持文本层PDF与Word .docx导入。仍须当前同刊、录入者本人、有效登录会话及editor/chief_editor角色；不增加正式投稿、共享资料或共同作者身份权限。只用合成或明确授权的公开非保密材料。

流程是：上传私有原件 → 本地完整文本提取和来源段映射 → 自动元数据候选 → 独立页面由负责人逐项核对并修改 → 显式确认完整快照后一次建立新版本。上传和模型提案不改变当前版本、人工核对状态或出版进度。邮件发送、录用/拒稿、撤稿和公开出版不在导入或对话工具中；EMAIL_SEND_ENABLED=false。

OJS/Janeway既有比较资料继续用于身份、稿件版本、文件关系及编辑确认分离的设计背景。新增导入提案、人类批准和原件来源关系属于本项目project_governance，不声称上游存在这三张同名表或具有相同AI/解析安全保证。解析官方依据与实际组件实验见[文档提取研究](../docs/research/document-ingest.md)。

## 三表与字段合同

迁移`15b39ecf7286`，前序`14a28dbe6175`。模型位于`apps/api/publishing/domain/document_models.py`。不放宽正式出版FileObject的UTF8/1MiB合同；原PDF/DOCX使用独立私有二进制CAS，批准后的规范化全文进入既有文本CAS与DossierVersion。字段/命名约束/迁移/SQL指纹见来源映射。

**DocumentImport / publishing_document_imports**

字段：id、dossier_id、journal_id、base_version_id、base_revision、filename、media_type、byte_size、sha256、storage_key、extraction_json、proposed_data、field_sources、metadata_provider、metadata_model、telemetry_json、digest、created_by、created_at。

- id是导入提案身份；dossier_id/journal_id/base_version_id通过`fk_document_import_base`绑定同包同刊实际基础版本，`uq_document_import_tenant`供批准复合外键使用。base_revision保存发起提取时的当前修订，提取/模型等待期间新版本出现则原候选不再可确认。
- filename、media_type、byte_size、sha256、storage_key描述保留原字节的私有原件，文件名不进入存储路径；`ck_document_import_shape`限制1..5MiB、正修订与SHA/digest格式。二进制原件与规范化UTF8文本的hash用途分开。
- extraction_json冻结完整规范化text、text SHA256、分段kind/number/start/end/text、解析器版本、固定warnings及页/段计数。位置为Python Unicode码点，不是UTF8字节；PDF定位页，DOCX定位提取段，不能冒称Word真实排版页码。
- proposed_data是未经核对的DossierData候选；field_sources冻结每个自动候选字段的value、逐字quote、原文start/end及页/段来源。负责人手改值必须保留人类来源语义，不能伪装成从原文件逐字抽取。
- metadata_provider/model明确记录DeepSeek还是Mock本地标签规则，telemetry_json仅安全数值/固定标签，未知消耗或费用不填0。`ck_document_import_content`只提供基础JSON对象/数组、MIME及provider检查，不冒称完整JSON Schema。
- digest绑定包/基础版/修订、原件身份、完整提取、候选、字段来源及provider/model；created_by是实际录入者，created_at是系统事实时间。读取、确认时重算digest并核对实际原件字节及提取文本SHA，不只信DB中的字符串。

**DocumentApproval / publishing_document_approvals**

字段：id、import_id、dossier_id、journal_id、version_id、reviewed_data、digest、reviewer_id、session_hash、created_at。

- `fk_document_approval_import`把导入id/包/刊绑定同一提案；`fk_document_approval_version`把新版本id/包/刊绑定同一资料。`uq_document_approved_import`和`uq_document_approved_version`防止一次导入生成多次批准或一版配多份批准；`uq_document_approval_tenant`供Source绑定完整关系。
- reviewed_data保存负责人最终核对并允许修改的完整元数据快照；digest绑定import digest、核对数据与新版本content_digest，`ck_document_approval_snapshot`检查摘要格式和JSON对象。
- reviewer_id/session_hash是当前有效登录负责人及会话摘要，不是模型宣称的批准。确认接口严格只接收JSON布尔true，拒绝数字/字符串；未核对、缺项、旧基础版、旧digest、失效角色/会话或损坏原件都不能建立新版本。
- 导入批准事务同时追加新DossierVersion、DocumentApproval、DocumentSource及本版DossierCheck；不再要求同一版重复完成一次普通资料确认。模型不能调用这个最终确认工具。

**DocumentSource / publishing_document_sources**

字段：version_id、dossier_id、journal_id、import_id、approval_id、origin_digest、created_at。

- version_id是本版来源关系主键；`fk_document_source_version`确保包/刊/版本一致，`fk_document_source_approval`绑定批准id/导入id/包/刊四列。原件关联是显式事实，不能因为两个TXT内容相同就推断它们来自某个PDF。
- origin_digest把导入/批准digest、该版content_digest和原件SHA连接，`ck_document_source_digest`检查格式。应用仍须重验原件、提取全文字节及版本FileObject，而非把hash列当作完整性已获证明。
- 仅修改元数据且沿用提取全文时，新增版本显式继承原件及同一原批准事实，同时重绑定新origin_digest；新元数据版仍需本版核对，不继承旧DossierCheck。显式替换TXT/Markdown正文不继承PDF/DOCX来源，历史版本的原件关系保留。

15b的插入guard检查包/刊、当前基础版、现任录入者角色、批准版本/数据/会话及原件-批准-规范化文本关系；Answer新增原件guard绑定引用中的origin_digest和原件SHA。三表均禁止UPDATE/DELETE/TRUNCATE，有任一导入/批准/来源历史时拒绝破坏性回退。SQL不能读取CAS，也不能代替应用的真实字节、逐字引文和段映射校验。

## API、候选和人类核对

`POST /api/dossiers/{id}/imports`接收request_id、expected_revision、version_id、file和authorized_material=true；CSRF、期刊/所有权、幂等及原权限重验走Action Gateway。提取/模型网络不持资料写锁，完成后才锁定并确认原基础版尚未变化；业务事实、回执与安全审计同事务。保存导入提案后当前版不变，失败不保存半个Import或自动降级伪造Mock成功。

DeepSeek使用受限propose_metadata提取器，只生成带逐字quote的题名/摘要/关键词/作者候选，未知字段留空；输入是有界前置信息，不声称识别了全文所有作者。Mock仅为明确标记的本地标签识别。value必须是quote原样子串、quote必须来自提取原文；通讯作者必须有包含该人姓名与明确通讯标记的原文。ORCID格式归一不等于身份认证，贡献、声明或关键权限不由模型臆造。

独立核对页展示可改候选、完整提取正文、原件下载、页/段、字段来源和解析提示。负责人必须本人阅读后新勾选确认，`POST /imports/{import_id}/confirm`绑定request_id、当前expected_revision、导入digest、完整最终data及acknowledged=true。请求锁/资料锁后重验身份与原件，修订或快照变化返回冲突；重复同UUID不创建第二个版本或第二份批准。

## 原文引用

当前版本对话仍只读。正文quote先按spec014逐字核验版本文本，再按quote实际start/end与原始提取segments的重叠计算所有页/段位置。不能固定贴第一页、只按source chunk起点推断页码，跨页/段引用保留多个location。metadata引用仅在当前叶字段值与原候选来源值精确一致时附原件来源；修改后的值可以引用该版已录入字段，但不得伪称原文候选。

浏览器定位重新获取授权版本，核对版本digest、文件hash与origin_digest，右侧展示精确原文/页或段。原件下载以attachment返回，不能把PDF/Word主动内容嵌进产品执行。历史引用只定位其原版本，不覆盖当前未保存表单。

## 解析边界与验收目标

仅文本层PDF与.docx，扫描无文/任意空白PDF页、加密、旧.doc、超限、异常OOXML/ZIP、宏/嵌入/修订等明确拒绝。普通HTTP/HTTPS/mailto外部超链接只保留显示文字，不请求目标；外部模板/链接图片等拒绝。图片/图表/公式不作语义转录，PDF阅读顺序与DOCX线性段编号须提示负责人核对。资源限额子进程不等于OS沙箱或生产安全认证。

必须实际验收：

1. 两份有效合成PDF/DOCX上传后得到完整文本和作者候选，当前版本/核对状态不变；读取/重试/刷新可恢复。
2. 负责人在独立页修改完整候选、核对原文并确认，恰好建立一版及批准/来源/资料核对，重复请求不再建版；缺项/false/数字/旧digest/旧基础版均拒绝。
3. 规范化文本与私有原件逐字节/hash绑定，原件/提取被改、权限/会话在解析或锁等待期间撤销、同刊他人/跨刊访问均不能绕过。
4. 真实/Mock引用定位正确PDF页或DOCX段，包括跨段quote；手改元数据不伪造原文来源；仅改元数据继承原件但不继承核对，换TXT脱离原件。
5. 三表完整迁移与Base一致、历史防改删/TRUNCATE/嫁接、空迁移可回退而有历史拒绝；全部后端/浏览器/静态及scripts/verify.sh运行，真实DeepSeek结果另记，不能用模拟HTTP代替真实验收。

已实际通过：解析71项、导入API42项、含空终答纠正的问答54项、UI相关18项；真实DeepSeek PDF与DOCX各一轮完整导入/确认/问答，另实际Chromium各一轮引用定位/刷新/375px检查；API/Web重启后完整数据与原件逐字节一致。最终全量计数、失败修复与证据见[交付记录](../docs/development/document-import-review.md)及PROGRESS.md。局部测试有重叠，不相加当作全量总数。
