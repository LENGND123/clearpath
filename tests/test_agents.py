import os

import pytest

from app.db import connect, memory_name, ping
from app.seed import account_statuses, reset_all


def _up() -> bool:
    try:
        ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _up(),
    reason="FalkorDB is not running. Start it with docker compose up falkordb.",
)


@pytest.fixture()
def seeded():
    reset_all()
    yield


def test_ledger_blast_pages_on_call_and_skips_unrelated_services(seeded):
    from app.agents import ask

    out = ask("What breaks if the ledger service goes down?", "aditya", "s1")
    assert out["tool"] == "blast_radius"
    assert set(out["facts"]["dependent_ids"]) == {
        "payments-api",
        "risk-api",
        "settlement",
        "checkout-api",
        "mobile-app",
        "notifications",
    }
    assert out["facts"]["paged_person_id"] == "sara"
    assert out["facts"]["on_call_person_id"] == "sara"
    assert out["facts"]["page_reason"] == "ON_CALL_FOR"
    assert out["facts"]["severity"] == "sev1"
    assert out["facts"]["prior_decision_id"] == "DEC-17"
    assert any(action["type"] == "OPEN_INCIDENT" for action in out["actions"])


def test_status_page_takes_no_action(seeded):
    from app.agents import ask

    out = ask("What breaks if the status page goes down?", "aditya", "s1")
    assert out["facts"]["dependent_ids"] == []
    assert out["actions"] == []


def test_card_network_does_not_take_down_ledger(seeded):
    from app.agents import ask

    out = ask("What breaks if the card-network goes down?", "aditya", "s1")
    ids = set(out["facts"]["dependent_ids"])
    assert "payments-api" in ids
    assert "checkout-api" in ids
    assert "ledger" not in ids
    assert "risk-api" not in ids
    assert "postgres-primary" not in ids


def test_standing_order_is_per_operator(seeded):
    from app.agents import ask

    ask("Next time the ledger fails, page Rohan first", "aditya", "s1")
    aditya = ask("What breaks if the ledger service goes down?", "aditya", "s2")
    priya = ask("What breaks if the ledger service goes down?", "priya", "s1")
    assert aditya["facts"]["paged_person_id"] == "rohan"
    assert aditya["facts"]["on_call_person_id"] == "sara"
    assert aditya["facts"]["page_reason"] == "PROCEDURE_OVERRIDE"
    assert priya["facts"]["paged_person_id"] == "sara"
    assert priya["facts"]["page_reason"] == "ON_CALL_FOR"


def test_blast_incident_is_updated_not_duplicated(seeded):
    from app.agents import ask
    from app.db import harbor_name, rows

    ask("What breaks if the ledger service goes down?", "aditya", "s1")
    ask("What breaks if the ledger service goes down?", "aditya", "s2")
    found = rows(
        connect()
        .select_graph(harbor_name())
        .query("MATCH (i:Incident {source: 'agent'}) RETURN count(i) AS n")
    )
    assert found[0]["n"] == 1


def test_payments_page_uses_on_call_not_pagerank(seeded):
    from app.agents import ask

    out = ask("Who on the team has worked on payments-api before?", "aditya", "s1")
    assert out["facts"]["person_ids"] == ["anika", "sara"]
    assert out["facts"]["project_counts"]["anika"] == 2
    assert out["facts"]["paged_person_id"] == "anika"
    assert out["facts"]["page_reason"] == "ON_CALL_FOR"


def test_notifications_page_uses_pagerank(seeded):
    from app.agents import ask

    out = ask("Who on the team has worked on notifications before?", "aditya", "s1")
    assert out["facts"]["person_ids"] == ["leela", "nia"]
    assert out["facts"]["page_reason"] == "pageRank"
    assert out["facts"]["algorithm"] == "algo.pageRank"
    assert out["facts"]["scores"]["leela"] > out["facts"]["scores"]["nia"]
    assert out["facts"]["paged_person_id"] == "leela"


def test_fraud_freezes_only_the_linked_component(seeded):
    from app.agents import ask

    out = ask("Which accounts are linked to flagged transaction TX-1042?", "aditya", "s1")
    assert set(out["facts"]["frozen_ids"]) == {"A-880", "A-221", "A-334", "A-902"}
    assert out["facts"]["handoff_person_id"] == "leela"
    statuses = account_statuses()
    assert statuses["A-880"] == "frozen"
    assert statuses["A-902"] == "frozen"
    assert statuses["A-100"] == "open"
    assert statuses["A-101"] == "open"
    assert statuses["A-500"] == "open"
    assert statuses["A-501"] == "open"


def test_mira_last_month_skips_may_and_hands_off_open_ticket(seeded):
    from app.agents import ask

    out = ask("What did Mira Shah ask for last month, and was it resolved?", "aditya", "s1")
    assert out["facts"]["ticket_ids"] == ["T-19", "T-22"]
    assert out["facts"]["open_ticket_ids"] == ["T-22"]
    assert out["facts"]["handoff_person_id"] == "ishan"
    assert "T-30" not in out["answer"]


def test_rahul_has_no_september_tickets(seeded):
    from app.agents import ask

    out = ask("What did Rahul Sen ask for last month?", "aditya", "s1")
    assert out["facts"]["ticket_ids"] == []
    assert out["actions"] == []


def test_human_decision_survives_agent_decision(seeded):
    from app.agents import ask

    ask("What breaks if the ledger service goes down?", "aditya", "s1")
    out = ask("What did we decide the last time ledger failed?", "aditya", "s2")
    assert out["facts"]["decision_id"] == "DEC-17"
    assert out["facts"]["decided_by"] == "leela"
    assert "replica" in out["facts"]["summary"]


def test_recall_reads_the_earlier_session(seeded):
    from app.agents import ask

    ask("What breaks if the ledger service goes down?", "aditya", "sess-a")
    out = ask("What did we decide in earlier sessions?", "aditya", "sess-b")
    assert out["tool"] == "recall"
    assert any("ledger" in question.lower() for question in out["facts"]["episode_questions"])
    assert any(row["session_id"] == "sess-a" for row in out["facts"]["episodes"])


def test_parallel_memory_writes(seeded):
    from concurrent.futures import ThreadPoolExecutor

    def one(index: int) -> None:
        graph = connect().select_graph(memory_name("load"))
        graph.query(
            "CREATE (:Episode {id: $id, n: $n})",
            {"id": f"e{index}", "n": index},
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(one, range(20)))
    from app.db import rows

    found = rows(
        connect().select_graph(memory_name("load")).query("MATCH (e:Episode) RETURN count(e) AS n")
    )
    assert int(found[0]["n"]) == 20


def test_http_ask(seeded):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/ask",
        json={
            "question": "What breaks if the status page goes down?",
            "user_id": "aditya",
            "session_id": "http1",
        },
    )
    assert response.status_code == 200
    assert response.json()["facts"]["dependent_ids"] == []
    assert client.get("/api/health").json()["ok"] is True


def test_env_host_is_visible():
    # Keeps the skip reason honest when CI sets the host and the socket is closed.
    assert os.getenv("FALKORDB_HOST", "localhost")
