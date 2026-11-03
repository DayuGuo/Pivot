# 产品展示 Demo 交付记录

2026-11-03。当前阶段是本机可演示、适合GitHub展示、可生成RackNerd安装包的产品项目。未创建/推送远端GitHub仓库，未连接VPS，不是生产系统上线。

## 实现与体验

一条命令 `./scripts/demo.sh`，健康检查通过后访问 http://localhost:3110，无登录或模型凭据。中心对话常驻；左侧本人工作/主对话/新稿录入、底部日历筛选截止日；右侧当前步骤、原文、作者和证据。资料/会话/未发消息保存在当前浏览器，手机使用工作与材料抽屉。

真实可操作：编辑题名、摘要、全部正文段落和既有作者元数据；录入本地新稿；导入不超过1 MB的有效UTF8 TXT/Markdown；引用高亮与重复定位；真实公开论文链接；重置。摘要与全文独立，历史来源文字变化后提示过期。本文所谓“真实可操作”指浏览器内演示操作，不表示数据库、权限或模型能力。

所有助手输出均为明确预设模拟，原创合成材料不含真实作者身份。新文本可以阅读和编辑，不假装被通用AI完整理解。没有PDF解析/ORCID认证/业务API/外发/正式决定。现有真实后端 `/publishing` 与模型配置没有被展示版替换；本轮未重建主业务栈，源码新增 `/demo` 已在独立验证栈13100验收。

## 实际执行证据

| 检查 | 实际结果与范围 |
| --- | --- |
| 完整 `scripts/verify.sh` | 最终退出0：835 Pytest、46 Playwright；数据库迁移/漂移、研究门禁、Ruff、ESLint、TypeScript、API/Web准确构建启动均通过。后端326.79秒，浏览器1.6m；1项既有Starlette/httpx warning。`artifacts/demo-full-verify-final.log` |
| 独立静态包 | 相同11个Demo场景在3110全部通过，最终一键版本报告 `artifacts/demo-final-one-command-e2e.log`。包含长正文不截断、旧引用失效、重复引用、会话隔离、日历、375px抽屉、纯文本XSS及零`/api`请求 |
| 补充真实浏览器操作 | TXT/MD导入并刷新恢复、坏UTF8和PDF拒绝、重置、HTTP环境UUID后备、损坏缓存恢复；pageerror0、API请求0。`artifacts/demo-extra-acceptance.json` |
| 响应式 | 1440×1000、1024×768、768×900、375×812、667×375全部无横向溢出且输入在视口内；减少动画模式下抽屉导航通过。仅Linux Chromium，不声称Safari/iOS实机验收。`artifacts/demo-render-report.json` |
| 一键启动 | 原生构建、专用label更新、只读/128MB/0.5CPU/环回端口与health通过。无效端口99999实际退出1，未修改服务 |
| 运行资源 | 初次空闲15.39 MiB，128MB限制；Nginx1.28.3。不是VPS容量/线路测试 |
| 静态归档 | 154项路径、约4.7 MB；首页与资源完整，无源码/API/env/node_modules。`artifacts/demo-package-manifest.json`保存最终包字节数与SHA256 |
| amd64离线包 | 约29 MB，实际manifest为linux/amd64、标签`publishing-os-demo:linux-amd64`，构建/加载通过；本机ARM64无x86仿真，启动报`exec format error`退出255，3112测试11条均连接拒绝，**未通过运行验收**。`artifacts/demo-amd64-build.log`、`demo-amd64-runtime.log`、`demo-amd64-e2e.log` |
| GitHub CI | 新增独立Demo workflow，定义x86 runner构建/加载离线包→health→11条验收→上传包与证据，远端尚未执行 |

首轮完整回归是835后端通过、45浏览器通过/1失败：两个并行Playwright进程共用输出目录，清理了仍在使用的trace，抛ENOENT。保留 `artifacts/demo-full-verify.log`。修正为DEMO_PATH静态运行使用独立报告/追踪目录；完整重跑835+46退出0，不删除或跳过测试。

amd64离线包的实际运行留待x86 CI或VPS，不更改本机系统以安装仿真。架构无关静态包和本机原生版本已经验收，展示阶段可继续；不能将`docker run`返回ID说成服务已正常运行。此前误导的无架构离线包已移除。

## 独立复核与视觉证据

采用Frontend Design、UI/UX Pro Max、Impeccable、Web Design Guidelines；继承DESIGN.md与用户Hermes截图，不改变已有视觉系统。UI/UX推荐的作品集/衬线方案不适用本工作台，仅采用交互/可访问性知识。四技能约定与surface brief见docs/design/demo-workspace.md。未运行detector、没有comp-led或新设计系统持久化。

独立finish reviewer初审fix：新稿正文/摘要复用截断、重复来源不重新定位、重复eyebrow。全部修复并加两条回归；同一reviewer复核源码/截图/日志逐项resolved，ship范围仅这三项。独立安装reviewer发现ARM离线包不匹配常见amd64 VPS；目标平台、标签、包名、文档及CI已修，元数据与校验和复核resolved。两位复核未自行运行Docker/VPS或远端CI，未用其意见替代实际测试。

提交的 `docs/preview/demo-desktop.png`（1440×1000）、`demo-mobile.png`（375×812）是真实本地Chromium截图，来源http://127.0.0.1:3110，仅原创合成资料，不是合成界面图；未复制用户Hermes截图或其中私人会话内容。补充材料抽屉/平板截图留本地artifacts。继承色彩、字体、边界与响应式适配，DESIGN.md保持原样。

## 费用、协作与后续

本轮新增产品模型请求0，DeepSeek未调用。使用既有Codex与电脑，未购买服务器或专业服务。Codex子任务为隔离测试文件编写、只读UI复核、只读安装复核，各返回可检查成果；Token/费用未知，不伪造精确成本或称为DeepSeek原生子Agent实验。主Agent整合权限边界与最终验收。

模式扫描时347个文本文件未发现指定sk/常见GitHub/AWS/private-key模式，历史891文本对象未发现sk/private-key模式；只记录路径/计数，不打印疑似值。这是有限模式扫描，不是完整凭据审计或公开发布许可。未读取全局auth。

下一步先收集演示反馈；之后按spec011补受控资料录入、版本化解析、只读证据问答与专业复核。VPS安装、域名/TLS、实际线路和远端CI留下一次部署验收，不接入保密稿件或开放真实邮件。
