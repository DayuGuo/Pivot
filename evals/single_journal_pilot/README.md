# 单刊内容评价准备包

本包冻结了6篇独立公开许可论文的42个不同检查问题，供指定编辑随后独立建立和复核参考判断。当前是工程参考草案，**实际编辑评价未执行，评价者未分配，不能报告专家准确率或节时效果**。

这些论文在此前工程调试中已经使用。9项 `retained_for_followup` 从本次冻结起留作后续复核，不能宣传为全新语料、真正盲测或从未见过的测试集。同一篇论文的PDF、Word及v1/v2不重复计篇。

## 使用文件

| 文件 | 用途 |
| --- | --- |
| `manifest.json` | 唯一论文身份、上游许可、实际文件SHA和解析快照绑定 |
| `checkpoints.json` | 工程预标问题、确切原文位置、预期可回答性及参考判断；第一轮独立标注时不给评价者 |
| `editor-materials.json` | 不含AI或工程参考判断的材料索引、署名许可、原件路径及快照 |
| `snapshots/*.json` | 从实际文件提取并冻结的文本、页/段范围、解析器版本与警告 |
| `editor-evaluation-template.json` / `.csv` | 每项问题的空白人评表，不包含工程参考答案 |
| `efficiency-timing-template.csv` | 空白净耗时记录，包含查证、纠错、重试与导出 |
| `protocol.md` | 独立标注、分歧处理、效率比较及真实计数的执行方法 |
| `validate.py` | 标准库离线校验和汇总，无联网、模型、数据库或业务写入 |

独立评价时复制空白表并记录评价者代号，给评价者问题、材料索引和所需原件/解析全文。先隐藏 `checkpoints.json` 的工程参考判断及已有AI结论。代号不认证身份；第二位编辑须由负责人实际安排，不能由模板中的空槽位推算人数。

## 许可与材料范围

| 论文身份 | 版本及来源 | 格式与边界 |
| --- | --- | --- |
| `zenodo:19059298` | [Clinical Practice Guidelines recommendations versus Cochrane systematic reviews…](https://zenodo.org/records/19059298) | 许可公开的未发表手稿，CC BY 4.0；本包使用作者原生DOCX，不宣称已同行评审 |
| `doi:10.1371/journal.pcbi.1003285` | [Ten Simple Rules for Reproducible Computational Research](https://doi.org/10.1371/journal.pcbi.1003285) | 出版者PDF，原文CC BY声明，Editorial |
| `doi:10.1371/journal.pmed.0020124` | [Why Most Published Research Findings Are False](https://doi.org/10.1371/journal.pmed.0020124) | 出版者PDF，原文CC BY声明，Essay |
| `doi:10.12688/f1000research.5686` | [Open Science Peer Review Oath，v1/v2](https://f1000research.com/articles/3-271) | CC BY 4.0，正文XML转制Word，公开修订说明节选及已许可意见段落 |
| `doi:10.12688/f1000research.154614` | [Key Guidelines for Responding to Reviewers，v1/v2](https://f1000research.com/articles/13-921) | 同上，不冒充出版社原生Word |
| `doi:10.12688/f1000research.143013` | [Preprint attitudes survey，v1/v2](https://f1000research.com/articles/13-6) | 同上，不含期刊清单等补充原件 |

作者、审稿人署名、许可证证据和转制出处分别保留在本包与原有 [public_documents manifest](../public_documents/manifest.json)、[public_revisions manifest](../public_revisions/manifest.json)。原作者和审稿人保留版权。分发本包的文本、节选或转制品时，一并保留这些署名、来源、许可证与转换说明。软件代码的授权不替代源内容许可。

共21个来源，其中9个是原有修回manifest中的明确许可审稿段落，逐字引用坐标相对这些字段文本，标为 `manifest_field`；它们不是整份报告。其余12个是实际原件或明确转制文档的冻结提取。不能把21个来源或13份不同字节文件当成21篇/13篇论文。

三套修回材料都只有公开修订说明节选，**完整逐点回复信为0**。任务B的15个检查点将作者回应、正文落实和编辑充分性分开。局部题名、结构、指导语或表格单元的修改可以定位；整项要求是否充分完成仍需编辑和完整材料。7条 `located_change` 不是7条“整项修订已通过”，也不是模型运行结果。未改但有说明、只回应部分要求和声称补引用却未定位到均有单独问题。

本包42项中任务A为27项，任务B为15项；33项用于准备与调试，9项后续保留。问题按业务含义设计，引用可包含多段上下文，未把同一长意见切成多行来增加检查点数量。该规模不代表全学科覆盖，也不代表系统容量。

## 离线命令

在仓库根目录执行，无需设置模型密钥：

```sh
.venv/bin/python evals/single_journal_pilot/validate.py validate --report artifacts/spec027/pilot-preparation-check.json
.venv/bin/python evals/single_journal_pilot/validate.py summary
.venv/bin/pytest -q tests/api/test_pilot_evaluation.py
```

`validate`和`summary`均校验上游manifest摘要与许可对应、独立论文身份、实际来源SHA、冻结文本SHA、页/段范围、逐字引文、检查点去重及最低计数。输出的是工程参考完整性，不能由它推导语义准确率；它也不会重新解析PDF以证明提取完整。

本次冻结时实际原件已经存在本机并重新提取核对，校验报告见忽略目录 `artifacts/spec027/pilot-preparation-check.json`。公开资料3份原件位于忽略的 `artifacts/public-papers`，修回转制文档在既有 `evals/public_revisions`；校验器绝不自动下载或调用模型。新检出仓库若缺原件会明确失败并报告 `source_file_missing`，不能仅靠已提交的解析快照宣称核对原件通过。需要补原件时按上游manifest的固定来源和摘要另行取得，现有显式抓取入口为 `scripts/evaluate-public-papers.py --fetch`；抓取不代表模型评价或正式导入。

普通Pytest的17项校验器测试只使用临时合成文件，不依赖忽略目录，也不访问数据库或模型。最终应用全量回归由主Agent统一执行。
