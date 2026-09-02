# Knowledge Agent Cloud Lightweight Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在同一台 2 核 4 GiB 阿里云 ECS 上新增可回退的 Knowledge Agent 轻量实例，同时保留本地全量运行能力和现有旧项目。

**Architecture:** 单一 GitHub 代码库通过环境变量切换运行能力；模型路径统一从项目根目录或显式环境变量解析。ECS 使用独立目录、Python 虚拟环境及两个 systemd 服务，FastAPI 仅监听本机，Streamlit 通过公网端口提供演示访问。

**Tech Stack:** Python 3.12、FastAPI、Streamlit、systemd、Ubuntu 22.04、Git、pytest

**Spec:** `docs/superpowers/specs/2026-09-03-cloud-lightweight-deployment-design.md`

## Global Constraints

- ECS 为 Ubuntu 22.04、2 vCPU、4 GiB、84 GiB 系统盘、无 GPU、1 Mbps 带宽。
- 旧项目 `/opt/Intelligent-EC-agent-jiu` 及端口 `7860` 必须持续保留。
- 新项目固定部署到 `/opt/knowledge_agent`。
- FastAPI 使用 `127.0.0.1:8000`；Streamlit 使用 `0.0.0.0:8501`。
- ECS 设置 `VLM_ENABLED=false`、`RERANKER_ENABLED=false`；本地代码不删除完整模型能力。
- `.env`、`datas/`、`models/`、SQLite、Chroma、日志和测试临时目录不得进入 Git。
- 公开注册只能获得普通用户权限。
- 未配置域名和 HTTPS，本阶段只提供公网 IP 演示访问。

---

### Task 1: 跨平台模型路径与轻量开关

**Files:**
- Modify: `common/constants.py`
- Modify: `agent_server/rag/embed_loader.py`
- Modify: `agent_server/rag/reranker.py`
- Modify: `agent_server/rag/loader.py`
- Test: `harness_test/test_cloud_deployment_config.py`

**Interfaces:**
- Consumes: `common.constants.PROJECT_ROOT`
- Produces: `BGE_MODEL_PATH: Path`、`RERANKER_MODEL_PATH: Path`、`VLM_MODEL_DIR: Path`，均支持环境变量覆盖。

- [ ] **Step 1: 写跨平台路径失败测试**

```python
def test_default_model_paths_are_project_relative():
    from common import constants

    assert constants.BGE_MODEL_PATH == constants.PROJECT_ROOT / "models" / "bge-base-zh-v1.5"
    assert constants.RERANKER_MODEL_PATH == constants.PROJECT_ROOT / "models" / "bge-reranker-base"
    assert constants.VLM_MODEL_DIR == constants.PROJECT_ROOT / "models" / "qwen2.5-vl"
```

- [ ] **Step 2: 运行测试并确认当前 Windows 硬编码导致失败**

Run: `.\.venv\Scripts\python.exe -m pytest harness_test/test_cloud_deployment_config.py::test_default_model_paths_are_project_relative -q`

Expected: FAIL，当前 `embed_loader.py` 或 `reranker.py` 仍包含 `F:\code\knowledge_agent`。

- [ ] **Step 3: 在常量模块集中定义模型路径**

```python
BGE_MODEL_PATH = Path(os.getenv("BGE_MODEL_PATH", str(PROJECT_ROOT / "models" / "bge-base-zh-v1.5")))
RERANKER_MODEL_PATH = Path(os.getenv("RERANKER_MODEL_PATH", str(PROJECT_ROOT / "models" / "bge-reranker-base")))
VLM_MODEL_DIR = Path(os.getenv("VLM_MODEL_DIR", str(PROJECT_ROOT / "models" / "qwen2.5-vl")))
```

让三个模型加载模块导入这些常量；传给第三方库时使用 `str(path)`，错误消息也使用解析后的路径。

- [ ] **Step 4: 增加环境变量覆盖测试**

```python
def test_model_paths_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("BGE_MODEL_PATH", str(tmp_path / "bge"))
    monkeypatch.setenv("RERANKER_MODEL_PATH", str(tmp_path / "reranker"))
    monkeypatch.setenv("VLM_MODEL_DIR", str(tmp_path / "vlm"))
    import importlib
    from common import constants

    reloaded = importlib.reload(constants)
    assert reloaded.BGE_MODEL_PATH == tmp_path / "bge"
    assert reloaded.RERANKER_MODEL_PATH == tmp_path / "reranker"
    assert reloaded.VLM_MODEL_DIR == tmp_path / "vlm"
```

- [ ] **Step 5: 运行聚焦测试**

Run: `.\.venv\Scripts\python.exe -m pytest harness_test/test_cloud_deployment_config.py harness_test/test_m1_rag.py -q --basetemp=.pytest_cloud_paths -p no:cacheprovider`

Expected: PASS。

- [ ] **Step 6: 提交路径改动**

```powershell
git add -- common/constants.py agent_server/rag/embed_loader.py agent_server/rag/reranker.py agent_server/rag/loader.py harness_test/test_cloud_deployment_config.py
git commit -m "fix: 支持跨平台模型路径配置"
```

### Task 2: 阻止公网注册管理员

**Files:**
- Modify: `agent_server/api/auth_router.py`
- Modify: `harness_test/test_m3_account_management.py`

**Interfaces:**
- Consumes: `register_user(username: str, password: str, role: str)`
- Produces: `POST /api/auth/register` 始终以 `employee` 角色创建用户。

- [ ] **Step 1: 写管理员提权回归测试**

```python
def test_public_register_cannot_create_admin(client):
    response = client.post(
        "/api/auth/register",
        json={"username": "public_user", "password": "Passw0rd!", "role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "employee"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest harness_test/test_m3_account_management.py::test_public_register_cannot_create_admin -q`

Expected: FAIL，响应角色当前为 `admin`。

- [ ] **Step 3: 固定公共注册角色**

```python
@router.post("/register")
def register(payload: RegisterRequest):
    user = register_user(payload.username, payload.password, "employee")
    return ok({"id": user["id"], "username": user["username"], "role": user["role"]})
```

保留请求字段只用于兼容现有客户端；管理员创建账号继续走已鉴权的 `/api/auth/admin/users`。

- [ ] **Step 4: 运行认证和权限测试**

Run: `.\.venv\Scripts\python.exe -m pytest harness_test/test_m3_account_management.py harness_test/edge/test_m4_api_edges.py -q --basetemp=.pytest_cloud_auth -p no:cacheprovider`

Expected: PASS。

- [ ] **Step 5: 提交安全修复**

```powershell
git add -- agent_server/api/auth_router.py harness_test/test_m3_account_management.py
git commit -m "fix: 限制公共注册为普通用户"
```

### Task 3: 创建轻量部署配置

**Files:**
- Create: `deploy/knowledge-agent.env.example`
- Create: `requirements-cloud.txt`
- Create: `deploy/systemd/knowledge-agent-api.service`
- Create: `deploy/systemd/knowledge-agent-web.service`
- Create: `scripts/check_deployment_config.py`
- Test: `harness_test/test_cloud_deployment_config.py`

**Interfaces:**
- Produces: 两个 systemd unit 和一个不含密钥的 ECS 环境模板。
- FastAPI service consumes: `/opt/knowledge_agent/.env`
- Streamlit service consumes: `KNOWLEDGE_AGENT_API_BASE_URL=http://127.0.0.1:8000`

- [ ] **Step 1: 写部署文件约束测试**

```python
def test_ecs_template_is_lightweight_and_contains_no_real_key():
    text = Path("deploy/knowledge-agent.env.example").read_text(encoding="utf-8")
    assert "VLM_ENABLED=false" in text
    assert "RERANKER_ENABLED=false" in text
    assert "KNOWLEDGE_AGENT_API_BASE_URL=http://127.0.0.1:8000" in text
    assert "AGNES_API_KEY=" in text
    assert "paddlepaddle" not in Path("requirements-cloud.txt").read_text(encoding="utf-8")

def test_systemd_units_use_isolated_directory_and_ports():
    api = Path("deploy/systemd/knowledge-agent-api.service").read_text(encoding="utf-8")
    web = Path("deploy/systemd/knowledge-agent-web.service").read_text(encoding="utf-8")
    assert "WorkingDirectory=/opt/knowledge_agent" in api
    assert "--host 127.0.0.1 --port 8000" in api
    assert "WorkingDirectory=/opt/knowledge_agent" in web
    assert "--server.address 0.0.0.0 --server.port 8501" in web
```

- [ ] **Step 2: 运行测试并确认部署文件不存在**

Run: `.\.venv\Scripts\python.exe -m pytest harness_test/test_cloud_deployment_config.py -q`

Expected: FAIL，缺少 `deploy/` 文件。

- [ ] **Step 3: 创建无密钥环境模板**

```dotenv
AGNES_API_KEY=
AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
AGNES_MODEL=agnes-2.0-flash
VLM_ENABLED=false
RERANKER_ENABLED=false
DATAS_DIR=/opt/knowledge_agent/datas
APP_DB_PATH=/opt/knowledge_agent/datas/app.db
CHROMA_DIR=/opt/knowledge_agent/datas/chroma
BGE_MODEL_PATH=/opt/knowledge_agent/models/bge-base-zh-v1.5
KNOWLEDGE_AGENT_API_BASE_URL=http://127.0.0.1:8000
LOG_LEVEL=INFO
```

同时创建 `requirements-cloud.txt`，只保留 FastAPI、Uvicorn、LangChain/LangGraph、Chroma、sentence-transformers、文档文本解析、Streamlit 和 requests 等轻量运行依赖；不安装仅由已关闭能力使用的 `paddlepaddle`、`paddleocr`、VLM 和 4-bit 依赖。通过导入 `agent_server.main` 和 `web.app` 验证依赖集合完整。

- [ ] **Step 4: 创建 systemd 服务**

API unit 使用 `/opt/knowledge_agent/.venv/bin/python -m uvicorn agent_server.main:app --host 127.0.0.1 --port 8000`；Web unit 使用 `/opt/knowledge_agent/.venv/bin/python -m streamlit run web/app.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false`。两者设置 `Restart=on-failure`、`RestartSec=5`，Web 设置 `After=knowledge-agent-api.service`。

- [ ] **Step 5: 创建静态部署检查器**

`scripts/check_deployment_config.py` 检查模板无真实 key、路径为 `/opt/knowledge_agent`、API 不监听公网、两个 unit 名称及端口正确；失败时退出码为 1，成功输出 `DEPLOYMENT_CONFIG_OK`。

- [ ] **Step 6: 运行部署配置测试和检查器**

Run: `.\.venv\Scripts\python.exe -m pytest harness_test/test_cloud_deployment_config.py -q --basetemp=.pytest_cloud_deploy -p no:cacheprovider`

Run: `.\.venv\Scripts\python.exe scripts/check_deployment_config.py`

Expected: 测试 PASS，检查器输出 `DEPLOYMENT_CONFIG_OK`。

- [ ] **Step 7: 提交部署配置**

```powershell
git add -- deploy/knowledge-agent.env.example deploy/systemd/knowledge-agent-api.service deploy/systemd/knowledge-agent-web.service requirements-cloud.txt scripts/check_deployment_config.py harness_test/test_cloud_deployment_config.py
git commit -m "feat: 添加 ECS 轻量部署配置"
```

### Task 4: 补充本地全量和 ECS 轻量说明

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `scripts/verify_readme.py`

**Interfaces:**
- Produces: 可复现的本地全量模式和 ECS 轻量模式操作说明。

- [ ] **Step 1: 扩展 README 校验规则**

检查 README 必须包含 `本地全量模式`、`ECS 轻量模式`、三个模型目录、`VLM_ENABLED=false`、`RERANKER_ENABLED=false`、`systemctl`、`8501`，并明确模型、密钥和业务数据不随 Git 提供。

- [ ] **Step 2: 运行 README 校验并确认失败**

Run: `.\.venv\Scripts\python.exe scripts/verify_readme.py`

Expected: FAIL，旧 README 尚未包含两套部署说明。

- [ ] **Step 3: 更新 README 与本地环境模板**

README 写明本地完整模型目录：

```text
models/
├── bge-base-zh-v1.5/
├── bge-reranker-base/
└── qwen2.5-vl/
```

同时给出 Windows 本地启动命令、ECS 轻量环境变量、systemd 安装命令和健康检查命令；不得写入真实 API key、公网账号密码或业务数据。

- [ ] **Step 4: 验证文档**

Run: `.\.venv\Scripts\python.exe scripts/verify_readme.py`

Expected: 输出 README 校验通过。

- [ ] **Step 5: 提交文档**

```powershell
git add -- README.md .env.example scripts/verify_readme.py
git commit -m "docs: 补充本地全量与 ECS 轻量运行指南"
```

### Task 5: 本地总验收并发布 GitHub

**Files:**
- Verify only: entire tracked tree

**Interfaces:**
- Produces: 通过测试且不包含敏感运行数据的 `master` 提交。

- [ ] **Step 1: 运行全量测试**

Run: `.\.venv\Scripts\python.exe -m pytest harness_test -q --basetemp=.pytest_cloud_full -p no:cacheprovider`

Expected: 退出码 0，无失败用例。

- [ ] **Step 2: 运行语法与部署检查**

Run: `.\.venv\Scripts\python.exe -m compileall -q agent_server common web scripts`

Run: `.\.venv\Scripts\python.exe scripts/check_deployment_config.py`

Expected: 两条命令退出码均为 0。

- [ ] **Step 3: 检查 Git 发布边界**

Run: `git status --short --ignored`

Run: `git ls-files | Select-String -Pattern '(^|/)(\.env|datas|models|logs|\.pytest|\.codex|codex)(/|$)|\.(db|sqlite|sqlite3|log|pyc)$'`

Expected: `.env`、数据、模型和运行产物均未被跟踪，源码改动均已提交。

- [ ] **Step 4: 同步并推送**

```powershell
git fetch origin
git rev-list --left-right --count origin/master...master
git push origin master
```

禁止强制推送；若远端领先则停止，先检查远端提交并采用非破坏性同步。

### Task 6: ECS 预检、安装与验收

**Files:**
- Deploy from: GitHub `master`
- Server-only secrets: `/opt/knowledge_agent/.env`
- Server-only data: `/opt/knowledge_agent/datas/`
- Server-only models: `/opt/knowledge_agent/models/`

**Interfaces:**
- Consumes: 已发布 GitHub 提交、现有 ECS SSH 访问、真实 LLM API key。
- Produces: `knowledge-agent-api.service`、`knowledge-agent-web.service`。

- [ ] **Step 1: 只读预检旧项目和服务器资源**

Run:

```bash
ssh root@8.154.20.121
free -h
df -h /
ss -lntp
systemctl --failed
ps -ef | grep -E 'python|streamlit|uvicorn' | grep -v grep
```

确认 `7860` 仍由旧项目使用，`8000` 和 `8501` 未被占用；若端口冲突、可用磁盘低于 20 GiB，或旧项目服务异常，停止部署并报告。

- [ ] **Step 2: 创建并验证 4 GiB Swap**

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -h
```

如果 `/swapfile` 已存在，先用 `swapon --show` 和 `ls -lh /swapfile` 验证，不覆盖现有 Swap。

- [ ] **Step 3: 克隆新项目且不触碰旧目录**

```bash
git clone https://github.com/jiujiu369/knowledge_agent.git /opt/knowledge_agent
cd /opt/knowledge_agent
git rev-parse --short HEAD
python3 --version
```

若目录已存在则先检查 `git status`、当前提交及 `.env`/数据备份，不执行覆盖式删除。

- [ ] **Step 4: 创建虚拟环境并安装轻量运行依赖**

```bash
apt-get update
apt-get install -y software-properties-common git
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y python3.12 python3.12-venv
python3.12 -m venv /opt/knowledge_agent/.venv
/opt/knowledge_agent/.venv/bin/python -m pip install --upgrade pip
/opt/knowledge_agent/.venv/bin/python -m pip install -r /opt/knowledge_agent/requirements-cloud.txt
```

安装过程中持续观察 `free -h` 和 `df -h /`；不得卸载旧项目依赖或复用旧项目虚拟环境。

- [ ] **Step 5: 配置密钥、目录和基础 BGE 模型**

```bash
install -m 600 /opt/knowledge_agent/deploy/knowledge-agent.env.example /opt/knowledge_agent/.env
mkdir -p /opt/knowledge_agent/datas/chroma /opt/knowledge_agent/models/bge-base-zh-v1.5
```

在服务器终端中编辑 `/opt/knowledge_agent/.env` 写入真实 API key；不在聊天、Git、shell history 或日志中打印 key。通过安全文件传输将 BGE 模型放入指定目录，保留 VLM 和 reranker 为关闭状态。

- [ ] **Step 6: 安装并启动 systemd 服务**

```bash
cp /opt/knowledge_agent/deploy/systemd/knowledge-agent-api.service /etc/systemd/system/
cp /opt/knowledge_agent/deploy/systemd/knowledge-agent-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now knowledge-agent-api.service
systemctl enable --now knowledge-agent-web.service
systemctl status knowledge-agent-api.service --no-pager
systemctl status knowledge-agent-web.service --no-pager
```

- [ ] **Step 7: 在服务器本机验收**

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8501/_stcore/health
ss -lntp | grep -E ':7860|:8000|:8501'
free -h
systemctl is-active knowledge-agent-api.service knowledge-agent-web.service
```

Expected: 三个端口均存在，两个新服务为 active，旧项目 `7860` 不受影响，无重启循环或 OOM。

- [ ] **Step 8: 配置安全组并做公网业务验收**

在阿里云安全组新增 `TCP 8501` 入方向规则；优先将来源限制为用户当前公网 IP，仅在确需公开演示时使用 `0.0.0.0/0`。浏览器访问 `http://8.154.20.121:8501`，验证注册只能得到普通用户、管理员登录、基础知识检索、一次 LLM 对话、创建工单和管理员处理工单。

- [ ] **Step 9: 验证重启恢复与回退边界**

```bash
systemctl restart knowledge-agent-api.service knowledge-agent-web.service
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8501/_stcore/health
systemctl is-active knowledge-agent-api.service knowledge-agent-web.service
```

若新服务失败，只执行 `systemctl disable --now knowledge-agent-api.service knowledge-agent-web.service`；不得停止、删除或覆盖旧项目服务和 `/opt/Intelligent-EC-agent-jiu`。
