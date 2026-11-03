# 资料区外部引用边界

2026-11-03，组件研究与实际验收。实现为`packages/review_sources.py`，不接收模型密钥，不调用模型，不检索或上传稿件正文。

## 官方依据与取舍

[DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)描述模型提出函数调用、应用提供工具结果后继续回答；当前官方示例使用`deepseek-flash`及非思考模式，严格格式模式另有Beta条件。引用、权限、版本与关键操作必须继续由后端检查，不能把工具输出格式正确视为业务授权。

[Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)提供公开的出版物登记元数据，`/works/{doi}`可查询单个DOI，无需新账户或额外凭据。本切片采用精确DOI查询，避免把稿件片段或作者资料当搜索词发给第三方。调用方必须先确认DOI确实来自当前授权版本或本次用户问题；适配器本身只验证标识符语法，不授予资料访问权限。

返回`verified_metadata`仅表示Crossref成功返回同一DOI的可读取题名记录；不表示论文全文已阅读、引文支持某一科学结论、作者身份已认证、研究可信度已评定或撤稿状态已全面核对。作者最多返回前10项、年份缺失时为null；题名与作者文本仍视为不可信外部数据。

## 接口与网络限制

`normalize_doi(value)`支持有界ASCII裸DOI、`doi:`或精确`doi.org`/`dx.doi.org`网址，其他地址、控制字符、查询参数和片段拒绝；不尝试猜测、修复或自动补全未知DOI。`lookup_doi(doi, timeout=5.0, transport=None)`固定GET到`https://api.crossref.org/works/`，路径中的标识符转义，不接受可配置端点。

使用专门TLS上下文、关闭环境代理和重定向、不传Cookie/Authorization，拒绝压缩、非JSON及超过256KiB的响应。网络总预算默认为5秒、最大10秒，响应分块读取并核对长度；不重试。无效JSON、重复键、NaN、HTTP错误、限流或超时仅返回固定状态。404为`not_found`，其他失败为`unavailable`；不反射远端错误正文。同步接口须在worker使用，不能从运行中的事件循环调用。

成功结果仅保留DOI、题名、作者、年份、获取时间和固定来源范围；链接由本地生成的`https://doi.org/{doi}`及Crossref API URL组成。不会读取或直接输出记录中的任意出版商URL，也不会跟随DOI跳转。主流程应在外部请求前后重新检查原授权/版本，未核验结果不得标为可信引用。

## 实际验证

模拟HTTP组件测试实际 **78 passed**（0.21秒），Ruff检查与格式检查通过。覆盖任意URL/路径/控制字符、错误DOI记录、重定向、Cookie/凭据、响应大小/压缩/长度、非有限JSON/重复键、总期限、代理与TLS密钥日志禁用。没有数据库、模型或邮件外发操作。

2026-11-03T16:32:37Z实际请求公开DOI `10.1371/journal.pmed.0020124`，返回`verified_metadata`，题名为 *Why Most Published Research Findings Are False*、John P. A. Ioannidis、2005年；结果链接为[DOI记录](https://doi.org/10.1371/journal.pmed.0020124)，实际来源为[Crossref元数据](https://api.crossref.org/works/10.1371%2Fjournal.pmed.0020124)。未请求出版商全文。该实连只证明这一公开DOI当时可查询，不推断其他机构、ORCID、DOI注册机构或未来网络状态。

复验命令：`.venv/bin/pytest -q tests/api/test_review_sources.py`。本文件记录组件结果；整套资料区真实模型、权限、版本与浏览器验收由Lead整合后执行`./scripts/verify.sh`，本组件通过不等于整体完成。
