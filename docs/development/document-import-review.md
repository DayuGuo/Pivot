# PDF / Word 导入、人工核对与原件引用交付

2026-11-03，spec015，本地真实资料区增量；没有更新公网静态Demo或连接VPS。实现合同见[spec015](../../specs/015-document-import-review.md)，解析依据与依赖限制见[研究记录](../research/document-ingest.md)。

## 操作

1. `./scripts/start.sh`，打开 http://localhost:3100/library。账号 `editor@publishing.test` / `EditorDemo2026!`；只用合成或明确授权公开非保密资料。
2. 新建或选择本人资料，点击右侧“导入 PDF / Word”，选择文本层PDF或`.docx`并声明材料授权。
3. 等待提取后进入独立候选核对页。检查完整提取、原件、字段证据与提示，补齐作者顺序/机构/通讯邮箱/来源等必填项。候选页面可刷新恢复，当前资料版本尚未改变。
4. 负责人本人确认完整快照后保存新版本：一次创建版本、导入批准、原件来源和该版资料核对。再次修改会新建待核对版；模型不能调用确认。
5. 回到中心对话提问，点击引文查看该版本原文与PDF页/Word提取段，可授权下载原件。Word段编号不是其排版页码；精确引文不是科学正确性证明。

## 实现与权限

新三表DocumentImport/DocumentApproval/DocumentSource、迁移15b39ecf7286；36字段、13命名约束与上游比较映射已登记。导入/确认经Action Gateway，当前刊、本人、有效editor/chief_editor会话、CSRF、幂等与基础版本/revision均由后端校验。异步提取/模型后及锁等待后再次检查；旧候选、撤权、损坏原件均不能升级。历史不可UPDATE/DELETE/TRUNCATE，有历史拒绝回退，完整Base结构测试不排除新表。

原PDF/DOCX存独立私有二进制CAS；规范化全文仍遵循现有UTF8/1MiB文本FileObject。SHA、提取hash、版本digest与origin_digest重验；只改元数据继承原件而不继承新版本核对，换TXT则显式脱离来源。人工改值不挂旧候选证据；元数据作者索引还检查姓名。正文按quote实际重叠计算全部页/段，不按chunk起点猜位置。浏览器只下载原件，不运行内嵌主动内容。

模型元数据工具只有propose_metadata，未知留空、候选value/quote逐字校验、通讯证据须指向该人；前部14,000字符窗口只用于元数据识别，全文仍完整解析索引。真实失败明确报错，不静默Mock。Mock是标明的本地标签规则，未知字段仍由人补齐。对话沿用版本证据只读工具，不能发邮件、核对资料或作编辑决定。

## 实际验收

**最终串行scripts/verify.sh实际退出0：1112 Pytest（381.04秒）＋66 Playwright（2.0m）**。研究来源/架构边界、Ruff/ESLint/TypeScript、完整迁移/结构及准确前后端构建通过。完整日志`artifacts/document-import-full-verify-delivery.log`，JUnit `artifacts/pytest.xml`；4条警告来自Starlette兼容、测试fixture add_js弃用与两条Alembic配置弃用，未隐藏或删除测试。

- 解析71项通过；导入API42项通过；问答（含空终答纠正）54项通过；相关UI18项通过。这些局部集有重叠，不与全量相加。
- 最新完整迁移相关81项通过（48.55秒），包括历史数据库不可变、空迁移回退/有历史拒绝、最新完整结构比较；`alembic check`无漂移。本机与独立栈已升级15b。
- 真实DeepSeek API两格式通过：各提取2作者、14字段来源，原件下载与实际字节一致。上传不升版，测试驱动显式模拟演示负责人改表单/确认一次后v2已核对；重放不重复创建。尾标记精确定位PDF第2页901..937、DOCX第23段953..989。报告`artifacts/document-import-live.json`，PDF4.198秒、DOCX4.388秒（导入至确认/QA完整脚本每案例用时）。
- 实际Chromium另对两格式各发一轮真实DeepSeek问题，引用精确高亮、刷新恢复，375px无横溢；pageerror0、发信/决定请求0、该浏览器检查确认请求0。报告`artifacts/document-import-live-browser.json`及对应桌面/手机截图。
- 实际重启API/Web后，同一会话完整资料投影（含版本/作者/历史对话引用）、导入快照、原件字节/hash逐项相等，provider仍deepseek；没有额外模型调用。`artifacts/document-import-live-restart.json`。
- 邮件草稿/批准、编辑决定与正式人类确认计数在真实验收前后不变。资料确认仅测试驱动模拟合成数据负责人，不是模型工具调用，也不代表真实稿件获人工签收。EMAIL_SEND_ENABLED=false。

离线完整重现命令（串行，不同时跑共享verification数据库/Playwright产物）：

```bash
COMPOSE_PROJECT_NAME=publishing-os-verification COMPOSE_FILE=compose.yaml:infrastructure/compose.verify.yaml DATABASE_URL=postgresql+psycopg://publishing:publishing_local@localhost:55433/publishing E2E_BASE_URL=http://127.0.0.1:13100 ./scripts/verify.sh
```

显式真实合成验收：`.venv/bin/python scripts/accept-document-import.py --live`，固定本机8100/55432，沿运行服务的DeepSeek环境，不读模型密钥；会新增合成资料并由脚本模拟确认。初始启动/更新使用安全start.sh，勿用缺环境的主栈Compose覆盖现有live配置。

## 失败、修复与遥测

初轮PDF的两次供应商HTTP成功，但候选schema/原文证据校验最终失败，业务回滚、未建立Import。旧诊断未给出具体字段，不能断言唯一根因。补安全字段路径/固定原因诊断、明确换行和通讯姓名要求、共享遥测收集后，两格式首试提取通过；没有放宽逐字检查。

真实浏览器期间发现模型返回claims/questions/external_dois全部为空，旧逻辑曾保存无结论回合；该历史仍保留不可改。新增dossier_response_empty，读取来源后允许现有预算内一次纠正，仍为空则回滚明确失败；3轮/8工具预算不扩大，3个新回归覆盖首次空纠正/重复空/无来源空。之后PDF、DOCX浏览器验收通过。浏览器脚本还修正relative API URL、重复问题/引文选择器；额外调用全部计入遥测。

遥测只汇总本轮带确切合成验收source_note的3资料：2完成导入、6已存问答（含旧策略1个空终答）、1失败导入；16供应商attempt均HTTP成功，输入32,911/输出3,255 tokens，供应商耗时合计22,706ms，费用null待账单。HTTP成功不等于业务成功；不宣称本轮经历供应商503后恢复。报告`artifacts/document-import-live-telemetry-summary.json`。原生3项委派均完成，但其Token/费用/耗时未暴露而留null，见[委派记录](document-import-delegation.json)；不冒称DeepSeek成为原生子Agent。

最终阶段曾因Lead将完整验证与上一轮浏览器对同一verification栈重叠运行，旧严格布尔测试的全局回执/审计计数受无关写入干扰，1111通过/1失败。修复为按测试期刊隔离6项计数，保留全部422/状态/回执断言，28项资料测试重新通过后最终全量串行重跑；不删除已有数据或测试。此前1107+66、1109+66均通过，最后交付仅以本页最终新结果为准。

## 限制与后续专业复核

文本层PDF/.docx≤5MiB，PDF≤60页、文字≤1MiB；无OCR、旧.doc、加密/扫描/任意空白PDF页支持。异常ZIP/XML、宏/嵌入/外部模板图片/修订评论/动态字段等明确拒绝。HTTP/HTTPS/mailto超链接只取显示文字、不访问目标。图表/图片/公式不作语义理解，PDF顺序和DOCX线性化必须人核对；不能将文本完整提取冒称视觉内容已审阅。

15秒墙钟/12秒CPU/512MiB等解析子进程控制、最小环境和应用层限制不是OS沙箱、杀毒或对解析漏洞的安全保证。正式真实资料试点前，专业工程师必须复核文件攻击面与系统隔离、身份/对象权限、模型出域与隐私、数据库不可变/留存、备份恢复及部署。下一步以多样化获授权公开样本和固定问答集评估准确性/覆盖/人工返工，再评估OCR、复杂排版与外部全文授权。ORCID目前仅格式检查，不是认证；外部引用仍只核对已给DOI的Crossref书目，不声称已读外部全文。
