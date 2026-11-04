# 已安装私人体验版的保留数据更新

适用于用户已安装的v0.2.0-preview.1，目标[preview.2补丁包](https://github.com/DayuGuo/Pivot/releases/tag/v0.2.0-preview.2)。本次修复确认回执与查询，拆分资料服务；没有新表、字段或迁移，旧版本、原件、核对和v1回执保留。开发者没有连接或更新用户VPS。

**使用原安装用户和原来的`--state`路径，不重新init，不删除容器卷，不在旧包目录覆盖解压。** 原状态目录可能是`/opt/pivot-app-data`，也可能是你选择的`~/.local/share/pivot-app`；以实际安装时使用的路径为准，不打印/上传credentials.json。

在VPS的新目录下载并校验（Docker Compose v2/Python3.11已安装）：

```bash
(
set -euo pipefail
mkdir pivot-v0.2.0-preview.2
cd pivot-v0.2.0-preview.2
pivot_release=https://github.com/DayuGuo/Pivot/releases/download/v0.2.0-preview.2
curl -fLO "$pivot_release/pivot-app-linux-amd64.tar.gz"
curl -fLO "$pivot_release/pivot-app-linux-amd64-SHA256SUMS"
sha256sum --check pivot-app-linux-amd64-SHA256SUMS
tar -xzf pivot-app-linux-amd64.tar.gz
cd pivot-app-linux-amd64
# 如果你的原状态路径不同，只改下一行；不要创建一套新状态。
pivot_state=/opt/pivot-app-data
python3.11 manage.py update --state "$pivot_state"
python3.11 manage.py status --state "$pivot_state"
)
```

更新管理器先暂停API/Web写入，备份数据库和完整原件，再沿用原项目/卷加载镜像。密钥和私人密码从原受保护状态恢复，不需要重新发送或写进命令。保留同一端口及原HTTPS/隧道方式；静态Demo和其浏览器资料不被覆盖。邮件固定false，关键操作继续由负责人确认。

验证顺序：登录、打开一份旧资料、检查题名/作者/原件/核对标识，点击旧引用，再上传一份合成或公开授权文件走独立核对。不要用保密稿件试错。健康检查只证明服务/配置就绪，真实模型仍以实际只读问答为准。

本机用上一发行后端生成的三份合成资料/旧确认回执做过真实备份升级实验，完整快照、原件SHA和会话一致，旧回执恢复且不同导入被拒绝；另有原生x86新包安装/恢复验收。这不等于已在你的AlmaLinux VPS验证。

若更新失败，保留旧包、原状态、卷和备份；不要盲目降级数据库或将dump覆盖到现库。按[完整安装器的隔离恢复说明](../../infrastructure/vps/README.md)在新项目/卷中验证后，由负责人决定是否切换。专业运维/权限/隐私复核仍是保密试点前的关口。
