from __future__ import annotations

from io import BytesIO

from harness_test.fixture.app_client import auth_headers


def test_auth_rejects_missing_token_and_duplicate_username(api_client):
    """验证认证`rejects``missing`令牌`and``duplicate`用户名。

    :param api_client: 隔离测试环境提供的 FastAPI 测试客户端与辅助数据；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    missing = api_client.get("/api/auth/me")
    headers = auth_headers(api_client, "alice")
    duplicate = api_client.post("/api/auth/register", json={"username": "alice", "password": "Passw0rd!", "role": "employee"})

    assert headers["Authorization"].startswith("Bearer ")
    assert missing.status_code == 401
    assert duplicate.status_code == 400


def test_auth_rejects_invalid_password_shape(api_client):
    """验证认证`rejects``invalid`密码`shape`。

    :param api_client: 隔离测试环境提供的 FastAPI 测试客户端与辅助数据；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    response = api_client.post("/api/auth/register", json={"username": "bob", "password": "short", "role": "employee"})

    assert response.status_code == 422


def test_rbac_rejects_employee_admin_routes(api_client):
    """验证`rbac``rejects``employee`管理员`routes`。

    :param api_client: 隔离测试环境提供的 FastAPI 测试客户端与辅助数据；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    headers = auth_headers(api_client, "alice")

    response = api_client.get("/api/auth/admin/users", headers=headers)

    assert response.status_code == 403


def test_tool_router_reports_unknown_tool_as_404(api_client):
    """验证工具`router``reports``unknown`工具`as``404`。

    :param api_client: 隔离测试环境提供的 FastAPI 测试客户端与辅助数据；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    headers = auth_headers(api_client, "alice")

    response = api_client.post("/api/tools/not_a_tool", json={}, headers=headers)

    assert response.status_code == 404


def test_tool_router_reports_schema_errors_as_422(api_client):
    """验证工具`router``reports`数据结构`errors``as``422`。

    :param api_client: 隔离测试环境提供的 FastAPI 测试客户端与辅助数据；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    headers = auth_headers(api_client, "alice")

    response = api_client.post("/api/tools/doc_retrieve", json={"query": "差旅", "top_k": 99}, headers=headers)

    assert response.status_code == 422


def test_chat_rejects_blank_message(api_client):
    """验证处理对话`rejects``blank`消息。

    :param api_client: 隔离测试环境提供的 FastAPI 测试客户端与辅助数据；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    headers = auth_headers(api_client, "alice")

    response = api_client.post("/api/chat", json={"message": "   "}, headers=headers)

    assert response.status_code == 422


def test_knowledge_upload_rejects_unsupported_file(api_client):
    """验证知识库上传`rejects``unsupported`文件。

    :param api_client: 隔离测试环境提供的 FastAPI 测试客户端与辅助数据；类型由调用方及当前处理场景决定。
    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    admin_headers = auth_headers(api_client, "root", role="admin")

    response = api_client.post(
        "/api/knowledge/upload",
        files={"file": ("bad.txt", BytesIO(b"bad"), "text/plain")},
        headers=admin_headers,
    )

    assert response.status_code == 400
