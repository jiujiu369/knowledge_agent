# Codex 执行提示词集（企业内部知识库工单智能体）

> 用途：本文件是把项目计划转成的分步执行提示词，按 M0→M6 逐个复制代码块发送，每步独立可跑、跑通自检后再进下一步。**各 M 代码块已自包含，Codex 无需读取任何外部计划文档。**
>
> **发送方式（省 token / 防上下文丢失）**：每个 M 代码块已「按需内置其所需约束」，新会话只需复制对应 M 代码块单独发送即可，**无需再粘贴顶部 §0 共用约束**。
>
> 路径：`F:\code\knowledge_agent` ｜ Python 3.12.9（已建 `.venv` 并装好全部依赖）｜ 全程中文注释
>
>
>
> **自检规则（每个里程碑必做，Codex 报告完成前必须先跑通）**
> 每个 M 完成后，Codex 必须在终端跑一遍验收 + 自检命令，确认程序能**真正启动 / 导入 / 跑通最小冒烟**，任何 ImportError、启动失败、命令行报错都必须就地修复后再宣告完成。失败时输出失败摘要与修复 diff，不得跳过。

---

## 0. 共用约束（参考总表；各 M 提示词已按需内置其所需条目，发送时无需再附本段）

1. 向量库只用**单个 Chroma** + 异常兜底，**禁止双库主备**。
2. 业务数据（用户/工单/文档）用 **SQLite** 持久化，**禁止 JSON 文件持久化**。
3. 必须提供 **Streamlit** 轻量前端（登录 / 对话 SSE / 工单 / 上传）。
4. RAG 链路：**向量检索 → BGE-Reranker 重排 → 关键词兜底 → 相似度阈值过滤**。
5. **Loop 闭环只产出建议报告，不直接改写线上 Prompt**（需人审）。
6. 幻觉防护 = **规则护栏**（比对工单/金额/条款与检索内容），不声称模型级检测。
7. 代码必须可运行，每个里程碑给出验收命令。
8. **本地模型走本地路径**：BGE Embedding 强制从 `F:\code\knowledge_agent\models\bge-base-zh-v1.5\` 加载，**禁止 sentence-transformers 自动下载**，**禁止调用任何云端 Embedding/重排 API**；Reranker 若暂无本地权重则先以「占位 + 开关」实现并打 TODO，等本地权重就位再启用。
9. **每里程碑结束前必须自检可运行**：在终端实际跑通验收命令 + 最小冒烟（服务能起 / 模块能导入 / 关键函数能返回结果），任何报错必须就地修复后再宣告完成，并在里程碑交付摘要里附上自检命令与输出截图/日志。
10. **依赖已预装，禁止自行 pip install**：全部第三方库已在 `.venv` 装好。Codex 运行命令前先激活 `.venv`；若遇 `ImportError` 确需新包，**立即停下报告用户**，严禁擅自 `pip install`（避免误装到系统 Python、触发联网下载或版本冲突）。
11. **全程固定 Python 3.12.9（即 `.venv` 内的解释器）**：所有 `python` / `pytest` / `uvicorn` 命令都必须走 `.venv\Scripts\` 下的可执行文件；严禁使用系统 PATH 里的 `python` 或 `py`（默认 3.14）。Codex 每次启动新命令前先确认解释器版本为 3.12.x（`python --version` 应为 3.12.9）。

---

## M0 提示词（脚手架与环境）

```
在 F:\code\knowledge_agent 初始化项目脚手架，目标：FastAPI 服务能起、/docs 可访问。

任务：
1. 创建以下目录骨架（无需读取任何外部文档，按此直接建）：
   - common/（含 models/、constants.py、logger_base.py、file_utils.py、exception.py、config_base.py）
   - datas/（公司制度 PDF/.docx 源文件 + chroma/ 向量库子目录 + app.db；注意：用户直接放置 PDF/.docx，向量库落在 datas/chroma/，SQLite 落在 datas/app.db）
   - agent_server/（core/、rag/、tools/、graph_flow/、api/、logs/）
   - web/、harness_test/、loop_optimizer/、docs/、scripts/
2. 根目录 `requirements.txt` 已由用户预创建（全部依赖合并，单一来源）。**不要重建或改动它**；依赖已在 `.venv` 装好，本阶段无需安装。
3. common/ 基础模块：models/（Pydantic: User/Ticket/Doc/RetrievalResult）、constants.py（角色权限映射、RAG 阈值、限流参数）、logger_base.py（统一日志、按天分割）、file_utils.py（文件锁 / IO 工具，如安全读写、路径规范化）、exception.py（全局异常+错误码）、config_base.py（环境变量读取）。
4. agent_server/main.py：FastAPI 实例 + 一个 /health 接口；agent_server/core/config.py **按以下 LLM 规格实现**（OpenAI 兼容协议）：
   - base_url：`https://apihub.agnes-ai.com/v1`
   - model：`agnes-2.0-flash`
   - **API Key 必须从环境变量 `AGNES_API_KEY` 读取**（用 `python-dotenv` 加载 `.env`），**严禁在代码、注释、注释示例、日志、报错信息中硬编码或打印任何 key**。**采用惰性加载**：`config.py` 仅在真正发起 LLM 请求时（M2+ 的 graph_nodes LLM 决策节点）才读取并校验 key，缺失才抛清晰异常；**M0 起服务（/health）不应因缺少 key 而失败**，禁止在模块导入阶段强求 key。
   - 默认参数：temperature=0.2、stream=True（与 SSE 流式对齐），其它参数走 OpenAI SDK 默认。
5. 在仓库根创建 `.env.example`（提交进 git，给 Codex/新人参考用），含三行模板：`AGNES_API_KEY=<your-key-here>`、`AGNES_BASE_URL=https://apihub.agnes-ai.com/v1`、`AGNES_MODEL=agnes-2.0-flash`；并在 README 说明「把 `.env.example` 复制为 `.env` 并填入真实 key」。
6. .gitignore 必须包含：.venv/、datas/chroma/、datas/app.db、__pycache__/、*.pyc、**.env**、**.env.*（但保留 `.env.example`）**、web/uploads/、harness_test/report/*/allure-results/。

验收（自检必跑，顺序不可跳）：
- 第 1 步（确认依赖，不安装）：激活已存在的 `.venv`，运行 `python -c "import fastapi, uvicorn, langchain, langgraph, chromadb, sentence_transformers, paddleocr, streamlit, pytest"` 应全部成功；若任一 ImportError，**停止并报告用户，严禁自行 pip install**。
- 第 2 步（起服务）：在已激活的 `.venv` 中 `cd agent_server && uvicorn main:app --reload`，访问 http://127.0.0.1:8000/docs 返回 OpenAPI 页面，/health 返回 {"status":"ok"}。
- 第 3 步（模块导入）：在仓库根目录 `python -c "import common.models, common.constants, common.logger_base, common.file_utils, common.exception, common.config_base"`，全部无 ImportError。
- 把第 1–3 步的命令与输出末 20 行贴到本里程碑交付摘要里；任一步失败必须就地修复再宣告 M0 完成。

约束（本里程碑强制，其余同理）：
- 向量库只用单个 Chroma + 异常兜底，禁止双库主备。
- 业务数据用 SQLite 持久化，禁止 JSON 文件持久化。
- BGE Embedding 强制从本地路径 F:\code\knowledge_agent\models\bge-base-zh-v1.5\ 加载，禁止自动下载、禁止调用云端 Embedding/Rerank API（M0 阶段不强制加载模型，仅占位）。LLM 生成层允许走云端 API（Agnes，OpenAI 兼容协议），但 key 一律从 `AGNES_API_KEY` 环境变量读取，严禁硬编码或打印；**config 惰性加载，M0 起服务不依赖 key 是否就位**。
- 每个里程碑结束前必须自检可运行：实际跑通验收+冒烟，报错就地修复再宣告完成。
- 环境：`.venv`（Python 3.12.9，依赖全装好）已就位；激活后跑命令，禁 pip install、禁系统 python/py（默认 3.14）。
```

---

## M1 提示词（RAG 核心跑通）★ 最高优先级

```
在 F:\code\knowledge_agent/agent_server/rag 实现 RAG 核心链路，目标：用 F:\code\knowledge_agent\datas 下的公司制度文件能对任意提问返回 Top-K 相关片段，且 rerank 后相关性可见提升。文档源目录为 F:\code\knowledge_agent\datas（用户直接放置 PDF/.docx），向量库存于 F:\code\knowledge_agent\datas\chroma，loader 扫描该目录时忽略 chroma/ 子目录与 app.db。

任务：
1. loader.py（图文混排抽取）：
   - 文本：PDF 用 PyMuPDF/pdfplumber；.docx 用 python-docx。
   - 表格结构化（必做）：.docx / PDF 表格抽成 Markdown（| 列 | 值 |）或「列名：值」文本块，保留行列语义，避免拍平丢信息。
   - 插图抽取 + OCR（必做，本地免费）：从 .docx（解压 `word/media/`）与 PDF（按页提取图片）取出插图，调用本地 PaddleOCR 识别图中文字，作为带标记文本块（如 `[插图内容: 项目单位 / 技术故障 / 判断故障类型 …]`）并入文档；PaddleOCR 走本地模型、禁止联网下载。
   - 插图语义增强（可选）：若本地存在 VLM 权重（如 `F:\code\knowledge_agent\models\qwen2.5-vl/`），用其对插图生成一句话语义描述替代/补充纯 OCR 文本；未就位则跳过，打 TODO。
   - 防御性兜底：若目录中意外出现 .doc 老格式，先用 `subprocess` 调本地 `soffice --headless --convert-to docx` 尝试转换，失败打 WARN 跳过；不阻塞其他文件入库。
2. chunker.py：按可配置 size/overlap 分片（默认 size=500, overlap=50）；对表格块、插图文本块保留完整语义边界，不强行按 size 切断表格/插图描述。
3. embed_loader.py：本地加载 BGE Embedding（sentence-transformers），**显式传 model 路径 `F:\code\knowledge_agent\models\bge-base-zh-v1.5`**，禁止自动下载；验证输出 768 维。提供单例 + 懒加载，避免重复加载。
4. vector_store.py：单个 Chroma 集合（持久化目录 `F:\code\knowledge_agent\datas\chroma`），支持增量入库 / 单文档更新 / 全量重建；向量库不可用时返回友好提示且不崩服务（兜底走关键词检索）。
5. reranker.py（新增）：BGE-Reranker 占位 + 开关，默认禁用；若 `F:\code\knowledge_agent\models\bge-reranker-base/` 存在则加载，否则只暴露接口并在 README 打 TODO；禁止联网下载。
6. retriever_pipe.py：实现 向量检索 → rerank（启用时）→ 关键词兜底（BM25 或简单包含匹配）→ 相似度阈值过滤 的完整管线，对外暴露 retrieve(query, top_k=5) -> List[RetrievalResult]。

验收（自检必跑）：
- 第 0 步（确认抽取依赖，不安装）：依赖已在项目 `.venv` 预装好（含 paddlepaddle/paddleocr/jieba/rank_bm25），激活 `.venv`，确认 `python -c "import paddleocr"` 成功（本地推理不联网）。注意：PaddleOCR **首次实际运行**会自动下载中文字体模型（几百 MB，本地免费、仅一次），属正常、无需 pip 操作；若字体下载失败导致 OCR 报错，先报告用户。
- 直接读取 F:\code\knowledge_agent\datas 下的公司制度文件（含 7 份 PDF + 1 份 IDC运维管理手册.docx）写入向量库后，对典型提问（如「差旅报销上限多少」「新员工转正条件」「保密协议签订流程」「技术故障怎么处理」）验证：
  (a) 文本/表格类提问返回片段含答案；
  (b) 若本地 reranker 权重（F:\code\knowledge_agent\models\bge-reranker-base/）已就位，则启用 rerank 验证 Top-1 比未 rerank 更相关；若未就位则跳过本项并在 README 打 TODO（你当前只放了 bge-base，reranker 默认占位）。
  (c) 低相似度提问走关键词兜底或返回无结果提示；
  (d) 含插图/流程图的文档入库后，针对插图节点文字的提问（如「技术故障处理流程有哪些分支」）能返回 PaddleOCR 抽到的正确文字片段。
- 冒烟脚本 `python -m agent_server.rag.smoke_test` 必须在终端一次跑通，输出"✅ M1 自检通过"+ 每个文件的入库条数（含表格块/插图块计数）+ 3 条提问的 Top-3 结果。
- 把冒烟脚本输出贴到本里程碑交付摘要里。
- **若 M0 未建 .env.example，本阶段请补建**（含 `AGNES_API_KEY=<your-key-here>` / `AGNES_BASE_URL` / `AGNES_MODEL` 三行模板 + 可选 `LLM_EVAL_ENABLED` 开关；README 加「复制为 .env 填真实 key」一句）。

约束（本里程碑强制）：
- 向量库只用单个 Chroma + 异常兜底，禁止双库主备。
- RAG 链路：向量检索 → (启用时)BGE-Reranker 重排 → 关键词兜底 → 相似度阈值过滤。
- BGE Embedding 强制从本地路径 F:\code\knowledge_agent\models\bge-base-zh-v1.5\ 加载，禁止自动下载、禁止调用云端 API；Reranker 无本地权重则占位+开关+TODO。
- 每个里程碑结束前必须自检可运行：实际跑通验收+冒烟，报错就地修复再宣告完成。
- 环境：`.venv`（Python 3.12.9，依赖全装好）已就位；激活后跑命令，禁 pip install、禁系统 python/py（默认 3.14）。
```

---

## M2 提示词（Agent 主服务）

```
在 F:\code\knowledge_agent/agent_server 实现主业务智能体，目标：跑通「登录→提问→触发工具→工单落库」全链路。

任务：
1. core/auth.py：PBKDF2 密码哈希、注册/登录、FastAPI 依赖校验当前用户。
2. core/rbac.py：角色（普通员工/管理员）→ 可用工具集合过滤；调用越权工具返回 403。
3. core/db.py：SQLite 建表 user/ticket/doc，库文件位于 F:\code\knowledge_agent\datas\app.db，封装 CRUD（用连接池/事务，避免并发锁竞争）。
4. tools/：schemas.py（各 Tool 入参 Pydantic）+ business_tools.py（6 个 Tool：doc_retrieve、match_similar_ticket、create_consult_ticket、query_ticket_list、export_ticket_stat 仅管理员、knowledge_manage 仅管理员）。
5. graph_flow/：state.py（全局状态）、prompt_template.py（系统提示词 + 规则护栏模板）、graph_nodes.py（身份校验/并行RAG/**LLM决策（调 `core.llm_client` 中转，统一从 `AGNES_API_KEY` + `AGNES_BASE_URL` + `AGNES_MODEL` 环境变量读取，OpenAI 兼容协议，model=`agnes-2.0-flash`，默认 temperature=0.2、stream=True）**/工具执行/工单持久/结果输出节点）、graph_builder.py（有向图，支持多轮工具循环与分支跳转）。**严禁在任何 .py 文件、注释、日志、报错信息中硬编码或回显 API key；key 缺失时直接抛清晰异常并退出，绝不走静默 fallback。**
6. api/：auth_router（注册/登录/获取角色）、chat_router（普通问答 + SSE 流式，实时推送工具调用过程）、ticket_router（工单 CRUD + 管理员导出）、knowledge_router（文档上传 + 向量库运维）。全局：统一返回格式、全局异常捕获、接口限流、输入校验（超长/乱码/空白过滤）。

验收（自检必跑）：
- 用 Postman / curl / 前端完成：注册员工 → 登录拿 token → 提问触发 doc_retrieve → 自动建工单 → query_ticket_list 能看到该工单。
- 用管理员账号可 export_ticket_stat、可 knowledge_manage；普通员工调用 export_ticket_stat 返回 403。
- 冒烟脚本 `python -m agent_server.smoke_test` 必须一次跑通，自动完成「注册→登录→提问→查工单」并断言关键状态码（200/401/403）。
- uvicorn 启动后 curl /docs 返回 200，访问流式接口能用 curl -N 看到事件流。
- **LLM 真连自检**（必跑，`.env` 已就位）：在 `.venv` 内跑 `python -c "from dotenv import load_dotenv; load_dotenv(); from openai import OpenAI; c=OpenAI(api_key=__import__('os').environ['AGNES_API_KEY'], base_url=__import__('os').environ['AGNES_BASE_URL']); r=c.chat.completions.create(model=__import__('os').environ['AGNES_MODEL'], messages=[{'role':'user','content':'回复一个字: OK'}]); print('LLM_OK:', r.choices[0].message.content)"`，应输出包含 `LLM_OK:` 且内容非空。若任一环境变量缺失或返回为空，立即停下报告用户（不允许静默跳过或写假断言）。
- 把冒烟输出 + curl 截图 + LLM 真连命令末 10 行贴到本里程碑交付摘要。

约束（本里程碑强制）：
- 业务数据用 SQLite 持久化（库文件 F:\code\knowledge_agent\datas\app.db），禁止 JSON 文件持久化。
- 向量库只用单个 Chroma + 异常兜底，禁止双库主备。
- 幻觉防护 = 规则护栏（比对工单号/金额/条款与检索内容，输出风险分），不声称模型级检测。
- 代码必须可运行，本里程碑给出验收命令与冒烟脚本。
- 每个里程碑结束前必须自检可运行：实际跑通验收+冒烟，报错就地修复再宣告完成。
- 环境：`.venv`（Python 3.12.9，依赖全装好）已就位；激活后跑命令，禁 pip install、禁系统 python/py（默认 3.14）。
```

---

## M3 提示词（Streamlit 前端）

```
在 F:\code\knowledge_agent/web 实现 Streamlit 演示前端，目标：无后端基础的人也能点开即用，看到完整问答 + 工单。

任务：
1. app.py 登录页：输入账号密码 → 调用 agent_server 登录接口拿 token。
2. 对话页：调用 chat 接口（SSE 流式打字机效果），实时展示工具调用过程（如「正在检索知识库…」）。
3. 工单列表页：调用 query_ticket_list 展示当前用户工单；管理员额外显示导出按钮。
4. 文档上传页：管理员调用 knowledge_manage 上传 PDF/Word，显示入库进度。

验收（自检必跑）：
- 第 0 步（确认前端依赖，不安装）：依赖已在 `.venv` 预装好（含 streamlit/requests），激活 `.venv`，确认 `python -c "import streamlit"` 成功即可，无需重新安装。
- streamlit run web/app.py 启动后无报错；浏览器（或 streamlit headless）打开各页面截图保存到 docs/screenshots/。
- 自动化冒烟 `python -m web.smoke_test`：requests 直接打后端 4 类接口，断言状态码 + 返回结构，把输出贴交付摘要。
- 至少覆盖以下 4 个截图：登录页 / 对话页（含工具调用过程）/ 工单列表 / 上传页。

约束（本里程碑强制）：
- 必须提供 Streamlit 轻量前端（登录 / 对话 SSE / 工单 / 上传），前端只调用 API 不直连向量库。
- 每个里程碑结束前必须自检可运行：实际跑通验收+冒烟，报错就地修复再宣告完成。
- 环境：`.venv`（Python 3.12.9，依赖全装好）已就位；激活后跑命令，禁 pip install、禁系统 python/py（默认 3.14）。
```

---

## M4 提示词（Harness 自动化测试）★ 最强差异点

```
在 F:\code\knowledge_agent/harness_test 实现自动化测试，目标：功能/边界全绿 + 压测产出量化数字（写简历）。

任务：
1. fixture/：mock_user.py（模拟员工/管理员）、mock_docs/（测试用 PDF）、temp_vector_env.py（临时隔离向量库，不污染正式数据）。
2. case/func/：test_auth（哈希/登录成败/重复注册）、test_rbac（越权拦截/脱敏）、test_rag（正常检索/低相似过滤/向量库崩溃降级）、test_tools（6 工具入参/返回）、test_graph（多轮工具/分支/并行检索）、test_api（参数缺失/权限/ SSE 完整性）。
3. case/edge/：test_bad_input（超长/乱码/空白/纯表情）、test_llm_exception（401/429/5xx/超时兜底）、test_corrupt_file（损坏 PDF/空文件/超大文件）。
4. case/stress/：stress_chat.py、stress_upload.py（Locust 模拟 50/100 并发，统计 QPS/P95/失败率）。
5. report/：Allure 输出目录；run_harness.py：一键跑 func+edge+短压测。

验收（自检必跑）：
- 第 0 步（确认测试依赖，不安装）：依赖已在 `.venv` 预装好（含 pytest/locust/allure-pytest），激活 `.venv`，确认 `python -c "import pytest, locust"` 成功即可，无需重新安装。
- pytest 功能 / 边界全绿；locust 压测输出 QPS、平均耗时、P95、失败率并写入报告；allure 生成可视化报告。
- run_harness.py 必须一次跑通：func→edge→stress(短压测，30 秒即可)→allure generate，退出码 0。
- 把 pytest / locust / allure 三段输出末 20 行贴到交付摘要，并把 QPS / P95 / 测试覆盖率数字回填到 docs/resume_point.md 对应占位（用真实数字而非 TBD）。

约束（本里程碑强制）：
- 向量库只用单个 Chroma，测试必须隔离，不污染正式 F:\code\knowledge_agent\datas\chroma 与 F:\code\knowledge_agent\datas\app.db。
- 业务数据用 SQLite 持久化，禁止 JSON 文件持久化。
- **压测 / pytest 必须 mock LLM**（用 monkeypatch 或 pytest-mock 替换 `core.llm_client`，返回固定字符串），**严禁真实调用 Agnes**：50/100 并发会把你的 token 额度烧光。func/edge 用例如需 LLM 也走 mock。
- 每个里程碑结束前必须自检可运行：实际跑通 pytest/locust/allure，报错就地修复再宣告完成。
- 环境：`.venv`（Python 3.12.9，依赖全装好）已就位；激活后跑命令，禁 pip install、禁系统 python/py（默认 3.14）。
```

---

## M5 提示词（Loop 半自动闭环）

```
在 F:\code\knowledge_agent/loop_optimizer 实现半自动迭代闭环，目标：跑一次能生成可读优化建议报告，人审后手动合并。

任务：
1. collector/：log_reader.py 读 agent_server/logs 全量日志；sample_extract.py 提取三类样本（低匹配检索、高幻觉会话[风险分>0.3]、高频重复提问）。
2. filter/：data_clean.py 去重/过滤测试噪音/乱码；sample_label.py 标记问题类型（制度缺失/提示词漏洞/分片不合理）。
3. updater/（半自动，不直接改）：vector_auto_update.py 只产出「向量库优化建议」（缺失知识点/分片参数建议）；prompt_refresh.py 只产出 prompt_diff.md（针对高频幻觉追加的约束规则 diff）。
4. output/：bad_sample.csv（结构化待优化样本）、optimize_report.md（本次样本数/调整参数/预期方向）、prompt_diff.md。
5. run_loop.py：手动/可配合 crontab 启动。

验收（自检必跑）：
- 用 agent_server 跑若干次问答产生日志后，执行 `python loop_optimizer/run_loop.py`，必须一次跑通生成：
  - bad_sample.csv（≥1 行）
  - optimize_report.md
  - prompt_diff.md
- 自检脚本断言：以上 3 个文件均存在且非空；线上 Prompt 文件（agent_server/graph_flow/prompt_template.py）哈希与运行前一致（证明未被脚本改动）。
- 把生成的 3 个文件路径 + 前 20 行内容贴到交付摘要。

约束（本里程碑强制）：
- Loop 闭环只产出建议报告（bad_sample.csv / optimize_report.md / prompt_diff.md），严禁脚本直接改写线上 Prompt 或自动重建生产向量库，需人审合并。
- **LLM 评估默认关闭**：loop_optimizer 内部如需 LLM 评样本质量（替代或辅助规则打分），必须**读 `LLM_EVAL_ENABLED` env，默认 false（false 时只用规则打分，不调 LLM）**；用户显式设 `LLM_EVAL_ENABLED=true` 时才允许调用 Agnes，避免定期任务烧 token。
- 每个里程碑结束前必须自检可运行：实际跑通 run_loop.py + 哈希校验，报错就地修复再宣告完成。
- 环境：`.venv`（Python 3.12.9，依赖全装好）已就位；激活后跑命令，禁 pip install、禁系统 python/py（默认 3.14）。
```

---

## M6 提示词（文档 / 演示 / 容器化）

```
在 F:\code\knowledge_agent 补全文档与交付物，目标：新人按 README 10 分钟跑通，简历有料。

任务：
1. docs/：architecture.md（三层架构图 + 数据流，可用 mermaid）、api_doc.md（接口说明，补充 /docs 之外的业务注释）、demo_guide.md（本地完整演示步骤）、resume_point.md（简历/面试口述亮点 + 量化指标占位，从 M4 压测结果回填真实数字）。
2. README.md：项目说明、环境安装（**第一步：复制 `.env.example` 为 `.env` 并填入 `AGNES_API_KEY`，key 不要提交进 git**）、启动命令（后端+前端）、架构一句话、截图或演示 GIF 说明位置、明确写「Embedding/向量库/OCR 全本地；仅 LLM 生成层走云端（Agnes，OpenAI 兼容协议）；API Key 通过环境变量注入」。
3. docker-compose.yml：服务 + 测试环境一键起（可选加分项，基础镜像只用 python:3.11-slim，避免外部模型下载）。

验收（自检必跑）：
- 新人克隆后按 README 在 10 分钟内完成「装依赖 → 起后端 → 起前端 → 上传文档 → 提问命中」全流程：把这条 10 分钟通关脚本写进 scripts/freshman_run.sh 并在干净 venv 下跑通。
- 跑通后执行 `python scripts/verify_readme.py`（由 Codex 写一个最小校验脚本）检查 README 中所有命令 / 路径 / 截图链接真实存在。
- resume_point.md 含真实数字（从 M4 回填，不再是 TBD）。

约束（本里程碑强制）：
- Loop 闭环只产出建议报告，不直接改写线上 Prompt（半自动，需人审）；README 如实描述此点。
- 幻觉防护 = 规则护栏，不声称模型级检测；README 如实描述此点。
- 每个里程碑结束前必须自检可运行：实际跑通 freshman_run.sh + verify_readme.py，报错就地修复再宣告完成。
- 环境：`.venv`（Python 3.12.9，依赖全装好）已就位；激活后跑命令，禁 pip install、禁系统 python/py（默认 3.14）。
```

---

## 使用建议

- **首次跑通优先保 M0–M4**（核心 + 演示 + 测试差异点），M5/M6 可视时间补。
- **每发一个提示词给 Codex 后，先看它的「自检输出」**：Codex 必须实际跑通验收命令 + 冒烟脚本，输出末 20 行；自检失败 Codex 需就地修复并重跑，不得跳过。
- **每个里程碑建议开一个新 Codex 会话**：代码落在磁盘上，下一会话 Codex 直接读已有文件继续；上下文更干净。
- **若 Codex 试图引入双向量库 / JSON 持久化 / 自动改 Prompt / 调用云端 Embedding 或 Rerank**，引用共用约束 1/2/5/8 驳回。
- **LLM 仅允许走 Agnes（OpenAI 兼容协议，model=`agnes-2.0-flash`，base_url=`https://apihub.agnes-ai.com/v1`）**：key 走环境变量 `AGNES_API_KEY`，**严禁硬编码或回显**；若 Codex 想换模型/换 provider，**先停下报告用户**。
- **datas/ 现有 8 份制度文件**：7 份 PDF + 1 份 IDC运维管理手册.docx（用户已将原 .doc 转为新格式）。M1 loader 直接读 PDF + .docx，无需额外的 .doc 转换依赖。
- **依赖已预装在 `.venv`，Codex 每次只需激活它**：发任一里程碑前提醒 Codex 先 `activate .venv`；若它报 ImportError 想 `pip install`，引用共用约束 10 驳回，由你决定。
- **隐私权衡（提醒）**：LLM 生成层走云端意味着公司制度文档经由 Agnes API 出境，仅适用于演示/学习场景；生产环境请改用本地 Ollama。
