# 邮箱绑定

编辑/主编登录后打开侧栏“邮件”。支持自建 SMTP、Gmail、Outlook 配置保存、验证、断开和重新绑定；账号与状态持久化到 PostgreSQL，变更有审计。作者/审稿人不能管理邮箱。保存只表示配置已登记，不表示连接成功。

## 本地演示，无需凭据

选择“本地 Mailpit”预设，填写一个 `.test` 合成邮箱和名称，保存后点击“验证连接”。应用在 Compose 网络执行 EHLO 并关闭连接，状态应为“已验证”；不发送邮件。刷新保留配置，断开后可重新绑定；重新绑定必须重新验证。

## 自建 SMTP

填写主机、端口、TLS 和认证方式。远程连接必须 STARTTLS（通常587）或隐式TLS（通常465），服务器证书须可信；密码认证可指定用户名。管理员将精确 `host:port` 加入 `MAIL_SMTP_ALLOWLIST`，例如 `mailpit:1025,smtp.example.test:587`。只有本地 Mailpit1025 无认证允许明文。容器中的 localhost 指容器自身。

## 凭据配置

浏览器只填引用名，例如 `EDITORIAL`、`GMAIL`、`OUTLOOK`，不填写密码或 token。引用限1–32位大写字母、数字、下划线且以字母开头。展开页面“服务器配置”取得真实期刊 UUID。

1. 复制 `infrastructure/mail.env.example` 到 `.env.mail`（已忽略），设置权限600；也可由安全环境注入。不要提交填充后的文件或把实际值放在命令参数中。
2. 设置 `MAIL_CREDENTIAL_<REF>_JOURNAL_ID` 为页面所示期刊 UUID；设置同前缀的 `PASSWORD`（SMTP）或 `ACCESS_TOKEN`（云服务）。期刊不匹配时按缺凭据处理。
3. 运行 `docker compose up -d --force-recreate --wait api` 加载新环境；仅 restart 不重新加载 env_file。然后在页面验证连接。

## Gmail / Outlook

管理员需先在对应平台完成 OAuth 应用和用户授权，再安全注入访问令牌。应用当前没有授权跳转、token 自动刷新或撤销界面。令牌过期后更新服务器配置并重新验证。

- Gmail：只调用 users.getProfile，检查 emailAddress 与绑定地址一致。可用 `https://www.googleapis.com/auth/gmail.metadata`；这是受限 scope，虽无发送权限但本身允许读取更多元数据，本适配器只调用 profile。授权和平台验证要求见[官方范围说明](https://developers.google.com/workspace/gmail/api/auth/scopes)。
- Outlook：Microsoft Graph `/me?$select=mail,userPrincipalName`，需要登录用户的 delegated `User.Read`。只验证账户身份，不能证明邮箱可读或地址有发信权限。见[官方 Get user](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0)。

缺凭据、权限失败、地址不匹配或网络失败会显示真实安全状态，绝不模拟“已连接”。实际云账号尚未测试，因为未提供服务器端授权凭据。接口的离线协议测试和本地 Mailpit 已执行，详见 PROGRESS.md 与 docs/research/mail-providers.md。

## 发信边界

`EMAIL_SEND_ENABLED=false`，没有发信传输器、收件箱或审稿邀请 UI。绑定和验证不授予发信权限；未来每一封真实邮件仍需授权人员对收件人、正文、附件不可变快照逐封审批，修改即撤销审批。当前测试没有向真实个人发送邮件。
