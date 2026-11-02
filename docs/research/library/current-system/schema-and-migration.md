# v0.1最小领域模型与增量迁移建议

本文件是基于当前源码断层的建议，须由Lead结合OJS/Janeway固定版本证据定稿，尚未实施。

## 建议的关系实体

| 实体 | 首版关键字段/约束 | 不该混在这里的内容 |
|---|---|---|
| manuscripts扩展 | journal、submission_number、created_by、current_version_id、phase、current_step_id、revision、submitted_at/updated_at；journal+number唯一；editor可空 | 署名作者列表、文件二进制、每个审稿人的状态 |
| manuscript_versions | manuscript、version_no、schema_version、title/abstract/language/type、metadata_snapshot、content_digest、frozen_at、created_by；稿件+version_no唯一 | 覆盖已经提交的版本；已发表内容与可变个人资料混用 |
| author_snapshots | version、ordinal、name、email、ORCID可空、affiliations快照、is_corresponding、contribution、linked_user_id可空；version+ordinal唯一 | 根据姓名/email自动授予登录权限 |
| file_objects | journal、storage_key不可由模型指定、sha256、size、media_type、scan_status、created_by/at；内容不可变 | 仅存未经验证的外部URL或把上传二进制塞JSONB |
| version_files | manuscript、version、file_object、purpose、visibility、display_name、anonymization_checked_by/at | 审稿人只靠前端隐藏真实文件名/作者信息 |
| assignments | manuscript、user、capability、starts_at、ends_at、assigned_by、reason；当前有效分派部分唯一 | 把角色头衔当作全期刊无条件读取权限 |
| workflow_step_runs | manuscript、step_key、cycle_no、version、status、policy_version、entered/completed_at、outcome；稿件+步骤+循环唯一 | 通过重置同一行抹去退回、重做与修回历史 |
| work_items | manuscript、step_run、kind、assignee或pool、due_at、state、priority、blocking、confirmation_id | 每稿每kind永久唯一，导致第二轮修回无任务 |
| check_runs | step_run、version、file_digest、kind、method/provider、report_file、result_jsonb、review_outcome、confirmation_id | LLM生成的“检查完成”直接转成放行事实 |
| form_drafts | manuscript/task、schema_key/version、base_revision、data_jsonb、sources_jsonb、revision、owner | 模型任意schema、可执行JS表单、默认勾选声明 |
| action_proposals | manuscript/task、action_type、payload_snapshot、base_revision、policy_version、evidence_digests、digest、expires_at、superseded_at | 原地改写待确认的完整内容；客户端自报digest被当作事实 |
| human_confirmations | proposal、responsible_user、digest、outcome/reason、confirmed_at；不可变 | AI聊天文本、人已打开页面、截止超时代表同意 |
| review_rounds | manuscript、round_no、version、type、required_reports、policy_snapshot、state | 邀请数与有效接受数/报告数混为一个计数 |
| review_invitations | round、reviewer_user、attempt_no、response_due/review_due、status、conflict_response、responded_at；轮+reviewer+attempt唯一 | 发出站内邀请即视为审稿人已接受；邮件批准即邀请响应 |
| review_assignments | invitation唯一、round/manuscript/version、reviewer、accepted_at、status | 接受后可任意读取其他轮次或稿件 |
| review_reports | assignment、report_no、author_visible_snapshot、editor_private_snapshot、recommendation、confirmation、submitted_at/digest | 把审稿建议直接写成最终决定；作者看到私密意见 |
| editorial_decisions | manuscript/round/version、type、rationale_snapshot、author_visible_snapshot、decider、confirmation、decided_at | 决定即通知已发，或在Agent中暴露最终confirm工具 |
| production_packages | manuscript、accepted_version、package_revision、state、created_by；文件关联通过用途明确的package_files或受控关系 | 把review版/稿件当前可变版本误用作最终接受版 |
| publication_previews | manuscript/package、metadata_snapshot、file_digests、created_at、confirmation、scope=local_preview | 用“预览”实际公开未授权稿件；未确认就生成正式DOI/外部URL |
| publishing_action_receipts | actor、journal、request_uuid、input_digest、action_type、response；actor+journal+request唯一 | 改动旧CommandReceipt的摘要、目标解析或回执内容 |

署名机构可先使用不可变JSON数组快照；不要为了首版另建机构身份注册系统。长表单内容/来源、评审表单答案可用版本化JSONB，核心外键、状态、身份、轮次、日期必须关系化。审稿意见逐点回复首版可采用与报告明确关联的回复信文件；若实现逐条回复，再增加review_comments/revision_responses的真实FK，而不是用模型生成文本ID充当关系。

## 数据库必须守住的约束

1. 所有子实体持有manuscript_id；与版本/步骤/轮次的复合FK明确属于同稿。建议在被引用表增加`UNIQUE(id, manuscript_id)`，子表用`FOREIGN KEY(version_id, manuscript_id)`，不能仅靠单UUID存在。
2. 当前版本/步骤指针同样保证属于本稿。循环FK可先插入空指针、创建版本/步骤后同事务更新，最后添加约束；不要为简化而取消所有完整性保护。
3. 角色/分派属于同一期刊。写入口从数据库取得目标journal，不信任客户端/模型字段；关键关系可增加`(id,journal_id)`唯一与复合FK。可访问author/reviewer投影不能包含权限过滤前的计数。
4. 版本、最终报告、确认快照和已决定内容不可原地改；文件内容寻址。借鉴已有email_approvals触发器，但确认撤销应是新增失效/替代事实，不改写原批准内容。
5. 邀请当前active状态可用部分唯一索引防同轮重复邀请；历史attempt保留。报告和有效接受数按真实实体/状态计数，拒绝者不计有效报告。
6. 索引至少覆盖`(journal,phase,updated_at)`、`(assignee,state,due_at)`、`(manuscript,version_no)`、`(round,reviewer,status)`；按实际访问检查EXPLAIN后补JSONB索引，先不全面GIN。
7. due_at统一有时区UTC；用户“今天”边界在后端按工作区时区计算。无截止/等待他人与逾期分别表达，左栏排序不是LLM输出。
8. 一次正式动作锁顺序固定为稿件→步骤/任务→提案→相关草稿/邀请；重验actor/session/分派/COI、revision/digest、文件hash、所需报告，然后确认/推进/生成任务/审计/回执同事务提交。模型网络调用不应持有稿件行锁等待数十秒。

## 增量实施顺序

**M1: 非破坏扩展。** 新领域表与命名空间，加入正式稿件编号/可空编辑/版本指针/来源标记等可空列。保留旧models字段/旧表，旧API与回执不改变。会话工作期刊先确定；多membership时必须显式选择，不能取首条。

**M2: 保真回填。** 旧manuscript UUID沿用；为旧title/author创建标为legacy的版本/署名快照，editor分派保留原事实，现有screening映射legacy_screening。旧任务链接到legacy步骤或作为旧任务保留，不补查重/范围审核/人工确认。保存回填来源/时间/脚本版本，重复运行不重复创建。缺失作者机构/文件不伪造，显示legacy未提供。

**M3: A+B可运行切片。** 从作者账号真实创建准备稿→整理→缺项表单→上传合成原稿/匿名稿→独立审核确认提交→产生编辑部预审任务；前端三栏读取这一对象，同一ID贯通。只迁移本切片使用的表，保持旧demo供回归。

**M4: 分段初筛与分派。** 实现真实check_runs、每关确认与退回补交；人工上传查重报告而非制造自动查重结果；主编明确范围审核和分派，责任编辑质量关口。此时再切换“我的工作”为正式任务默认入口。

**M5: 站内评审闭环。** 加轮次/邀请/报告，指定测试审稿人接受/拒绝/利益冲突；只提供分派版本的匿名材料。报告审核提交、编辑汇总建议、主编决定、作者修回。仅站内邀请，不增加真实邮件传输器。

**M6: 制作与本地预览。** 接受版关联制作包/校样文件，出版人员与作者分别完成负责人任务，独立确认生成需登录的本地预览；不得自动正式公开或注册DOI。

**M7: 切换与回归。** 新正式领域查询/草稿投影替换主入口；旧fixture UI明确保留演示标记/路径，不能读一部分真实、一部分固定历史拼成同稿。验证upgrade与二次启动、历史回执、角色拒绝/匿名化、并发冲突/确认失效、mail不变量。此目标内不要求删除旧列/旧表。

## 接口建议

新增`/api/publishing/...`等明确命名空间避免与旧`/api/manuscripts/{uuid}`语义碰撞；按Lead定稿即可。最低接口为：我的任务/可见稿件/进度投影、准备稿/字段草稿/文件对象上传下载、步骤提案/独立review/confirm、轮次/站内邀请响应/报告草稿与审核提交、修回、决定提案、制作包与本地预览。确认API不进入Agent registry，也不能由自然语言“确认一下”绕过独立页。

真实对话工具以`ContextRepository`/领域projection替换load_cases，而不是直接返回完整ORM对象；每个工具调用重新查actor/journal/目标权限，模型上下文不超过该用户的API投影。原demo工具与真实工具registry分开，避免demo-001误识别为正式UUID。允许工具仅创建候选/草稿/建议和受控非关键动作。
