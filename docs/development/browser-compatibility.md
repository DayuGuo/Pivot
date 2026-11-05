# 浏览器兼容性与复核入口

Pivot按[Next.js现代浏览器边界](https://nextjs.org/docs/architecture/supported-browsers)开发：Chrome/Edge/Firefox111+、Safari16.4+是框架目标，不是本项目已经逐版实测的承诺。实际版本/计数以PROGRESS和spec026验收报告为准。IE、旧.doc、扫描件/OCR仍不在范围。

本地完整验证：先用scripts/setup.sh安装依赖与Chromium/Firefox/WebKit。Linux缺系统库时，按[Playwright官方安装方式](https://playwright.dev/docs/browsers)执行`npx playwright install-deps chromium firefox webkit`；不能假设下载二进制后已能启动全部引擎。

```sh
COMPOSE_PROJECT_NAME=publishing-os-verification \
COMPOSE_FILE=compose.yaml:infrastructure/compose.verify.yaml \
DATABASE_URL=postgresql+psycopg://publishing:publishing_local@localhost:55433/publishing \
E2E_BASE_URL=http://127.0.0.1:13100 ./scripts/verify.sh
```

隔离Mock站已启动时，可选`E2E_BASE_URL=http://127.0.0.1:13100 npm run test:e2e -- --project=firefox`，或`--project=webkit`。默认运行全部三个项目，单worker，不能与Pytest共用数据库并发。静态Demo的DEMO_PATH和独立报告目录沿用原合同。测试工具安装只发生在开发/CI环境，VPS运行包不安装浏览器。

共享browser.ts使用getRandomValues生成UUIDv4回退，绝不用Math.random代替幂等标识；存储异常只影响刷新恢复、不影响当前输入。控制器与计时器代替较新的[AbortSignal.any](https://developer.mozilla.org/en-US/docs/Web/API/AbortSignal/any_static)，保留真实取消/期限。HTTPS/localhost上的WebCrypto仍是摘要核验必要条件，无能力时安全失败，不以弱摘要或不验证文本冒充已核对来源。[beforeunload](https://developer.mozilla.org/en-US/docs/Web/API/Window/beforeunload_event)的preventDefault和returnValue均保留，但移动系统强制结束进程仍不能保证触发。

三引擎验证包括真实登录、持久化、PDF/Word导入、人审和受控原文下载；模型和夹具标签仍按实际来源显示。API缺失/IME229事件是故障注入，短视口是浏览器模拟，并非旧版本、真实中文输入法、物理触屏或软键盘测试。Windows Edge、macOS/iOS Safari和Android真机仍需发布前补测。安全/权限最终在服务端执行，与浏览器显示能力无关。
