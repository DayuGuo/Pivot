# 对现有 Publishing OS 的差距评估与 v0.1 建议

日期：2026-11-02。对现有 `apps/api/publishing/models.py`、spec003和已运行合成编辑工作台作只读对照。下文是工程建议，不能作为已迁移/已运行的证据；主Agent负责最终架构和权限实现。

## 已观察到的缺口

| 现有实现 | OJS证据带来的问题 | 建议 |
| --- | --- | --- |
| Manuscript只有author_id/editor_id/title/status | 未分派编辑的新投稿无法自然创建；多作者/版本/署名历史缺失 | editor可空、稳定投稿身份与不可变版本/作者快照分离；保留旧ID |
| Membership唯一(user,journal)且只有一个role | OJS有用户↔角色组多对多、有效期、稿件分派、建议权 | 增加成员角色集合和稿件级capability/有效期，不将全局editor作为任意稿件授权 |
| EditorialTask唯一(manuscript,kind) | 无法保存重复轮次/退回后同类任务；无期限/输入版本 | 新work_item或扩展执行实例键，唯一仅限制同实例的有效任务，历史不覆写 |
| 真实稿件无版本/文件/作者表 | 当前六篇fixture的长文和版本不能替代真实投稿数据库 | 将提交内容、作者排序、文件对象/用途/匿名化版本规范化保存，逐步替换fixture接口 |
| 私有JSONB状态/对话已真实保存 | JSON草稿没有正式轮次、分派、确认外键，不足以承载出版事实 | 保留UI私有草稿，正式业务使用关系实体+受约束快照，二者界面明确 |
| 审稿人当前没有读取分派 | 无法完成受邀、接受、报告；不能只换role提示词 | 邀请响应→接受分派→轮次/个人文件授权→报告提交链 |
| email draft/approval已有安全不变量 | 尚未连通稿件/轮次/邀请/负责人任务及完整业务UI | 保留快照绑定、修订撤销；站内邀请/决定与邮件发送分开，禁发默认不动 |
| 合成草稿决定字段可选结论 | 不等于正式决定历史/人类确认 | 正式决定必须独立记录、阶段与版本校验、明确decider+confirmation |
| 无issue/galley/真实出版制作 | “预览完成”容易误标为published | 首版实现校样/作者确认/本地publication_preview，后续issue/DOI/公开发布另开范围 |

## 最小实体建议，不是一次创建全部空表

可以先按以下薄层贯通一条稿件，在真正用到某实体时建表：

1. **Submission聚合**：扩展稿件稳定身份、编号、当前阶段/步骤、revision、submitted_at；版本(序号、标题、摘要、类型、语言、schema_version、frozen_at、digest)，author_snapshot(ordinal/name/email/ORCID/affiliations/corresponding)，file_object+version_file(哈希/大小/MIME/用途/可见性)。
2. **责任与确认**：assignment(manuscript/user/capability/stage/start/end)，step_run(input_version,cycle,state)，work_item(assignee,due,status,kind)，proposal(输入revision、payload快照、policy_version、digest)及confirmation(实际有权负责人、结果、理由、时间)。初审检查的report与人工outcome单独保存。
3. **审稿闭环**：review_round(version/policy/目标报告数/status)，invitation(选中reviewer、回复/报告期限、冲突声明、响应)，accepted_assignment，report(author_visible_comments/private_comments/recommendation/submitted_snapshot/confirmation)。不能让模型传入任意接收者或身份。
4. **决定与制作**：editor_recommendation与editorial_decision分开；修回新version/reply；制作任务、proof_version、作者proof_confirmation和local_publication_preview快照。正式对外发布/DOI/外发邮件留在授权范围外。

首版可把通常一对一、不会独立查询的字段放入版本化JSONB，例如affiliations列表、期刊检查表答案；但稿件/期刊/版本/轮次/责任人与确认引用、状态和可见性不能仅藏在任意JSON。应让未来ORM迁移能直接加实体约束。

## 建议首批约束与索引

- `UNIQUE(journal_id, submission_number)`，`UNIQUE(manuscript_id, version_no)`；当前版本/步骤通过同稿复合外键或同等数据库约束保证。
- 作者署名顺序唯一(version_id,ordinal)，通讯作者至少一位/唯一规则由期刊策略与事务校验；不要让AI自动勾选责任声明。
- 固定提交版本和确认快照不可UPDATE内容，变更新建版本；实际文件字节哈希与snapshot引用一起核验。
- 有效审稿分派可以部分唯一(round_id,reviewer_id) WHERE status为active，但邀请拒绝/取消/账号合并历史仍保留，不能简单全表唯一造成历史丢失。
- `(journal_id, phase, updated_at)`；`(assignee_id,status,due_at,created_at,id)`；`(manuscript_id,round_no)`；精确任务索引应以真实列表查询计划校验，不照搬上游所有索引。
- 每个可变草稿/聚合有revision；proposal绑定base_revision和输入hash，确认时行锁+重新校验。不要在用户阅读确认页时持有长事务。
- 邀请response_due_at与report_due_at分开，UTC时间存储。今日/逾期投影明确用户时区，不能用浏览器硬编码日期作为业务事实。
- 状态值用类型化枚举和CHECK/外键保护；区分not_run/pending/failed/completed、人工判断pass/return/reject。没有检测器不应伪造检测结果。
- 下载与报告查询有同稿/同轮次/分派过滤，计数也用相同过滤，避免左栏总数泄漏。

## 迁移与回填

OJS升级代码中的孤儿关系清理、0→NULL、阶段决定常量漏迁移修复说明：成熟系统仍需要明确的数据修复，不应假设历史完美。我们不能直接运行它的迁移，也不能复制删除孤儿策略到现有用户库。

对本项目建议expand/backfill/cutover：

1. 先备份合成数据副本，增加新表和可空引用，不删旧Manuscript/Message/CommandReceipt ID。
2. 旧title/author/editor导入一份legacy版本及明确legacy分派/步骤；原screening只记legacy_screening，不补造预审、查重、主编确认。
3. 保持原指令/回执、会话、邮箱审批API兼容，新增版本化真实业务接口；用只读对照确认投影一致后再切写。
4. 明确数据库前向迁移/历史修复策略；不可回滚的内容快照/审计不应通过随意downgrade丢弃。迁移测试至少验证旧稿、旧审计、旧幂等响应仍可读/重试。
5. 后续再移除editor_id非空/旧任务唯一等限制。不要一次无依据地“清理”旧记录或把演示fixture的假历史变成正式记录。

## 优先顺序与验收口径

先建立作者投稿→独立确认→编辑预审/主编分派→真实角色待办和当前步骤的最小链，再扩展审稿/修回/决定/校样。数据库从这条纵向业务逐步增长，研究目录在每个切片引用对应OJS来源重审。

验收以一篇真实数据库测试稿件贯穿所有已宣布阶段为准：能切账号执行、有待办、能拒绝越权、能刷新恢复、有版本文件与不可变确认、重复/并发不重复推进。当前对话和DeepSeek可准备材料，但模型不能决定角色/关键状态或调用最终确认。真正完成的产品必须超出源码研究与静态页面；本研究本身不代表任何新业务已上线。
