# 系统架构

Knowledge Agent 采用三层解耦：主服务、前端演示、测试与优化闭环。业务数据、制度文档、Embedding、向量库、OCR 都在本机运行；只有 LLM 生成层通过环境变量配置云端 API。

```mermaid
flowchart LR
    User["员工 / 管理员"] --> Web["Streamlit 前端\nweb/app.py"]
    Web --> API["FastAPI 主服务\nagent_server/main.py"]

    API --> Auth["Auth / RBAC\ncore/auth.py\ncore/rbac.py"]
    API --> Chat["Chat API + SSE\napi/chat_router.py"]
    API --> Ticket["Ticket API\napi/ticket_router.py"]
    API --> Knowledge["Knowledge API\napi/knowledge_router.py"]
    API --> Tool["Tool Router\napi/tool_router.py"]

    Chat --> Graph["LangGraph 风格编排\ngraph_flow/graph_builder.py"]
    Graph --> Tools["业务工具\ntools/business_tools.py"]
    Tools --> RAG["RAG 检索链路\nretriever_pipe.py"]
    RAG --> Loader["文档解析 + OCR\nloader.py"]
    RAG --> Embedding["本地 BGE Embedding\nmodels/bge-base-zh-v1.5"]
    RAG --> Chroma["本地 Chroma\ndatas/chroma"]
    Tools --> DB["SQLite\ndatas/app.db"]
    Graph --> LLM["云端 LLM API\nkey from env"]

    Chat --> QALog["结构化问答日志\nagent_server/logs/qa_events.jsonl"]
    QALog --> Loop["Loop Optimizer\ncollector/filter/updater"]
    Loop --> Output["人工审核产物\nbad_sample.csv\noptimize_report.md\nprompt_diff.md"]

    Harness["Pytest + Locust + Allure\nharness_test"] --> API
```

## 数据流

1. 用户在 Streamlit 登录，前端保存 token 并调用 FastAPI。
2. 对话请求进入 `chat_router`，后端检查 Bearer token 和 RBAC。
3. Graph 节点执行身份检查、文档检索、历史工单匹配、LLM 决策。
4. RAG 使用本地制度文档、本地 BGE Embedding、本地 Chroma 和关键词兜底。
5. LLM 只接收检索上下文和问题，不接收数据库文件或原始文档目录。
6. 需要工单时写入 SQLite，并将工具事件通过 SSE 返回给前端。
7. 问答结果写入结构化 JSONL，M5 离线读取并生成审核建议。

## 安全边界

- `.env` 不入文档、不入日志、不入测试输出。
- 测试通过 `APP_DB_PATH`、`DATAS_DIR`、`CHROMA_DIR`、`QA_LOG_PATH` 使用临时目录。
- M5 只生成建议文件，不直接修改 `prompt_template.py`，不自动重建生产向量库。
