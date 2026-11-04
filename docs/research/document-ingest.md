# PDF / Word 文本提取边界与实验

## 2026-11-04：公开真实论文后的v2修正

实际样本与许可见[评测目录](../../evals/public_documents/README.md)，运行结果见[交付记录](../development/public-paper-evaluation.md)。解析专项由71增至93项，22个新增用例覆盖合法OPC部件定位、缓存EndNote/页码、恶意路径/字段、纯本地PDF打开页与原有主动内容拒绝；实际93项通过（8.46秒），后续上层回归另有记录。

[Microsoft ResolvePartUri](https://learn.microsoft.com/en-us/dotnet/api/system.io.packaging.packurihelper.resolveparturi?view=windowsdesktop-9.0)明确列出相对父部件URI的合法解析案例。实现只在ZIP内部规范化并确认实际条目，不允许逃逸到文件系统。[Word FieldCode](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.fieldcode?view=openxml-3.0.1)区分字段指令与其显示结果；本实现不求值，仅允许指定页码及EndNote缓存文字。结构不闭合/缺少引文缓存拒绝，未渲染页码明确提示。普通内部引用不是外部模板授权。

[pypdf Reader接口](https://pypdf.readthedocs.io/en/stable/modules/PdfReader.html)与实际公开PDF检查用于区分本地打开页数组和动作字典；v2只忽略前者，脚本/动作字典/表单/附件仍拒绝。Word自动项目符号/编号没有重建，新增特定提示；原Word正文与独立LibreOffice对照的11个差异均为bullet前缀，正文行内容保留。段/页范围仍按完整实际提取文字定位，不冒称视觉版面等价。以下2026-11-03实验计数是v1历史记录。

2026-11-03。仅为编辑资料包导入建立受限文本提取，不扩展正式投稿文件白名单，也不把解析完成当作稿件、署名或科学结论已获确认。

## 官方依据与取舍

- [pypdf 官方文本提取文档](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)指出文本提取与OCR不同；PDF的视觉排版不保证阅读顺序，内容流解码可能占用大量内存。采用固定[pypdf 6.21.4](https://pypi.org/project/pypdf/6.21.4/)，只提取文本层，不请求外部OCR、不执行JavaScript。
- [Python zipfile](https://docs.python.org/3.12/library/zipfile.html)提供中央目录的压缩/解压大小与文件条目。DOCX以有界ZIP读取，先检查条目、总解压大小、压缩比、路径与对象类型，不将条目解压到用户指定路径。
- [defusedxml 官方说明](https://pypi.org/project/defusedxml/)描述DTD、实体扩展和外部实体风险。采用0.7.1，所有OOXML/XML relationship都禁止DTD、实体及外部解析。
- [Microsoft WordprocessingML结构](https://learn.microsoft.com/en-us/office/open-xml/word/structure-of-a-wordprocessingml-document)：按正文段落及表格单元格段落提取文字，另外跟踪正文实际引用的页眉/页脚和脚注/尾注。段编号是提取后的顺序，不是Word页码；未使用的ZIP内部文本不能冒充正文。

## 已实现合同

`packages.document_ingest.extract_document(filename, raw)`返回text、segments、parser、warnings、page_count、paragraph_count。`text`是各非空段以两个换行连接；每个segment带kind、1起算number、Unicode码点start/end及text。DOCX额外带part说明正文/页眉/脚注来源。父进程再次核对拼接及每一段位置，确保`text[start:end] == segment.text`；规范化CR/LF并去掉页/段外侧空白，不做静默前缀截断。

原件上限5 MiB；提取文本上限1 MiB；PDF最多60页且任一页无可读文本即拒绝，不把扫描/部分文本当完整成功。DOCX最多500个ZIP条目、20 MiB总解压大小、受限单条目/XML及压缩比；有修订、批注、文本框、白名单外字段、宏/嵌入对象等不支持内容时明确拒绝；指定缓存页码/EndNote处理见v2。表格、实际引用的页眉/脚注等文本按顺序线性展开并给出固定提示。普通图片/图形未转录，必须人工查看原件；不声称图表或公式语义已提取。

DOCX常用HTTP/HTTPS及mailto外部超链接保留显示文字，忽略、不访问也不返回target，并给出`external_hyperlink_targets_ignored`；外部模板/链接图片/OLE等关系拒绝。mailto仅接受无authority且有地址路径的显示链接；目标收件人/subject/body参数不进入提取结果，其他scheme没有放行。PDF URI链接不跟随，JavaScript/打开动作字典/Launch/表单/附件等主动内容拒绝；纯本地打开页数组见v2。旧二进制.doc、.docm、加密PDF、坏签名/超限/不可完整读取文件均以固定安全错误拒绝。

解析使用固定Python命令`-I -B`的独立子进程，临时空工作目录、close_fds、最小环境（不含模型密钥、数据库地址或服务环境），不执行LibreOffice或文档里的程序。15秒父进程墙钟、12秒CPU、512 MiB地址空间、6 MiB输出文件、32个FD、零子进程额度以及禁核心转储；超时杀进程组。Python审计钩子拒绝socket和启动其他程序。**这些是资源控制与应用层防御，不是OS沙箱或对未知解析器漏洞的安全认证**；真实生产仍需独立容器/系统级隔离和专业评估。异常不反射原文件内容、路径或解析器堆栈。

## 合成文件和实际实验

`tests/documents/synthetic-manuscript.pdf`是有效2页PDF，937个提取字符；同名.docx是有效Word文档，989个提取字符、23个非空段，含中文、表格和实际DOI超链接。二者都含Synthetic Author Alpha/Beta、合成机构、.test邮箱、未认证示例ORCID及末尾`END-OF-SYNTHETIC-DOCUMENT-TRACE-2026`，不是实际科研材料。可按目录中的生成脚本重建；DOCX生成器使用临时npm工具目录，不改变项目Web依赖。

已实际将PDF两页用Poppler渲染；PDF第一页及DOCX经LibreOffice临时profile导出后的第一页已目视检查，题名/作者/正文/表格/中文与尾标记可读。Word导出的PDF为1页、无加密/表单/JavaScript。LibreOffice仅用于我们自己生成的可信fixture视觉验证，**不在生产上传提取路径里**。渲染位于`/tmp/pivot-document-render`，不作为持久产品附件。

专项实际执行：`pytest -q tests/api/test_document_parser.py`在mailto兼容补充后为**71 passed（6.09秒）**（此前67项5.42秒已通过）；Ruff与format检查通过。覆盖真实文件提取、逐字位置、空白/扫描页、加密/超页、PDF主动内容、ZIP炸弹/重复/路径穿越、DTD/实体、外部关系、普通HTTP/HTTPS及mailto超链接、mailto参数不进入提取结果、空地址/authority/控制字符拒绝、不执行的隐藏部件、修订/嵌入、文档上限、父进程协议校验、最小环境与超时杀组。最终日志`artifacts/document-parser-mailto.log`，此前67项日志`artifacts/document-parser-final.log`。两条警告分别来自既有Starlette兼容提示及恶意PDF fixture使用pypdf已弃用的add_js构造器；生产提取器不调用该构造器。

这里不宣称已验证导入API、人工确认、数据库/浏览器或真实模型链；这些由Lead另行整合验收。
