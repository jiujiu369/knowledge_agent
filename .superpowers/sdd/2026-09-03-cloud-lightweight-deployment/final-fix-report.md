# 云端轻量部署最终修复报告

## 状态与提交

- 状态：全部指定阻断项已修复，本地最终验收通过。
- 分支：`cloud-lightweight`
- 实现提交：`b8841b2`（`fix: 收口云端轻量部署阻断项`）
- 发布边界：本次没有执行 `git push`，也没有修改主检出。

## 改动

1. 新增 `scripts/bootstrap_admin.py`：只允许交互式 TTY，通过 `getpass` 两次无回显读取密码，拒绝命令行凭据，不读取管理员密码环境变量，并调用 `agent_server.core.auth.register_user(..., "admin")` 创建可登录管理员。
2. README 与 Task 6 统一为 Ubuntu 22.04 显式安装和使用 Python 3.12；创建 `knowledge-agent` 系统账户，并约束源码、`.venv`、`.env`、`datas/`、`models/` 的所有权和最小权限。
3. 两个 systemd unit 统一使用 `User=knowledge-agent`、`Group=knowledge-agent`、`UMask=0027`；部署环境模板把 QA 日志放到服务账户可写的 `datas/logs/`。
4. `requirements.txt` 补齐运行时直接依赖和完整模式模型栈，包括 PyMuPDF、pdfplumber、python-docx、openai、python-dotenv、transformers、bitsandbytes、Pillow、torch、torchvision、accelerate、httpx、numpy；`requirements-cloud.txt` 内容未削弱，并由静态契约锁定。
5. 部署检查器新增运行时 AST import 扫描、完整/轻量依赖契约、QA 日志路径与 systemd UMask 校验；README 检查器拒绝 Ubuntu 默认 `python3`、Streamlit 首页伪健康检查和易过期的 pytest 硬编码数量。
6. Task 6 的真实 ECS 地址改为本地环境变量；补入干净虚拟环境、`pip check`、API/Web 导入、真实健康端点、逐端口监听、`NRestarts`、cgroup 内存、可用内存、内核 OOM 与重启后复验硬条件。
7. 新增 bootstrap、README、部署配置及依赖契约聚焦测试；新增硬验收命令的先红后绿回归覆盖。

## 测试命令与结果

- TDD 初始聚焦测试：新增契约首次运行得到 `10 failed, 11 passed`；逐项实现后聚焦套件通过。
- `F:\code\knowledge_agent\.venv\Scripts\python.exe -m pytest harness_test/test_bootstrap_admin.py harness_test/test_cloud_deployment_config.py harness_test/test_readme_deployment_contract.py harness_test/func/test_m6_docs.py harness_test/test_docstring_coverage.py -q --basetemp=... -p no:cacheprovider`
  - 结果：`27 passed, 2 warnings in 5.19s`
- `F:\code\knowledge_agent\.venv\Scripts\python.exe -m pytest harness_test -q --basetemp=... -p no:cacheprovider`
  - 最终结果：`191 passed, 2 skipped, 364 warnings in 58.80s`
- `F:\code\knowledge_agent\.venv\Scripts\python.exe -m compileall -q agent_server common loop_optimizer scripts web harness_test`
  - 结果：退出码 `0`
- `F:\code\knowledge_agent\.venv\Scripts\python.exe -m pip check`
  - 结果：`No broken requirements found.`
- `VLM_ENABLED=false RERANKER_ENABLED=false python -c "import agent_server.main; import web.app; print('API_WEB_IMPORT_OK')"`
  - 结果：`API_WEB_IMPORT_OK`
- `F:\code\knowledge_agent\.venv\Scripts\python.exe scripts/check_deployment_config.py`
  - 结果：`DEPLOYMENT_CONFIG_OK`
- `F:\code\knowledge_agent\.venv\Scripts\python.exe scripts/verify_readme.py`
  - 结果：`README verification passed`
- `git diff --check` 与 `git diff --cached --check`
  - 结果：退出码 `0`

## 剩余 concerns

1. 当前验收环境为 Windows；Ubuntu 22.04 上的账户/权限、Python 3.12 安装、systemd、三端口、内存与 OOM 硬验收仍须按 Task 6 在真实 ECS 执行。
2. 本地 `pip check` 验证的是现有项目虚拟环境；体积较大的完整模型栈未在本次 Windows 修复中重新下载并做真实模型推理，部署前仍应在目标模式的干净环境安装验证。
3. 测试仍有既存弃用告警：FastAPI `on_event`、`datetime.utcnow()` 与 Starlette TestClient；本次无新增失败。
