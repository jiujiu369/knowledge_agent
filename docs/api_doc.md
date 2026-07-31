# API 文档

默认地址：`http://127.0.0.1:8000`

除 `/health`、`/api/auth/register`、`/api/auth/login` 外，接口需要：

```text
Authorization: Bearer <token>
```

统一 JSON 响应：

```json
{"code":"ok","message":"ok","data":{}}
```

错误响应会返回 `code=error` 或 `code=internal_error`。

## Health

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |

## Auth

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | 注册用户 |
| POST | `/api/auth/login` | 登录并返回 token |
| GET | `/api/auth/me` | 当前用户信息与可用工具 |
| POST | `/api/auth/change-password` | 修改当前用户密码 |
| GET | `/api/auth/admin/users` | 管理员列出用户 |
| POST | `/api/auth/admin/users` | 管理员创建用户，默认密码 `123456` |
| POST | `/api/auth/admin/users/{user_id}/reset-password` | 管理员重置密码 |
| DELETE | `/api/auth/admin/users/{user_id}` | 管理员删除用户 |

注册请求：

```json
{"username":"alice","password":"Passw0rd!","role":"employee"}
```

登录请求：

```json
{"username":"alice","password":"Passw0rd!"}
```

## Chat

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat` | 非流式问答 |
| POST | `/api/chat/stream` | SSE 流式问答和工具事件 |
| GET | `/api/chat/history` | 当前用户问答历史 |

问答请求：

```json
{"message":"差旅报销标准是什么"}
```

SSE 事件：

```text
event: tool
data: {"tool":"doc_retrieve","count":3}

event: done
data: {"answer":"...","ticket_id":1}
```

## Ticket

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/tickets` | 用户看自己的工单，管理员看全部 |
| GET | `/api/tickets/{ticket_id}` | 查询单个工单 |
| PATCH | `/api/tickets/{ticket_id}` | 更新工单状态 |

更新状态请求：

```json
{"status":"closed"}
```

## Knowledge

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/knowledge` | 管理员列出入库文档 |
| POST | `/api/knowledge/rebuild` | 管理员重建知识库索引 |
| POST | `/api/knowledge/upload` | 管理员上传 `.pdf`、`.docx`、`.doc` |

上传使用 multipart form-data，字段名为 `file`。

## Tools

统一入口：

```text
POST /api/tools/{tool_name}
```

| 工具 | 角色 | 请求 |
| --- | --- | --- |
| `doc_retrieve` | 员工/管理员 | `{"query":"差旅报销","top_k":5}` |
| `match_similar_ticket` | 员工/管理员 | `{"query":"故障处理","limit":5}` |
| `create_consult_ticket` | 员工/管理员 | `{"title":"咨询","content":"问题","answer":"答复"}` |
| `query_ticket_list` | 员工/管理员 | `{"status":"open","mine_only":true}` |
| `export_ticket_stat` | 管理员 | `{"format":"json"}` |
| `knowledge_manage` | 管理员 | `{"action":"list"}` 或 `{"action":"rebuild"}` |

越权返回 `403`，未知工具返回 `404`，参数错误返回 `422`。
