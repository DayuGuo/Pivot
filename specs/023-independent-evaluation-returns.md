# 第六批：独立评价人工核对、回传与分歧

PR #3获用户明确授权，于2026-11-05合并main 3e8729a0003a93514592fc0696bd33ef0c95cb4d。本批不部署VPS、不删历史、不启用邮件或模型确认工具。

## 范围与流程

回答下按需打开“独立评价回传”，负责人登记reader-a等代号，服务器生成持久v2评价包。每个回答最多10个不同代号，每代号只允许一个包，重复操作按请求UUID恢复；代号不是账号或身份认证，不声称独立专家已签署。只允许该资料真实所有者、当前期刊有效editor/chief_editor访问和操作，不引入外部共享token或放宽reviewer权限。旧spec022只读v1包仍可下载，未登记、无可靠服务端映射，不能直接回传。

负责人下载v2JSON，通过获授权的方式收集填写结果（系统不发送邮件）；只能更改每条assessment的verdict/note，可换序，原文/作者/版本/结论/引文/ID不可变。supported/unsupported/uncertain须5–2000字理由；未评价保持null及空理由，至少一条已评价。上传只做无写入预览，实际负责人在独立页面逐条查看完整结论/意见、定位原文、核对缺项，再逐项勾选和整体显式本人核对，提交确认。中间对话始终保留。刷新未保存预览需重新选择本地文件，不把未确认文件保存在浏览器持久存储。

每次确认追加记录，绑定预览digest、完整包digest、原Answer/原版本、前置return ID、本人/会话；同UUID重放恢复原回执，旧前置ID409，不自动覆盖并发结果。历史版本可回传，明确标记，不迁移成当前版资料核对。所有写入通过Action Gateway同事务审计。模型没有登记/回传/确认工具，回传不创建ClaimReview/DossierCheck或正式决定。

按每代号最新确认统计；有依据和无依据同时存在才标明确分歧，待核对、未评价和未回传单列，无多数决定或科学准确率。旧确认仍有有界历史（10默认/50最大）和序号游标；最新统计不重复累计同代号历次意见。不同Answer/版本不混算。代号不同不证明现实中是不同人。

## 数据合同

**EvaluationPackage / publishing_evaluation_packages**

字段：id、answer_id、dossier_id、journal_id、version_id、content_digest、evaluator_code、packet_json、claim_map、packet_digest、created_by、session_hash、created_at。13字段。packet_json为隐藏AI判定的完整不可变v2模板，claim_map为服务端随机ID到精确原Claim的映射，不向下载者公开；2MiB模板/256KiB映射上限。

**EvaluationReturn / publishing_evaluation_returns**

字段：id、package_id、dossier_id、journal_id、version_id、content_digest、packet_digest、assessments_json、digest、return_no、submitted_by、session_hash、created_at。13字段。128KiB意见快照。复合FK包/资料/期刊/版本，按包序号唯一；SQL来源/代号数量/目标集合与追加序号守卫，UPDATE/DELETE/TRUNCATE禁止，有任一历史拒绝降级。

新增迁移17d51aeb9408，前序16c40fda8397。原33表/原迁移/旧回执指纹不改，先备份后仅在本机应用增量升级。研究映射绑定26字段与具体约束/SQL函数，静态映射不是运行证明。

## 模块与视觉

共享evaluation_sources重建精确历史材料，claim_evaluation保留兼容v1路由；evaluation_access做已登记映射和对象检查；evaluation_protocol是纯JSON校验与分歧计算；evaluations组合HTTP和网关。新页面在现有workspace右栏，不替换中间对话。FrontEnd Design方向沿DESIGN.md的Hermes Operate，白/淡灰/细蓝线、Noto Sans，不加卡片装饰；UIUX Pro Max用于确认与错误恢复，Impeccable精简、Web Guidelines验收。正式人类确认在独立页，上传预览不能冒称保存。

## 研究取舍

本轮重新读取[OJS review guide](https://github.com/pkp/ojs-user-guide/blob/main/en/editorial-workflow/review.md)和[Janeway editor guide](https://janeway.systems/pages/support/guides/editor-guide-to-review.html)。采用固定材料、意见与决定分开、保留原评审、默认私有。没有照搬自动通知、一次性登录链接或编辑覆盖原意见；本表为项目评价治理，不声称与上游数据库字段完全相同。

## 验收计划

真实PostgreSQL/CAS：登记/下载/无写入预览/逐条确认/回执/修订/分页/统计，跨角色/所有者/期刊/资料/版本拒绝，篡改材料和opaque ID拒绝，历史版本、并发旧前置、部分和不确定结果、坏源重放、SQL不可变/降级。浏览器真实文件下载/上传/定位/勾选/刷新/分歧、断线同UUID恢复/切换/撤权、桌面与375px。公开授权资料只做明确模拟验收，不冒充实际专家意见。最后冻结源码后scripts/verify.sh与CI，已执行结果见PROGRESS。
