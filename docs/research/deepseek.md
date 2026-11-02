# DeepSeek 协作路径与验证报告

验证日期：2026-11-02；本地 CLI：`codex-cli 0.165.0`。主会话模型与全局 Codex 配置均未修改。只检查 `DEEPSEEK_API_KEY` 是否存在，结果为不存在；未读取全局认证文件、未使用旧密钥、未进行真实 DeepSeek API 调用。

## 官方资料与结论

- [DeepSeek 2026-10-17 更新日志](https://api-docs.deepseek.com/updates/)确认 DeepSeek-V4.1-Flash-1017 通过 `deepseek-flash` 调用。这个 ID 是滚动别名，本项目保留所要求的版本名称与研究日期，不声称能从无密钥实验确认实际服务端模型版本。
- [DeepSeek 官方 Codex 集成](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/)使用 Responses API、自定义模型目录和模型提供商配置。官方脚本会修改全局配置；本任务没有执行该脚本，也没有将密钥写入配置。独立 CLI 实验仅在临时目录设置隔离的子进程 `CODEX_HOME`。
- [OpenAI Subagents 文档](https://learn.chatgpt.com/docs/agent-configuration/subagents)规定子 Agent 继承父提供商；自定义 Agent 文件中的 `model_provider` 不能覆盖父配置。当前会话的原生模型枚举也没有 DeepSeek。因此不将原生跨提供商子 Agent 当作可靠的工程依赖。
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)将模型返回的工具请求与应用执行分离；[Responses API 指南](https://api-docs.deepseek.com/guides/responses_api/)描述 Codex 所需协议。兼容的请求格式不等于兼容全部 Codex 工具、编排或安全边界，必须逐条实验。

## 实际实验

| 实验 | 结果 | 证据与边界 |
|---|---|---|
| 独立 Codex → loopback 假 Responses 服务 → 真实 shell 工具 → 工具结果回传 | 通过 | `evals/model_probe_result.json`：2 次模型请求，模型 ID `deepseek-flash`；执行无副作用的 `printf probe-tool-ok`；后续请求包含 `function_call_output`；CLI 退出 0。只验证本地传输与工具往返，不验证 DeepSeek 服务。 |
| 独立 Codex 原生 `spawn_agent(model=deepseek-flash)` 假响应实验 | 未通过，不能证明原生跨提供商兼容 | `evals/model_native_probe_result.json`：CLI 将所构造的 function_call 返回 `unsupported call: spawn_agent`；也试过 namespace 编码，均未得到可靠原生调度。退出 0 只代表外层 CLI 正常结束，不能当作委派成功。失败可能涉及本地假响应编码/模型目录；不能归因于真实 DeepSeek。抓取的工具 schema 不提供 `model_provider` 参数。 |
| 独立安全 API 委派器默认 Mock | 通过 | `evals/model_delegate_mock.json` 和 `evals/model_delegation_metrics.json`。结果标记 MOCK，落在唯一临时任务目录，须 Lead 审核；不执行模型代码。 |
| DeepSeek HTTP 工具响应契约、未知工具/参数拒绝、异常与凭据清理 | 通过离线契约测试 | `evals/model_gateway_test.py` 使用 `httpx.MockTransport`，没有外网请求；不能作为实际供应商验证。 |
| 真实 DeepSeek / Ollama / vLLM | 未验证 | 无新 DeepSeek 密钥；未部署本地模型服务。保留显式 opt-in 的可测试接口。 |

## 选择的可运行替代方案

`packages/model_gateway` 为最小安全 API 委派器与运行时网关。`MockModelProvider().propose(message)` 返回 `Proposal(tool, arguments, provider)`；实时供应商通过同一接口返回不可信提案。唯一出版工具为 `create_test_manuscript_and_assign_screening`，参数必须为空；角色、期刊范围、用户、状态迁移、幂等与审计仍全部由后端决定。未知工具、额外参数与畸形结果拒绝执行。

工程任务委派使用 `python -m packages.model_gateway.delegate`，可选类型 `research/api/react/tests/documentation`。Mock 为默认；`--live` 显式启用且要求可信环境中导出的新 `DEEPSEEK_API_KEY`。真实 API 固定使用 HTTPS 官方域名，不跟随重定向，不把密钥、任务、供应商错误正文或生成代码写入日志。委派输出只保存到独立 UUID 任务目录的固定 `result.json`，不执行代码、不覆盖源码；Lead 审核后才集成。Ollama/vLLM 适配器预留同一 HTTP 接口，显式启用且仅允许 loopback 地址。

运行时接入还要求 `MODEL_PROVIDER=deepseek` 和 `MODEL_LIVE_ENABLED=true`，避免环境中偶然存在密钥导致自动外发。当前产品仍为 Mock。公开/合成上下文以外的数据不得发送给模型。

## 可复现命令

在仓库根目录执行（本机沙箱中 loopback 监听需要授权，普通开发主机无需额外选项）：

```bash
.venv/bin/pytest -q evals/model_gateway_test.py
.venv/bin/python evals/model_codex_probe.py
.venv/bin/python evals/model_codex_probe.py --native-provider-test
.venv/bin/python -m packages.model_gateway.delegate --kind research --task 'Inspect a synthetic API contract boundary'
.venv/bin/python -m packages.model_gateway.report /tmp/publishing-delegations
```

取得新密钥并通过安全环境导出后，可对合成任务追加 `--live` 执行同一委派器；不要将密钥写入命令、文档、Git、配置或日志。真实失败不会静默伪装成 Mock 成功。

## 指标口径

每个任务 `telemetry.json` 记录 provider/model、成功状态、输入/输出 Token、耗时、返工次数、成本与错误码；`report` 汇总尝试数、成功率、Token、耗时、返工与未知成本覆盖率。Mock 为 0 Token / $0；真实 Token 读取供应商 usage，缺失为 null。实际账单成本未取得则为 null，不能用 0 代替。总成功率只描述已执行样本，并单列 Mock 次数，不代表模型质量。API 错误及无效工具的失败也计入；无真实供应商调用时不能报告真实供应商成功率。

本轮保留 1 次 Mock 委派样本，成功 1/1、Token 0、成本 $0；真实 DeepSeek 尝试数 0。离线契约测试 7 项通过。原生跨供应商能力保持未验证，独立 API 路径已实现且可在提供新密钥后执行真实验证。
