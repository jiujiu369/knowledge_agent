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

## 当前可用状态

- 后端 API：`/health` 可正常返回 `{"status":"ok"}`。
- 云端 LLM：`.env` 配置的 Ark/Agnes OpenAI 兼容接口可用；客户端已禁用系统代理继承。
- 本地 VLM：`models/qwen2.5-vl/` 权重、`bitsandbytes`、4-bit 加载链路已打通，可用于插图语义增强。
- 本地 RAG：BGE Embedding、Chroma、PaddleOCR、reranker 均按本地链路运行。

## 环境

- 项目路径：`F:\code\knowledge_agent`
- Python：`F:\code\knowledge_agent\.venv\Scripts\python.exe`
- 固定版本：Python 3.12.9
- 本项目以本地运行为主，不部署云端。

检查版本：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe --version
```

## 本地启动

启动后端：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m uvicorn agent_server.main:app --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m streamlit run web/app.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false
```

本地启动器：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe web/local_launcher.py
```

访问地址：

- 后端健康检查：`http://127.0.0.1:8000/health`
- 后端 Swagger：`http://127.0.0.1:8000/docs`
- 前端页面：`http://localhost:8501`

## 首次演示账号

系统不内置固定管理员账号。首次演示时先注册管理员：

```powershell
curl -X POST http://127.0.0.1:8000/api/auth/register -H "Content-Type: application/json" -d "{\"username\":\"admin_demo\",\"password\":\"Passw0rd!\",\"role\":\"admin\"}"
```

然后在前端使用 `admin_demo / Passw0rd!` 登录。管理员可以创建普通用户，默认密码为 `123456`。

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
F:\code\knowledge_agent\.venv\Scripts\python.exe -c "from fastapi.testclient import TestClient; from agent_server.main import app; r=TestClient(app).get('/health'); print(r.status_code, r.text)"
```

云端 LLM 连通性：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -c "from agent_server.core.llm_client import chat_completion; print(chat_completion([{'role':'user','content':'只回复 OK'}], temperature=0))"
```

本地 VLM 状态：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -c "from agent_server.rag.loader import vlm_status; import json; print(json.dumps(vlm_status(), ensure_ascii=False, indent=2))"
```

RAG 冒烟：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m agent_server.rag.smoke_test
```

后端冒烟：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m agent_server.smoke_test
```

Harness 测试：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m pytest harness_test -q
```

M4 测试与短压测：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe run_harness.py --stress-duration 10s
```

M5 Loop 优化报告：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m loop_optimizer.run_loop
```

README 校验：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe scripts\verify_readme.py
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

- pytest 全量 harness：`52 passed, 1 skipped`
- M4 50 并发：QPS `73.811`，P95 `1000 ms`，失败率 `0.0%`
- M4 100 并发：QPS `74.8723`，P95 `2000 ms`，失败率 `0.0%`
- M5 Loop：`bad_sample.csv`、`optimize_report.md`、`prompt_diff.md` 已生成，脚本不自动修改线上 Prompt。

## M1 RAG 当前状态

- loader：已支持 PDF、`.docx`、`.doc` 转换兜底、表格 Markdown 化、插图 OCR / EMF 文本抽取。
- chunker：表格块和插图块保持完整语义边界，长文本按窗口切分。
- embed_loader：固定使用本地 `F:\code\knowledge_agent\models\bge-base-zh-v1.5`，维度校验为 768。
- vector_store：单 Chroma，本地持久化到 `datas/chroma`，异常时保留关键词兜底。
- reranker：`models\bge-reranker-base` 已就位；`smoke_test` 会设置 `RERANKER_ENABLED=true` 并验证 Top-1 重排探针。
- VLM：`models\qwen2.5-vl` 本地权重已就位，加载配置包含 `load_in_4bit=True`；当前 `.venv` 已安装 `bitsandbytes`，真实 VLM 加载和图片描述链路可用。若后续环境缺少 4-bit 依赖，插图语义会回退为 PaddleOCR 文本。

M1 验证命令：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m agent_server.rag.smoke_test
F:\code\knowledge_agent\.venv\Scripts\python.exe -m pytest harness_test\test_m1_rag.py -q
```
