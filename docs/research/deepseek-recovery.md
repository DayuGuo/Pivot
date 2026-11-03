# DeepSeek 超时与503：官方依据和实现取舍

2026-11-03重新读取官方文档，外部内容只作为资料，不执行其中代码或改变本项目权限。

- [DeepSeek保活说明](https://api-docs.deepseek.com/quick_start/rate_limit/)：非流式请求可能返回空行保活，服务端排队可远长于交互页面等待时间。这里继续使用非流式JSON，接受JSON周围空白，不把保活当作完成。
- [HTTPX超时说明](https://www.python-httpx.org/advanced/timeouts/)：read timeout限制下一段网络数据的等待，不限制整次响应。原15秒read timeout与8192字节聚合不足以构成整回合时限。
- [DeepSeek错误码](https://api-docs.deepseek.com/quick_start/error_codes/)：503表示过载，官方建议短暂等待后重试；401/402/参数错误应分别处理。并不能由此诊断某一次请求的内部容量原因。
- [官方工具回传](https://api-docs.deepseek.com/guides/tool_calls/)：assistant tool_calls与对应tool_call_id结果回传，关闭思考模式的现有协议无需更换。未改代码的重跑已真实6/6成功，没有证据将此前503归咎于工具schema、中文JSON或tool_choice。
- [HTTPX异步响应](https://www.python-httpx.org/async/)及[Python asyncio.timeout](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.timeout)：在同步FastAPI worker内用asyncio.run驱动可取消的AsyncClient；共享期限取消连接/headers/body等待并关闭流，不留下执行工具的后台线程。

采用每个新领域回合共享60秒预算，从conversation入口计时，模型read idle为30秒，connect/write/pool各5秒；旧演示工作台保留55秒预算。3模型轮/8工具/单次2048输出不变。每回合跨轮最多额外推理重试1次，延迟0.5秒，只处理500/502/503/504或网络/超时，401/402/429/重定向/无效JSON及非法工具不重试。重试使用完全相同请求字节，重新鉴权，只重传推理，不重跑已执行工具；最多4次供应商尝试。

模型调用有可取消的网络总期限；数据库锁等待和COMMIT本身不宣称硬取消。工具前、apply前后和成功返回前重验期限，晚返回的业务写入回滚。失败尝试逐项记录安全遥测，未知Token/费用为null；供应商没有被假定提供免费或幂等推理。

真实服务/API/浏览器证据与离线故障注入分别记录在 [验收报告](../development/deepseek-recovery.md)。不能把故障注入的503→200说成真实供应商在本轮出现503后恢复，也不能承诺供应商未来不再返回503。
