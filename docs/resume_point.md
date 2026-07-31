# 简历量化点

## 项目一句话

基于 FastAPI + Streamlit + 本地 RAG + LangGraph 风格编排的企业内部知识库工单智能体，支持制度问答、自动工单、RBAC、压测和半自动 Loop 优化。

## 工程化亮点

- 三层解耦：`agent_server/` 主服务、`web/` 前端、`harness_test/` 测试闭环、`loop_optimizer/` 半自动优化。
- 数据本地不上云：制度文档、SQLite、Chroma、Embedding、OCR 均在本机运行。
- LLM key 走环境变量，只有生成层调用云端 API。
- RBAC 覆盖员工和管理员：管理员可管理知识库、账号、全部工单；员工只能访问自己的问答和工单。
- M5 Loop 从结构化问答日志抽取低匹配、高幻觉风险、高频问题，输出人工审核建议，不自动改线上 Prompt。

## M4 压测结果

数据来自 `harness_test/results/m4_summary.json`，命令为：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe run_harness.py --stress-duration 10s
```

| 并发 | 请求数 | QPS | P95 | 失败率 |
| --- | ---: | ---: | ---: | ---: |
| 50 | 668 | 73.811 | 1000 ms | 0.0% |
| 100 | 676 | 74.8723 | 2000 ms | 0.0% |

## 测试结果

- M4 交付时：`pytest harness_test -q` 为 `36 passed`。
- M5 后全量：`pytest harness_test -q` 为 `41 passed`。
- `run_harness.py` 覆盖 func + edge + Locust 50/100 短压测 + Allure 结果。
- 测试隔离使用临时 DB、临时 Chroma、mock LLM，避免污染 `datas/app.db` 和 `datas/chroma`。

## RAG 命中情况

RAG 冒烟脚本为：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m agent_server.rag.smoke_test
```

脚本覆盖 3 个代表性问题：

- 差旅报销上限
- 新员工转正条件
- 技术故障处理流程分支

脚本输出每个问题的 Top-3 检索片段、score 和 source，并验证低相关问题走兜底或无结果。当前未把命中率写成百分比，避免编造未统计指标。

## 可写入简历的表述

- 搭建企业制度知识库智能体，基于本地 BGE Embedding + Chroma + BM25 兜底实现 RAG 检索，制度数据不出本机。
- 设计 FastAPI + Streamlit 演示链路，支持 SSE 工具事件可视化、自动创建咨询工单和管理员工单流转。
- 建立 Pytest + Locust + Allure 测试闭环，50/100 并发短压测失败率 0.0%，QPS 约 74。
- 实现半自动 Loop 优化模块，从问答日志归集低质量样本并生成 `prompt_diff.md`，坚持人审后生效。
