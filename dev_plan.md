# 企业内部知识库工单智能体 — 开发计划（实习简历项目）

> 目标：一个能端到端演示的 AI 工程化项目——员工/管理员通过网页问答企业制度、自动生成工单、管理员管知识库；背后是带重排的 RAG + LangGraph 多工具 Agent + RBAC，含完整自动化测试与半自动优化闭环。
> 周期：4 周（M0–M6），核心可压缩至 3 周保 M0–M4。
> 路径：`F:\code\knowledge_agent` ｜ Python 3.12.9（`.venv` 已建好并装齐依赖）｜ 全程中文注释。

---

## 一、当前环境状态（已就绪，无需重装）

- **Python 3.12.9**：`.venv` 已创建，全部依赖已装好（fastapi / langgraph / chromadb / sentence-transformers / paddlepaddle+paddleocr / streamlit / pytest / locust / allure-pytest 等，共 187 个包）。
  - ⚠️ 系统默认 `python`/`py` 指向 3.14，**禁止使用**；全程只用 `.venv\Scripts\` 下解释器。
- **本地 BGE Embedding**：`F:\code\knowledge_agent\models\bge-base-zh-v1.5\`（已下载，含 `pytorch_model.bin`，sentence-transformers 直接传路径加载，**禁止联网下载**）。
- **公司制度文件**：`F:\code\knowledge_agent\datas\`（7 份 PDF + 1 份 `IDC运维管理手册.docx`，原 `.doc` 已转新格式）。
- **向量库 / SQLite**：分别落在 `datas/chroma/`、`datas/app.db`（loader 扫描 `datas/` 时忽略这两个）。
- **依赖清单**：根目录单一 `requirements.txt`（唯一来源，已存在，禁止改动或重建）。
- **未就位资源**：BGE-Reranker 本地权重、VLM 本地权重均**暂缺**，按下方「占位 + 开关 + TODO」处理。

---

## 二、已定关键决策（硬约束）

| # | 决策 | 说明 |
|---|---|---|
| 1 | 单 Chroma + 异常兜底 | 禁止双向量库主备 |
| 2 | SQLite 持久化 | 用户/工单/文档落库，禁止 JSON 文件持久化 |
| 3 | Streamlit 轻量前端 | 登录 / 对话(SSE) / 工单 / 上传 |
| 4 | RAG 链路 | 向量检索 → (启用时)BGE-Reranker 重排 → 关键词兜底 → 相似度阈值过滤 |
| 5 | Loop 半自动 | 只产出建议报告(diff)，不直接改线上 Prompt，需人审 |
| 6 | 幻觉防护=规则护栏 | 比对工单号/金额/条款与检索内容，不声称模型级检测 |
| 7 | 代码可运行 | 每里程碑给验收命令 + 冒烟脚本 |
| 8 | 本地模型走本地路径 | BGE 强制本地加载，禁自动下载/云 API；Reranker 无权重则占位+TODO |
| 9 | 每里程碑自检 | 实际跑通验收 + 最小冒烟，报错就地修复再宣告完成 |
| 10 | 禁自行 pip install | 依赖已装好，遇 ImportError 停手报告用户 |
| 11 | 固定 Python 3.12.9 | 所有命令走 `.venv\Scripts\`，禁系统 python/py |

---

## 三、目录结构

```
F:\code\knowledge_agent\
├── common/                  # 跨模块基础
│   ├── models/              # Pydantic: User / Ticket / Doc / RetrievalResult
│   ├── constants.py         # 角色权限映射、RAG 阈值、限流参数
│   ├── logger_base.py       # 统一日志（按天分割）
│   ├── file_utils.py        # 文件锁 / IO 工具
│   ├── exception.py         # 全局异常 + 错误码
│   └── config_base.py       # 环境变量读取
├── agent_server/            # 主服务
│   ├── core/                # auth(PBKDF2) / rbac / db(SQLite) / config
│   ├── rag/                 # loader / chunker / embed_loader / vector_store / reranker / retriever_pipe
│   ├── tools/               # schemas + 6 个业务 Tool
│   ├── graph_flow/          # state / prompt_template / graph_nodes / graph_builder
│   ├── api/                 # auth_router / chat_router(SSE) / ticket_router / knowledge_router
│   ├── logs/                # 运行日志（Loop 读取源）
│   └── main.py              # FastAPI 入口
├── web/                     # Streamlit 前端
├── harness_test/           # func / edge / stress + allure + run_harness.py
├── loop_optimizer/         # collector / filter / updater(半自动) / output / run_loop.py
├── docs/                    # 架构/API/演示/resume_point + screenshots/
├── datas/                   # 公司制度 PDF/.docx（你放置）+ chroma/ + app.db
├── models/                  # bge-base-zh-v1.5/（已就位）+ reranker/、qwen2.5-vl/（可选）
├── scripts/                 # freshman_run.sh / verify_readme.py
├── requirements.txt         # 单一依赖清单（已存在）
├── .gitignore               # 排除 .venv/ datas/chroma/ datas/app.db *.pyc .env web/uploads/ ...
└── README.md
```

---

## 四、里程碑计划（M0→M6，每步独立可跑）

### M0 脚手架与环境
- **任务**：创建目录骨架；根 `requirements.txt` 已存在勿改；`common/` 基础模块；`main.py` 起 FastAPI + `/health`；`.gitignore`。
- **验收（自检必跑，顺序不可跳）**：
  1. 激活 `.venv`，`python -c "import fastapi,uvicorn,langchain,langgraph,chromadb,sentence_transformers,paddleocr,streamlit,pytest"` 全绿（ImportError 则停手报用户，**禁 pip install**）。
  2. `cd agent_server && uvicorn main:app --reload` → `/docs` 可访问，`/health` 返回 `{"status":"ok"}`。
  3. 根目录 `python -c "import common.*"` 无 ImportError。
- **交付**：骨架 + 起服成功截图 + 命令末 20 行输出。

### M1 RAG 核心跑通 ★ 最高优先级
- **任务**（`agent_server/rag/`）：
  - `loader.py` 图文混排抽取：PDF(PyMuPDF/pdfplumber) + .docx(python-docx)；**表格结构化**（抽成 Markdown「列:值」保留行列语义）；**插图抽取 + 本地 PaddleOCR**（必做，免费，禁联网）并入 `[插图内容:…]`；VLM 语义描述（可选，有 `models/qwen2.5-vl/` 才启用）；意外 `.doc` 走 soffice 转换兜底。
  - `chunker.py`：默认 size=500/overlap=50，表格块/插图块保留完整语义边界。
  - `embed_loader.py`：本地 BGE **显式传路径 `models/bge-base-zh-v1.5`**，禁下载，输出 768 维，单例懒加载。
  - `vector_store.py`：单 Chroma（`datas/chroma/`），增量/单文档更新/全量重建 + 异常兜底（崩了走关键词检索）。
  - `reranker.py`：BGE-Reranker **占位 + 开关**，无本地权重则禁用 + TODO。
  - `retriever_pipe.py`：向量检索 → rerank(启用时) → 关键词兜底(BM25) → 阈值过滤，暴露 `retrieve(query, top_k=5)`。
- **验收**：PaddleOCR 依赖已装（首次运行才会自动下几百 MB 中文字体，本地免费仅一次）；读取 `datas/` 入库后验证：(a) 文本/表格提问返回含答案片段；(b) reranker 就位才验证 Top-1 提升，否则跳过+TODO；(c) 低相似走兜底/无结果；(d) 含插图提问能返回 PaddleOCR 文字。**冒烟** `python -m agent_server.rag.smoke_test` 一次跑通，输出入库条数(含表格/插图块计数)+3 条提问 Top-3。

### M2 Agent 主服务
- **任务**：`auth`(PBKDF2) / `rbac`(角色→工具集，越权 403) / `db`(SQLite `datas/app.db`，连接池/事务) / `tools`(6 个：doc_retrieve、match_similar_ticket、create_consult_ticket、query_ticket_list、export_ticket_stat-管理员、knowledge_manage-管理员) / `graph_flow`(6 节点有向图，多轮工具循环+分支) / `api`(auth/chat-SSE/ticket/knowledge + 全局异常处理+限流+输入校验)。
- **验收**：注册员工→登录→提问触发 doc_retrieve→自动建工单→`query_ticket_list` 可见；管理员可 export/knowledge_manage，员工调 export 返回 403。**冒烟** `python -m agent_server.smoke_test` 跑通「注册→登录→提问→查工单」并断言 200/401/403；`curl -N` 看 SSE 事件流。

### M3 Streamlit 前端
- **任务**：登录页(token) / 对话页(SSE 打字机+实时工具过程) / 工单列表页 / 文档上传页。前端只调 API 不直连向量库，加 loading 态。
- **验收**：`streamlit run web/app.py` 无报错；`python -m web.smoke_test` 用 requests 打 4 类接口断言；截图存 `docs/screenshots/`（登录/对话/工单/上传）。

### M4 Harness 自动化测试 ★ 最强差异点
- **任务**：`fixture`(mock 用户/文档/临时向量库隔离) / `case/func`(auth/rbac/rag/tools/graph/api) / `case/edge`(坏输入/LLM异常/损坏文件) / `case/stress`(Locust 50/100 并发) / `run_harness.py` 一键 func+edge+短压测+allure。
- **验收**：pytest 全绿；locust 输出 QPS/P95/失败率；`run_harness.py` 退出码 0；**真实数字回填** `docs/resume_point.md`（覆盖 TBD）。测试隔离，不污染 `datas/chroma` 与 `datas/app.db`。
- ⚠️ `locust` 在已加载 ssl 的交互 shell 里 `import` 会 RecursionError（gevent 冲突），但 **CLI 入口正常**；压测用 `locust` 命令即可，脚本内避免直接 import。

### M5 Loop 半自动闭环
- **任务**：`collector`(读日志抽三类样本：低匹配/高幻觉[风险>0.3]/高频问) / `filter`(去重标注) / `updater`(半自动：**只产出**向量库优化建议 + `prompt_diff.md`) / `output`(bad_sample.csv + optimize_report.md + prompt_diff.md) / `run_loop.py`。
- **验收**：跑若干问答产生日志后 `python loop_optimizer/run_loop.py` 一次生成 3 文件且非空；**哈希校验**线上 Prompt 文件未被改动。严禁脚本直改线上 Prompt 或自动重建生产向量库。

### M6 文档 / 演示 / 容器化
- **任务**：`docs/`(architecture mermaid / api_doc / demo_guide / resume_point 真实数字) / `README.md`(明确写「全栈本地零 API 成本/数据本地不上云」) / `docker-compose.yml`(可选，基础镜像 python:3.11-slim) / `scripts/freshman_run.sh` + `verify_readme.py`。
- **验收**：干净 venv 下 `freshman_run.sh` 10 分钟跑通「装依赖→起后端→起前端→上传→提问命中」；`verify_readme.py` 校验 README 命令/路径/截图真实存在。

---

## 五、执行与发送约定

- **方式**：按 M0→M6 顺序，每个里程碑**开一个新 Codex 会话**，只复制对应 M 代码块发送（块内已按需内置所需约束，无需另贴共用约束段）。
- **每步先跑验收 + 冒烟**，看 Codex 贴的「自检末 20 行」确认绿了再进下一步；失败要求它就地修复重跑。
- **若 Codex 想加双库/JSON/自动改 Prompt/调云端 Embedding**，引用决策 1/2/5/8 驳回。

---

## 六、风险与边界（面试如实表述）

- **Reranker / VLM 暂缺**：当前仅 bge-base 就位；重排与多模态描述按计划为「占位+开关」，权重就位后再启用。简历写「RAG 重排设计 + 本地可插拔」，不要声称已跑通重排效果。
- **流程图插图**：PaddleOCR 抽到节点文字可检索，但箭头/上下游关系语义无法 100% 还原；精确流程问答建议同时在制度文档里补充「步骤化文字」。
- **规则护栏 ≠ 模型级幻觉检测**：是轻量规则比对，降低风险分而非消除幻觉。
- **半自动闭环**：优化建议需人审手动合并，非生产自动调参。

---

## 七、简历落点（量化指标待 M4 回填）

- 工程化三层解耦（主服务 / Harness 测试 / Loop 闭环）+ 完整自动化测试与 Allure 报告。
- RAG：本地 BGE + Chroma + 关键词兜底 + 重排可插拔 + 图文混排抽取（表格结构化 + 插图 OCR）。
- Agent：LangGraph 多节点编排、多轮工具循环、6 业务 Tool、RBAC 越权拦截。
- 量化数字占位：QPS、P95、测试覆盖率、RAG 命中率（M4 压测后填实）。
- 半自动迭代闭环：低质量样本自动归集 + 人审优化建议，体现 MLOps 思维。
