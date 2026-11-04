# 第四批：逐条结论人工复核

PR #1已获用户明确授权，于2026-11-04合并main（f67f24e）。用户要求不部署VPS。本阶段只在开发/验收环境实现可持久化的人工证据反馈，不开启外发邮件或正式决定。

## 产品范围

每条采用/待核对结论旁提供人工复核入口：先定位原文，再选择有依据/无依据/待核对并填写理由、显式勾选本人已核对。保存追加反馈；修改意见新增下一份记录，旧结论、模型判定、资料版本与既有核对不改。单条证据快照限32KiB，超过明确413、无部分写入，不截断原文；理由空白/空字符入库前422。历史版本可复核，记录明确绑定当时版本，不继承为当前版，也不改变稿件状态。它不是正式同行评审报告、出版决定或科学认证。本轮不宣称有真实专家盲评。

## 数据合同

**ClaimReview / publishing_claim_reviews**

字段：id、answer_id、dossier_id、journal_id、version_id、claim_bucket、claim_index、claim_json、claim_digest、content_digest、verdict、note、review_no、reviewed_by、session_hash、created_at。

独立append-only表16字段，迁移16c40fda8397，前序15b39ecf7286。answer FK与version/dossier/journal复合FK保证资源存在；插入guard重验原Answer中具体bucket/index快照、版本、负责人归属，串行序号。uq_claim_review_sequence防同一序号重复；目标/判定/理由/摘要/快照均有命名约束。UPDATE/DELETE/TRUNCATE禁止；有反馈历史拒绝降级移除新表。原表/回执格式/历史不重写。

API只接受当前有权的实际资料所有者编辑/主编，session与CSRF检查沿原链。Action Gateway绑定完整目标、前一review ID、精确claim和版本摘要；同UUID重放只读恢复，同UUID跨目标拒绝，旧前置反馈ID409，不以最后写覆盖先前意见。审核前重验版本全文和原件CAS。反馈仅写本表及网关回执/审计，不创建DossierCheck或任何正式确认。模型工具无反馈写权限。

复核摘要按Answer导出最新反馈；比较记录的人工意见与已有AI检查，排除Mock/未检查和人工待核对，零可比项比例为null，不作科学准确率。私人反馈不自动出域或训练。

GET按每条结论懒加载，review_no倒序、SQL有界分页，不在加载对话时逐条发请求；POST明确个人核对、必填实际理由。页面切换不接受迟到结果；失败保留表单和原UUID，修改内容会清除旧勾选。重试前重验登录身份。

## 研究取舍

OJS官方编辑指南区分review/recommendation和编辑决定；Janeway官方指南保留原始评审、逐项答案可见性以及独立Decision Helper。这里只借鉴“原意见保留、反馈/决定分离、人工权限明确”的模式，不复制上游字段代码、不开放作者可见性，也不假称这是成熟同行评审功能。

来源（本轮读取）：https://github.com/pkp/ojs-user-guide/blob/main/en/editorial-workflow/review.md 、https://janeway.systems/pages/support/guides/editor-guide-to-review.html 。静态数据库参考沿用已固定OJS/Janeway索引，新增表属于project_governance。

## 验收

真实PostgreSQL保存/重放/冲突、原Answer不变、无资料核对/邮件/决定；跨用户/期刊/角色/会话、错版本/摘要、bucket/index、缺勾选、旧前置值与分页；DB约束/不可变/安全迁移；浏览器实际提交、刷新、改理由重核对、失败同UUID恢复和375px；最后scripts/verify.sh完整通过。未执行结果不能标通过。公开论文已有Answer可用于只读复核和负责人模拟，不使用保密材料，不冒充专家签署。
