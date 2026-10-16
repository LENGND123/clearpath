"""Synthetic Harbor Pay graph. Every person, account, and ticket is fictional."""

from __future__ import annotations

from app.db import (
    connect,
    coord_name,
    delete_graph,
    harbor_name,
    list_graph_names,
    rows,
)

# Demo clock is the hackathon weekend, so "last month" means September 2026.
DEMO_TODAY = "2026-10-17"
LAST_MONTH_START = "2026-09-01"
LAST_MONTH_END = "2026-10-01"

SERVICES = [
    ("ledger", "Ledger", 0),
    ("postgres-primary", "Postgres primary", 0),
    ("payments-api", "Payments API", 0),
    ("checkout-api", "Checkout API", 0),
    ("card-network", "Card network", 1),
    ("risk-api", "Risk API", 1),
    ("settlement", "Settlement", 1),
    ("mobile-app", "Mobile app", 1),
    ("feature-store", "Feature store", 2),
    ("notifications", "Notifications", 2),
    ("marketing-site", "Marketing site", 3),
    ("status-page", "Status page", 3),
]

# (dependent, dependency) — the dependent calls the dependency.
DEPENDS = [
    ("ledger", "postgres-primary"),
    ("payments-api", "ledger"),
    ("payments-api", "card-network"),
    ("risk-api", "ledger"),
    ("risk-api", "feature-store"),
    ("checkout-api", "payments-api"),
    ("checkout-api", "risk-api"),
    ("mobile-app", "checkout-api"),
    ("settlement", "ledger"),
    ("settlement", "payments-api"),
    ("notifications", "payments-api"),
    ("status-page", "marketing-site"),
]

TEAMS = [
    ("payments", "Payments"),
    ("ledger", "Ledger"),
    ("risk", "Risk"),
    ("mobile", "Mobile"),
    ("sre", "SRE"),
    ("support", "Support"),
    ("compliance", "Compliance"),
    ("settlement", "Settlement"),
]

PEOPLE = [
    ("anika", "Anika Shah", "Payments lead", "payments"),
    ("rohan", "Rohan Mehta", "Ledger engineer", "ledger"),
    ("sara", "Sara Iqbal", "SRE", "sre"),
    ("dev", "Dev Patel", "Risk engineer", "risk"),
    ("kabir", "Kabir Das", "Mobile engineer", "mobile"),
    ("leela", "Leela Nair", "Compliance", "compliance"),
    ("nia", "Nia Joseph", "Support", "support"),
    ("ishan", "Ishan Rao", "Settlement lead", "settlement"),
]

PROJECTS = [
    ("payments-v2", "Payments v2", ["payments-api", "ledger"]),
    ("ledger-split", "Ledger split", ["ledger", "postgres-primary"]),
    ("checkout-rewrite", "Checkout rewrite", ["checkout-api", "payments-api"]),
    ("risk-rules", "Risk rules", ["risk-api", "feature-store"]),
    ("mobile-checkout", "Mobile checkout", ["mobile-app", "checkout-api"]),
    ("settlement-flow", "Settlement flow", ["settlement", "ledger"]),
    ("notify-revamp", "Notifications revamp", ["notifications"]),
]

WORKED_ON = [
    ("anika", ["payments-v2", "checkout-rewrite"]),
    ("sara", ["payments-v2", "ledger-split"]),
    ("rohan", ["ledger-split"]),
    ("dev", ["risk-rules"]),
    ("kabir", ["mobile-checkout"]),
    ("ishan", ["settlement-flow"]),
    ("nia", ["notify-revamp"]),
    ("leela", ["notify-revamp"]),
]

# Directed "asks this person for help". PageRank reads these incoming edges.
KNOWS = [
    ("kabir", "anika"),
    ("dev", "anika"),
    ("anika", "sara"),
    ("ishan", "rohan"),
    ("rohan", "sara"),
    ("sara", "rohan"),
    ("nia", "leela"),
    ("kabir", "leela"),
]

ON_CALL = [
    ("anika", "payments-api"),
    ("sara", "ledger"),
    ("dev", "risk-api"),
    ("ishan", "settlement"),
]

OWNS = [
    ("anika", "payments-api"),
    ("rohan", "ledger"),
    ("dev", "risk-api"),
    ("kabir", "mobile-app"),
    ("ishan", "settlement"),
]

ACCOUNTS = [
    ("A-100", "Mira household", "open"),
    ("A-101", "Mira joint", "open"),
    ("A-880", "North mule", "open"),
    ("A-221", "Hop account", "open"),
    ("A-334", "Buffer account", "open"),
    ("A-902", "Exit account", "open"),
    ("A-500", "Unrelated A", "open"),
    ("A-501", "Unrelated B", "open"),
]

LINKS = [
    ("A-100", "A-101"),
    ("A-880", "A-221"),
    ("A-221", "A-334"),
    ("A-334", "A-902"),
    ("A-902", "A-880"),
    ("A-500", "A-501"),
]

AGENTS = [
    ("coordinator", "Coordinator"),
    ("impact", "Impact"),
    ("people", "People"),
    ("fraud", "Fraud"),
    ("memory", "Memory"),
    ("support", "Support"),
    ("company", "Company"),
]


def _q(graph, query: str, params: dict | None = None):
    if params:
        return graph.query(query, params)
    return graph.query(query)


def seed_harbor(graph=None) -> None:
    graph = graph or connect().select_graph(harbor_name())

    for team_id, name in TEAMS:
        _q(graph, "MERGE (:Team {id: $id, name: $name})", {"id": team_id, "name": name})

    for service_id, name, tier in SERVICES:
        _q(
            graph,
            "MERGE (s:Service {id: $id}) SET s.name = $name, s.tier = $tier",
            {"id": service_id, "name": name, "tier": tier},
        )

    for src, dst in DEPENDS:
        _q(
            graph,
            "MATCH (a:Service {id: $a}), (b:Service {id: $b}) "
            "MERGE (a)-[:DEPENDS_ON {weight: 1}]->(b)",
            {"a": src, "b": dst},
        )

    for person_id, name, role, team in PEOPLE:
        _q(
            graph,
            "MERGE (p:Person {id: $id}) SET p.name = $name, p.role = $role",
            {"id": person_id, "name": name, "role": role},
        )
        _q(
            graph,
            "MATCH (p:Person {id: $p}), (t:Team {id: $t}) MERGE (p)-[:MEMBER_OF]->(t)",
            {"p": person_id, "t": team},
        )

    for project_id, name, uses in PROJECTS:
        _q(
            graph,
            "MERGE (p:Project {id: $id}) SET p.name = $name",
            {"id": project_id, "name": name},
        )
        for service_id in uses:
            _q(
                graph,
                "MATCH (p:Project {id: $p}), (s:Service {id: $s}) MERGE (p)-[:USES]->(s)",
                {"p": project_id, "s": service_id},
            )

    for person_id, projects in WORKED_ON:
        for project_id in projects:
            _q(
                graph,
                "MATCH (p:Person {id: $p}), (pr:Project {id: $pr}) MERGE (p)-[:WORKED_ON]->(pr)",
                {"p": person_id, "pr": project_id},
            )

    for src, dst in KNOWS:
        _q(
            graph,
            "MATCH (a:Person {id: $a}), (b:Person {id: $b}) MERGE (a)-[:KNOWS]->(b)",
            {"a": src, "b": dst},
        )

    for person_id, service_id in ON_CALL:
        _q(
            graph,
            "MATCH (p:Person {id: $p}), (s:Service {id: $s}) MERGE (p)-[:ON_CALL_FOR]->(s)",
            {"p": person_id, "s": service_id},
        )

    for person_id, service_id in OWNS:
        _q(
            graph,
            "MATCH (p:Person {id: $p}), (s:Service {id: $s}) MERGE (p)-[:OWNS]->(s)",
            {"p": person_id, "s": service_id},
        )

    for agent_id, name in AGENTS:
        _q(graph, "MERGE (:Agent {id: $id, name: $name})", {"id": agent_id, "name": name})

    _q(
        graph,
        "MERGE (p:Procedure {id: 'PROC-ledger'}) "
        "SET p.name = $name, p.service_id = 'ledger', p.steps = $steps",
        {
            "name": "Ledger outage",
            "steps": (
                "Compute the blast radius, page the on-call unless this operator "
                "has a standing page order, open one incident, and cite the last human decision."
            ),
        },
    )
    _q(
        graph,
        "MERGE (d:Document {id: 'DOC-ledger-runbook'}) "
        "SET d.title = $title, d.kind = 'runbook'",
        {"title": "Ledger failover runbook"},
    )
    _q(
        graph,
        "MERGE (i:Incident {id: 'INC-17'}) "
        "SET i.title = $title, i.severity = 'sev2', i.status = 'resolved', "
        "i.opened_at = '2026-09-18', i.source = 'human'",
        {"title": "Ledger replication lag"},
    )
    _q(
        graph,
        "MATCH (i:Incident {id: 'INC-17'}), (s:Service {id: 'ledger'}) MERGE (i)-[:AFFECTS]->(s)"
    )
    _q(
        graph,
        "MERGE (d:Decision {id: 'DEC-17'}) "
        "SET d.summary = $summary, d.decided_at = '2026-09-18', d.source = 'human'",
        {
            "summary": (
                "Fail reads over to the replica and page the ledger on-call before any schema change."
            )
        },
    )
    _q(
        graph,
        "MATCH (d:Decision {id: 'DEC-17'}), (i:Incident {id: 'INC-17'}) MERGE (d)-[:ABOUT]->(i)"
    )
    _q(
        graph,
        "MATCH (d:Decision {id: 'DEC-17'}), (p:Person {id: 'leela'}) MERGE (d)-[:DECIDED_BY]->(p)"
    )
    _q(
        graph,
        "MATCH (d:Decision {id: 'DEC-17'}), (doc:Document {id: 'DOC-ledger-runbook'}) "
        "MERGE (d)-[:CITES]->(doc)"
    )

    _q(graph, "MERGE (:Customer {id: 'mira', name: 'Mira Shah'})")
    _q(graph, "MERGE (:Customer {id: 'rahul', name: 'Rahul Sen'})")

    tickets = [
        ("T-19", "Refund the duplicate checkout charge", "resolved", "2026-09-12", "2026-09-14", "mira", "checkout-api", "nia"),
        ("T-22", "Settlement to my bank is still pending", "open", "2026-09-28", "", "mira", "settlement", "nia"),
        ("T-30", "Change the email on my profile", "resolved", "2026-05-02", "2026-05-03", "mira", "marketing-site", "nia"),
        ("T-31", "Update my phone number", "resolved", "2026-05-11", "2026-05-11", "rahul", "marketing-site", "nia"),
    ]
    for ticket_id, title, status, opened, resolved, customer, service, owner in tickets:
        _q(
            graph,
            "MERGE (t:Ticket {id: $id}) "
            "SET t.title = $title, t.status = $status, t.opened_at = $opened, t.resolved_at = $resolved",
            {
                "id": ticket_id,
                "title": title,
                "status": status,
                "opened": opened,
                "resolved": resolved,
            },
        )
        _q(
            graph,
            "MATCH (c:Customer {id: $c}), (t:Ticket {id: $t}) MERGE (c)-[:FILED]->(t)",
            {"c": customer, "t": ticket_id},
        )
        _q(
            graph,
            "MATCH (t:Ticket {id: $t}), (s:Service {id: $s}) MERGE (t)-[:ABOUT]->(s)",
            {"t": ticket_id, "s": service},
        )
        _q(
            graph,
            "MATCH (t:Ticket {id: $t}), (p:Person {id: $p}) MERGE (t)-[:OWNED_BY]->(p)",
            {"t": ticket_id, "p": owner},
        )

    for account_id, name, status in ACCOUNTS:
        _q(
            graph,
            "MERGE (a:Account {id: $id}) SET a.name = $name, a.status = $status",
            {"id": account_id, "name": name, "status": status},
        )
    for src, dst in LINKS:
        _q(
            graph,
            "MATCH (a:Account {id: $a}), (b:Account {id: $b}) MERGE (a)-[:LINKED_TO]->(b)",
            {"a": src, "b": dst},
        )
    _q(
        graph,
        "MATCH (c:Customer {id: 'mira'}), (a:Account {id: 'A-100'}) MERGE (c)-[:HAS_ACCOUNT]->(a)"
    )
    _q(
        graph,
        "MATCH (c:Customer {id: 'mira'}), (a:Account {id: 'A-101'}) MERGE (c)-[:HAS_ACCOUNT]->(a)"
    )
    _q(
        graph,
        "MATCH (c:Customer {id: 'rahul'}), (a:Account {id: 'A-500'}) MERGE (c)-[:HAS_ACCOUNT]->(a)"
    )

    _q(
        graph,
        "MERGE (t:Transaction {id: 'TX-1042'}) "
        "SET t.amount = 48000, t.currency = 'INR', t.flagged = true, t.ts = '2026-10-02'",
    )
    _q(
        graph,
        "MATCH (t:Transaction {id: 'TX-1042'}), (a:Account {id: 'A-880'}) "
        "MERGE (t)-[:FROM_ACCOUNT]->(a)"
    )
    _q(
        graph,
        "MATCH (t:Transaction {id: 'TX-1042'}), (a:Account {id: 'A-221'}) "
        "MERGE (t)-[:TO_ACCOUNT]->(a)"
    )

    _q(graph, "MERGE (:Domain {id: 'fraud-review', name: 'Fraud review'})")
    _q(
        graph,
        "MATCH (p:Person {id: 'leela'}), (d:Domain {id: 'fraud-review'}) MERGE (p)-[:OWNS]->(d)"
    )

    for label, prop in (
        ("Service", "id"),
        ("Person", "id"),
        ("Account", "id"),
        ("Customer", "id"),
        ("Transaction", "id"),
        ("Ticket", "id"),
        ("Project", "id"),
    ):
        _try_index(graph, label, prop)


def _try_index(graph, label: str, prop: str) -> None:
    modern = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
    legacy = f"CREATE INDEX ON :{label}({prop})"
    try:
        graph.query(modern)
    except Exception:
        try:
            graph.query(legacy)
        except Exception:
            return


def is_seeded() -> bool:
    try:
        result = connect().select_graph(harbor_name()).query(
            "MATCH (s:Service {id: 'ledger'}) RETURN s.id AS id"
        )
    except Exception:
        return False
    return bool(result.result_set)


def reset_all() -> None:
    db = connect()
    delete_graph(harbor_name(), db)
    delete_graph(coord_name(), db)
    for user_id in ("aditya", "priya", "load"):
        delete_graph(f"memory_{user_id}", db)
    try:
        names = list_graph_names(db)
    except Exception:
        names = []
    for name in names:
        if name.startswith("memory_"):
            delete_graph(name, db)
    seed_harbor(db.select_graph(harbor_name()))


def ensure_seeded() -> None:
    if not is_seeded():
        seed_harbor()


def account_statuses() -> dict[str, str]:
    result = connect().select_graph(harbor_name()).query(
        "MATCH (a:Account) RETURN a.id AS id, a.status AS status"
    )
    return {row["id"]: row["status"] for row in rows(result)}
