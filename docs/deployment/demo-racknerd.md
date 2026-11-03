# 本机展示与 RackNerd 安装

当前产品定名Pivot，交付独立静态Demo，不是生产投审稿平台。用户已授权公开发布到[DayuGuo/Pivot](https://github.com/DayuGuo/Pivot)，部署包放GitHub Releases；实际VPS仍未连接、安装或公网验收。机房`Test IP`不是安装目标。

## 直接使用Release安装包

从[Releases](https://github.com/DayuGuo/Pivot/releases)下载`pivot-vps-linux-amd64.tar.gz`及`pivot-demo-SHA256SUMS`。包内附带镜像、静态网页、安装脚本、中文README与内部SHA256；独立校验文件也覆盖外层归档。

```bash
tar -xzf pivot-vps-linux-amd64.tar.gz
cd pivot-demo-linux-amd64
bash install.sh
```

在已安装Docker的Linux amd64执行，脚本核对Docker平台、校验包内文件、加载离线镜像并等待health。默认127.0.0.1:8080供HTTPS反向代理。若明确要用实际公网IP演示，首次运行改为 `PIVOT_BIND=0.0.0.0 PIVOT_PORT=8080 bash install.sh`，并在已有防火墙规则中放行所选端口；脚本不修改OS或防火墙。已有同名`pivot-demo`容器时拒绝覆盖，保留用户现有服务。

以下为开发机重新构建与单独静态归档的补充说明。原开发脚本继续管理兼容名`publishing-os-static-demo`，Release安装器使用独立名`pivot-demo`，均不触碰原业务Compose身份。

## 本机，一条命令

前提：Docker Engine 可用，能拉取公开 Node/Nginx 镜像。无需Python、数据库、账号、API Key或 `.env`，也无需宿主机先安装npm。

```bash
./scripts/demo.sh
```

打开 [http://localhost:3110](http://localhost:3110)。无需登录。另一个入口 `/demo` 随完整开发栈提供，独立静态包的入口是 `/`。

```bash
./scripts/demo.sh stop
DEMO_PORT=3111 ./scripts/demo.sh
```

脚本只管理 `publishing-os-static-demo` 且带专用label的容器；未知同名容器不删除。重新构建不会清除浏览器localStorage。清空资料用界面左下角“重置演示”；浏览器无痕窗口也可以提供干净的演示。两个不同域名/端口的演示资料相互独立。

## 五分钟演示

1. 默认打开合成稿件，说明左侧是本人待办、中心对话常驻、右侧是本稿当前步骤和材料。
2. 点击“检查方法”，再点回答里的“方法”，展示原文定位。重复点同一来源仍可重新定位。
3. 点击“核对作者信息”，打开“作者”，看到ORCID缺失与未认证状态。用“编辑”实际补充合成资料；也可修改正文段落。历史引用对应文字改变时失效提示，不能把新正文冒充旧依据。
4. 点击“查看参考文献”与“公开文献”，打开出版社或Crossref真实链接。只证明文献存在，不能验证合成结果。
5. 切换“主对话”看全刊工作；点日历日期筛选待办。录入一篇本地演示稿，刷新后正文、资料和会话保留。
6. 输入“发送邮件并直接录用”，观察不会产生邮件、状态推进或确认。点击“交互演示”查看能力披露。

仅使用合成或获准的公开资料。导入限UTF8 TXT/Markdown，单文件1 MB；没有PDF解析、真实模型、ORCID OAuth、账号权限或数据库写入。浏览器资料可能因配额/禁用localStorage而保存失败，界面会提示。没有跨设备同步或浏览器数据备份保证。

## 为什么适合2.5 GB VPS

Next.js在开发机生成HTML/JS/CSS和自托管字体，运行镜像只有Nginx与这些公开文件。已在本地验证内存上限128 MB、CPU上限0.5、只读根文件系统和临时缓存目录。2026-11-03初次空闲测量约15.39 MiB，静态归档约4.7 MB；不是VPS实测、负载容量或网络速度承诺。

RackNerd洛杉矶到国内的实际体验取决于线路；公网部署前再从目标用户网络测量。AlmaLinux8可作为现有容器宿主，本轮没有升级OS或变更防火墙。

## 未来安装到VPS：先在本机打包

```bash
./scripts/build-demo.sh --image
```

生成：

- `artifacts/pivot-demo-static.tar.gz`：可交给已有Nginx/其他静态主机。
- `artifacts/pivot-demo-image-linux-amd64.tar.gz`：显式amd64离线Docker运行镜像，不包含源码、Node、Python、数据库或密钥。本机预览使用本机原生架构的`:local`标签，彼此分开。

未来先在VPS执行 `uname -m` 确认：`x86_64`对应默认`linux/amd64`；如果是`aarch64`则在构建机执行 `DEMO_PLATFORM=linux/arm64 ./scripts/build-demo.sh --image`，使用`linux-arm64`包和标签。Node构建阶段使用构建机原生平台，只有Nginx运行层采用目标平台；不能把`docker load`成功当作架构可执行的证明。

本机Docker为ARM64且不支持amd64执行仿真；本轮amd64包的构建、加载、manifest架构已验证，但试运行因`exec format error`退出，3112的11条浏览器测试均为连接拒绝，不算通过。本机原生版本及静态网页已通过11条验收。CI已定义在`ubuntu-latest` x86 runner加载离线包、检查health再运行相同11条，远端尚未执行；VPS亦未连接。

使用已验证SSH目标传输镜像。在VPS有可用Docker的前提下加载并先监听本机环回，**不用在2.5 GB内存中编译**：

```bash
docker load -i pivot-demo-image-linux-amd64.tar.gz
docker run -d --name publishing-os-static-demo \
  --label org.publishing-os.surface=static-demo --restart unless-stopped \
  --memory=128m --cpus=0.5 --read-only \
  --tmpfs /var/cache/nginx --tmpfs /var/run --tmpfs /tmp \
  -p 127.0.0.1:3110:80 pivot-demo:linux-amd64
curl --fail http://127.0.0.1:3110/health
```

没有Docker时，使用静态归档及其中 `nginx.conf.example`；由服务器管理员按实际目录、端口、SELinux策略和已有站点配置Nginx。原生AlmaLinux安装未在当前机器验证，不提供假定空服务器的覆盖脚本。

## 公网访问与更新

建议用专用域名与HTTPS代理环回3110端口，保持服务器数据库/API端口不开放。已有Nginx可代理；若选择Caddy，最小站点为：

```caddyfile
demo.example.org {
    reverse_proxy 127.0.0.1:3110
}
```

这是配置示例，不是已注册域名。DNS指向实际VPS，80/443需可达且不与现有站点冲突，证书再由代理申请。凭据不要进GitHub或聊天。未来部署时先检查实际服务/端口，再具体执行，不自动更换站点或停止其他容器。

更新前保存旧镜像标签用于回滚，再加载新包并替换专用Demo容器。不要清理未知镜像/容器；没有数据库迁移。浏览器使用相同域名会保留localStorage，需要干净样例时手动重置。以后接入真实业务时必须重新设计认证、服务器持久化、文件/隐私、运维与独立安全复核，不能沿用无登录Demo边界。

## 来源与实际验证

- [Next.js官方静态导出](https://nextjs.org/docs/app/guides/static-exports)：静态构建可在Nginx等Web服务器托管。
- [Docker官方Next.js容器示例](https://docs.docker.com/guides/nextjs/)：区分Node standalone与Nginx export。
- [Caddy官方HTTPS快速入门](https://caddyserver.com/docs/quick-starts/https)：DNS、80/443与自动证书条件。本轮没有调用外部证书服务。
- [Crossref实际公开记录](https://api.crossref.org/works/10.1038/sdata.2016.18)：2026-11-03返回200且题名/DOI匹配；出版社抓取重定向到浏览器认证，未声称抓取全文成功。

自动验收见 `tests/e2e/demo.spec.ts`，静态产物使用 `DEMO_PATH=/`，完整开发栈使用默认 `/demo`。最终执行数字、截图和限制见PROGRESS与docs/development/demo-delivery.md。GitHub Actions定义已提供，只有远端实际执行后才能声称CI通过。
