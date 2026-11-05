# 第五批：复核读取一致性与独立评价材料

用户明确授权PR #2合并，2026-11-04已合并main 42f720c1e83a8a4ddb9ac5e93f93a1d9e65fc145。下一阶段分支codex/evidence-review-integrity，不部署VPS、不删除历史、不自动合并新PR。继续一本期刊、资料审阅的范围，不扩展为真实投稿或作者身份认证。

## 复核与维护

已复现P2：原反馈历史先查latest_id、再查页，中间追加记录会返回旧提交基准和新列表，造成不必要的409（原写入CAS仍安全）。改为同一SQL中的head/page CTE＋LEFT JOIN，一个MVCC语句快照；页已耗尽仍返回真正head。负责人编辑过程中的新记录仍必须显式重新载入，不静默更新前端基准。

来源鉴权与CAS重验移入claim_review_sources，查询/分页/投影移入claim_review_queries，HTTP路由组合服务；已有Input/ReviewAction及幂等指纹不变。边界检查同时禁止HTTP路由相互导入，纯模块不获取模型或业务写入权限。不改表、旧迁移、digest、旧Answer或反馈历史。

## 最小新功能

回答下新增“下载独立评价包”：GET /api/dossiers/{dossier_id}/answers/{answer_id}/evaluation-package。仅当前实际所有者editor/chief_editor会话可用，源版本可以是历史版本。只读导出，不注册模型工具，不创建回执/业务审计/人工反馈/资料核对/决定/邮件。

JSON schema claim-evaluation-package.v1含完整该版正文、作者等录入资料、版本/文件摘要与文件名/媒体类型、PDF页/Word提取段和受鉴权原件下载路径、全部采用及待核对候选的文本和精确原文坐标。返回附件与no-store。拒绝无全文、损坏CAS、错版/错摘要、失配Unicode坐标/引文、原件页段不匹配或空候选，409且不返回部分评价材料。

使用白名单重建引文，不复制原Answer wrapper、问题、provider/model、support、bucket/index、telemetry或既有人工意见；合并两组、随机UUID与随机顺序。每条assessment初始verdict null/note空。可在本地手填JSON，暂不支持回传、自动计分或正式签署；不宣称是专家盲评。文案/原稿仍可能让评价者推测来源，作者保留，所以不是双盲或匿名稿。

全文与作者仍是私人资料，不生成公开链接/共享token；下载后仅用于已授权的内部评价。ORCID未认证、Crossref未读全文、逐字定位不代表科学正确这些既有边界不变。没有新增真实模型调用或新论文样本。

## 设计

沿用DESIGN.md的Hermes Operate风格：白#fff、侧栏#f5f7fa、墨#30343b、次要#646c78、细线#e3e8f0、蓝#2463ff，现有Noto Sans/系统字体，三栏与中心对话不改。回答后的单行行动组随窄屏换行，不另造卡片或说明区；现有复核摘要旁增加具名下载按钮。按需提示包含全文/作者与隐藏AI标签的范围。44px触控高度、原生键盘、加载/失败重试/成功提示；页面切换丢弃迟到下载，下载请求前和回包后分别重验会话身份，变化清除资料。

Frontend Design用于保持视觉方向，UI/UX Pro Max检索download feedback error recovery，Impeccable按既有Operate规范精简入口，Web Design Guidelines以本轮最新官方规则验收。沿用本会话已运行的Impeccable context，不重复运行。

## 研究与取舍

本轮重新读取[OJS review guide](https://github.com/pkp/ojs-user-guide/blob/main/en/editorial-workflow/review.md)及[Janeway editor review guide](https://janeway.systems/pages/support/guides/editor-guide-to-review.html)。借鉴固定评审材料、限定可见性、保留原意见、评价与编辑决定分离。Janeway明确提示匿名评审需要检查原件识别信息，本包故意保留作者元数据用于该产品的作者审阅，不称匿名评审。两者的自动通知/一键邀请/删评审行为不引入。本批无数据库新字段，现有固定版本研究映射不重写。

## 验收

先失败后修复的真实PostgreSQL并发读取复现；完整原反馈测试；PDF/Word原件引用和Unicode定位、历史版本、无全文/坏来源、越权/登出拒绝；导出前后全资料投影与数据库业务计数相同。浏览器真实下载、503重试、迟到结果隔离和身份变化；桌面/375px查看。最后冻结运行源码后scripts/verify.sh，结果记录在PROGRESS与阶段报告，不把计划视作通过。
