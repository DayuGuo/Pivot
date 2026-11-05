# 正式文件与公开修回回归：来源与取舍

研究/实现日期：2026-11-05。这里只记录可核对的来源与工程选择，运行结果见docs/development/spec025-review.md，不把研究或模型自查说成专家验收。

## 成熟系统经验

再次查阅本项目已固定源码/版本的[OJS工作流与政策](library/ojs/workflow-and-policy.md)、[OJS来源清单](library/ojs/source-manifest.json)及[Janeway字段字典研究](library/janeway/README.md)。上游AGPL源码只静态研究，未复制或执行到Pivot。

- OJS的review_round_files、review_files与实际分派区分“稿件有文件”与“本轮/本人可读的文件”。官方修回指南提醒先上传修回，再建新轮，避免错轮次。这支持本轮绑定当前实际version和用途，不凭最近上传、题名相同或文本hash巧合推断。
- Janeway的core.File/FileHistory、ReviewRound.review_files和RevisionRequest.response_letter支持稳定稿件、文件历史、评审轮、修回请求/回复分离。FrozenAuthor说明作者身份/快照与登录权限不能混同。
- 本轮新增FormalDocumentImport/Binding是独立治理设计，不是上游现成同名表。外加不可变原件/选择范围、确认会话、继承批准链和可恢复核对页，不把上传当人工通过，不自动给审稿人原始文件属性/身份数据。

官方入口：[PKP Learning OJS](https://docs.pkp.sfu.ca/learning-ojs/)、[Janeway官方仓库](https://github.com/openlibhums/janeway)。静态源版本与精确SHA以本地清单为准，不冒称重新安装/验收了上游生产系统。

## 原文与许可

完整来源、著者、DOI、评审报告许可、版本SHA和转换声明见[公开修回语料](../../evals/public_revisions/README.md)及manifest.json。三组文章：

- [Oath v1](https://f1000research.com/articles/3-271/v1) / [v2](https://f1000research.com/articles/3-271/v2)。
- [Responding to Reviewers v1](https://f1000research.com/articles/13-921/v1) / [v2](https://f1000research.com/articles/13-921/v2)。
- [Preprint attitudes v1](https://f1000research.com/articles/13-6/v1) / [v2](https://f1000research.com/articles/13-6/v2)。

根文章XML明确CC BY 4.0，入选reviewer-report也逐条核对独立license节点。作者文章内version-changes修订说明属于文章许可正文，保留实际文字作为回复节选。网页嵌套作者评论未有同等可复用许可证明，不套用文章CC BY、不提交完整PDF/XML评审附录。没有完整rebuttal letter，不以“作者回复全部可读”做回归假设。

保留出版社原生文章页、不重新排版的PDF节选共6份；原始全文PDF含26/27、23/33等页，文章页边界分别记录。Word共9份为许可XML文本转换，包含6版文章与3份修订说明节选，不是出版社原生Word。测试不能因此证明复杂作者Word的分页/批注/OCR/公式可靠。XML独立段落守卫与原生PDF页数/提取边界一并校验，不只拿解析器自身输出作唯一真值。

## 真实解析缺陷

两个较新版本对初次被严格解析器拒绝：Type1字体指定WinAnsi但无ToUnicode，未用槽129被解为U+0081，触发“不完整文本”保护。缺fontTools的CFF依赖是同时观察到的问题，但单加依赖不足以修复此例。

依据[Apache PDFBox官方问题PDFBOX-1713](https://issues.apache.org/jira/browse/PDFBOX-1713)和[Adobe PDF Reference 1.4 Appendix D](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.4.pdf)的WinAnsi未用槽规则，以及已固定pypdf6.21.4的字体处理实现，先完整检查对象图，再只为明确WinAnsi、无ToUnicode的支持字体建立内存bullet映射（127/129/141/143/144/157）。不覆盖其他编码、不丢未知控制字符、不修改原始二进制。parser标识升text-v3，历史v2快照与摘要不改；依赖fonttools4.68.0精确锁定。非WinAnsi控制符仍拒绝。

## 回归发现的逻辑问题

原整份PDF混有评审附录和作者“已修改”说明，可能被误作正文证据；增加人审页/段范围，PDF比较从实际正文页3开始。已知回复节选标source_complete=false，不能由未给出的部分推断作者未回应。

长意见旧规则只保留前1200字，现保留全部连续片段且任何片段不能证明整项完成；8项一批可继续。继续按钮保留草稿追加提示，后端采用最后一行明确的起始项，避免保留原问题时总从第1项重复。

真实DeepSeek暴露不稳定的漏项/引文或schema不符。增加当前ID枚举/精确条数、一次同截止时间的格式纠正，反馈只含后端结构错误、固定字段/缺失ID，不回显未知字段名/模型文本/凭据。仍不匹配即失败；不进行模糊匹配、不由服务端伪造缺项结论。所有语义判断仍需负责人核对，相同供应商独立上下文不能等同独立专家。
