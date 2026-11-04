# spec017 · 独立完整 VPS 私人体验包

目标：原静态展示站保持运行，在2核/2.5GB VPS旁部署完整应用，体验真实DeepSeek与受限PDF/Word导入。不是正式生产上线，不连接或修改用户VPS。

- 原生linux/amd64 CI预编译API/Web/PostgreSQL，离线镜像、Compose、标准库管理器、合成样本和SHA256一起交付。VPS不编译、不自建模型、不需要Codex。
- 独立pivot-*项目/卷/环回3210；数据库/API不发布端口。DB320MiB/API768MiB/Web384MiB，总1472MiB硬限制，无Mailpit。单用户顺序操作，不宣称并发容量或整机实测。
- 初始化要求独立编辑邮箱和私有密码，公开演示账号密码不可用；后台保留随机不可用密码的合成角色。镜像/归档无凭据、用户数据或运行状态；部署私密状态在包外700目录/600文件，运行时仅环境注入。
- 默认SSH隧道，独立HTTPS子域需显式Secure cookie；不更换原站代理/域名，不迁移或删除浏览器localStorage。
- 邮件发送固定false，启动也拒绝启用。模型没有邮件/确认/关键决定工具；版本核对与正式决定权限不改变。
- 普通启动保留卷；更新先停写备份数据库和原件，再加载镜像/增量迁移。备份完整性校验；恢复只到新项目/新卷/新端口，拒绝覆盖现有数据。旧包保留，不自动数据库降级。
- 真正执行包安装、私有登录、两格式导入/候选不升版/独立核对/引用、重启/完整恢复、实际浏览器定位、内存与OOM检查；Mock验收与真实DeepSeek验收分别记录。x86成功后才将确切CI包标为可用于RackNerd。
- 运行scripts/verify.sh，并记录本轮发现的远端Python HTML解析兼容缺陷与修复；不删测试。未实装用户VPS不得宣称部署成功。

安装命令和边界见[infrastructure/vps/README](../infrastructure/vps/README.md)，执行证据见[交付报告](../docs/development/private-vps-preview.md)。
