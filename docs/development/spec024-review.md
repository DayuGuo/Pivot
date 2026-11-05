# spec024：当前稿件建议与修回对照验收

最终界面源码：aadccc358f573333e8d687d40aedc3f174505e56。后端及模型协议与116ca1f相同；d45223c仅补齐严格恢复夹具，aadccc3仅增加版本/历史界面提示和浏览器断言。基于未合并PR #4的codex/evaluation-returns建立增量分支；没有合并PR #4、修改main或部署VPS。无新迁移，数据库head仍17d51aeb9408。

可审查交付：[PR #5](https://github.com/DayuGuo/Pivot/pull/5)，基于PR #4的增量，两者均未自动合并。

## 最终验证

本机scripts/verify.sh exit0：1344后端、6条既有第三方弃用提醒，596.84秒；93浏览器3.5m，静态、研究/依赖约束、离线引文18、迁移零漂移与准确镜像构建启动均通过。

最后版本提示补强仅在后端测试阶段改两个React文件和同一浏览器用例；apps/api、packages、tests/api和verify脚本Git对象与d45223c完全相同，随后lint/typecheck/build和全部浏览器测试使用aadccc3。不是在测试中修改后端或验收脚本，也没有跳过或删除测试。历史对照桌面/375px实际已查看，版本v1→v2、流程变化后历史警告均可见。

前一d45223c远端verify42018557800实际1344后端525.91秒＋93浏览器2.5m通过；最后aadccc3的[完整CI42019900996](https://github.com/DayuGuo/Pivot/actions/runs/42019900996)顶层与全部步骤成功，实际1344后端400.63秒＋93浏览器2.0m；[静态42019900851](https://github.com/DayuGuo/Pivot/actions/runs/42019900851)成功。精确状态见spec024-results.json。后续提交只更新交付文档，未改运行/测试/验收脚本。

## 产品行为

资料区与正式出版对话共用至多三条小型建议，只追加草稿，保留原输入、不自动发送。依据真实缺项、作者关联、已有证据分歧、当前角色/归属/阶段/待办，不根据尚未读取的论文想象质量。用户当前公开资料占位v1尚无全文/作者，实际浏览器只提示补资料。权限/版本/修订号不匹配或资料切换的迟到响应不会恢复旧建议。

正式修回通过现有聊天请求比较作者已获分享的要求、实际原/新稿与回复。严格逐字唯一引文、版本/文件SHA/位置、实际非空白改动、受限覆盖与第二个独立AI上下文检查；不足则待核对。已有作者回复不能同时判为未回应，哪怕两个模型步骤均同意。大修仍需正式重新送审。分析不勾选人工复核、不确认提交、不发邮件、不作决定。

guidance_rules和revision_compare为无数据库/业务动作权的纯模块；guidance鉴权路由、revision_sources来源服务、chat事务/期限/幂等集成及共用React组件分离。scripts/check-boundaries.py约束依赖，既有对话JSON保存结果，不增表。

## 已执行与先失败记录

专项39 API通过22.69秒，3浏览器通过56.9秒。首次API假定ManuscriptVersion存在journal_id，经真实数据库测试发现后移除错误假设，保留父稿件/期刊与实际文件归属检查；测试夹具id键/import问题已修正。另一次宿主沙箱不能连接隔离数据库，12纯测试通过/27连接错误，不作为产品验证，获准连接后完整专项重跑通过。

第一次真实DeepSeek两工具调用成功，但将已有回复、尚未补链接分类为未回应；新增自动回归先失败，改为“已有回复引文则不接受缺席断言”，并收紧语义提示。修复后的回归通过；旧源码完整验收中止、CI42015975923/42015976054取消，均不记成功。产品源码首次全量1344后端通过514.94秒，浏览器90通过/3失败，原因均为旧严格恢复夹具拒绝新增/api/publishing/guidance；修复只显式登记三个已知只读建议路径，不删除测试/断言，仍拒绝未知接口和任何真实mutation。恢复/建议13项专项通过8.6秒；前次完整退出1及远端42016415063失败记录保留，新的最终全量见结构化结果。

修复后实际DeepSeek deepseek-flash：两阶段总3.288秒，样本量/分组P01为修改有证据，链接P02为部分回应；所有返回引用逐字定位通过。输入2667、输出283 Token，API成本未知/null，需以供应商账单核对。包含首次实验共4次实际调用，输入5318、输出568 Token，分类返工1次，无传输失败。Mock全链与真实模型合成协议分别记录，不能冒称真实论文修回或真实模型正式工作流端到端已验收。

## 本机数据与界面

使用scripts/start.sh两次更新本机，保留已选DeepSeek环境；未读取全局认证、改变主模型或输出密钥。更新前后35张publishing_*表956行逐表摘要完全一致，24个CAS文件均与内容地址相符。真实浏览器打开用户当前资料，点建议仅填草稿；POST0、投影不变、页面错误0。登录会话/认证审计另计。

已查看桌面、375px与深色建议栏截图。深色按钮最终前景#A6B2FF/背景#2D354C，等候既有140ms颜色过渡结束后记录，未把过渡中间帧误当最终样式。Web Design Guidelines最新源已读取：https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md 。本轮修复主题变量继承、触屏44px、异步建议aria-live、长SHA换行与段落间距；原生button/details、焦点、草稿保留与页面切换均实际测试。没有宣称执行未运行的设计检测器。

EMAIL_SEND_ENABLED=false，Mailpit0。主API原投稿Mock与editorial DeepSeek是不同配置，真实模型实验以实际工具返回为据，不以health.available代替鉴权。没有VPS更新或新安装包验收。

## 重现与限制

隔离全验收：

```bash
COMPOSE_PROJECT_NAME=publishing-os-verification \
COMPOSE_FILE=compose.yaml:infrastructure/compose.verify.yaml \
DATABASE_URL=postgresql+psycopg://publishing:publishing_local@localhost:55433/publishing \
E2E_BASE_URL=http://127.0.0.1:13100 ./scripts/verify.sh
```

纯合成协议默认Mock：`.venv/bin/python scripts/accept-revision-comparison.py`。已配置DeepSeek的本机API内显式真实调用：`docker compose exec -T api python - --live < scripts/accept-revision-comparison.py`，不读写稿件/审批/邮件。

单次8段要求、每段1200字符，原稿8000/新稿与回复各12000字符窗口，最长128检索词。超出明确不完整，不能排除漏项。正式修回仍需既有校核UTF-8 txt/md全文；资料区PDF/Word原件解析和负责人确认保持不变，尚未实现两流程自动衔接。独立AI上下文不是专家，分类仍可能错误，不能代替修回复核或出版决定。下一步用许可的成对原/修订稿与回复、获授权真实编辑确定评价标准，并连接经核对的PDF/Word原件页段定位。

后续实际许可样本与评价标准见[修回评价计划](spec024-revision-evaluation-plan.md)。
