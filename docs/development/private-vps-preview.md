# 完整 VPS 私人体验包验收

2026-11-04，spec017。目标为在原静态站旁运行受限单用户应用，不执行用户VPS部署。本机为ARM64，RackNerd为amd64，平台证据分开记录。

## 实现

专用离线镜像包包含PostgreSQL17、单worker FastAPI、Next.js standalone、独立Compose、Python标准库管理器、合成PDF/DOCX与SHA256。独立pivot-*项目/卷，只有环回Web端口3210；无Mailpit/本地模型，运行总上限1472MiB。镜像在开发机/CI构建，服务器不编译。

初始化私人编辑，默认演示密码不可用；其余合成身份不可用随机密码不披露。登录页不预填/展示演示密码；独立HTTPS开启Secure cookie，SSH隧道默认HTTP仅环回。部署秘密在包外700目录/600文件，应用从环境接收，镜像/发行归档白名单不包含状态或凭据。不改变Codex主配置。邮件固定禁用且启动复核；模型无最终确认/决定工具。

管理器支持停止保留卷、数据库＋原件一致备份、更新前自动备份，以及只向新项目/新卷恢复；拒绝覆盖未知容器或既有卷。失败首次启动保留原状态，可用原包重试；不要求删卷。恢复后的原件属主在入口修正，然后UID10001/有效能力清零运行。备份SHA只用于完整性，不是未知来源认证或加密。

额外修复：资料chat/import代理从30秒调整为75秒，覆盖后端60秒共享预算；不扩大后端推理/工具权限。上一轮GitHub verify41809242259实际有两项畸形HTML作者失败（1155通过）；Python补丁版本解析行为不同，现明确拒绝声明文本，不依赖异常是否抛出，不改测试断言。

## 执行记录

本机静态检查/TypeScript通过；16项私人引导/凭据权限/项目隔离测试已通过。首轮管理器用Path.open的opener不兼容，改为os.open独占创建，保留失败日志。真实包首轮两格式导入/核对/引用/重启通过，恢复因Compose create不支持--no-deps而失败；更正后发现私有700目录在恢复后的属主遍历受限，新增仅初始化所需DAC能力，降权后无有效能力。失败测试项目保留数据，没有对现有服务或用户VPS做删除。

完整 `scripts/verify.sh` 实际退出0：**1173 Pytest（520.72秒）＋66 Playwright（2.0m）**；静态、迁移/漂移和准确API/Web构建通过，4项既有第三方弃用警告。证据 `artifacts/vps-full-verify.log`。更新后的部署管理器另通过格式检查；包级实验以下单独记录。

ARM64开发机实际包级Mock与DeepSeek均通过：两种合成文件导入、候选不升版、测试驱动独立核对、逐字原件引用、同会话重启，以及新项目/新卷的完整数据库＋原件恢复。当前源码的负责人确认由测试驱动模拟，不是模型动作或专家签收。原应用与静态站容器ID保留，模型密钥在内存中借用既有服务环境，不写测试状态文件；DeepSeek服务的邮件/批准/正式决定/正式人类确认计数均0。实际进程UID10001/CapEff零；数据库/API端口未发布。

实际预编译私人界面的两格式定位、刷新、375px及空白登录/无演示快捷账号均通过；Mock与真实DeepSeek分别记录 `vps-mock-browser.json`、`vps-deepseek-browser.json`，错误/邮件/决定/确认请求0。API+重启/恢复报告 `vps-preview-acceptance.json`、`vps-live-acceptance.json`。短合成DeepSeek两格式各完整操作约5.34/5.12秒。

额外在受限真实服务导入已许可公开八作者Word（34327字符/128段）及其明确转制PDF（34622字符/25页），逐版核对并问Results：9份CPG/62条声明与原文相符，精确引用定位正确；两次完整操作约11.31/23.12秒。首个附加驱动把人工更正后的所有元数据引用都误要求有原件定位，报KeyError；修正驱动后重测，不放宽产品引用规则。报告 `vps-public-paper.json`。这不是全面语义证明：其中Word附加回答提到补表，但所选短摘引未覆盖补表句，仍须编辑查看上下文，不能把所有附带文字标为已验证。

该长稿负载的cgroup各自观测峰值DB111075328/API142327808/Web78688256字节（约106/136/75MiB），全部无OOM；峰值不一定同时发生，不代表最大文件、并发或整台VPS内存。容器上限仍为320/768/384MiB。本轮未在用户VPS实装。

最终发布源码为 `a408b63d708a1a3ae405455e2f19a5c5d4bd0e8c`。原生x86[完整包验收](https://github.com/DayuGuo/Pivot/actions/runs/41817314184)、[完整应用CI](https://github.com/DayuGuo/Pivot/actions/runs/41817314556)、[原静态Demo回归](https://github.com/DayuGuo/Pivot/actions/runs/41817314161)全部实际成功。远端完整CI **1173 Pytest（364.28秒）＋66 Playwright（1.7m）**，4项第三方弃用警告；迁移/漂移、静态与准确构建通过。此前旧候选完整CI因许可文件修正被取消，未冒称通过。

原生x86使用Mock、不注入真实密钥，安装相同预编译产物后两格式/独立核对/精确引用/重启/完整隔离恢复与浏览器均通过。cgroup观测峰值DB84746240/API132907008/Web56807424字节，全部无OOM，邮件/决定计数0。实际浏览器确认/邮件/决定请求与页面错误0。它与ARM开发机的真实DeepSeek实验分别列明，不混称在x86/VPS调用了真实模型。

已发布[私人体验预发行 v0.2.0-preview.1](https://github.com/DayuGuo/Pivot/releases/tag/v0.2.0-preview.1)，4附件：完整离线包、SHA256、INSTALL.md、去掉私密状态路径的release-validation.json。包为上述x86 CI的确切产物：283307112字节，SHA256 `17511ef9b3b9d5b261c4f9da104ce89c5999abadb716c34e80f87f2fd8b67de3`。外层及所有内部文件SHA一致，归档仅8个已知文件，不含密钥、状态、数据库或上传原件；三镜像均amd64。Next standalone遗漏的许可文本已补齐，实际Web镜像内487份npm/字体notice及Noto OFL确认保留，没有替项目选择新的开源许可证。GitHub502首次没有创建草稿，已安全重试；四附件服务端SHA256均与CI文件一致；匿名下载INSTALL/SHA文件逐字节相等，公开归档流可访问且gzip头正确（未重复下载整包）。结果见本地 `artifacts/vps-release-amd64`。

本轮真实模型遥测（仅专属隔离项目，含附加驱动重测）为6次完成导入/6次回答、20provider attempts/18有效完成、业务失败0，输入83269/输出18378 tokens、provider耗时77921ms；费用null待账单，主Codex用量未知，原生子Agent0。报告 `vps-model-telemetry.json`；不把协议重试当作首次全部成功。

## 使用与范围

[包内安装与数据保护说明](../../infrastructure/vps/README.md)、[规格](../../specs/017-private-vps-preview.md)。原静态站/原浏览器资料不迁移；实际VPS的SSH、防火墙、TLS、OS内存与负载未验收。本机/CI容器上限实验不等于整台2.5GB VPS性能保证。仅少量公开授权或合成材料，正式保密试点前仍需专业安全、运维与隐私复核。

依据：[Docker资源约束](https://docs.docker.com/engine/containers/resource_constraints/)、[Next.js standalone](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)、[AlmaLinux8 Python3.11软件包](https://errata.almalinux.org/8/ALSA-2026-4473.html)。Compose网络文档在本轮两次抓取超时，具体隔离以实际Compose配置/端口检查验证，不冒称取得未读内容。
