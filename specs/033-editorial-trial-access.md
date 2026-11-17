# 033：单刊编辑试用入口与账号生命周期

2026-11-17。基线：`5ea3f82`，依赖未合并的日历和期限问答（PR #12/#13）。本片不合并、不部署、不自动联系编辑。最终执行证据见 PROGRESS。

## 产品范围

让部署负责人能为同一期刊的指定编辑开独立账号、结束访问和安全恢复；私人版登录直接到资料区。第一轮以2位编辑、许可公开材料、任务A（导入/作者核对/原文问答/记录意见）试用，沿用既有资料、评价与导出，不另造传统管理后台。每人的资料仍私有，运维身份不授予读取他人资料的产品权限。

## 数据与边界

新增 `trial_accounts` 七字段：user_id主键且FK users、journal_id FK journals、operator_id FK users、status（active/disabled）、revision（>=1）、created_at、updated_at。迁移 `33a1b9c7d204` 只建表，不更改旧用户、密码、角色或稿件。已有托管记录时禁止downgrade，避免丢失停用状态。

使用现有 User、Membership、LoginSession、ActionReceipt、AuditEvent。试用成员只新建一个既有期刊的editor角色；不按邮箱接管已有账号，不合并作者身份，不自动分派稿件，不授主编/管理员。每刊最多10个托管账号，包括已停用者；这是小批试用的操作上限，不是并发容量结论。

`operations/trial_accounts.py` 是仅服务器运维可调用的认证 Action Gateway，不注册HTTP路由或模型工具。仅private-preview、邮件false、配置operator邮箱与真实密码匹配、operator确有目标单刊editor身份时允许执行。每次 mutation 需确定journal、请求UUID、人工确认、枚举原因；旧账号还需user_id与expected_revision。操作者绑定不因修改部署邮箱自动转交。

成功修改、撤销会话、审计及回执在同一事务。UUID重复只读原结果，且重验revision；有密码的重试另外比较当前scrypt，不把密码或密码快速摘要放进回执。不同内容、旧revision、已被后续操作取代的回执拒绝。审计原因使用枚举，避免自由文本带入秘密。失败整体回滚，命令错误不回显参数或数据库异常。

停用保留账号、成员关系、资料及全部历史，撤销所有会话。恢复与轮换密码要求新密码且仍撤销旧会话；恢复后旧请求/旧cookie也不能复活。密码16–256字符，不复用公开演示密码或operator密码。无邮件通知/自助注册/自动密码重置。

账号共享advisory锁先于session/member锁；登录、身份切换、最后提交使用共享锁，运维变更用独占锁。模型推理期间不持新锁，最后提交再检查状态及原会话。登录拿锁后重新读取密码，防止轮换时使用缓存旧哈希。运维等待锁最多5秒、SQL单语句10秒；失败后先查名单，不盲目创建新请求。

## 使用入口

私人包 `manage.py trial-list/create/disable/resume/rotate-password`。先list取得期刊及账号revision，修改用命令中的目标ID；无可控制回显的TTY时拒绝读取（GetPassWarning作为错误）；密码只无回显读取后通过stdin管道传入容器，不能通过命令行参数设置，不保存参与者明文密码。负责人按已有线下安全方式交付登录信息；程序不代发邮件。

login与auth/me增加landing_path。私人profile的editor/chief_editor为/library，其余为/；前端只接受精确站内目标。原显式conversation/manuscript深链优先。资料页返回登录只传entry=library和合法dossier UUID，不接受任意URL。已登录但身份不允许进入资料区的作者/审稿人返回原根工作区，不携带编辑资料入口参数。页面路由不替代后端对象授权。

## 验收

真实PostgreSQL测试覆盖两位编辑隔离、已有账号拒绝、跨刊与操作者拒绝、角色漂移、名单上限、回执冲突、审计失败回滚、停用/恢复/轮换、旧请求撤权、并发登录及CLI无秘密输出。三引擎覆盖登录落点、恢复资料、旧对话保留、非法目标和作者越权。运行scripts/verify.sh后才记录完成。

## 专业复核与未完成

这不是正式编辑部上线授权。实际编辑评价为0；DeepSeek当前凭据/真实模型本片未验收；完整回复信语料为0；目标VPS本片未操作。保密材料、真实机构账号与扩大公网访问前，专业工程师须复核账号生命周期、文件隔离、模型出域、版本确认、DB/CAS一致备份及2.5GB负载。保留负责人的关键决定权和EMAIL_SEND_ENABLED=false。
