# F：制作、作者校样与本地预览的边界

2026-11-03 再次阅读本库固定来源。这里只记录后续设计，E/F尚未验收。

OJS3.5[官方制作指南](https://github.com/pkp/pkp-docs/blob/44b289e7c27094f1c2003e69bf30c8b832b85f35/learning-ojs/editorial-workflow/en/production.md)区分制作材料、最终载体galley与作者校样；本库 `ojs/sources/pkp-docs/production.md` 是中文研究摘要，非上游全文。Janeway1.8.4 [production/models.py](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/production/models.py) 分开ProductionAssignment、TypesetTask、files_for_typesetting和galleys_loaded；[proofing/models.py](https://github.com/openlibhums/janeway/blob/e24b23bd112ff7ca08097620d8a31041a25f9d26/src/proofing/models.py) 分开ProofingRound、ProofingTask及CorrectionTask。相应字段摘录已在本库带许可/哈希归档，上游代码没有运行。

Janeway[预出版指南](https://janeway.systems/pages/support/guides/editor-guide-to-prepub)要求核对元数据与最终文件一致，并特别警告不要误把附加私有文件作为galley发布；DOI、期次、日期、通知和最终发布是不同步骤。本地初级样本只实现冻结录用版本→制作人员上传实际文本校样→作者独立校样确认/要求更正→制作人员确认鉴权本地预览。这里的预览不设公开路由、不注册DOI、不宣称正式发表、不发送通知。

实现取舍：录用版本及其VersionFile已冻结，因此校样必须是独立关系引用实际FileObject，不能把proof追加到旧版本的冻结文件集中。每份校样固定 accepted_version_id、录用决定、元数据快照、文件hash及制作人工确认；作者校样结果另存不可变记录。要求更正保留旧包和反馈，重开制作待办，新校样再次确认。最终预览只能引用作者明确通过的确切校样包和制作负责人确认，不从“最新文件”动态拼接。

预览渲染采用安全文本/React转义，禁止执行上传HTML/脚本；下载重验实际CAS字节。访问限原作者与本稿有相应授权的工作人员，历史审稿邀请不授予校样或预览权限。模型可以理解状态、辅助文字，但不提供校样通过或预览最终确认工具。首版不实现多格式PDF/XML排版、DOI/期次/生产发布，后续通过独立Publication/Galley实体扩展。
