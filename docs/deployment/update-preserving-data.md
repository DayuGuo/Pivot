# 更新代码并保留资料

2026-11-04。本页提供由服务器负责人执行的命令；本轮没有连接、修改或部署 VPS。源码修复基线为 `87cbc4d`，完整本机回归为1157 Pytest＋66 Playwright；[真实论文评测报告](../development/public-paper-evaluation.md)记录具体范围和限制。

如果VPS仍为静态Demo，现在可在旁边安装[完整应用私人体验预发行](https://github.com/DayuGuo/Pivot/releases/tag/v0.2.0-preview.1)，使用其[独立管理器安装/备份/更新说明](../../infrastructure/vps/README.md)。下面的源码原位更新命令仅适用于旧开发Compose，不用于替换静态站或新私人包。

## 先区分当前安装

此前发布到 `pivot.anotherdayu.com` 的包是静态 Demo：Nginx＋浏览器 localStorage，没有 PostgreSQL、真实 DeepSeek 或 PDF/Word 解析后端。这轮真实功能属于完整 Compose 应用；更新旧静态安装包不会启用它们。本轮没有发布替换静态包的新版 Release，也没有宣称公网已更新。

先在已有源码目录执行 `docker compose ps -a`。如果没有本项目的 `api`、`web`、`db`，请不要执行下一节的完整栈更新。可以先只更新源码，保留旧站服务、域名和浏览器存储：

```bash
# 在 VPS 已有 Pivot Git 仓库目录内执行；不是解压后的静态安装包目录。
git status --short
git fetch origin main
git merge --ff-only origin/main
```

有本地改动时先停止并核对，不使用 reset/clean 覆盖。若 VPS 只有解压安装包，可另建目录 `git clone https://github.com/DayuGuo/Pivot.git Pivot-source`；这不会替换运行容器。静态浏览器资料不能自动变成数据库资料；保持原域名和浏览器、不清空站点存储。完整栈第一次安装应作为独立测试服务，先按 [README](../../README.md) 在环回地址验证；不要直接把已知演示账号的开发栈公开到互联网。完整栈尚未在这台2.5GB VPS实装或压测，不以静态站的资源测量推断其容量。

## 已有完整 Compose 栈：备份后更新

前提：在**原安装目录**使用**原 Compose 项目名和覆盖文件**；已安装 Git、Docker Compose、Python3。自定义 `COMPOSE_PROJECT_NAME` / `COMPOSE_FILE` 必须与原服务一致，不能改名创建另一组空卷。下面适用于仓库默认 Compose；有定制数据库/存储路径时由维护者按实际配置调整。先安排维护窗口，暂停用户写入。

下面整个代码块可粘贴进 Bash。子 Shell 遇错停止，不关闭登录终端。备份失败时 API/Web 可能保持停止；保留原代码并用 `./scripts/start.sh` 恢复，不能跳过失败继续升级。

```bash
(
set -euo pipefail
umask 077
# 当前目录必须是原 Pivot Git 仓库。
test -z "$(git status --porcelain)" || { echo '工作区有改动，停止更新。'; exit 1; }
test -n "$(docker compose ps -a -q api)" || { echo '未找到原 API，停止更新。'; exit 1; }
test -n "$(docker compose ps -a -q db)" || { echo '未找到原数据库，停止更新。'; exit 1; }
git fetch origin main
git merge-base --is-ancestor HEAD origin/main || { echo '本地与远端分叉，停止更新。'; exit 1; }

# 放在仓库外，权限仅当前用户；不备份/打印密钥或容器环境。
pivot_backup="$(dirname "$PWD")/pivot-backups/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$pivot_backup/files"
git rev-parse HEAD > "$pivot_backup/source-commit.txt"
docker compose stop api web
docker compose exec -T db pg_dump -U publishing -d publishing -Fc > "$pivot_backup/database.dump"
test -s "$pivot_backup/database.dump"
docker compose exec -T db pg_restore --list < "$pivot_backup/database.dump" > "$pivot_backup/database-contents.txt"
docker compose cp api:/data/publishing-files/. "$pivot_backup/files/"

git merge --ff-only origin/main
# 保留现有服务的真实模型环境；不要用默认 compose up 替代而意外切回 Mock。
# 原数据库卷和原件卷继续沿用；API 启动时只执行增量 Alembic 迁移和幂等初始化。
./scripts/start.sh
docker compose exec -T api alembic current
docker compose exec -T api alembic check
docker compose exec -T api python -c 'import os; assert os.environ.get("EMAIL_SEND_ENABLED") == "false"; print("EMAIL_SEND_ENABLED=false")'
curl --fail --silent --show-error http://127.0.0.1:3100/api/health
printf '\n备份位置：%s\n' "$pivot_backup"
)
```

`./scripts/start.sh` 的宿主机部分只使用 Python 标准库，不需要在 VPS 安装本地测试环境。它会构建 API/Web；小内存 VPS 的首次完整构建未经本轮验证，可在开发机/CI构建匹配架构镜像后传输，不把构建失败解释为可删除数据库来重试。迁移/结构检查失败应停止对外开放并保留备份。`pg_restore --list`仅检查归档可读性，本页备份流程尚未在用户 VPS 执行，也不等于实际恢复演练。

保持同一目录、项目身份、数据库卷和文件卷；**不要运行 `docker compose down -v`、volume prune、数据库重建、`git clean` 或界面“重置演示”**。备份应另存到受控位置。不要向当前库直接恢复或降级：历史冻结触发器可能禁止有数据的迁移回退。失败时保留现场，由维护者在隔离库和隔离文件目录恢复并验证，再决定切换，不以覆盖现库作为默认回滚。

## 模型与人工关口

本轮本机实际重新调用 `deepseek-flash`，3962ms完成 `inspect_manuscript` 与 `list_tasks` 只读工具回环，返回1条引用、`state_changed=false`；不是仅检查健康配置。证据为本机忽略目录 `artifacts/live-model-smoke.json`。运行服务三个非敏感标志为 `provider=deepseek`、`live_enabled=true`、`EMAIL_SEND_ENABLED=false`。

VPS 首次需要真实模型时，在交互终端运行 `python3 scripts/start-live-model.py`，无回显输入**新密钥**，或者从管理员安全环境注入；不要写进命令参数、仓库、聊天或日志。已有真实服务更新使用上面的保留环境启动器；当前进程没有新密钥且也没有可恢复的既有真实配置时仍为明确 Mock，不声称真实 API 已接通。健康接口只能证明配置；VPS上还需登录，使用合成/授权公开资料完成一次只读提问并检查引用，不能把本机成功当作 VPS 网络与模型成功。

Compose把 `EMAIL_SEND_ENABLED` 固定为 `false`；AI无发送邮件或最终确认工具。导入只生成候选，负责人在独立核对页确认后才保存新版本；正式录用、拒稿等关键决定继续由有权限负责人确认。更新不提供任何绕过这些关口的开关。
