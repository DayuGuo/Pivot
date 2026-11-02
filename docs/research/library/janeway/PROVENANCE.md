# 来源、许可与复现

采集日期为2026-11-02，固定源码v1.8.4 / e24b23bd112ff7ca08097620d8a31041a25f9d26。官方 [发布页](https://github.com/openlibhums/janeway/releases/tag/v1.8.4) 和官网“Source code”指向当前openlibhums/janeway；不以搜索摘要中的旧1.7.5标记作为最新版本。

## 上游代码

`sources/*-model-fields.txt` 与 `sources/migrations/*.txt` 是公开Janeway软件的静态摘录；保留原始文件路径、提交、原行号、Birkbeck作者与AGPL v3声明。完整许可在 `sources/LICENSE`，逐来源URL与原文件/摘录哈希在manifest.json。仅作为研究数据保存，没有导入、运行或合并为Publishing OS应用代码。

`model-fields.json` 和 `field-index.csv` 是独立AST静态索引；字段类型、参数和显式Meta来自原声明。不是Django迁移图的执行结果，也不是“所有实际物理列”的保证。继承的时间/主键、ForeignKey隐式索引、ManyToMany中间表、modeltranslation动态翻译列和手写数据库操作未展开。

## 官网文档

采集的每个当前官网页面footer均明确标注Content CC BY4.0，并以`rel=license`链接到 http://creativecommons.org/licenses/by/4.0/ 。正文署名Birkbeck, University of London / Open Library of Humanities；页面底部保留的软件AGPL与内容CC-BY区别。

仓库不保留完整网页HTML或第三方脚本，只保存`main`正文的纯文本提取；每份文件开头给出原作者、来源URL、日期、CC BY4.0链接和格式变化说明。导航/图像/排版已省略，正文措辞未改。manifest保留原HTML的SHA256用于追溯版本，不把网站当前内容冒称特定1.8.4代码版本。若有新文档许可变化，应重新审核采集，而不是盲目按旧许可继续归档。

官方网页均为当前无版本路径。旧`janeway.readthedocs.io`搜索结果仍显示1.7.5等历史文档；本研究只使用它定位新官方文档/仓库，没有归档或把旧RTD文档结论混为v1.8.4。

## 采集方法与范围

用无认证、禁交互凭据的公共HTTPS浅克隆到`/tmp/publishing-janeway-research/upstream`；仅解析源码AST和读取纯文本，没有执行任何上游Python/Django/PHP、迁移或插件。没有访问全局认证、保密稿件或个人服务数据。

`collect_evidence.py` 可重新读取该固定缓存并抓取指定公开网站；它不clone、不修改应用数据库、不运行上游代码。重跑后官网正文可能因上游更新改变，必须重新记录哈希/日期；固定commit源码应保持一致。

本目录归档的代码、文档与研究者自写分析采用各自原许可；第三方源不能因位于本仓库就被重新许可。自写结论在README中清晰标为观察或建议，不能推断上游已实现我们要求的不可变审批/AI权限设计。

开发助手Token、账单与任务墙钟工具未提供，telemetry.json相应字段保留null；实际来源数量和静态解析计数另有可验证记录。
