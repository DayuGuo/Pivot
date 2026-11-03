# Pivot 首次公开发行

2026-11-03。用户将产品暂定名Pivot，并明确选择公开GitHub仓库。源码已上传[DayuGuo/Pivot](https://github.com/DayuGuo/Pivot)，发行入口为[v0.1.0-demo](https://github.com/DayuGuo/Pivot/releases/tag/v0.1.0-demo)。已公开发布为Demo预发行版；用户VPS仍未连接，不是生产部署。

## 发行内容与边界

对外UI、页签、README和发行归档改名Pivot；保留数据库/Python包/Compose/旧缓存身份。独立Demo的主/稿件对话、日历、作者与正文编辑、来源定位均为合成资料与明确模拟回答，浏览器本地存储。无模型密钥、业务API、真实外发或重大决定。实际运行用户权限和业务状态仍由现有后端控制，未为公开Demo开放真实稿件。

VPS包包括离线amd64 Nginx镜像、架构无关静态网页、中文说明、安装器与SHA256。安装器默认127.0.0.1:8080，可显式PIVOT_BIND=0.0.0.0供IP演示；检查平台、内部校验和、已有容器和health。不会安装系统组件、改防火墙或覆盖其他容器。

## 真正执行的验收

- 本机完整verify退出0：835 Pytest（350.82秒）+48 Playwright（1.7m），静态/迁移/漂移/前后端构建通过，1项既有第三方warning，日志`artifacts/pivot-full-verify-final.log`。
- Pivot原生静态11/11、实际页面标题/品牌断言与合成截图通过。
- [真实x86部署验收](https://github.com/DayuGuo/Pivot/actions/runs/41652918740)在Ubuntu Runner上构建，解压完整VPS包，逐项SHA256检查，运行install.sh，Nginx health通过，再跑相同11条浏览器场景全部通过（另在独立静态入口11/11）。没有把ARM机器构建/加载冒称x86可执行。
- Release附件使用上述CI实际测试过的字节。之后源码变更仅涉及测试导入排序与fresh静态检查；`git diff 55d85a3 e77380d -- apps/web/components/demo infrastructure/demo scripts/install-demo.sh scripts/build-demo.sh scripts/package-vps-demo.sh`为空，运行包源码相同。
- 首次本地完整回归暴露旧会话切换GET未完成时刷新恢复旧URL。已将选择意图在请求前保存、失败回滚；新增两条可控挂起/500回归，原有链不删，定向10/10通过。
- 首次GitHub全栈CI因checkout浅克隆缺历史基线失败，保留检查，改fetch-depth:0；第二次发现一处被本地Ruff缓存掩盖的测试导入排序，已修复并使verify的静态检查禁用缓存。fresh Ruff/format全部通过，相关决定模块4项实际数据库回归通过。最终[全栈CI](https://github.com/DayuGuo/Pivot/actions/runs/41654140553)已success：835 Pytest（356.30秒）+48 Playwright（1.6m）；最新[e77380d静态CI](https://github.com/DayuGuo/Pivot/actions/runs/41654140412)也已成功。不将此前失败报告混称成功。

## 附件校验和

| 附件 | 字节数 | SHA256 |
| --- | ---: | --- |
| `pivot-vps-linux-amd64.tar.gz` | 35611686 | `7a3e8a52c6d1f96f0f9f45874843cde0f880a5bf7cda9f3c20fe274b1bccfb6a` |
| `pivot-demo-image-linux-amd64.tar.gz` | 30744374 | `3a82686be60303b9e3cb0d6754564e4a3a569210a264de6d1207840d7e734419` |
| `pivot-demo-static.tar.gz` | 4858176 | `7f553a27dbf4d1e0403bce1f1edae30df36adfd36a0a8d4049ee16eb6f9fc4f1` |
| `pivot-demo-SHA256SUMS` | 288 | `e2fc1dbe73194502b49d68ee0ed00c4cc9f9cb24852f39cbc345f6e245ddc8dd` |

已逐一对比GitHub服务端asset.digest/size/state与CI附件，4项一致。校验记录`artifacts/pivot-release-assets-final.json`；已在发布后用无登录HTTP客户端实际下载完整VPS包：HTTP 200，35611686字节，SHA256与CI测试包一致。报告`artifacts/pivot-public-download-acceptance.json`。

## GitHub授权与发布方式

GitHub连接器确认账号DayuGuo与仓库，应用现有权限写入CI；CLI原OAuth缺workflow scope时未要求提供新密钥、未修改全局认证。源码推送只包含与远端一致的工作流，发行二进制由同账号gh CLI上传。全局模型设置未改，未读取全局auth文件或输出凭据。公开前扫描351当前文本文件及942历史文本对象，未命中指定sk/GitHub/AWS/private-key模式；这是有限模式扫描，不是完整安全认证。

未上传.env、运行数据库、真实稿件或日志；截图仅合成数据。用户自行部署时仍需确认实际VPS架构、Docker可用、端口/HTTPS与线路。邮箱与重大业务操作权限不因项目公开而解除。
