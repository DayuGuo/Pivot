# 第一批编辑任务包与真实模型验收

本轮沿用PR #14的独立账号能力，先让两位编辑各自完成公开材料导入、作者核对和有依据的问答。账号和安装仍需负责人安排；当前真实编辑参与数为0，完整逐点回复信为0。

## 首次试用包

在仓库根目录执行：

```bash
.venv/bin/python -m evals.single_journal_pilot.task_pack --output artifacts/editor-first-session-002
```

目录必须尚不存在。包包含两份原件、4个问题、来源许可、空白人评/计时表和摘要；不包含工程参考答案。已实际生成的001包可查看本机`artifacts/editor-first-session-001/TASKS.md`。给每位编辑独立副本，保留原始包。完整协议见[任务包说明](../../../evals/single_journal_pilot/task-pack.md)。本轮不把第一次熟悉材料的操作时间称为提效结果。

## 真实 DeepSeek

仅在本机、已有项目依赖和本地Docker可用时执行：

```bash
cd /home/dayu/Project/Publishing-os
.venv/bin/python scripts/start-trial-live.py --live
```

优先读取该终端的新DEEPSEEK_API_KEY，否则在安全TTY无回显询问。不把密钥发送到聊天。入口固定Linux本机`unix:///var/run/docker.sock`，忽略DOCKER_HOST/DOCKER_CONTEXT远端配置；不是VPS部署脚本，也不支持远程Docker。它不重启原主服务或Mock验证栈，使用新项目、独立端口/卷；邮件配置文件不继承，发送固定禁用。只启动API、数据库和Mailpit，不运行浏览器界面。

先验证四个合成资料场景（全文/作者、真实DOI工具、禁止关键动作、换版引文），再生成两篇许可真实论文的PDF/DOCX待核对候选并检查原文/作者关联。真实论文候选不会自动批准。语义支持、人类核对、正式版本保存后问答仍需实际编辑；逐字引文正确不是科学结论正确。缺少原件时按[材料说明](../../../evals/single_journal_pilot/README.md)获取，不将快照充当原件。

每次运行生成`artifacts/editorial-trial-live/<时间-随机ID>/result.json`与分步骤报告，保留失败。报告固定阶段、HTTP状态、失败类别和供应商返回的Token/耗时；费用未知保持null，不估造账单。没有密钥时不启动服务或调用模型，终端退出2；只有实际DeepSeek返回并通过全部门禁才能记真实验收成功。结果不代表真实论文完整审阅或专家人评。

验收结束可停止该独立服务（不删除数据卷）：

```bash
env -u DOCKER_CONTEXT -u DOCKER_HOST docker --host unix:///var/run/docker.sock compose -f compose.yaml -p pivot-trial-live stop
```

也可保留本机独立服务供后续诊断。不要运行down -v、重建现有安装state或替换原数据。

## 后续放行

补齐至少两套明确许可的完整逐点回复；安排两名真实编辑独立评价和分歧复核；对新的私人amd64包做保留数据升级/恢复及2.5GB并发实测，再由专业工程师复核。上述项目未完成，不宣称生产就绪。邮件继续禁用、关键决定人工确认，不合并或部署VPS。

## 官方接口依据

2026-11-17查阅[DeepSeek工具调用](https://api-docs.deepseek.com/guides/tool_calls/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)和[首个调用](https://api-docs.deepseek.com/en/)。保留现有deepseek-flash与客户端allowlist，工具参数由后端校验；未因新增服务端搜索功能而扩大模型权限。文档可用性不证明当前密钥或供应商成功，必须以本次实际结果为准。
