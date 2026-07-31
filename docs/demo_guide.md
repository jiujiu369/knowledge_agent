# 本地演示指南

## 1. 准备环境

确认虚拟环境：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe --version
```

应输出 `Python 3.12.9`。

复制 `.env.example` 为 `.env`，只填写本机环境变量需要的 LLM key。不要把真实 key 写入文档、代码或截图。

## 2. 启动服务

方式一：本地启动器。

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe web/local_launcher.py
```

方式二：手动启动。

后端：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m uvicorn agent_server.main:app --host 127.0.0.1 --port 8000
```

前端：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m streamlit run web/app.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false
```

访问：

- 后端：`http://127.0.0.1:8000/docs`
- 前端：`http://localhost:8501`

## 3. 创建管理员账号

项目不内置固定管理员账号。首次演示先调用注册接口：

```powershell
curl -X POST http://127.0.0.1:8000/api/auth/register -H "Content-Type: application/json" -d "{\"username\":\"admin_demo\",\"password\":\"Passw0rd!\",\"role\":\"admin\"}"
```

在前端登录：

- 账号：`admin_demo`
- 密码：`Passw0rd!`

## 4. 管理员流程

1. 进入“账号”页，创建普通员工账号，默认密码为 `123456`。
2. 进入“上传”页，上传 PDF 或 Word 制度文档。
3. 点击上传并入库，后端会写入 `datas/` 并重建本地 Chroma。
4. 进入“工单”页，可查看全部工单、导出统计、更新状态。

## 5. 员工问答流程

1. 使用管理员创建的员工账号登录。
2. 进入“对话”页，输入制度问题，例如“差旅报销标准是什么”。
3. 前端展示工具事件：身份确认、知识库检索、历史工单匹配、LLM 决策、工单创建。
4. 若后端判断需要跟进，会自动创建咨询工单。
5. 进入“对话记录”查看历史问答，进入“工单”查看自己的工单。

## 6. Loop 优化流程

问答完成后，后端会写入结构化日志：

```text
agent_server/logs/qa_events.jsonl
```

生成半自动优化产物：

```powershell
F:\code\knowledge_agent\.venv\Scripts\python.exe -m loop_optimizer.run_loop
```

输出：

- `loop_optimizer/output/bad_sample.csv`
- `loop_optimizer/output/optimize_report.md`
- `loop_optimizer/output/prompt_diff.md`

该流程只生成建议，不自动修改线上 Prompt。
