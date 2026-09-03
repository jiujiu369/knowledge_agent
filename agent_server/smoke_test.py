from __future__ import annotations

import sys
import time

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from agent_server.core.auth import register_user
from agent_server.main import app


def main() -> None:
    """执行当前模块的主流程并协调各项处理步骤。

    :return: 无返回值；函数通过副作用、断言或异常完成其职责。
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()

    client = TestClient(app)
    suffix = str(int(time.time()))
    employee = f"emp_{suffix}"
    admin = f"admin_{suffix}"
    password = "Passw0rd!"

    print("M2 smoke: register employee")
    r = client.post("/api/auth/register", json={"username": employee, "password": password, "role": "employee"})
    assert r.status_code == 200, r.text

    print("M2 smoke: login employee")
    r = client.post("/api/auth/login", json={"username": employee, "password": password})
    assert r.status_code == 200, r.text
    employee_token = r.json()["data"]["token"]
    employee_headers = {"Authorization": f"Bearer {employee_token}"}

    print("M2 smoke: unauth ticket query -> 401")
    r = client.get("/api/tickets")
    assert r.status_code == 401, r.text

    print("M2 smoke: chat question -> ticket")
    r = client.post("/api/chat", json={"message": "技术故障怎么处理，请创建咨询工单"}, headers=employee_headers)
    assert r.status_code == 200, r.text
    chat_data = r.json()["data"]
    assert chat_data["ticket_id"], r.text
    assert chat_data["guardrail"]["risk_score"] >= 0
    print(f"ticket_id={chat_data['ticket_id']}")

    print("M2 smoke: query ticket list")
    r = client.get("/api/tickets", headers=employee_headers)
    assert r.status_code == 200, r.text
    assert any(item["id"] == chat_data["ticket_id"] for item in r.json()["data"]["items"])
    print(f"ticket_count={len(r.json()['data']['items'])}")

    print("M2 smoke: employee export forbidden -> 403")
    r = client.post("/api/tools/export_ticket_stat", json={}, headers=employee_headers)
    assert r.status_code == 403, r.text

    print("M2 smoke: register/login admin")
    register_user(admin, password, "admin")
    r = client.post("/api/auth/login", json={"username": admin, "password": password})
    assert r.status_code == 200, r.text
    admin_headers = {"Authorization": f"Bearer {r.json()['data']['token']}"}

    print("M2 smoke: admin export ticket stat")
    r = client.post("/api/tools/export_ticket_stat", json={}, headers=admin_headers)
    assert r.status_code == 200, r.text
    print(f"ticket_stat_total={r.json()['data']['total']}")

    print("M2 smoke: admin knowledge manage list")
    r = client.post("/api/tools/knowledge_manage", json={"action": "list"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    print("knowledge_manage=ok")

    print("✅ M2 自检通过")


if __name__ == "__main__":
    main()
