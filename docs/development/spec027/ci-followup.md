# PR #8 最后一轮CI复核

状态：修复源码`6f76d7d117622e4756b021ae3834188ed76d4925`的五轮CI全部完成并通过，证据快照2026-11-05T22:44:32.866203+00:00。应用代码仍为`3307df676cc64a84c0ab6a591f66c2e9d2901582`；后续只有CI工具、专项测试、工作流及文档。本轮不合并、不部署VPS、不发布Release，不更新本机主服务或数据；邮件禁用和负责人确认不变。

## 修复后的实际结果

完整[push 42119052986](https://github.com/DayuGuo/Pivot/actions/runs/42119052986)与[PR 42119062980](https://github.com/DayuGuo/Pivot/actions/runs/42119062980)均顶层及全部步骤success：各1559后端（10条提醒，579.79/667.98秒）＋399浏览器（三引擎各133，13.8/16.1分钟），0失败/跳过/flaky/浏览器重试。研究/模块边界、Ruff/format、18条离线引文、迁移无漂移、ESLint/TypeScript、准确镜像构建启动通过。安装均首次成功，push28秒/PR80秒；不是用专项测试代替完整门禁。

静态[push42119052972](https://github.com/DayuGuo/Pivot/actions/runs/42119052972)与[PR42119062915](https://github.com/DayuGuo/Pivot/actions/runs/42119062915)各17/17步骤success，各完成静态成品33＋amd64静态包33，三引擎各11，无浏览器重试。push依赖首次27秒成功；PR首次300秒超时124，实际切换官方HTTPS镜像、第二次成功，合计357秒。安装重试与浏览器重试分别统计；真实日志验证了超时和回退路径，不声称没有安装重试。

原生完整包[42119052983](https://github.com/DayuGuo/Pivot/actions/runs/42119052983)全部20步骤成功，官方HTTPS预检后Chromium依赖14秒完成。归档302150234字节，SHA256为`959164d7a77fcff11e6ccaf7cf6ffaeb8db55591c5d485a37883c5f5f692dcf0`。外SHA、七内部SHA、来源、linux/amd64及实际运行镜像ID一致。PDF/DOCX导入、人核、Mock带精确引文问答、浏览器定位/刷新、重启/恢复均通过。4并发返回200/429/429/429，同UUID恢复/重放且资料不变。

实际已发布preview.4升级保留原48表62行4CAS，累计新增7表为空；新增本次测试核对/人判后55表72行5CAS在新项目恢复全等，旧cookie和引用可读。邮件/正式决定记录均0，各阶段无OOM/restart；其他服务ID不变，测试项目停止且卷保留。总容器硬限1472MiB不代表用户VPS整机容量认证。最新包仅为CI artifact，[操作指南](operating-guide.md)已指向该包，旧3307包的SHA与报告保留。

## 原始失败与取消记录

请求检查的4bf09e7静态push42115429771/PR42115440795均17/17步骤success、各33＋33项；依赖首次26/50秒成功。完整push42115429493成功（1530后端397.74秒＋399浏览器11.4分钟）；PR42115441284被后续提交按既有concurrency取消，不计通过或测试失败。

原生包[42115429481](https://github.com/DayuGuo/Pivot/actions/runs/42115429481)确实失败：系统依赖两次300秒返回124，共602秒；包未构建，后续验收跳过。日志显示Azure Ubuntu镜像传输极慢，没有已证明的HTTP/DNS/TLS错误或APT锁等待。失败及两次安装诊断保留在`artifacts/spec027/amd64-followup-ci/`，不由后续通过覆盖。日志管道闭合、诊断上传和job cleanup完成，但没有远端进程快照，不认证零残留。

6f本机完整门禁会话中断143，没有wrapper完成回执；1559后端487.96秒/10提醒及390浏览器（Chromium133、Firefox133、WebKit124）已通过，剩余9项未取得完成结果，不能记本机完整exit0。日志和JUnit保留，最终完整结论来自上述两轮真实远端`verify.sh`，未借用旧3307本机成功。专项37项另通过，属于完整门禁的重叠覆盖，不累加。

## 修复与复核边界

- 安装器仅允许唯一chromium/firefox/webkit，默认仍三引擎；原生包浏览器只有Chromium，故只装对应依赖。完整和静态继续三引擎。
- 镜像回退工具先核对hosted Ubuntu24.04/amd64/root及固定临时目录，只改两个固定APT文件。拒绝异常源、符号链接或意外配置，备份0700/0600不上传；保留`.sources`、签名、证书、TLS和有效期校验。
- 原生包显式官方镜像预检，其他安装首次失败才回退。root timeout每次300秒，TERM后15秒KILL宽限，最多两次；APT网络timeout30秒/retry1。sudo仅额外保留五个非敏感CI上下文。
- 37项离线合同、bash语法及独立代码复核通过，未发现新的阻断问题；未在本机执行sudo/APT或改写`/etc`。宿主限制针对镜像工具，安装器本身仍允许显式本机依赖安装。普通异常回滚已测，磁盘/回滚自身故障不在认证范围。

取舍依据GitHub官方[镜像列表](https://github.com/actions/runner-images/blob/main/images/ubuntu/scripts/build/configure-apt-sources.sh)、[APT网络配置](https://github.com/actions/runner-images/blob/main/images/ubuntu/scripts/build/configure-apt.sh)和Ubuntu[APT文档](https://manpages.ubuntu.com/manpages/jammy/man5/apt.conf.5.html)，2026-11-05读取。网络timeout不等于整文件传输时限，外层总期限保留。

## 证据与保留事项

机器可读台账为[ci-followup.json](ci-followup.json)和[results.json](results.json)；安全日志/状态在`artifacts/spec027/ci-followup/`，最新包审计在`artifacts/spec027/amd64-repaired-ci/`。本机只读健康200、DeepSeek配置保留、EMAIL_SEND_ENABLED=false、Mailpit0；本轮DeepSeek请求0，未改主库、CAS或配置。没有合并、Release或VPS操作。

三项独立委派中两项由子Agent完成，完整CI日志核对因子Agent配额中断由Lead完成，未知Token/成本不编造。实际编辑评价、完整回复材料、真实设备及专业工程复核仍见[交接清单](external-handoff.md)，CI通过不替代这些工作。
