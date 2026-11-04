# Pivot 私人体验版

这是完整 Next.js＋FastAPI＋PostgreSQL 的预编译包，支持真实 DeepSeek 对话与受限文本层 PDF/Word 导入。仅用于少量用户、非保密的私人体验，不是生产投审稿服务。原静态展示站保持运行，原域名和浏览器 localStorage 不修改，也不会自动迁移为数据库资料。

## 安装

前提：Linux amd64、已安装 Docker Engine＋Compose v2、Python3.11+，建议至少4GB可用磁盘。此包无构建步骤；不要在2.5GB VPS上安装 Node/npm、编译镜像或启动本地模型。先检查 `python3.11 --version`。AlmaLinux8的[官方软件包中提供Python3.11](https://errata.almalinux.org/8/ALSA-2026-4473.html)；如缺少可由管理员执行 `sudo dnf install python3.11`，不要替换系统Python或修改dnf依赖。先校验外层 SHA256，再解压；仅从项目官方发行页下载。

```bash
sha256sum --check pivot-app-linux-amd64-SHA256SUMS
tar -xzf pivot-app-linux-amd64.tar.gz
cd pivot-app-linux-amd64
python3.11 manage.py init --state /opt/pivot-app-data
python3.11 manage.py up --state /opt/pivot-app-data
```

初始化时填写自己的登录邮箱、16字符以上密码，并无回显输入**新的** DeepSeek API Key。邮箱仅为登录标识，不发信、不做邮箱所有权认证。空密钥为明确Mock；不会用已公开的密钥或在真实调用失败后偷偷降级Mock。秘密保存在包目录以外的 `/opt/pivot-app-data/credentials.json`（目录700、文件600），由管理员保护；应用只从容器环境读取。文件未加密，备份数据库也含私人资料，应限制服务器与Docker管理员访问，不上传GitHub/聊天。日志和镜像包不包含这些秘密。不需要在VPS设置Codex。

默认项目名 `pivot-app`，端口127.0.0.1:3210；PostgreSQL/API不发布端口。不管理 `pivot-demo`、`publishing-os-static-demo`、开发栈或其他项目，不修改防火墙、DNS、系统服务或旧反向代理。端口冲突会失败，不停止占用服务。运行总内存硬上限1472MiB（DB320＋API768＋Web384），预留其余给系统、Docker、旧站和代理；不是整台VPS总内存或并发容量保证。只做少量用户的私人体验：解析和模型对话共享一个非排队名额，忙时429/Retry-After提示主动重试；API单worker，Next代理也在缓冲上传前限重任务。轻读取和人工核对不占此名额。单个解析器上限不等于应用平均内存，压力测试见发行验收报告。API入口仅为专用卷恢复属主临时使用chown/DAC能力，随后降为UID10001、无有效能力运行；根文件系统只读。

## 先通过 SSH 隧道体验

在自己的电脑执行，替换SSH连接信息：

```bash
ssh -N -L 3210:127.0.0.1:3210 用户名@VPS实际IP
```

打开 `http://localhost:3210/library`，使用刚设置的邮箱/密码登录；没有可用的公开演示密码。创建资料，导入包内两份完全合成测试稿，独立核对页补齐作者信息、确认后保存新版本，再询问方法/作者机构并点击引用。只使用合成或公开授权资料。PDF须有文字层（≤5MiB、≤60页），Word须为`.docx`；扫描件/旧.doc、复杂主动内容与不完整解码明确拒绝，无OCR或图表/公式完整理解。

资料区UI不会将候选当作核对完成；AI没有负责人确认工具。模型问答引用仍需人工判断科学含义。真实邮件发送固定禁用；录用/拒稿等关键决定仍需有权限负责人确认。本包只开放一个私人编辑登录；合成作者/审稿人/主编身份保留随机不可用密码，不能靠默认演示密码登录或做决定。

## 独立 HTTPS 子域名

如要公网体验，先停服务，在**已有私密状态**的 `credentials.json` 中只将 `access` 从 `tunnel` 改为 `https`，保持其余字段与600权限，然后 `python3.11 manage.py up --state /opt/pivot-app-data`。不要打印或发出文件内容。Cookie随后有Secure标志，必须通过HTTPS登录，HTTP隧道不再保持会话。使用新子域名（如你拥有的 `app.pivot.anotherdayu.com`），避免与旧展示站共享origin/localStorage。DNS和证书由管理员配置；下面仅为已有Nginx配置示例，不自动安装/覆盖原站：

```nginx
server {
    listen 443 ssl;
    server_name app.pivot.anotherdayu.com;
    # ssl_certificate /管理员已配置的证书/fullchain.pem;
    # ssl_certificate_key /管理员已配置的证书/privkey.pem;
    client_max_body_size 8m;
    location / {
        proxy_pass http://127.0.0.1:3210;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 90s;
    }
}
```

证书行必须填写实际证书后才能启用，并由维护者执行 `nginx -t`。不公开数据库或API端口。受控公网体验尚需服务器管理员检查TLS、账号、备份、访问范围；不能收集保密稿件。保持旧展示域名的代理配置不变。

## 状态、备份、更新

```bash
python3.11 manage.py status --state /opt/pivot-app-data
python3.11 manage.py backup --state /opt/pivot-app-data
python3.11 manage.py stop --state /opt/pivot-app-data
```

备份短暂停写，保存数据库dump＋全部原件，并对文件计算SHA256；结束后仅启动原容器，失败也保留数据。备份不包含模型密钥和登录明文；私密状态目录另行安全保管。不要将备份放在Web公开目录。`stop`不删除任何卷。备份同时应有服务器外的安全副本。

收到新版本后解压至**新包目录**，原私密状态路径、项目名、端口不变，在新目录执行：

```bash
python3.11 manage.py update --state /opt/pivot-app-data
```

更新先自动备份，再加载新镜像/增量迁移；普通up拒绝跳过版本备份。不要重新init，不执行down -v/volume prune/数据库重建。新包不会从旧静态Demo浏览器提取数据。更新失败保留旧包、备份和现场，不能直接降级有冻结历史的数据库。

## 隔离恢复

用**备份对应的原版本包**，初始化另一个状态、项目和端口；重新输入原编辑邮箱及原密码（恢复后数据库密码哈希仍为原值），并配置新密钥。恢复绝不覆盖正在运行的应用或原卷：

```bash
python3.11 manage.py init --state /opt/pivot-restore-data --project pivot-restore --port 3212
python3.11 manage.py restore --state /opt/pivot-restore-data --backup /opt/pivot-app-data/backups/实际备份目录
```

恢复完成后先用3212隧道检查版本、全文、作者、原件和引用，再由维护者决定是否切换代理。恢复目标存在容器或数据卷会拒绝；不要删除旧卷绕过此保护。SHA256用于发现意外变化，不证明未知来源备份可信。

## 依据与边界

[Docker资源限制](https://docs.docker.com/engine/containers/resource_constraints/)、[Compose网络](https://docs.docker.com/compose/how-tos/networking/)、[Next.js standalone](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)。本包不自建模型、不真实发送邮件、不自动配置生产环境。实际平台/内存与功能验收以同版本GitHub发行报告为准；开发机/CI容器通过不等于已经在你的AlmaLinux VPS安装。
