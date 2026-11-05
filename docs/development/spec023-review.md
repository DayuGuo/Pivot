# spec023：独立评价人工回传与分歧

交付[PR #4](https://github.com/DayuGuo/Pivot/pull/4)已推送，未自动合并；冻结源码c81df74后仅更新交付文档。

## 授权和交付边界

用户授权PR #3合并，2026-11-05T09:18:52Z已按精确head89208d3合并main **3e8729a0003a93514592fc0696bd33ef0c95cb4d**。合并后main的verify42001351711、static42001351668和既有amd64隔离包CI42001351533均success；这些验证不含本批新回传功能，也不是用户VPS部署。本批codex/evaluation-returns未自动合并、没有新Release、没有连接或更新VPS。

## 实现与复核

- EvaluationPackage/EvaluationReturn独立13＋13字段，新增17d51aeb9408迁移；原33表、历史迁移/回执指纹与正式业务模型不改。包固定原Answer/版本/全文和作者，随机ID→原Claim的映射仅在后端，已登记v2模板不可变；旧v1只读导出兼容，但不能凭未登记随机ID回传。
- 只允许本资料实际所有者且当前仍有本刊editor/chief_editor角色。Session/CSRF、精确原件/全文CAS、包/期刊/资料/版本、预览digest和每条核对ID在后端重验；不能传入另一人的身份。按每Answer每代号唯一、最多10代号；这是负责人指定代码，未认证现实身份或人数。
- 上传仅预览，无业务写。严格JSON内容和类型比较，只允许assessment变化；换序允许，原文/作者/版本/opaque ID/结论/引文/指令均不能改。至少一条非null、5–2000字理由；未评价null＋空理由；空字符/重复/缺项/额外字段拒绝。代码复核中保留了数值float与bool区别，不能以Python的True==1绕过模板绑定。
- 独立页在现有右栏，中央对话保留；负责人逐条查看意见/原文高亮，逐项勾选并整体显式本人核对。确认追加Return，绑定不可变digest和前置return ID；同UUID恢复，真实并发200/409。它不创建ClaimReview、DossierCheck或出版决定。
- 摘要只取每代号最新确认，旧记录可分页查完整意见。仅supported与unsupported并存算明确分歧；uncertain、未评价和未回传单列，不多数决定、不作科学准确率。不同Answer/版本不混算。
- evaluation_sources/access/protocol分别维护来源、权限映射、纯JSON/统计；evaluations只组合HTTP与网关。dossier_actions.event新增可选evidence_id关联新事件，旧调用的审计形状不变。直接导入与路由互导受check-boundaries约束，26字段/具体约束/SQL guard静态映射完整；此检查不是动态权限证明。
- 下载在请求前和生成文件前双重身份校验，页面切换丢弃迟到结果；确认回执不完整保留相同UUID。更改上传文件清除全部勾选，翻旧记录不更新提交基准。未保存文件仅在组件内存，刷新需重新上传；没有新增浏览器持久私人存储。

## 执行证据

冻结运行源码 **c81df74b6e0d07da185288772c28fbadca118cb4**。

- 本机完整scripts/verify.sh **exit0：1319后端437.43秒＋91浏览器2.5m**；Ruff/格式、ESLint/TypeScript、研究与模块边界、离线原文18对、Alembic升级/零漂移、准确API/Web镜像构建启动全部通过。6条Starlette/httpx、pypdf及Alembic既有类别弃用提醒，未删除测试。日志artifacts/spec023/full-verify.log，JUnit artifacts/pytest.xml。
- 专项32新API11.19秒；与既有反馈/导出合并81项22.19秒；迁移/资料81项46.55秒，其中生产53项实际JUnit重绑研究证据，旧观测保留。相关35浏览器22.1秒，新实际链最终3项4.8秒，含真实DB下载/上传/定位/保存/刷新/分歧、真实并发、回执丢失重试及等待中换登录。
- 初次迁移遇到SQLAlchemy把SQL中的JSON冒号识别为绑定参数，已修正空格，隔离DB升级成功。早期静态检查发现贡献字段可能缺失，改为安全空数组；重复勾选用例原先先提交合法单项再改body，导致409，修正为一开始真正重复ID，后端422断言保留。完整失败/修正日志不删除，不以重试冒充原因修复。
- 桌面/375px截图已查看，对话保持可见、无横向溢出；Frontend Design/Impeccable沿既有Hermes Operate，UIUX Pro Max检索确认/错误恢复，Web Guidelines最新官方规范已读；检测[]。不声称完成屏幕阅读器/所有浏览器/物理设备认证。
- 远端同源码static-demo42005578299 success，两轮11项10.8/7.7秒；同源码[完整verify42005578631](https://github.com/DayuGuo/Pivot/actions/runs/42005578631)所有步骤与顶层均success，实际1319后端519.74秒＋91浏览器2.5m、6提醒。日志remote-verify.log、head/status/jobs在ci-run.json；没有从本机结果推断远端成功。

## 现有数据与公开材料

升级前DB/CAS备份在忽略目录artifacts/spec023/private-backup，目录0700、文件0600，未上传。主服务使用scripts/start.sh保留既有选定DeepSeek环境；升级后原33表940行逐表摘要完全一致，两张新表空，upgrade-preservation.json。

随后使用已存在、许可在evals/public_documents/manifest.json分别注明的research-findings-word与clinical-word历史回答，经实际浏览器登记v2、下载、上传、逐项定位/勾选/确认和刷新。两份资料共5条结论、每份两个模拟代号，产生4包/4回传/8网关回执；相反意见仅为测试分歧，理由明确“自动验收模拟负责人…不代表专家意见”，不是实际编辑或专家评分。每份原Dossier/版本/Answer投影完全相同，分歧数2和3正确，新模型调用/邮件或关键决定请求/页面错误0。重跑不会重复增加记录，也不覆盖被人修改的最新意见。证据public-returns.json；仅本机已有公共历史夹具，fresh CI用合成材料从头建立数据。

最终35表956行。仅排除这8条新增、类型和响应ID均匹配新评价的网关回执后，旧33表940行完整摘要仍一致；不是笼统忽略整张回执表。原24个CAS常规文件逐一hash相同，files-preservation.json与data-preservation-final.json。没有重置、删除、降级或恢复旧数据。

本阶段没有真实供应商推理/凭据重新鉴权，不把health.available当模型调用成功。邮箱禁发、Mailpit捕获0与关键决定人工权限保持；不改变主模型或Codex全局配置。API成本无新调用，Codex自身使用量未独立计量。

## 研究与后续

本轮重新读取[OJS review guide](https://github.com/pkp/ojs-user-guide/blob/main/en/editorial-workflow/review.md)与[Janeway editor review guide](https://janeway.systems/pages/support/guides/editor-guide-to-review.html)，采用固定材料、默认私有、保留原意见、评价和编辑决定分离；没有引入自动通知、一次性登录链接或覆盖原始意见。本两表是项目治理，不宣称上游数据库有同名实体。

下一步由获授权的实际编辑确定评价标准，再设计真实评价者账号/任务分派、可追溯签署和更广许可语料；当前仍由资料负责人收集/核对回传，代号不认证身份。真实机密稿件试点前请专业工程师复核解析隔离、对象权限、模型出域隐私、迁移/运行分权、不可变历史和备份恢复。
