from __future__ import annotations

import uuid

from locust import HttpUser, between, task


class KnowledgeAgentUser(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self) -> None:
        self.username = f"u_{uuid.uuid4().hex[:16]}"
        self.password = "Passw0rd!"
        register = self.client.post(
            "/api/auth/register",
            json={"username": self.username, "password": self.password, "role": "employee"},
            name="/api/auth/register",
        )
        if register.status_code != 200:
            register.failure(f"register failed: {register.status_code}")
            return
        login = self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": self.password},
            name="/api/auth/login",
        )
        if login.status_code == 200:
            self.headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}
        else:
            login.failure(f"login failed: {login.status_code}")
            self.headers = {}

    @task(6)
    def chat(self) -> None:
        self.client.post(
            "/api/chat",
            json={"message": "差旅报销标准是什么"},
            headers=self.headers,
            name="/api/chat",
        )

    @task(2)
    def list_tickets(self) -> None:
        self.client.get("/api/tickets", headers=self.headers, name="/api/tickets")

    @task(1)
    def query_ticket_tool(self) -> None:
        self.client.post(
            "/api/tools/query_ticket_list",
            json={"mine_only": True},
            headers=self.headers,
            name="/api/tools/query_ticket_list",
        )

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="/health")
