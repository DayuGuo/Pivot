# 完整 VPS 私人体验包验收

2026-11-04，spec017。目标为在原静态站旁运行受限单用户应用，不执行用户VPS部署。本机为ARM64，RackNerd为amd64，平台证据分开记录。

## 实现

专用离线镜像包包含PostgreSQL17、单worker FastAPI、Next.js standalone、独立Compose、Python标准库管理器、合成PDF/DOCX与SHA256。独立pivot-*项目/卷，只有环回Web端口3210；无Mailpit/本地模型，运行总上限1472MiB。镜像在开发机/CI构建，服务器不编译。

初始化私人编辑，默认演示密码不可用；其余合成身份不可用随机密码不披露。登录页不预填/展示演示密码；独立HTTPS开启Secure cookie，SSH隧道默认HTTP仅环回。部署秘密在包外700目录/600文件，应用从环境接收，镜像/发行归档白名单不包含状态或凭据。不改变Codex主配置。邮件固定禁用且启动复核；模型无最终确认/决定工具。

管理器支持停止保留卷、数据库＋原件一致备份、更新前自动备份，以及只向新项目/新卷恢复；拒绝覆盖未知容器或既有卷。失败首次启动保留原状态，可用原包重试；不要求删卷。恢复后的原件属主在入口修正，然后UID10001/有效能力清零运行。备份SHA只用于完整性，不是未知来源认证或加密。

额外修复：资料chat/import代理从30秒调整为75秒，覆盖后端60秒共享预算；不扩大后端推理/工具权限。上一轮GitHub verify41809242259实际有两项畸形HTML作者失败（1155通过）；Python补丁版本解析行为不同，现明确拒绝声明文本，不依赖异常是否抛出，不改测试断言。

## 执行记录（持续更新）

本机静态检查/TypeScript通过；16项私人引导/凭据权限/项目隔离测试已通过。首轮管理器用Path.open的opener不兼容，改为os.open独占创建，保留失败日志。真实包首轮两格式导入/核对/引用/重启通过，恢复因Compose create不支持--no-deps而失败；更正后发现私有700目录在恢复后的属主遍历受限，新增仅初始化所需DAC能力，降权后无有效能力。失败测试项目保留数据，没有对现有服务或用户VPS做删除。

完整scripts/verify.sh、修复后的包级恢复、浏览器和amd64 CI正在执行；此处没有将未完成检查写成通过。证据分别位于artifacts/vps-full-verify.log、vps-mock-lifecycle-ownership-fix.log和GitHub Actions。

## 使用与范围

[包内安装与数据保护说明](../../infrastructure/vps/README.md)、[规格](../../specs/017-private-vps-preview.md)。原静态站/原浏览器资料不迁移；实际VPS的SSH、防火墙、TLS、OS内存与负载未验收。本机/CI容器上限实验不等于整台2.5GB VPS性能保证。仅少量公开授权或合成材料，正式保密试点前仍需专业安全、运维与隐私复核。

依据：[Docker资源约束](https://docs.docker.com/engine/containers/resource_constraints/)、[Next.js standalone](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)、[AlmaLinux8 Python3.11软件包](https://errata.almalinux.org/8/ALSA-2026-4473.html)。Compose网络文档在本轮两次抓取超时，具体隔离以实际Compose配置/端口检查验证，不冒称取得未读内容。
