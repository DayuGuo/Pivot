# 本人日历交付记录

[草稿 PR #12](https://github.com/DayuGuo/Pivot/pull/12)已完成本阶段工程验收，保持未合并、未部署。应用源码`1d9610f5ea2d5fcc1fa9dddaa1c30943ba54f83d`；验证源码`1502d72fd88897870d313439d0cfc87ccc8133e5`只修正浏览器恢复测试等待方式及文档，应用、依赖、迁移、启动脚本和后端测试差异为空。[范围](../../specs/031-personal-deadline-calendar.md) · [官方研究](../research/deadlines-2026-11-06.md) · [结构化结果](personal-calendar-results.json)。

## 使用

在主工作台、正式出版、内部资料或演示工作台左下角展开“日历”。选择月份、日期或“逾期”，查看当前身份实际获分派的正式稿件期限，点击任务进入稿件。中央对话保持可见；有未保存资料时沿用原离开确认。

日期按浏览器IANA时区解释，页脚明确显示；服务不支持该时区时，由用户显式选择UTC。桌面日期格用方向键/Enter，窄屏、短屏及触屏用原生日期选择。逾期汇总跨月/跨年，条目包含年份；没有日期明确未设，不填假日期。原生Tab可进入并滚动到任务链接。

网络或正文超时可主动重新载入；分页422重读首批，不重复失效游标。401/403清空旧结果，身份变化重建。正式工作台待办快照变化后，日历只读刷新并保留月份/日期；其他入口展开或切换筛选读取最新，不宣称服务器推送。

## 数据与模块

唯一日期事实来自持久WorkItem.due_at：既有流程已把邀请回应/报告、负责人确认的修回和其他正式步骤期限写入任务。只显示当前期刊、本人、当前职务、有效分派及真实步骤；审稿人保持本人邀请题名，制作使用合规录用版本，历史署名冲突仍回避。作者须切换到作者职责查看草稿/修回/校样；其他职务不自动兼任。旧legacy记录不补造日期。

metadata_access共享搜索的安全题名SQL；calendar_queries只构造职责查询；calendar路由处理当地半开日期区间、DST、游标和会话复核。计数与分页均先授权，三条有界数据查询不依赖最近200篇浏览窗口，不加载原件/模型。components/calendar复用四入口。没有新表、迁移、日期修改、提醒、邮件、外部同步或跨刊汇总。

NextSteps保持身份/稿件/版本key，消息变化通过refreshToken重读数据，请求序号忽略迟到刷新，避免历史到达重建按钮而丢失点击；选择建议仍只填输入草稿。

## 实际验收

| 范围 | 结果 | 依据 |
| --- | --- | --- |
| 完整scripts/verify.sh，验证1502d72 | PR/push各1666后端＋540浏览器，每引擎180；0失败/跳过/浏览器重试 | [PR CI](https://github.com/DayuGuo/Pivot/actions/runs/42320043165) · [push CI](https://github.com/DayuGuo/Pivot/actions/runs/42320039623)，全部作业/步骤success |
| 静态CI，同一验证提交 | PR/push各17步骤success | Actions，含静态构建与隔离x86安装验证 |
| 本机后端，同一应用1d9610f | 1666项818.95秒，10条提醒；0失败/跳过 | artifacts/calendar/pytest3-final.xml |
| 本机完整浏览器，1502d72 | 540项1696.25秒/28.3m，三引擎各180；0失败/跳过/重试 | artifacts/calendar/browser4.log及退出回执 |

本机是分次验证，不声称本机完整scripts/verify.sh退出0；完整门禁权威是上述确切提交的远端两轮实际执行。验证脚本已核对应用与后端测试树相同、全量日志、JUnit及浏览器最后结果。CI后端实际424.69/535.59秒（各10提醒），浏览器14.9/16.1m。语法、Ruff/format、研究/模块边界、18条离线引文、迁移无漂移、ESLint/TypeScript及准确镜像构建均通过。

专项53 API、36日历、12建议/真实流程、3年份可见性、18重复恢复与全量重叠，不累加。仅合成或许可公开材料，应用真实模型请求0，本轮未验证DeepSeek凭据。Codex辅助审查的Token/费用未暴露，记null，不推断为零。

## 失败与修复保留

- 两处早期API夹具违反分派时序/冻结版本，改合法构造，未弱化数据库守卫。分页422、未知时区、响应头到达后正文停住、职责变化未刷新均先在旧镜像红测，再修复。
- 8e4c171本机完整exit1：1666 API过、536浏览器过1失败。历史恰在按下/松开间返回，使建议按钮重建。稳定上下文key与数据刷新修复，保留原失败及受控红测。
- cc02b68本机后端过，因新红测证实跨年逾期缺年份而主动停止，exit-15，不记完整通过。逾期补年份，普通月视图保留月份标题；36专项通过。WebKit首张截图未拍到条目，保留旧图，改原生Tab和两日期完整入视口断言，重叠3项11.5秒通过，重拍三图并逐张查看。
- 1d9610f本机完整exit1：1666 API过、539浏览器过1失败。WebKit即时URL比较先于恢复观察稳定。原生history旧镜像诊断5次42.1秒均恢复；不宣称五次重现了原时序。按[Playwright官方断言](https://playwright.dev/docs/test-assertions#auto-retrying-assertions)保留同一conversation精确谓词，改等待式URL断言，默认5秒/用例重试及消息/草稿/请求数条件不变。两恢复场景三引擎各重复3次，18项2.2m通过；随后完整本机浏览器及确切验证提交CI通过。

原日志/trace在忽略的artifacts/calendar/first-full-failure、second-full-interrupted、third-full-failure及各红测目录；没有删测试、改预期或清库。后续监控扫描整份日志，不只读取尾部。

## 视觉与运行边界

依据既定四技能和DESIGN扩展现有侧栏，遵守“Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining.” 单次日历目标检测[]不替代验证。通用fresh审查者按Impeccable要求独立查看十张重拍，解决月历P2；另看三张跨年图给出年份限定resolved/ship，共三轮。没有专用审查agent_type可用，实际使用通用fresh Agent；回执不认证后端、真机或读屏器。

本机Linux Chromium/Firefox/WebKit，WebKit显式Mesa软件渲染；不等同物理Safari、Edge、手机IME/软键盘认证。真实编辑评价、外部专业安全复核及本阶段新日历的原生VPS包安装/容量重测均未执行。

独立Mock项目13100（API18100/DB55433/Mailpit18025）前后端200，PostgreSQL正常，EMAIL_SEND_ENABLED=false、Mailpit0。原主应用四容器仍保持2026-11-06 12:59的原停止状态，主库、原件、模型环境及VPS未动。邮件和关键决定仍由负责人逐项确认；本阶段没有发行Release。

PR #11按授权合入main，bb340da树与47057cc已验收树一致。main原生amd64包、保留数据升级/隔离恢复CI成功是该main基线的证据，不能冒充日历已在VPS实装。当前交付草稿PR #12基于main。后续纯文档提交会触发独立CI，其状态另行查看，不能从1502d72推断其结束。

下一技术切片：基于同一职责SQL的只读期限问答；再按试用反馈规划负责人的受控改期、并发/历史与审计。跨刊、提醒、同步、注册和正式发布后置，继续安排有权编辑评价及专业工程复核。
