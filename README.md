# Knowledge Agent

企业内部知识库问答与工单智能体，面向本地演示和工程化交付。系统提供本地 RAG 检索、制度问答、用户主动创建工单、管理员审批工单、知识库文档管理、压测测试闭环和半自动 Loop 优化报告。

## 数据与密钥边界

- 数据本地不上云：`datas/` 下的制度文档、`datas/app.db`、`datas/chroma/` 均保存在本机。
- Embedding 本地运行：使用 `models/bge-base-zh-v1.5/`，不调用云端 Embedding。
- 向量库本地运行：Chroma 持久化在 `datas/chroma/`。
- OCR 本地运行：PaddleOCR 在本机解析 PDF/Word 插图文字。
- VLM 本地运行：`models/qwen2.5-vl/` 可用时对插图做语义增强，不上传图片。
- 只有 LLM 生成层走云端 API：通过 OpenAI 兼容接口访问 Agnes/Ark。
- 云端 LLM 客户端默认忽略系统代理环境变量，避免本机代理异常导致 Ark/Agnes HTTPS 连接失败。
- API key 只走环境变量：复制 `.env.example` 为 `.env` 后填写 `AGNES_API_KEY` 或 `ARK_API_KEY`，代码和文档不写真实 key。

## 运行模式与交付边界

本仓库支持同一代码库的两种运行方式：**本地全量模式**用于 Windows 演示与完整 RAG 能力；**ECS 轻量模式**用于 Linux 常驻服务。模型、密钥和业务数据不随 Git 提供：克隆仓库后仍需由部署者准备模型权重、`.env` 中的 LLM 密钥，以及自己的 `datas/` 业务数据和数据库备份，不能将“可克隆”视为“已可全量运行”。

### 本地全量模式

适用场景：Windows 本地演示，需要 Embedding、reranker、OCR 与 VLM 插图增强的完整链路。

项目根目录需要由部署者自行放置以下本地模型（均被 Git 忽略）：

```text
models/
├── bge-base-zh-v1.5/
├── bge-reranker-base/
└── qwen2.5-vl/
```

环境：Python 3.12.9。以下 Windows PowerShell 命令从 Git 克隆后在任意本地目录创建独立环境；`<仓库 HTTPS 地址>` 由部署者替换为实际仓库地址。

```powershell
git clone <仓库 HTTPS 地址> knowledge_agent
Set-Location .\knowledge_agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

在本机 `.env` 填入有效的 `AGNES_API_KEY` 或 `ARK_API_KEY`，并自行准备上述三个模型目录；不要把 `.env`、模型目录或 `datas/` 提交到 Git。本地全量模式使用 `.env.example` 中的 `VLM_ENABLED=true` 和 `RERANKER_ENABLED=true`。启动后端与前端：

```powershell
.venv\Scripts\python.exe -m uvicorn agent_server.main:app --host 127.0.0.1 --port 8000
.venv\Scripts\python.exe -m streamlit run web/app.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false
```

也可使用本地启动器：

```powershell
.venv\Scripts\python.exe web/local_launcher.py
```

访问地址：后端健康检查 `http://127.0.0.1:8000/health`，Swagger `http://127.0.0.1:8000/docs`，前端 `http://localhost:8501`。

### ECS 轻量模式

适用场景：Linux ECS 常驻运行。该模式只保留本地 BGE 检索和 Chroma；关闭 VLM、reranker 和其重型依赖，不应把本地全量模型目录直接作为 ECS 前置条件。

1. Ubuntu 22.04 自带的 `python3` 是 Python 3.10，不能用它创建本项目环境。先显式安装并确认 Python 3.12：

```bash
sudo apt-get update
sudo apt-get install -y software-properties-common git
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv
python3.12 --version
```

2. **先**创建与 systemd 一致的运行身份，再克隆代码和分配最小权限。代码、虚拟环境、模型和 `.env` 由 root 管理；服务账户只写 `datas/`，只读模型和密钥。全新安装执行：

```bash
export KNOWLEDGE_AGENT_REPO_URL='<你的仓库 HTTPS 地址>'
sudo useradd --system --user-group --home-dir /opt/knowledge_agent --no-create-home --shell /usr/sbin/nologin knowledge-agent
sudo git clone "$KNOWLEDGE_AGENT_REPO_URL" /opt/knowledge_agent
cd /opt/knowledge_agent
sudo chown -R root:knowledge-agent /opt/knowledge_agent
sudo chmod -R u=rwX,g=rX,o= /opt/knowledge_agent
sudo install -d -o knowledge-agent -g knowledge-agent -m 750 /opt/knowledge_agent/datas /opt/knowledge_agent/datas/chroma /opt/knowledge_agent/datas/logs
sudo install -d -o root -g knowledge-agent -m 750 /opt/knowledge_agent/models /opt/knowledge_agent/models/bge-base-zh-v1.5
sudo install -o root -g knowledge-agent -m 640 /opt/knowledge_agent/deploy/knowledge-agent.env.example /opt/knowledge_agent/.env
```

若用户或目录已存在，先用 `id knowledge-agent`、`git -C /opt/knowledge_agent status` 检查，不要重复 `useradd`、覆盖目录或删除既有 `.env`/数据。

3. 以受控方式将 BGE 权重放入 `/opt/knowledge_agent/models/bge-base-zh-v1.5/`，将业务文档、SQLite 与 Chroma 数据放在 `/opt/knowledge_agent/datas/`。用 `sudoedit /opt/knowledge_agent/.env` 填入实际 LLM 密钥；不要把密钥放入命令参数、`export`、聊天或日志。模板中的轻量关键值必须保持：

```dotenv
VLM_ENABLED=false
RERANKER_ENABLED=false
DATAS_DIR=/opt/knowledge_agent/datas
APP_DB_PATH=/opt/knowledge_agent/datas/app.db
CHROMA_DIR=/opt/knowledge_agent/datas/chroma
BGE_MODEL_PATH=/opt/knowledge_agent/models/bge-base-zh-v1.5
QA_LOG_PATH=/opt/knowledge_agent/datas/logs/qa_events.jsonl
KNOWLEDGE_AGENT_API_BASE_URL=http://127.0.0.1:8000
```

上传完成后收紧模型权限并硬检查服务账户权限；`.env` 必须保持 `root:knowledge-agent 640`，服务账户可读但不可写：

```bash
sudo chown -R root:knowledge-agent /opt/knowledge_agent/models
sudo find /opt/knowledge_agent/models -type d -exec chmod 750 {} +
sudo find /opt/knowledge_agent/models -type f -exec chmod 640 {} +
sudo chown -R knowledge-agent:knowledge-agent /opt/knowledge_agent/datas
sudo chmod -R u=rwX,g=rX,o= /opt/knowledge_agent/datas
test "$(stat -c '%U:%G %a' /opt/knowledge_agent/.env)" = 'root:knowledge-agent 640'
sudo -u knowledge-agent test -r /opt/knowledge_agent/.env
sudo -u knowledge-agent test ! -w /opt/knowledge_agent/.env
sudo -u knowledge-agent test -w /opt/knowledge_agent/datas
sudo -u knowledge-agent test -r /opt/knowledge_agent/models/bge-base-zh-v1.5
```

4. 用 Python 3.12 创建全新的 Linux 虚拟环境，安装未削弱的轻量依赖，并在启动前做依赖和导入验收。若 `.venv` 已存在，停止并查明来源，不要在未知环境上覆盖安装：

```bash
test ! -e /opt/knowledge_agent/.venv
sudo python3.12 -m venv /opt/knowledge_agent/.venv
sudo /opt/knowledge_agent/.venv/bin/python -m pip install --upgrade pip
sudo /opt/knowledge_agent/.venv/bin/python -m pip install -r /opt/knowledge_agent/requirements-cloud.txt
/opt/knowledge_agent/.venv/bin/python -m pip check
sudo -u knowledge-agent /opt/knowledge_agent/.venv/bin/python -c "import agent_server.main; import web.app; print('API_WEB_IMPORT_OK')"
```

5. 在启动公网服务前创建首个管理员。该命令不接受任何参数，也不从环境变量读取管理员密码；它要求交互式 TTY，并通过 `getpass` 两次无回显读取密码，再调用服务端认证逻辑创建 `admin`：

```bash
cd /opt/knowledge_agent
sudo -u knowledge-agent /opt/knowledge_agent/.venv/bin/python /opt/knowledge_agent/scripts/bootstrap_admin.py
```

6. 安装 systemd 单元。`knowledge-agent-api` 仅监听 `127.0.0.1:8000`，`knowledge-agent-web` 对外提供 `8501`；生产环境仍应按自己的网络策略限制访问该端口：

```bash
sudo cp /opt/knowledge_agent/deploy/systemd/knowledge-agent-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now knowledge-agent-api knowledge-agent-web
sudo systemctl status knowledge-agent-api knowledge-agent-web --no-pager
```

7. 用真实健康端点、自动重启计数、cgroup 内存与内核 OOM 日志做硬验收。两个新服务合计 `MemoryCurrent` 必须低于 3 GiB，`MemAvailable` 不低于 256 MiB，且 `NRestarts=0`：

```bash
set -euo pipefail
curl --fail --retry 10 --retry-delay 2 --retry-connrefused http://127.0.0.1:8000/health
curl --fail --retry 10 --retry-delay 2 --retry-connrefused http://127.0.0.1:8501/_stcore/health
sudo systemctl is-active knowledge-agent-api knowledge-agent-web
sudo systemctl show knowledge-agent-api knowledge-agent-web -p NRestarts -p MemoryCurrent --no-pager
test "$(sudo systemctl show knowledge-agent-api -p NRestarts --value)" -eq 0
test "$(sudo systemctl show knowledge-agent-web -p NRestarts --value)" -eq 0
API_MEMORY_BYTES=$(sudo systemctl show knowledge-agent-api -p MemoryCurrent --value)
WEB_MEMORY_BYTES=$(sudo systemctl show knowledge-agent-web -p MemoryCurrent --value)
test "$((API_MEMORY_BYTES + WEB_MEMORY_BYTES))" -lt $((3 * 1024 * 1024 * 1024))
MEM_AVAILABLE_KIB=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
test "$MEM_AVAILABLE_KIB" -ge $((256 * 1024))
KERNEL_LOG=$(sudo journalctl -k --since '-15 minutes' --no-pager)
if grep -Ei 'oom-kill|out of memory|killed process' <<<"$KERNEL_LOG" >/dev/null; then
  echo 'FAIL: kernel OOM evidence detected during deployment acceptance' >&2
  exit 1
fi
for PORT in 7860 8000 8501; do
  test -n "$(ss -lntH "sport = :$PORT")" || {
    echo "FAIL: port $PORT is not listening" >&2
    exit 1
  }
done
sudo journalctl -u knowledge-agent-api -u knowledge-agent-web -n 100 --no-pager
```

最后执行一次受控重启并重复两条 `curl`、`is-active`、`NRestarts`、`MemoryCurrent` 与 OOM 检查；若任一硬条件失败，只停止这两个新服务，不触碰旧项目或 `7860`。

### 管理员与 Web 冒烟

公网 `POST /api/auth/register` 只会创建 `employee`；不要再通过公网注册接口创建管理员。管理员必须在受信任的初始化或运维流程中预创建，且用户名、密码不得写入 Git、文档或命令历史。

Web 冒烟测试只登录这个预创建管理员。运行前在受限的部署环境中提供以下环境变量，再执行测试：

```bash
export KNOWLEDGE_AGENT_SMOKE_ADMIN_USERNAME='<预创建管理员用户名>'
export KNOWLEDGE_AGENT_SMOKE_ADMIN_PASSWORD='<预创建管理员密码>'
sudo -u knowledge-agent -E /opt/knowledge_agent/.venv/bin/python /opt/knowledge_agent/web/smoke_test.py
```

缺少任一变量时 `web/smoke_test.py` 会停止，不会注册或提升管理员账号。

## 核心流程

1. 管理员登录后进入“上传”页，上传 PDF、DOCX 或 DOC 文档并重建知识库。
2. 用户进入“对话”页提问，后端基于本地 RAG 检索和最近 5 轮对话上下文生成回答。
3. 普通对话不会自动创建工单。若模型建议建单，前端显示“创建工单”按钮，由用户自主提交。
4. 用户提交后，工单默认状态为 `pending`。
5. 管理员进入“工单”页，将工单审批为 `approved`、`rejected` 或 `closed`。
6. 管理员可在“上传”页删除已上传文档，系统会删除文档记录和本地文件，并重建知识库索引。

## API 概览

- `POST /api/auth/register`：注册用户。
- `POST /api/auth/login`：登录并获取 token。
- `GET /api/auth/me`：获取当前用户、角色和可用工具。
- `GET /api/auth/admin/users`：管理员查看用户列表。
- `POST /api/auth/admin/users`：管理员创建用户。
- `POST /api/auth/admin/users/{user_id}/reset-password`：管理员重置密码。
- `DELETE /api/auth/admin/users/{user_id}`：管理员删除用户。
- `POST /api/auth/change-password`：当前用户修改密码。
- `POST /api/chat`：非流式对话，保存对话历史，返回回答和可选 `ticket_suggestion`。
- `POST /api/chat/stream`：SSE 流式对话，返回工具事件和最终回答。
- `GET /api/chat/history`：查看当前用户对话历史。
- `GET /api/tickets`：查看工单列表；管理员可看全部，普通用户只看自己的。
- `POST /api/tickets`：用户主动创建待审批工单。
- `GET /api/tickets/{ticket_id}`：查看工单详情。
- `PATCH /api/tickets/{ticket_id}`：管理员审批或关闭工单。
- `GET /api/knowledge`：查看已入库文档。
- `POST /api/knowledge/upload`：管理员上传知识库文档。
- `POST /api/knowledge/rebuild`：管理员重建知识库索引。
- `DELETE /api/knowledge/{doc_id}`：管理员删除已上传文档并重建索引。
- `POST /api/tools/{tool_name}`：按 RBAC 调用工具。

## 主要函数介绍

### 后端入口

- `agent_server.main.startup()`：FastAPI 启动时初始化 SQLite 连接池。
- `agent_server.api.utils.ok()`：统一成功响应格式。
- `agent_server.api.utils.rate_limit_middleware()`：对 API 请求做基础限流，可用 `KNOWLEDGE_AGENT_DISABLE_RATE_LIMIT=1` 关闭。

### 认证与权限

- `agent_server.core.auth.register_user()`：创建新用户并保存密码哈希。
- `agent_server.core.auth.login_user()`：校验密码并生成 token。
- `agent_server.core.auth.get_current_user()`：从 `Authorization: Bearer ...` 中解析当前用户。
- `agent_server.core.rbac.role_tier()`：将角色归并为 `admin` 或 `employee` 权限层级。
- `agent_server.core.rbac.ensure_tool_allowed()`：校验当前角色是否可调用指定工具。

### 对话与 Agent

- `agent_server.graph_flow.graph_builder.build_graph()`：组装身份校验、RAG 检索、LLM 决策节点。
- `agent_server.graph_flow.graph_builder.run_agent()`：执行非流式对话。
- `agent_server.graph_flow.graph_builder.run_agent_events()`：执行流式对话并产出 SSE 事件。
- `agent_server.graph_flow.graph_nodes.parallel_rag_node()`：并行语义上聚合知识库检索和相似工单匹配结果。
- `agent_server.graph_flow.graph_nodes.build_agent_context()`：把最近 5 条对话历史和 RAG 片段合并为 LLM 上下文。
- `agent_server.graph_flow.graph_nodes.llm_decision_node()`：生成回答和工单建议；不会自动落库创建工单。
- `agent_server.api.chat_router.save_chat_history()`：保存问答历史并写入 QA 日志。

### 工单与工具

- `agent_server.tools.business_tools.doc_retrieve()`：调用本地 RAG 检索制度片段。
- `agent_server.tools.business_tools.match_similar_ticket()`：在已有工单中做相似问题匹配。
- `agent_server.tools.business_tools.create_consult_ticket()`：工具层创建咨询工单。
- `agent_server.tools.business_tools.query_ticket_list()`：按角色查询工单列表。
- `agent_server.tools.business_tools.export_ticket_stat()`：管理员导出工单统计。
- `agent_server.api.ticket_router.create_ticket()`：用户主动提交 `pending` 工单。
- `agent_server.api.ticket_router.update_ticket()`：管理员审批或关闭工单。

### RAG 链路

- `agent_server.rag.loader.scan_source_files()`：扫描 `datas/` 下可入库文档。
- `agent_server.rag.loader.load_documents()`：加载 PDF、DOCX、DOC 文档。
- `agent_server.rag.loader.ocr_image_bytes()`：对图片内容执行本地 OCR。
- `agent_server.rag.loader.enhance_image_text()`：在 VLM 可用时增强插图语义，默认保留 OCR 文本。
- `agent_server.rag.chunker.chunk_blocks()`：将文档块切分为检索 chunk。
- `agent_server.rag.embed_loader.embed_texts()`：使用本地 BGE 模型生成向量。
- `agent_server.rag.vector_store.RagVectorStore.upsert_chunks()`：写入本地 Chroma 向量库。
- `agent_server.rag.retriever_pipe.rebuild_index()`：重建知识库索引。
- `agent_server.rag.retriever_pipe.retrieve()`：执行向量、关键词和 reranker 组合检索。
- `agent_server.rag.reranker.rerank()`：在本地 reranker 可用时进行重排。

### 知识库管理

- `agent_server.tools.business_tools.knowledge_manage()`：管理员列出或重建知识库。
- `agent_server.api.knowledge_router.upload_knowledge()`：上传文档到本地 `datas/`。
- `agent_server.api.knowledge_router.delete_knowledge()`：删除文档 DB 记录和本地文件，并重建索引。
- `agent_server.core.db.upsert_doc()`：写入或更新文档元数据。
- `agent_server.core.db.delete_doc()`：删除文档元数据。

### 前端与启动器

- `web.frontend_api.stream_chat()`：调用后端 SSE 对话接口。
- `web.frontend_api.create_ticket()`：提交用户主动创建的工单。
- `web.frontend_api.delete_knowledge_doc()`：调用管理员删除文档接口。
- `web.app.render_chat()`：渲染对话页，显示历史、工具事件和创建工单按钮。
- `web.app.render_tickets()`：渲染工单列表和管理员审批入口。
- `web.app.render_upload()`：渲染文档上传、入库列表和删除入口。
- `web.local_launcher.LocalLauncher`：提供本地后端、前端启动、停止、状态检查和后端重启按钮。

### M4/M5 自动化

- `run_harness.py`：一键运行功能测试、边界测试、短压测并生成结果。
- `loop_optimizer.collector.collect_samples()`：从 `agent_server/logs` 抽取低匹配、高幻觉风险、高频问题样本。
- `loop_optimizer.filter.aggregate_samples()`：去重、聚合并生成优化发现。
- `loop_optimizer.updater.write_outputs()`：生成 `bad_sample.csv`、`optimize_report.md`、`prompt_diff.md`。
- `loop_optimizer.run_loop.main()`：运行 Loop 优化闭环；LLM 评估默认关闭，由 `LLM_EVAL_ENABLED` 控制。

## 自检命令

后端健康检查：

```powershell
.venv\Scripts\python.exe -c "from fastapi.testclient import TestClient; from agent_server.main import app; r=TestClient(app).get('/health'); print(r.status_code, r.text)"
```

云端 LLM 连通性：

```powershell
.venv\Scripts\python.exe -c "from agent_server.core.llm_client import chat_completion; print(chat_completion([{'role':'user','content':'只回复 OK'}], temperature=0))"
```

本地 VLM 状态：

```powershell
.venv\Scripts\python.exe -c "from agent_server.rag.loader import vlm_status; import json; print(json.dumps(vlm_status(), ensure_ascii=False, indent=2))"
```

RAG 冒烟：

```powershell
.venv\Scripts\python.exe -m agent_server.rag.smoke_test
```

后端冒烟：

```powershell
.venv\Scripts\python.exe -m agent_server.smoke_test
```

Harness 测试：

```powershell
.venv\Scripts\python.exe -m pytest harness_test -q
```

M4 测试与短压测：

```powershell
.venv\Scripts\python.exe run_harness.py --stress-duration 10s
```

M5 Loop 优化报告：

```powershell
.venv\Scripts\python.exe -m loop_optimizer.run_loop
```

README 校验：

```powershell
.venv\Scripts\python.exe scripts\verify_readme.py
```

## 文档

- 架构说明：`docs/architecture.md`
- API 文档：`docs/api_doc.md`
- 演示指南：`docs/demo_guide.md`
- 简历量化点：`docs/resume_point.md`
- 使用说明：`使用说明书.md`
- M4 结果：`harness_test/results/m4_summary.json`
- M5 输出：`loop_optimizer/output/`

## 当前量化结果

- pytest 全量 harness：以当前 checkout 执行“自检命令”中的全量命令为准；最近一次发布前证据记录在对应验收报告中，README 不固化易过期的用例数。
- M4 50 并发：QPS `73.811`，P95 `1000 ms`，失败率 `0.0%`
- M4 100 并发：QPS `74.8723`，P95 `2000 ms`，失败率 `0.0%`
- M5 Loop：`bad_sample.csv`、`optimize_report.md`、`prompt_diff.md` 已生成，脚本不自动修改线上 Prompt。

## M1 RAG 当前状态

- loader：已支持 PDF、`.docx`、`.doc` 转换兜底、表格 Markdown 化、插图 OCR / EMF 文本抽取。
- chunker：表格块和插图块保持完整语义边界，长文本按窗口切分。
- embed_loader：默认使用本地 `PROJECT_ROOT / models / bge-base-zh-v1.5`，可通过 `BGE_MODEL_PATH` 覆盖；维度校验为 768。
- vector_store：单 Chroma，本地持久化到 `datas/chroma`，异常时保留关键词兜底。
- reranker：`models\bge-reranker-base` 已就位；`smoke_test` 会设置 `RERANKER_ENABLED=true` 并验证 Top-1 重排探针。
- VLM：`models\qwen2.5-vl` 本地权重已就位，加载配置包含 `load_in_4bit=True`；当前 `.venv` 已安装 `bitsandbytes`，真实 VLM 加载和图片描述链路可用。若后续环境缺少 4-bit 依赖，插图语义会回退为 PaddleOCR 文本。

M1 验证命令：

```powershell
.venv\Scripts\python.exe -m agent_server.rag.smoke_test
.venv\Scripts\python.exe -m pytest harness_test\test_m1_rag.py -q
```
