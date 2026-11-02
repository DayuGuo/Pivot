# 编辑对话的真实 DeepSeek 传输边界

核查日期：2026-11-02。本记录只覆盖独立传输适配器，工作台工具、权限和事务由后端负责，不证明原生 Codex 跨提供商子 Agent 可用。

## 官方资料与实现取舍

- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)：官方示例使用 `deepseek-flash`、`https://api.deepseek.com`，模型返回调用后，应用执行函数，并将带 `tool_call_id` 的结果回传。本实现采用这一真实请求/工具结果协议；函数不是模型自身执行的。不开启 beta strict，所有参数仍需本地校验。
- [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)：使用 `/chat/completions`、非流式响应与 `thinking.type=disabled`，最大输出限制为2048 tokens。拒绝 length、content_filter 等非完整完成状态；验证单个 assistant choice、调用ID、函数名和JSON对象参数，丢弃无关返回字段。上下文、白名单及参数业务约束由调用方再验证。
- [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)：核查时 `deepseek-flash` 对应 DeepSeek-V4.1-Flash-1017，支持工具调用。公开费率区分缓存及峰谷时间，价格可能变化；不能仅用总Token推断账单。本适配器记录供应商返回的输入/输出Token，API成本保留null，待账单核对。

## 配置与安全

`EDITORIAL_MODEL_PROVIDER` 默认 `mock`；真实路径须同时设置 `EDITORIAL_MODEL_PROVIDER=deepseek`、`EDITORIAL_MODEL_LIVE_ENABLED=true` 及新的 `DEEPSEEK_API_KEY`。不改原投稿入口的 `MODEL_PROVIDER`，不读取或修改Codex全局配置。明确选择DeepSeek但缺条件时失败关闭，不能静默退回Mock并标为真实模型。

`editorial_model_status()` 只报告配置就绪，不联网，也不证明凭据有效。未知供应商配置只返回 unavailable 和固定错误码。Mock对象只是标记，确定性回复继续由应用完成。

传输只连接固定官方HTTPS地址；禁重定向和环境代理，专用TLS上下文不继承SSLKEYLOGFILE；读取超时15秒、连接超时5秒，请求上限512KiB、解码响应上限1MiB。异常不反射正文、密钥或原始异常链。工具调用最多4个，JSON参数拒绝重复键和非有限数值。本模块没有SQL、文件写入、shell、邮件或审批能力。

## 实际证据与未验证项

离线契约使用 httpx.MockTransport，覆盖两次请求中的真实工具调用/结果消息结构、鉴权头/模型ID、超时/重定向/错误脱敏、分块响应大小限制、格式截断、配置失败关闭及TLS/proxy约束。该证据只证明本地协议与安全实现，不证明官方服务实际可用。

本辅助任务真实供应商调用为0：没有读取新环境密钥；聊天中已暴露的密钥不使用。实际DeepSeek工具循环、账户授权、延迟、供应商可用性和账单均仍待新安全环境凭据验证。没有对公开网页已验证的协议兼容性作超出本地实验证据的推断。
