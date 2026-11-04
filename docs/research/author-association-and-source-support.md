# 作者关联与原文支持：spec020研究记录

研究日期：2026-11-04。目标是公开授权语料的作者归属、证据定位及结论支持，不开展医学建议或科学真伪评价。

## 已实际使用的一级材料

- [PLOS：Ten Simple Rules for Reproducible Computational Research](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003285)。出版页明确列出四位作者、对应机构及文章许可；本轮实际读取页面并解析PDF/JATS转制Word。作者编号3与4分别指Penn State和Emory，不因共同署名混配。Rule 7的建议不能说成已执行的试验。
- [PLOS：Why Most Published Research Findings Are False](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.0020124)。本轮网页两次超时，未把超时当作已读；已核验缓存出版社PDF与既有JATS转制Word，许可声明在原PDF。保留may、most、模拟范围；smaller studies指规模，不是研究数量。
- [Zenodo19059298](https://zenodo.org/records/19059298)。本轮网页/API访问受限；使用此前下载、SHA校验的公开未发表CC BY 4.0原生Word和明确标注的LibreOffice PDF。记录贡献者不等于稿件署名表。八位作者机构/联系邮箱来自稿件内命名块。
- [ORCID collecting and sharing IDs](https://info.orcid.org/documentation/collecting-and-sharing-orcid-ids/)、[How do I collect an authenticated iD?](https://info.orcid.org/ufaqs/how-do-i-collect-an-authenticated-id/)、[integration guide](https://info.orcid.org/documentation/integration-guide/getting-started-with-your-orcid-integration/)。官方区分录入ID和本人OAuth认证ID。当前仅保存未认证来源字段，不新增OAuth，不把ID格式/链接可打开当作认证。

每个文件的作者、题名、来源、许可、原件SHA及独立金标准在[manifest](../../evals/public_documents/manifest.json)。PLOS仅按文章CC BY声明记录，不推断许可版本；转制Word/PDF不冒充作者原件。未联系作者、未发送邮件。

## 从材料到工程取舍

作者快照关联是局部证据问题，不足以建立出版社全局人员身份。正向的命名块、上标编号与唯一脚注可自动关联；同名/共享邮箱/未认证ORCID只提示，不自动合并。缺乏正向关联宁可留空，但保留可点击的原始证据及固定原因。现有OJS/Janeway实体与人员/署名分层研究仍见library/comparison/database-decisions.md，本轮没有新增上游源码或改变其字段映射，不伪称再次完整研究上游。

逐字引用只能证明字符串位置，不能证明结论。采用确定性精确定位后追加独立上下文AI检查，以固定枚举记录反义、数量、限定语、身份、部分分句等问题。它使用同一供应商的新上下文，存在相关错误和提示注入风险；AI标签不是认证标志。进一步的盲测、更多原生Word、多栏/脚注/公式和专业编辑判分仍是后续工作。

独立金标准与模型输出分开：冻结18组正反事实用例后再调用模型；离线验证proposal回放不冒充自动提取。真实提取另经公开稿件导入API和独立金标准比对。来源精确、元数据归属、语义支持及人类最终核对分别验收。
