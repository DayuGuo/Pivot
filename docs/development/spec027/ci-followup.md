# PR #8 最后一轮CI复核

状态：修复后实际验收待执行。原请求检查提交4bf09e7；应用代码保持3307df6，变更仅限CI工具、专项测试、工作流和交付文档。本轮不合并、不部署VPS、不发布Release，保留已有数据；邮件禁用与负责人确认不变。

## 已复现的结果

4bf静态[push 42115429771](https://github.com/DayuGuo/Pivot/actions/runs/42115429771)和[PR 42115440795](https://github.com/DayuGuo/Pivot/actions/runs/42115440795)各17/17步骤成功；各自静态成品与amd64离线静态包均33项（三引擎各11），无浏览器重试。新host依赖helper均首次成功，26/50秒。重复场景不累计独立覆盖。

原生完整包[42115429481](https://github.com/DayuGuo/Pivot/actions/runs/42115429481)在系统依赖安装失败：两次300秒各返回124，合计602秒；包未构建，安装、升级恢复和浏览器步骤均跳过。日志显示Azure Ubuntu镜像下载字体和库文件极慢，没有明确HTTP错误、DNS/TLS错误或APT锁等待。不能把它写成应用失败，也不能把未执行的包验收算成功。

失败日志及两次安装诊断保留于`artifacts/spec027/amd64-followup-ci/`，安全摘要见其中failure-audit.json。超时后日志管道闭合、诊断上传及job cleanup完成；缺少远端进程快照，不认证“零残留”。

## 最小修复

- 安装器引擎参数仅允许唯一的chromium/firefox/webkit，默认仍全部三引擎。原生包实际浏览器验收只有Chromium，故只安装该引擎所需系统依赖；完整和静态回归仍覆盖三引擎。
- 新受控工具只在GitHub hosted、Ubuntu24.04、amd64、root和固定临时目录条件下改写两个固定APT文件。保留`.sources`、签名、证书与有效期校验，拒绝异常源、符号链接或意外配置，原件备份到CI临时目录，权限0700/0600，不上传。
- 原生包先显式切到官方HTTPS镜像，以实际验证该路径；其他安装首次失败后才回退。每次300秒、最多两次不变，另配置APT HTTP/HTTPS网络timeout30秒、retry1。sudo仅额外保留五个非敏感CI上下文，不保留模型/业务凭据。

取舍参照GitHub官方[镜像列表实现](https://github.com/actions/runner-images/blob/main/images/ubuntu/scripts/build/configure-apt-sources.sh)、[APT网络配置](https://github.com/actions/runner-images/blob/main/images/ubuntu/scripts/build/configure-apt.sh)和Ubuntu的[APT配置文档](https://manpages.ubuntu.com/manpages/jammy/man5/apt.conf.5.html)，2026-11-05读取。网络timeout不等于完整文件传输时限，安装器外层总期限继续保留。

37项离线专项、Ruff/format、bash语法、全仓语法、研究/模块边界及YAML检查通过；本机直接调用受控工具按预期拒绝。未在本机执行sudo/APT或改写`/etc`。实际GitHub镜像切换和修复后完整门禁必须另外记录，不能由离线测试推断。

## 最终证据与边界

准确source、CI作业、实际测试数、归档SHA/镜像ID和恢复结果记入[ci-followup.json](ci-followup.json)。本机已有应用/数据库/原件不更新；健康只读返回200、EMAIL_SEND_ENABLED=false、Mailpit0，无新DeepSeek调用。实际编辑评价、完整回复材料及专业工程复核仍按[交接清单](external-handoff.md)后续完成。
