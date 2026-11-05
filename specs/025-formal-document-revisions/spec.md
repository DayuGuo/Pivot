# 正式 PDF/Word 导入与修回对照

本轮在 PR #4/#5 获授权合并后的 main 上增量实现，不部署 VPS，不重置已有数据。遵循 PRODUCT.md、SECURITY.md 与 DESIGN.md；对话仍常驻主体位置。

## 最小闭环

作者/稿件负责人在 author_draft 或 author_revision 中上传文字层 PDF 或已处理修订/批注的 DOCX，明确来源授权与完整/节选范围。提取不会修改正式文件。独立核对页展示原件、全文、解析限制及正文起止页/段，三项显式确认后，精确选定文本才作为当前草稿用途文件。提交投稿或修回仍使用既有独立审核/确认。

原件、提取快照、正式版本/用途、选择范围、确认人和会话不可变绑定。草稿替换文件保留旧批准；新版本继承来源不伪装成新负责人确认。对照只读本轮正式请求、作者可见报告、旧/新稿和本次回复；不从资料区最近上传或题名推断正式关联。

## 验收约束

- PDF/DOCX 准备、核对、刷新恢复、提交修回和只读对照走实际 API/PostgreSQL/CAS；无假保存按钮。
- CAS、期刊、归属、稿件、草稿版本、revision、实际角色和会话重复校验。旧准备不能重基至新内容，同 UUID 精确恢复、不同内容拒绝。
- 原件下载只开放作者与实际非冲突编辑/主编的冻结版本；审稿人继续只读明确授权的匿名文本，不因可读文本取得含身份/属性的原始二进制。
- 长意见不丢尾段，每批最多8项，其余可继续；部分段落不能认定整项完成。已有输入中追加继续提示仍应从指定项开始。
- 模型逐项返回包含非要求/不确定项，工具 schema 限定实际 ID/精确数量；格式或引文不合格仅纠正一次，同一60秒期限和证据快照，再错则失败。纠正不放宽逐字、唯一、窗口、版本和改动校验。
- 真实公开原稿/修订稿、明确获许可的评审意见和作者文章内修订说明入回归。说明节选不得证明作者完全没有回应；不把回复“已改”或附录当成正文改动。
- 引用同时定位实际正式版本文本、PDF页/Word段、原件SHA；模型不得生成任意文件URL。
- 邮件默认禁用，重大操作继续独立负责人确认。AI只读对照不得新建决定、proposal或HumanConfirmation。

## 不宣称的能力

不提供 OCR、公式/图片语义、复杂 Word 排版还原或病毒扫描；现有隔离解析/体积/页数/超时约束沿用。Word公开样本是许可XML派生文本OOXML，不是出版社原生Word。作者修订说明是实际已发表说明节选，未取得许可的网页评论和完整回复信不归档。不将模型自查、小样本内部测试或相同提供商第二遍检查称为专家认可或科学准确率。

## 新增数据合同

**FormalDocumentImport / publishing_formal_document_imports**

- id：不可变导入身份。manuscript_id/journal_id/version_id：期刊、稿件和实际可编辑草稿复合归属；base_revision：提取时的处理修订号，从0开始。
- purpose：manuscript / blinded_manuscript / response；filename/media_type/byte_size/sha256/storage_key：原始二进制元数据及受控CAS键，5MiB上限。
- extraction_json：完整规范化全文、页/段 start/end/text、parser/warnings、提取SHA和material_scope；不是任意可执行文档。source_kind/source_note：synthetic或public_authorized及授权/转换说明。
- digest：上述全部来源和快照的确定性摘要。created_by/created_at：实际负责人和UTC时间。准备不改变正式版本或revision。按期刊/稿件/版本/时间/id索引有界待核对分页。

**FormalDocumentBinding / publishing_formal_document_bindings**

- id/file_id/manuscript_id/journal_id/version_id/file_object_id/import_id：批准/继承的证据身份、当时实际文件关系和精确CAS、导入来源。file_id为档案字段，插入和现行读取核对元组，不随草稿文件删除级联。
- kind/parent_id：confirmed为根本人批准，inherited引用原来源且不得伪造新确认；每个导入只准一根批准，每现行文件唯一来源。复合FK禁止跨期刊/稿件/import继承。
- confirmed_by/session_hash：根批准仅实际作者与有效本人会话；继承必须为空。selection_start/selection_end：完整首尾页/段的Unicode字符界限；数据库核对选择文本UTF-8字节长度与SHA等于正式FileObject。
- digest/created_at：完整来源/批准/范围/版本证据摘要及UTC时间。新增两表行不可更新/删除，禁止TRUNCATE；已有证据时禁止downgrade。

这些是项目独立设计的治理实体，并非OJS或Janeway的同名表。成熟系统来源只证明稿件/文件历史/轮次/修回请求需要分离，具体规范详见docs/research/formal-document-revisions.md。新增表32字段、具名约束和迁移函数由研究索引绑定至实际模型AST与增量迁移，运行结果另记PROGRESS。
