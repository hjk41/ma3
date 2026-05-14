from __future__ import annotations

from tests.conftest import make_ingest_payload, make_knowledge_payload


HPCX_PATH = "/mnt/cephfs/hpcx-v2.19-gcc/mlnx_ofed/ubuntu22.04/x86_64/ompi/bin/mpirun"
HOST_IP = "10.100.193.54"
EMAIL = "ops@example.com"
TOKEN = "token=supersecretvalue"


def test_agent_ingest_default_redacts_contextual_identifiers_and_secrets(authed_client):
    resp = authed_client.post("/agent/ingest", json=make_ingest_payload(
        problem=f"Use {HPCX_PATH} on {HOST_IP}; contact {EMAIL}; {TOKEN}",
        result_summary="Documented launch path",
    ))
    assert resp.status_code == 200, resp.text
    summary = resp.json()["record"]["summary"]
    assert "<redacted_path>" in summary
    assert "<redacted_ip>" in summary
    assert "<redacted_email>" in summary
    assert "token=<redacted_secret>" in summary
    assert HPCX_PATH not in summary


def test_agent_ingest_redaction_none_preserves_contextual_identifiers_but_not_secrets(authed_client):
    resp = authed_client.post("/agent/ingest", json=make_ingest_payload(
        problem=f"Use {HPCX_PATH} on {HOST_IP}; contact {EMAIL}; {TOKEN}",
        result_summary="Documented launch path",
        redaction_mode="none",
    ))
    assert resp.status_code == 200, resp.text
    summary = resp.json()["record"]["summary"]
    assert HPCX_PATH in summary
    assert HOST_IP in summary
    assert EMAIL in summary
    assert "token=<redacted_secret>" in summary
    assert "supersecretvalue" not in summary


def test_knowledge_redaction_none_preserves_contextual_identifiers(authed_client):
    resp = authed_client.post("/knowledge", json=make_knowledge_payload(
        question="Which mpirun should launch HPC-X OpenMPI jobs?",
        summary=f"Use {HPCX_PATH}; scheduler is at {HOST_IP}; {TOKEN}",
        knowledge_kind="process_protocol",
        tags=["ltp", "mpi", "hpc-x"],
        redaction_mode="none",
    ))
    assert resp.status_code == 200, resp.text
    record = resp.json()
    assert HPCX_PATH in record["summary"]
    assert HOST_IP in record["summary"]
    assert "token=<redacted_secret>" in record["summary"]
    assert "supersecretvalue" not in record["summary"]


def test_v2_agent_report_redaction_none_preserves_contextual_identifiers(authed_client):
    resp = authed_client.post("/v2/agent/report", json={
        "problem": f"MPI job must use {HPCX_PATH} from host {HOST_IP}; {TOKEN}",
        "task_type": "ltp mpi documentation",
        "goal": "preserve the useful runtime path",
        "target": {"product": "knowledge", "component": "process_protocol"},
        "outcome": "success",
        "result_summary": "Recorded the exact HPC-X launch path",
        "tags": ["ltp", "mpi", "hpc-x"],
        "redaction_mode": "none",
    })
    assert resp.status_code == 200, resp.text
    summary = resp.json()["record"]["summary"]
    assert HPCX_PATH in summary
    assert HOST_IP in summary
    assert "token=<redacted_secret>" in summary
    assert "supersecretvalue" not in summary
