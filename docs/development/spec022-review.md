# spec022：一致反馈历史与独立评价包

交付[PR #3](https://github.com/DayuGuo/Pivot/pull/3)已推送，未自动合并；冻结源码18d2391之后仅交付文档变化。

## 已执行的授权操作

PR #2在用户明确授权后，以冻结head dd6cd4cf9d9bf680e472b022b8a3747b44b001b6合并，main合并点42f720c1e83a8a4ddb9ac5e93f93a1d9e65fc145，GitHub记录2026-11-04T22:39:04Z。本批在codex/evidence-review-integrity独立开发，不自动合并后续PR，不连接/部署VPS，不发布新的VPS Release。PR #2合并自动触发既有main amd64包CI41927132953，原生构建/受限内存隔离安装、并发、重启/恢复和浏览器步骤均success、生成CI artifact；这只包含PR #2，未在用户VPS部署，也不含本批新功能。本机更新仅使用保留项目选定模型环境的scripts/start.sh，未读取全局认证文件。

## 代码逻辑复核和修正

1. **P2，已修复**：人工反馈历史latest_id和页原先分两条SELECT读取。用真实PostgreSQL回滚夹具，在首条SELECT执行后由do_orm_execute注入一次合法追加写入，确实返回旧latest_id与新items，先失败日志artifacts/spec022/history-race-red.log。现改同SQL head/page CTE与LEFT JOIN，单语句MVCC快照；空页仍保留head。该复现是确定性SQL交错，不是独立多worker压力测试；已有真实HTTP并发写冲突E2E继续回归。
2. **维护边界**：claim_review_sources承担精确历史版本/所有者/角色/CAS校验；claim_review_queries承担有界查询与投影；claim_reviews保持输入和Action Gateway组合。指纹ReviewAction、回执、原Answer/旧版本/人工关口不改。HTTP路由互导加入机械约束；纯投影不导入DB/HTTP/供应商。边界检查只约束直接静态导入，不证明所有动态依赖安全。
3. **新功能的引用合同**：历史引文必须匹配版本/摘要/文件hash、Unicode实际跨度及逐字quote。原件引用重新计算页/段与metadata来源，不复制AI自定义标签或URL。坏来源整包409，不静默裁剪/伪造原件依据。输出正文SHA可复算，文件名/媒体类型和metadata可复算原版本content_digest。
4. **P2，下载中的身份变化，已修复**：在Mock UI暂停导出响应、切换登录后释放响应，初版仍成功生成下载。先失败日志artifacts/spec022/inflight-red.log；现于发请求前及真正生成文件前各复核会话，第二次变化清除材料、不下载。第一轮尚未完成的完整回归已主动停止（exit143）、对应旧源码verify CI41928749895取消，不称成功。
5. **前端生命周期**：新下载入口先复核会话身份；加载/失败/成功都有可读提示，失败可重试。路由key和alive标识阻止切换资料后的旧请求自动下载。所有浏览器下载只在本人主动点击后触发，不增加后台预取/N+1模型请求。

没有声称已证明整个项目没有逻辑缺陷。该批复核重点为近期人工反馈/资料证据路径，以及新导出读取；正式业务的权限与数据约束由原全套回归继续覆盖。

## 独立评价包范围

在回答下选择“下载独立评价包”，得到私人JSON：同一历史版本的完整正文和作者资料、文件/版本摘要、PDF页或Word提取段，以及随机顺序候选和空白assessment。AI支持判定、采用/待核对桶和索引、原问题、遥测、模型身份与既有人工意见不输出；引文按白名单重建。原始材料/结论文案仍可能影响评价者，作者未匿名，所以只称隐藏AI标签的独立评价准备包。不是匿名/双盲评审，也没有新专家评分、受邀评价者账号、回传或自动评分。

没有新表/迁移。GET只读、本人编辑/主编对象鉴权、no-store/attachment；下载前后不改Answer、版本、Check、复核、回执或业务审计。原件路径仍要求登录，无共享token。没有模型人工确认/邮件/决定工具，EMAIL_SEND_ENABLED=false。

## 实际证据

合并后main本身另有verify41927132915 success，实际1260后端516.81秒＋84浏览器2.4m；这是PR #2的合并验收，不与本批新功能混计。

- 冻结源码18d23910c59e0837e4fbcd8208faca4b9754aa8d本机完整scripts/verify.sh **exit0：1287后端381.43秒＋88浏览器2.3m**；Ruff/格式、ESLint/TypeScript、研究/依赖/离线公开引文18、Alembic升级/零漂移、准确API/Web构建启动全部通过。5条第三方弃用警告，未删除测试。日志artifacts/spec022/full-verify-final.log，真实JUnit artifacts/pytest.xml。
- 同源码远端static-demo41929773645 success：两轮11项各11.4/10.9秒，原生静态镜像离线安装也通过；同源码远端完整[verify41929773512](https://github.com/DayuGuo/Pivot/actions/runs/41929773512)全部步骤与顶层均success：1287后端419.64秒＋88浏览器2.0m，5警告。日志remote-verify-final.log，实际head/status/jobs记录ci-final.json。
- 专项API：49通过9.80秒，含原反馈23＋新评价26；日志artifacts/spec022/api-delivery-focused.log。移模块后首次原反馈有1例仍指向旧内部路径，按新共享服务修夹具注入点后全部原断言保留。
- 相关Playwright：初轮修夹具后31通过18.2秒；修复请求中身份变化后最终32通过18.1秒，包含真实DB版本链、实际JSON文件下载、503重试、迟到结果、登录变化、历史基准及真实HTTP并发写。首轮30过/1失败为登录夹具安装早于初始会话加载，增加明确初始加载等待后通过，不删除断言。日志browser-focused.log与browser-focused-final.log。
- 静态：Ruff/格式、ESLint/TypeScript、研究/模块边界已单独通过。Impeccable检测[]，desktop375px截图已查看、无横向溢出；UIUX Pro Max本轮检索download feedback error recovery，Frontend Design/Impeccable按既有Hermes Operate方向保持布局，Web Guidelines最新官方规则已读。不是屏幕阅读器/实机键盘/跨浏览器认证。
- 本机公开材料：已有research-findings-word和clinical-word历史真实回答，实际浏览器各下载一份，分别2和3条候选；完整正文、作者、逐字引用/原件位置与版本一致，标签/旧人工意见省略，原资料投影相同。实际新增模型0、业务写0、页面错误0；test driver只检验包内容，不充当专业编辑判断。仅本机历史夹具验收，不是fresh-clone样本，通用CI由合成API/PW用例重新建立数据。
- 本机应用已更新；前后33张publishing_*表940行，逐表完整行排序hash一致，artifacts/spec022/data-preservation-final.json。会话/登录审计不在此业务表集合内。无需迁移/回退/重置，未执行恢复操作。
- 真实DeepSeek凭据本阶段未重新请求鉴权；既有选定服务配置保留，不把health.available当供应商成功证据。没有新API成本或token消耗。

## 研究来源与后续专业关口

本轮重新阅读[OJS官方review guide](https://github.com/pkp/ojs-user-guide/blob/main/en/editorial-workflow/review.md)和[Janeway官方editor guide](https://janeway.systems/pages/support/guides/editor-guide-to-review.html)，采纳固定材料、权限控制及评价/决定分离；不采纳自动邮件。无字段变更，上游固定索引及已有字段映射不重写。

下一阶段邀请实际编辑先独立评价，再设计受鉴权的评价结果回传、多评价者分歧与版本追踪；先确定独立人工评价的标准与授权。之后扩充许可明确的原生Word/多栏PDF脚注样本。受控真实稿件试点之前，请专业工程师复核文件解析隔离、对象鉴权、模型出域隐私、持久历史、运行/迁移分权与备份恢复。ORCID OAuth/共享账号/公开投稿继续不以本批导出代替实现和验收。
