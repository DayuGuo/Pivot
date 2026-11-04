# 第三批维护：作者关联与原文支持

实施范围：[spec020](../../specs/020-author-links-and-claim-support.md)，架构取舍ADR-030；不连接或自动更新VPS。邮件继续禁用、关键决定仍由实际负责人在独立页面确认。

## 已发现并修复的问题

- 原先“值在原文中”不足以保证属于该作者；现按明确命名块、署名编号与机构定义、唯一邮箱脚注建立正向关系。未取得关联的邮箱/ORCID/机构不继续挂给该人；原始线索可定位并显示固定原因。
- 编号后分号、Word段间空白、PDF具名作者简介曾导致合法关联丢失，已以公开样本和正反对照修复；邮箱脚注不自动推断通讯作者。
- 最后复核补上个人贡献归属：与邮箱/机构一样，必须明确属于该作者；原文中其他作者的贡献不能挂给此人。丢弃项之后保留项的field_sources下标按最终数组重排。正反例及下标共3测试，相关78项通过。六个本轮真实候选贡献均空，因此不把这些样本说成真实模型贡献识别准确率。
- 作者换序不能沿用数组下标当人；来源仅按同一导入唯一精确姓名和值映射，同名不猜。修改后的字段不伪造原件来源。
- 同名、重复ORCID、共享邮箱提示；重复ORCID草稿可保存、新确认前须修正，旧版本/回执不追溯重写。旧值沿用和本次识别分别提示。
- 准确引用也可能支持相反、过强或单位错的结论。增加独立上下文AI检查，将不足/矛盾候选折叠为待核对，保留引用和原因；不是绿色科学认证。Mock未评分，旧回答不重新贴检查通过标签。
- 实测首轮36个支持对照有2个无效协议响应；现只对检查协议允许一次有界纠正，同一60秒期限、不重做主工具/业务动作。失败503、不提交半个答案。

## 已执行公开语料实测

3篇许可明确论文、6个文件：公开未发表原生Word及其标注PDF、PLOS editorial/essay的出版社PDF及标注JATS转制Word。出处/许可/独立作者金标准见[样本目录](../../evals/public_documents/README.md)，研究取舍见[研究记录](../research/author-association-and-source-support.md)。它们不是六份作者原始投稿或科学真伪金标准。

- 真实DeepSeek自动导入6/6：26个作者位次，按独立金标准检查姓名、机构和邮箱，均无错配或列出字段缺失。导入仅生成候选、不升版。真实自动结果与离线金标准proposal回放分别报告。
- 独立文本比对继续检查原件SHA、全文、逐字字段来源及Poppler/LibreOffice对照。原生Word自动列表符号、视觉版面/公式、无OCR的既有限制仍在，不能从作者匹配推出全文视觉无损。
- 冻结18组正反事实，六文件共36组支持检查：首轮34完成/2协议失败，修复后36/36正确、误放0/误拒0/错误0，该检查点39次实际供应商attempt，输入45,352/输出2,269 Token。来源类型修复后的最终重跑仍36/36正确，36次attempt全部完成、无协议纠正，输入44,644/输出2,027 Token；费用未知null。旧失败和检查点报告均保留。
- 浏览器真实导入核对及问答6文件/12问通过；第一轮保留23条、移入待核对5条，包括无依据的缺项断言及复合句。检查发现一条以录入摘要冒称原件Summary的来源类型问题，已将original_text/original_metadata/recorded_metadata明确传给检查器并显示录入来源；修复后同类2条候选全部移入待核对，HTTP200但无采用结论，浏览器有用回答断言失败的记录保留。随后明确要求引用全文而非录入摘要的2问全部得到原文支持回答（1条Summary、2条作者机构），所有引用均original_text，实际页/段定位和刷新通过；0额外确认、0邮件/决定请求、0页面错误。该补问没有重写历史，也不把安全拦截冒充可用回答。6次核对由测试驱动模拟演示负责人完成，不代表作者/专家签收；模型确认工具0、邮件/决定请求0、页面错误0。刷新保持版本与问答，375px无横向溢出。

原始运行报告仅保存在忽略目录artifacts/spec020：staging.json、quality-audit.json、automatic-author-audit.json、live-support-first.json、live-support-second.json、browser-review-qa.json、qa-summary.json、scope-withheld-answer.json、browser-final-source.json与live-support-final.json。未把密钥、原始供应商错误或未经授权稿件加入仓库。

对24条此前采用结论以最终检查器再检查，22条保留、2条移入待核对：一条范围说明过强，一条“上标与联系方式字段一致”缺直接引用。该集来自模型旧输出，不是独立金标准，因此不把2条变化标成false rejection或混入36个冻结用例分数。此结果也显示同模型判断可变、人工复核必要；旧回答不重写。随后临床Word两问补测得到4条最小事实，全部带直接原文，0待核对。最终12问选集为初轮8问加上述两种Word的4个补问，共23条采用/3条待核对，23条均有原文件引用、浏览器高亮精确，0额外确认。选择与旧失败记录均保留，不把重跑当作盲测。

## 数据与权限

没有新迁移，head15b39ecf7286；旧导入digest及审批协议未修改。本机安全更新前后32个publishing_*表825行摘要相同。公开实测明确新增6份资料、12版本（含初始版）、6导入/审批/原件来源/资料核对、17问答（包含5个补问）及对应35回执。排除这些新评测记录后，原825行逐表摘要仍相同；此范围不包括认证/legacy表，不冒称全库每行比对。Mailpit0、EMAIL_SEND_ENABLED=false、正式工作流/邮件/关键决定不变。

## 界面验收与限制

遵循既有Hermes三栏/中心对话、字体与颜色，未新增装饰区块。不确定性与失败候选逐级展开，显示明确原因、来源定位和人工下一步。Frontend Design、UI/UX Pro Max（error summary validation）、Impeccable context/harden及[Web Design Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)（本轮实际读取）用于本批；实际源码检测无发现，桌面/375px合成截图已查看。另修复真实浏览器验收脚本刷新后过早截图：先等待实际题名可见/载入提示消失，再做手机布局；重放0模型调用/0确认，实际查看了加载完成的375px公开资料截图。源码检测不是屏幕阅读器或跨浏览器认证；真实手机软键盘、其他OS/浏览器未实测。

本批实际模型遥测包含失败/返工：6次导入7attempt、17个已存问答54attempt、所有支持对照/复查135attempt，共196attempt、输入416,186/输出26,470Token，费用未知null待账单。未估算Codex主Agent消耗。结构化脱敏结果见[spec020-results.json](spec020-results.json)。

## 最终回归

贡献修复前完整检查点scripts/verify.sh实际退出0：**1235 Pytest（378.70秒）＋81 Playwright（2.2m）**，Ruff/format、ESLint/TypeScript、研究/依赖门禁、18离线精确引文、PostgreSQL迁移/漂移、准确API/Web镜像构建启动通过。4项第三方弃用警告与前批类别相同。首轮1231过/1失败来自issue数组顺序假设，保留所有语义断言改为按字段/原因检查；新增3项来源类型契约，专项40通过后完整重跑。完整日志artifacts/spec020/full-verify-final.log和pytest.xml，不把首轮失败算通过。

个人贡献修复后最终串行scripts/verify.sh实际退出0：**1238 Pytest（378.50秒）＋81 Playwright（2.2m）**。全部Ruff/format、ESLint/TypeScript、研究/边界/18离线引文、迁移漂移、准确镜像构建启动通过；4项同类第三方弃用警告，未删测试。最终日志artifacts/spec020/full-verify-delivery.log。最终本机安全更新前后32表全部现存936行摘要相同、provider仍DeepSeek、邮件固定false。

## 下一步

更多独立原生Word、复杂署名/脚注、多栏、双语和数学样本；专业编辑盲评和反馈，避免只围绕固定小语料优化。ORCID OAuth及全局人员模型另立规范与迁移；文件攻击面、模型出域/隐私、权限/审计和备份恢复上线前须专业工程师复核。支持检查仍是同模型的新上下文判断，存在相关误判和提示注入风险；不能保证每条结论正确，不能代替科学/伦理/身份审查。

## 原生安装包与GitHub执行证据

已发布[私人体验包v0.2.0-preview.4](https://github.com/DayuGuo/Pivot/releases/tag/v0.2.0-preview.4)，源码d7c90b03f612f8761d167eed866a8b63165acbfa。原生amd64包283,323,571字节，SHA-256 `8dd2a9a99e1906cfeaa3d96021e5cfa22916ffa5af73b06d5e8f8563ebf59d85`；外包SHA和7个内文件SHA均已重验，5个附件与GitHub服务端大小/digest一致。

[原生任务41878817650](https://github.com/DayuGuo/Pivot/actions/runs/41878817650)安装、合成PDF/Word原件字节、模拟负责人核对、引用、重启和新项目/新卷隔离恢复通过；完整快照相等、旧服务ID未改。4路上传1成功/3受控429，同UUID主动恢复/幂等重放、完整资料未重复写入、0确认/邮件/决定；受限容器无OOM。原生浏览器0错误/0确认/0邮件或决定，PDF/Word引用与刷新通过。该包内供应商测试是Mock，不冒称真实DeepSeek或实际用户VPS容量。

[完整CI41878817674](https://github.com/DayuGuo/Pivot/actions/runs/41878817674)实际日志1238 Pytest（322.41秒）＋81 Playwright（1.8m），14个步骤包含Complete job全部success，无error。[静态任务41878817834](https://github.com/DayuGuo/Pivot/actions/runs/41878817834)两组11项通过，16步骤全部success。读取发行记录时，原生顶层completed/success，完整CI和静态顶层仍in_progress/null（其工作步骤/日志已完成）；明确记录API汇总延迟，不把顶层状态冒称成功。Actions另有Node20 action被Runner强制Node24的上游弃用提醒，不等于测试失败。

附件release-validation.json绑定准确源码、SHA、每步状态和本机真实公开资料结果；记录时状态快照不追溯改写。更新使用[UPGRADE.md](https://github.com/DayuGuo/Pivot/releases/download/v0.2.0-preview.4/UPGRADE.md)中的原安装用户和原--state，管理器先停写备份，保留原项目、卷、密钥、密码和静态站。不重新init、不删卷、不可用保密稿件试错。未连接/部署用户VPS。

## 集成状态

PR #1曾因自动审批认为默认分支发布需明确授权而未合并；当时main为a898a02。用户于2026-11-04明确授权后，已合并为f67f24e0dc2fef8639d122cc0e545ccdfe73332f，未部署VPS。先前审批拦截是历史状态，现已解除。预发行源码d7c90b0及当时验收/数据记录不追溯改写。下一阶段见spec021。
