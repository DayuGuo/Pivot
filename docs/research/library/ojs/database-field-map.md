# OJS 3.5.0-6 的实体、字段和约束

以下“观察”均来自固定提交，文件可在 [source-manifest.json](source-manifest.json) 找到带完整SHA的官方URL与本地快照。表结构主证据为迁移；API JSON schema用于补充属性语义/校验，不能等同DB列。字段集合是业务关键部分，完整选定表定义见 [schema-inventory.json](schema-inventory.json) 和sources，未把本文件冒称完整DDL。

## 1. 投稿身份与可发表版本分开

**观察**：PKP `classes/migration/install/SubmissionsMigration.php` 定义 `submissions`，OJS `classes/migration/install/OJSMigration.php` 定义 `publications`。

| 实体 | 关键字段 | 实际约束/语义 |
| --- | --- | --- |
| submissions | submission_id, context_id, current_publication_id, date_last_activity, date_submitted, last_modified, stage_id, locale, status, submission_progress | context_id→journals；current_publication_id可空，FK在publications创建后补，删除publication时设空；date_submitted可空，支持未完成投稿；stage_id与status独立；submission_progress是准备进度，不是学术结果 |
| publications | publication_id, submission_id, version, status, date_published, last_modified, primary_contact_id, section_id, issue_id, access_status, url_path, doi_id, seq | submission_id必填FK；version在该安装定义可空，不能声称DB已有(submission_id,version)唯一约束；primary_contact/section/issue/DOI可空且多为set-null；publication可以存在而未排期/未发表 |
| publication_settings | publication_setting_id, publication_id, locale, setting_name, setting_value | (publication_id,locale,setting_name)唯一；标题/摘要等多语言字段通过这里扩展，不是所有元数据都在publications固定列中 |
| submission_settings | submission_setting_id, submission_id, locale, setting_name, setting_value | 同样的实体+语言+名称唯一；不是新的稿件版本 |

`PKPSubmission.php` 中 STATUS_QUEUED=1、PUBLISHED=3、DECLINED=4、SCHEDULED=5；这组终态/队列状态并不能替代 `stage_id` 的投稿、审稿、编辑、制作流程。UI单个主状态通常是多个事实的投影，而不是往status里添加任意标签。

`classes/publication/Repository.php::version()` 会复制publication、增加version、清空datePublished并恢复queued状态，复制关联作者并重指primaryContact；DOI是否重新生成还取决于期刊版本策略。因此“创建修订版本”和“覆盖当前标题/作者列表”不是同一操作。OJS的publication版本偏出版元数据，不能直接宣称与我们的逐次稿件文件版本完全同义：Publishing OS应明确不可变提交版本/轮次使用哪个版本ID。

**对本项目的建议**：保留 manuscripts.id 为稳定投稿身份；新增 manuscript_versions 记录冻结提交/修回的内容、作者与文件快照，current_version_id为投影。首版就建立(manuscript_id,version_no)唯一及同稿复合FK，而不是照抄上游可空version。phase/current_step 与稿件终态分开。

## 2. 作者、登录用户、机构与通讯人

主证据：SubmissionsMigration、AffiliationsMigration、`schemas/author.json`，以及publication版本复制逻辑。

| 实体 | 关键字段 | 语义与边界 |
| --- | --- | --- |
| authors | author_id, publication_id, email(90), seq, include_in_browse, user_group_id | 作者归属于publication，不能把它当users的一行；seq保存署名顺序；user_group_id是作者/译者等贡献角色，可空FK；email不是自动授权账号的依据 |
| author_settings | author_id, locale, setting_name, setting_value | 每个作者的本地化givenName/familyName/preferredPublicName、ORCID、biography等属性由schema解释；(author_id,locale,setting_name)唯一 |
| author_affiliations | author_affiliation_id, author_id, ror | 一位作者可有多个机构；ror可空、有索引；不能把ROR必填当作投稿普遍要求 |
| author_affiliation_settings | author_affiliation_id, locale, setting_name, setting_value | 机构名称等本地化数据；实体+locale+setting_name唯一 |
| publications.primary_contact_id | author_id引用 | 通讯联系人的作者记录单独保存，不等于投稿者账号，也不等于每一位共同作者都有编辑系统访问权 |

API author schema把 email/givenName/publicationId/userGroupId列为required，familyName又可空——单名文化与本地化不能硬编码为“所有作者必须姓+名”。ORCID有专用校验；schema中的OAuth token属性为writeOnly，**不能把令牌作为文章公开元数据或交给LLM**。

**建议**：每版保存author_snapshots（顺序、显示姓名、邮箱、ORCID、机构、通讯标记、贡献）；linked_user_id可空，另用作者授权关系控制登录可见性。本项目当前User.name不够承载署名历史。邮箱长度应按自己的标准合理选择，不能因OJS旧schema的90字符限额机械缩短已有254字符账号邮箱。

## 3. 文件对象、阶段文件、修订与评审授权

主证据：FilesMigration、SubmissionFilesMigration、ReviewsMigration、API submissionFile schema。

| 实体 | 字段/关联 | 实际事实 |
| --- | --- | --- |
| files | file_id, path(255), mimetype(255) | 只是存储对象定位；这份安装定义没有sha256/扫描状态/不可变内容哈希，不得把它描述为已具备内容寻址/病毒扫描 |
| submission_files | submission_file_id, submission_id, file_id, source_submission_file_id, genre_id, file_stage, viewable, uploader_user_id, created_at, updated_at, assoc_type, assoc_id | 属于稿件且指向物理file；source_submission_file_id可空自引用，表达派生；genre为空允许；file_stage是用途/阶段，与主稿件stage不同；uploader可空便于账号删除后保留文件 |
| submission_file_revisions | revision_id, submission_file_id, file_id | 逻辑稿件文件的版本与具体存储对象分开；不要仅替换同一路径丢失历史 |
| review_round_files | review_round_file_id, submission_id, review_round_id, stage_id, submission_file_id | (submission_id,review_round_id,submission_file_id)唯一，轮次可供审稿的文件集合 |
| review_files | review_file_id, review_id, submission_file_id | (review_id,submission_file_id)唯一；每位审稿人的可见文件还可以进一步不同 |

许多单列外键只保证“ID存在”，没有直接保证同稿复合关联一致。Publishing OS应更严格：file-version/round/assignment必须同稿同刊，下载接口与查询序列化均重新检查授权。仅隐藏前端作者名字并不能防止原稿、文件名、文档属性、旧版文件泄漏身份。

**建议**：file_objects保存sha256、size、media_type、storage_key、scan_status；version_files保存明确purpose/visibility；匿名稿与带署名稿分别引用。首版可限制小型授权合成文本文件，校验实际字节、大小与哈希，不能只保存文件名或声称已支持未实现的PDF/DOCX解析。

## 4. 成员角色、阶段分派与建议权

主证据：RolesAndUserGroupsMigration、StageAssignment模型、`decision/Repository.php::validate()`、IsRecommendation trait。

| 实体 | 关键字段/约束 | 对权限的意义 |
| --- | --- | --- |
| user_groups | user_group_id, context_id, role_id, permit_self_registration, permit_metadata_edit, permit_settings, masthead | 期刊内角色组与能力开关；管理员组可有特殊null context语义，普通期刊组不能照搬为全局权限 |
| user_user_groups | user_user_group_id, user_group_id, user_id, date_start, date_end, masthead | 用户与角色组多对多，有有效期；该安装定义没有强制user+group唯一，不能推断永远只有一段历史任职 |
| user_group_stage | context_id,user_group_id,stage_id | 三者唯一；角色组允许访问哪些阶段，不是某位编辑已被分派到具体稿件 |
| stage_assignments | stage_assignment_id,submission_id,user_group_id,user_id,date_assigned,recommend_only,can_change_metadata | submission+group+user唯一；具体稿件的参与/访问授权；recommend_only和可改元数据能力单独保存 |
| review_assignments | reviewer_id + round/submission | 审稿人另有专用分派，不能只看编辑stage_assignments |

决定Repository会验证decision type、submission ID、decision所属stage与稿件当前stage一致；建议型决定还要求至少存在能正式决定的已分派编辑。**建议与最终决定是显式不同能力**，不是用户顶着“editor”全局角色就能做所有事。

**建议**：Membership改成用户/期刊/角色多对多或关联多角色表，保留任职有效期；Assignment保存稿件级capability与重分派历史。核心资格=期刊成员+有效分派/作者所有权+阶段+冲突，不能只写role IN(editor,chief)。主编同时是作者时必须拒绝自批。

## 5. 审稿轮次、邀请、响应、报告

主证据：ReviewsMigration、ReviewFormsMigration、ReviewRound模型、ReviewAssignment模型。

| 实体 | 具体字段/约束 | 必须保留的不同事实 |
| --- | --- | --- |
| review_rounds | review_round_id,submission_id,stage_id(nullable),round,review_revision,status | (submission_id,stage_id,round)唯一；PostgreSQL普通唯一索引对NULL的语义要另审，不能直接推断所有NULL阶段都只一条 |
| review_assignments | review_id,submission_id,reviewer_id,review_round_id,stage_id,round,step,review_method,review_form_id | 分派归轮次和稿件，review_method保留匿名策略；round字段冗余不能任意改成与round_id不一致 |
| review_assignments 响应/时刻 | date_assigned,date_notified,date_confirmed,date_completed,date_considered,date_acknowledged,date_due,date_response_due,last_modified | 邀请回复期限与报告期限分开；date_notified不等于接受，date_completed不等于编辑已确认有效 |
| review_assignments 冲突/异常 | competing_interests,recommendation,declined,cancelled,date_cancelled,quality,date_rated,date_reminded,reminder_was_automatic,considered,request_resent | 接受/拒绝/取消/完成/已确认不是同一状态；取消不删除历史 |
| review_form_elements | review_form_element_id,review_form_id,seq,element_type,required,included | schema式问题配置；included的作者可见语义需结合应用层，不能把全部报告直接给作者 |
| review_form_responses | review_form_response_id,review_form_element_id,review_id,response_type,response_value | 表单答案属于一份具体评审；名为review_form_responses_unique的索引在安装定义实际是普通index，不能误称DB唯一约束 |

**易踩坑**：源码注释明确，通常同轮不能重复分派同一审稿人，但账号合并后会保留两份历史，因此没有给(round,reviewer)加唯一键。我们的设计可选择约束同轮有效邀请/分派，取消或归档的历史仍保留；合并账号要有显式策略，不能凭简单unique导致迁移丢报告。

OJS3.5另有通用 `invitations` 表：invitation_id、key_hash、type、user_id/inviter_id可空、expiry_date、payload JSON、status枚举、email可空、context_id、timestamps及状态/期刊/用户/type组合索引。这是通用人员/操作邀请基础，不能因为名字像review invitation就把旧review_assignments中的所有工作流时间戳丢掉。

`ReviewRound::determineStatus()`综合决定、分派状态、逾期、编辑建议与确认推导当前轮次。PENDING_REVIEWERS、PENDING_REVIEWS、REVIEWS_READY、REVIEWS_COMPLETED、REVIEWS_OVERDUE等不是一条邀请的status直接复制。

**建议**：显式review_rounds + review_invitations + accepted review_assignments + immutable/submitted review_reports；首版将作者可见意见与编辑私密意见分开。邀请响应只允许本人，提交报告绑定已接受分派和固定版本，修改生成新报告版本/草稿而非覆盖已提交报告。

## 6. 编辑决定与生产出版

主证据：edit_decisions迁移、Decision常量与Repository、OJS publications/issues/galleys迁移、production指南。

| 实体 | 字段 | 设计事实 |
| --- | --- | --- |
| edit_decisions | edit_decision_id,submission_id,review_round_id(nullable),stage_id(nullable),round(nullable),editor_id,decision,date_decided | 独立的历史记录，而不是只把submission.status改掉；决定的轮次/阶段和实施者都可追溯 |
| issues | issue_id,journal_id,volume,number,year,published,date_published,date_notified,last_modified,access_status,open_access_date,show_volume/number/year/title,url_path,doi_id | 排期/期号、发表、读者通知是不同事实，日期可空；current_issue_id为journal的投影，不是所有稿件必须立刻有issue |
| publication_galleys | galley_id,publication_id,locale,label,submission_file_id(nullable),seq,remote_url,is_approved,url_path,doi_id | 一个publication可有多种最终格式；稿件文件≠读者最终载体；is_approved和真正published也不等价 |
| issue_galleys | galley_id,issue_id,file_id,locale,label,seq,url_path | 全期刊一期的完整PDF等，与每篇文章galley不同 |

Decision常量包括ACCEPT、PENDING_REVISIONS、RESUBMIT、DECLINE、SEND_TO_PRODUCTION及RECOMMEND_*，也存在恢复/新轮次/回退等类别。不要把数字直接存为本项目无语义枚举。首版使用明确代码、输入版本、负责人确认和不可变决定快照；编辑建议不应自动产生editorial_decision。

OJS3.5.0-6的修复迁移I12357处理旧系统生产阶段ACCEPT数值漏迁移，先检查最初安装版本，再只修正仍未映射的值。这说明跨版本迁移不能全库无条件替换数字、也不能伪造从前没有的确认记录。

**建议**：制作任务、校样版本、作者校样确认、最终publication_preview快照分开；首版只提供本地预览，未接DOI注册/公开站点发布不得显示“已正式发表”。未来正式发布再增加独立人类关口与外部幂等动作。
