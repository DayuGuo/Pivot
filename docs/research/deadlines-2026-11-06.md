# 截止日期与日历边界

本轮在2026-11-06重新查阅官方资料，以既有数据库事实做本人只读日历，不复制上游通知行为。

[OJS官方编辑评审指南](https://github.com/pkp/pkp-docs/blob/main/learning-ojs/editorial-workflow/en/review.md)分别规定审稿邀请回应期限与完成报告期限；[官方审稿人指南](https://github.com/pkp/pkp-docs/blob/main/learning-ojs/reviewer/en/index.md)把日期作为审稿安排事实，审稿人不能自行修改。直接文档站本轮请求502，使用官方 pkp/pkp-docs 仓库的同源指南核对，不把第三方镜像当权威。

[Janeway官方编辑评审指南](https://janeway.systems/pages/support/guides/editor-guide-to-review.html)允许负责人在分派审稿时确定期限，并在管理评审时调整；修回属于独立请求与作者返回材料的流程。[官方提醒指南](https://janeway.systems/pages/support/email-and-reminders/scheduling-reminders.html)将提醒与评审/修回期限相连。Pivot本轮仅借鉴期限与职责的关系，不启用自动提醒、邮件或上游的一键免登录链接。

映射：publishing_work_items.due_at 是本人当前任务的持久日期；reviews 创建回应/报告任务时使用 ReviewInvitation.response_due_at/report_due_at；decisions 在负责人确认后将 RevisionRequest.due_at 写入作者修回任务。日历不建立重复表，也不按稿件上传时间重新计算。旧任务没有日期时明确未设，不作AI推断。

选择当前职务、实际分派和授权题名的只读投影：主编不能借日历浏览所有人的私人任务；审稿人保持本人邀请题名；作者未提交草稿与历史署名冲突不因日期而扩大可见范围。日期以浏览器IANA时区解释，后端按当地月/日边界转UTC，覆盖夏令时；读取截止时间不意味着延长授权或批准迟交。

交互参考沿用项目既定四技能；UI/UX Pro Max本轮定向检索“calendar date keyboard navigation”，采用可见焦点、方向键及本地化日期。依据[Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)核对原生表单、明确图标名称、键盘、触屏、错误恢复、时区及窄屏。这里只扩展既有侧栏，不改变 DESIGN 的视觉权威。
