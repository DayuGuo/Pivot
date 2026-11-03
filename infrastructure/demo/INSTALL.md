# Pivot Demo 安装包

这是产品展示版本：合成稿件、模拟对话、浏览器本地存储，不连接模型/数据库，不发送邮件或作正式决定。不要录入保密稿件和真实私人资料。

适用：Linux amd64（`uname -m`为`x86_64`）、已安装Docker Engine。只运行Nginx，镜像不包含Node/Python；2核、2.5GB VPS可先做轻量展示。没有自动OS安装、开放防火墙或生产部署。

解压后在本目录运行：

```bash
bash install.sh
```

默认仅本机环回8080，供SSH隧道或HTTPS反向代理。若明确希望通过VPS公网IP的8080端口直接演示：

```bash
PIVOT_BIND=0.0.0.0 PIVOT_PORT=8080 bash install.sh
```

再在服务器防火墙/云防火墙放行该端口，访问`http://实际公网IP:8080`。日常分享建议专用域名与HTTPS代理。不要以机房Test IP当服务器IP。

安装器核对平台和SHA256，等待health；已有同名容器时拒绝覆盖。不需要API Key、登录账号或`.env`。它不修改其他容器、全局模型配置或系统防火墙。该版本没有服务器用户权限，不等于真实投审稿系统。

```bash
docker logs pivot-demo
docker stop pivot-demo
docker start pivot-demo
```

资料留在各自浏览器，修改域名/端口会成为独立存储。清空演示用界面的“重置演示”。更新前先核对旧容器label/镜像，再停止删除专用容器并运行新包；不要使用全局prune。

附带`pivot-demo-static.tar.gz`是CPU架构无关的静态网页，可交给现有Nginx；其中`nginx.conf.example`需按实际站点目录、端口和SELinux配置。ARM64宿主应使用原生构建或静态包，不能执行amd64镜像。

[源码与详细安装说明](https://github.com/DayuGuo/Pivot/blob/main/docs/deployment/demo-racknerd.md)。具体已验证版本与限制以GitHub Release说明为准，未在用户VPS上实际安装不声称完成公网部署。
