# 常驻主对话改版交付

日期：2026-11-02。最新用户反馈是恢复AI/对话优先，避免成为传统操作台。本轮实现契约spec005，保留spec004四页全部操作与原真实投稿链。

## 当前交互

左侧任务导航，中间常驻主对话，右侧上下文材料。普通桌面对话约占可用宽度43%；展开材料时对话仍保持可用宽度。四页切换不卸载对话，保留输入、消息和滚动。窄屏/放大通过实际容器大小重排，正文、输入和发送按钮都按真实可见区域验收。

可以询问当前稿件状态/下一步、尚未解决问题及原文依据；队列范围可查找今日任务或待邀请稿件。对话产生受控筛选/导航并打开工作材料。先人工选人后可要求准备私有邀请草稿；准备决定只打开中性编辑页，不选择学术结论。明确的另一稿件编号可以切换目标，模糊稿件名称要求澄清。

语义理解为明确标注的上下文Mock，未调用真实模型。对话、上下文快照、草稿及人工核验实际写入PostgreSQL；不是前端展示文本。旧消息标明当时稿件编号/版本，当前上下文包含版本与轮次。原有模拟检查工具收进主对话的展开区，不再作为浮动聊天入口。

## 数据、安全和恢复

新增`editorial_chat_turns`一表，迁移e7b24c91a603；原草稿/视图表复用。记录user+journal+request UUID唯一键、输入摘要、上下文与回应，同事务审计。GET只读最近50回合，历史不跨用户/期刊泄漏；POST需编辑/主编、CSRF与严格DTO。失败重试沿用UUID，丢失响应不重复执行；右侧刷新失败只重试刷新。

已有人工正文/主题/期限或自定义收件人不覆盖；候选选择自动产生的仅收件人元数据可以保留并补齐空信件。准备类请求先同步当前人工草稿，纯查询不要求完成全部表单。并发变更后的本地候选内容可预览、恢复或明确丢弃，不能因新服务器基线静默删除。空的自动收件人元数据不误报成人工正文冲突。

没有真实发信、正式决定、撤稿、取消评审或关键权限变更动作。聊天准备不构成审批。EMAIL_SEND_ENABLED=false；未使用已暴露密钥、未修改主模型或全局Codex配置，未执行生产部署。真实模型、完整正式流程和生产审批仍待后续实现。

## 验收证据

最终 `./scripts/verify.sh` 全量通过：**227 Pytest（22.39秒）+21 Playwright（46.6秒）**；Ruff/format、模型网关依赖边界、ESLint、TypeScript、PostgreSQL迁移/漂移及Docker生产构建通过。数据库head为e7b24c91a603。Pytest有1项第三方Starlette/httpx弃用警告。阶段验证另通过45个聊天API用例和13个工作台浏览器场景（原7+新增6，38.2秒）。`./scripts/start.sh` 已完成当前代码构建和启动。

新增覆盖：

- 同一对话DOM、未发送草稿、消息跨四页保留，刷新恢复；旧消息上下文不随选中稿件变化。
- 真实fixture状态/原文来源，队列筛选与右侧动作；聊天响应丢失后相同UUID重试仅保留一个回合。
- 从真实UI选人准备邀请，人工内容不覆盖；延迟PATCH时聊天等待同步，已提交回复被延迟时新人工编辑仍保留并可恢复。
- 4页×1366/1440/1920/390共16种布局，加4页CSS200，检查正文至少140px、输入/发送按钮真实可见、无横向溢出；展开材料仍有主对话。
- 保留全部原工作台场景：版本证据、段落级阅读恢复、笔记失败恢复、候选比较/邀请、两轮核验/决定草稿、模拟任务取消重试、主题/键盘/角色拒绝。

最终运行检查：`/api/health` HTTP 200，database=postgresql、email_send_enabled=false、model_provider=mock；Mailpit捕获总数0。最终主编阅读页截图artifacts/conversation-primary-final.png。

日志：artifacts/conversation-start.log、artifacts/conversation-workbench-acceptance.log、artifacts/conversation-final-verify.log。截图：artifacts/conversation-{work,read,reviewers,revision}-{1366,1440,1920,390}.png，及相同4页的-zoom200.png。当前源代码检测artifacts/conversation-design-audit.json为[]，不是WCAG全面认证。

独立源代码/1440截图审查确认主对话显著，指出未保存人工正文竞态；修复后用真实网络时序复现验证。实际验收又修正CSS缩放发送按钮裁切、正文不足和字体偏好加载前恢复阅读位置的问题。可见面积检查覆盖真实正文与发送按钮，而不仅检查外层面板。

仅实际验证Linux Chromium；CSS200使用document.style.zoom，不冒称OS或浏览器工具栏缩放。Windows/macOS、Safari/Firefox、真实手机软键盘未实测。数据与分析全部合成，原始文本下载与引用一致，不冒称PDF/DOCX解析或真实外部身份核实。

委派记录：docs/development/conversation-delegation.json。使用隔离文件所有权的原生Codex助手；真实DeepSeek调用为0，工具未提供的Token、计费及任务耗时保留null。主Agent集成、权限复核和最终验收。
