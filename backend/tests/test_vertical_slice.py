"""End-to-end tests for Milestone 1 vertical slice."""

import pytest
from app.core.models import ActionProposal, ExecutionContext, RiskLevel
from app.policy.engine import PolicyEngine


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_end_to_end_split_risk_and_approval(client):
    # Step 1: Ingest synthetic email
    payload = {
        "sender": "alice@example.com",
        "recipient": "me@example.com",
        "subject": "Sync about roadmap",
        "body": "Hi, please review the roadmap and send me a confirmation.",
    }
    ingest_res = await client.post("/api/tasks/ingest-email", json=payload)
    assert ingest_res.status_code == 200
    data = ingest_res.json()
    task_id = data["task_id"]
    # Task should pause in WAITING_APPROVAL due to Level 3 send_email proposal
    assert data["status"] == "WAITING_APPROVAL"

    # Step 2: Verify Level 2 tool (create_task) was auto-executed
    audit_res = await client.get(f"/api/audit?task_id={task_id}")
    assert audit_res.status_code == 200
    audit_logs = audit_res.json()

    create_task_logs = [
        log for log in audit_logs
        if log["tool_name"] == "create_task" and log["actor"] == "policy_auto"
    ]
    assert len(create_task_logs) == 1
    assert create_task_logs[0]["policy_decision"] == "ALLOW"

    # Step 3: Verify Level 3 tool (send_email) paused in approvals queue
    approvals_res = await client.get("/api/approvals?status=pending")
    assert approvals_res.status_code == 200
    approvals = approvals_res.json()
    task_approvals = [a for a in approvals if a["task_id"] == task_id]
    assert len(task_approvals) == 1

    pending_approval = task_approvals[0]
    assert pending_approval["tool_name"] == "send_email"
    assert pending_approval["status"] == "pending"

    # Step 4: Resolve approval with APPROVE
    approval_id = pending_approval["id"]
    resolve_res = await client.post(
        f"/api/approvals/{approval_id}/resolve",
        json={"action": "APPROVE"},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "approved"

    # Step 5: Verify task is now marked COMPLETED
    tasks_res = await client.get("/api/tasks")
    assert tasks_res.status_code == 200
    matching_tasks = [t for t in tasks_res.json() if t["id"] == task_id]
    assert len(matching_tasks) == 1
    assert matching_tasks[0]["status"] == "COMPLETED"

    # Step 6: Verify full audit trail for the approval and execution
    audit_res2 = await client.get(f"/api/audit?task_id={task_id}")
    all_logs = audit_res2.json()
    approved_exec_logs = [
        log for log in all_logs
        if log["tool_name"] == "send_email" and log["actor"] == "user_approved"
    ]
    assert len(approved_exec_logs) == 1


@pytest.mark.asyncio
async def test_approval_edit_resolution(client):
    # Ingest email
    payload = {
        "sender": "bob@example.com",
        "subject": "Quick question",
        "body": "Can you check this?",
    }
    ingest_res = await client.post("/api/tasks/ingest-email", json=payload)
    task_id = ingest_res.json()["task_id"]

    # Get pending approval
    approvals_res = await client.get("/api/approvals?status=pending")
    pending = [a for a in approvals_res.json() if a["task_id"] == task_id][0]

    # Resolve with EDIT
    edited_args = {
        "to": "bob@example.com",
        "subject": "Re: Custom Subject",
        "body": "Custom edited reply message.",
    }
    resolve_res = await client.post(
        f"/api/approvals/{pending['id']}/resolve",
        json={"action": "EDIT", "edited_args": edited_args},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "approved"

    # Verify audit shows user_edited
    audit_res = await client.get(f"/api/audit?task_id={task_id}")
    edited_logs = [
        log for log in audit_res.json()
        if log["actor"] == "user_edited" and log["tool_name"] == "send_email"
    ]
    assert len(edited_logs) == 1


def test_provenance_violation_block():
    policy = PolicyEngine(allowed_domains=["trusted.org"], trusted_emails=["boss@vip.com"])
    context = ExecutionContext(trigger_type="email", source_sender="alice@example.com")

    # Untrusted recipient attempt
    malicious_proposal = ActionProposal(
        tool_name="send_email",
        args={"to": "attacker@evil.com", "subject": "Secret", "body": "Data leak"},
        risk_level=RiskLevel.LEVEL_3,
    )
    decision = policy.evaluate(malicious_proposal, context)
    assert decision.allowed is False
    assert decision.requires_approval is True
    assert "Provenance violation" in decision.reason

    # Legitimate reply to sender
    legitimate_proposal = ActionProposal(
        tool_name="send_email",
        args={"to": "alice@example.com", "subject": "Re: Hi", "body": "Hello"},
        risk_level=RiskLevel.LEVEL_3,
    )
    decision_ok = policy.evaluate(legitimate_proposal, context)
    assert decision_ok.allowed is True
    assert decision_ok.requires_approval is True


@pytest.mark.asyncio
async def test_crash_restart_persistence(tmp_path):
    """Verify that a task paused in WAITING_APPROVAL persists across process/engine recreation."""
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession
    from app.db.database import get_session
    from app.main import app

    db_path = tmp_path / "test_crash.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    # Phase 1: Initialize DB, ingest email, pause in WAITING_APPROVAL
    engine1 = create_async_engine(db_url, echo=False)
    async with engine1.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_maker1 = async_sessionmaker(engine1, class_=AsyncSession, expire_on_commit=False)

    async def override_session_1():
        async with session_maker1() as session:
            yield session

    app.dependency_overrides[get_session] = override_session_1
    transport1 = ASGITransport(app=app)
    async with AsyncClient(transport=transport1, base_url="http://test") as client1:
        res = await client1.post(
            "/api/tasks/ingest-email",
            json={
                "sender": "carol@example.com",
                "subject": "Persistence check",
                "body": "Check crash recovery.",
            },
        )
        assert res.status_code == 200
        task_id = res.json()["task_id"]
        assert res.json()["status"] == "WAITING_APPROVAL"

        # Get the pending approval ID
        appr_res = await client1.get("/api/approvals?status=pending")
        approval_id = [a for a in appr_res.json() if a["task_id"] == task_id][0]["id"]

    # Simulate crash/shutdown: dispose engine and tear down session overrides
    app.dependency_overrides.clear()
    await engine1.dispose()

    # Phase 2: Simulate restart: reconnect to the same SQLite file on disk
    engine2 = create_async_engine(db_url, echo=False)
    session_maker2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)

    async def override_session_2():
        async with session_maker2() as session:
            yield session

    app.dependency_overrides[get_session] = override_session_2
    transport2 = ASGITransport(app=app)
    async with AsyncClient(transport=transport2, base_url="http://test") as client2:
        # Verify approval is still pending in DB
        appr_res = await client2.get("/api/approvals?status=pending")
        pending = [a for a in appr_res.json() if a["id"] == approval_id]
        assert len(pending) == 1

        # Resolve approval after restart
        resolve_res = await client2.post(
            f"/api/approvals/{approval_id}/resolve",
            json={"action": "APPROVE"},
        )
        assert resolve_res.status_code == 200
        assert resolve_res.json()["status"] == "approved"

        # Verify task is now completed
        tasks_res = await client2.get("/api/tasks")
        target_task = [t for t in tasks_res.json() if t["id"] == task_id][0]
        assert target_task["status"] == "COMPLETED"

    app.dependency_overrides.clear()
    await engine2.dispose()


