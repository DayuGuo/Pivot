# OJS 数据库与出版流程研究库

研究日期：2026-11-02。只读研究官方 OJS 3.5.0-6 LTS，未运行上游 PHP、未安装 OJS 数据库、未导入真实稿件，也未修改 Publishing OS 业务代码。

本次以 [PKP 官方下载页](https://pkp.sfu.ca/software/ojs/download/) 的当前发布说明和官方 git 标签交叉核对：3.5.0-6 于2026-11-01发布。检索缓存仍大量出现3.5.0-5，不能据此把旧版称为最新稳定版。固定 OJS `3_5_0-6` → `0f2de4ff3f399a65dbe5c24c035529c0ff9bc976`；其 `lib/pkp` gitlink → `c4c0aa8c5293254ad253544aea230b1b607d5249`。不能使用 pkp-lib main 代替这个依赖提交。官方编辑指南另固定 `pkp/pkp-docs` 提交 `44b289e7c27094f1c2003e69bf30c8b832b85f35`，指南frontmatter明确3.5。

| 文件 | 用途 |
| --- | --- |
| [source-manifest.json](source-manifest.json) | 每份来源的官方URL、日期、commit、用途、本地文件与SHA-256；失败的获取也单列 |
| [schema-inventory.json](schema-inventory.json) | 从选定安装迁移静态提取59个表的字段/外键/索引语句，供检索，不是可执行DDL或完整PHP解析器 |
| [database-field-map.md](database-field-map.md) | 核心实体的具体字段、关联、可空/唯一规则与Publishing OS映射 |
| [workflow-and-policy.md](workflow-and-policy.md) | 初审、审稿、决定、修回、制作/出版语义及权限分层 |
| [publishing-os-gap-and-v01.md](publishing-os-gap-and-v01.md) | 现有代码缺口、首版实体/约束/迁移和验收建议；明确与上游观察区分 |
| [sources/](sources/) | 固定官方源码快照/指南自撰摘要；未接入应用依赖 |
| [validation.json](validation.json) | 实际本地哈希、JSON和来源/分析引用一致性检查结果 |

研究结论的优先级是：固定源码/迁移中的真实字段与约束 → 同版本官方工作流说明 → 我们自己的产品推导。上游通用设计不覆盖本项目更严格的人类确认和邮件禁发要求。

## 重要限制

1. `Schema::create` 不是整个已部署数据库的全部历史。另有 `Schema::table` 后加外键和升级/修复迁移，静态inventory明确标识这个范围。没有执行 PHP 或 SQL，不能声称这些表已在本机迁移验证。
2. OJS使用通用PKP层与OJS特定层组合。`context_id` 在OJS指向journals，在其他PKP产品可指向presses等，不能把一个库的所有字段不加区分复制到我们的表。
3. 源码快照保留原版权头和上游GPLv3许可文本（OJS `docs/COPYING`、PKP `LICENSE`）。只为研究/证据；本报告是自主撰写的概念/字段分析，不把GPL代码粘贴为Publishing OS运行实现。后续若要直接复用源码，应先处理相应许可义务。
4. 指南仓库license端点及许可文件候选本次未成功返回，manifest如实记录。已读取的指南版本为3.5，但仓库只保留自行撰写的简短中文来源摘要；原文仅在/tmp隔离缓存，不提交整份原文。manifest分别记录原文与本地摘要哈希，不虚构已核实文档许可。
5. GitHub release API本次未成功返回发布metadata，但官网当前发布页、真实tag与固定checkout已验证；不将release API失败隐藏为成功。
6. 项目源码/上下游版本后续变化应新增研究批次，不能悄悄改动本次固定快照。可使用manifest哈希判断材料是否变化。
