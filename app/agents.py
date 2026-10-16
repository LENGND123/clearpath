"""Graph tools. The answer and every action come from FalkorDB rows, not from a model."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.db import check_user_id, connect, coord_name, harbor_name, memory_name, rows
from app.planner import Plan, plan
from app.seed import LAST_MONTH_END, LAST_MONTH_START

def ask(question: str, user_id: str = "aditya", session_id: str = "session") -> dict:
    user_id = check_user_id(user_id)
    session_id = _session(session_id)
    question = " ".join((question or "").split())
    if not question:
        raise ValueError("Ask a question first.")
    if len(question) > 500:
        raise ValueError("Keep the question under 500 characters.")

    chosen = plan(question)
    handler = {
        "blast_radius": blast_radius,
        "who_knows": who_knows,
        "fraud_ring": fraud_ring,
        "customer_history": customer_history,
        "past_decision": past_decision,
        "recall": recall,
        "set_procedure": set_procedure,
        "search": search,
    }[chosen.tool]
    result = handler(chosen, user_id)
    result["planner"] = chosen.planner
    result["question"] = question

    episode_id = _write_episode(user_id, session_id, question, result)
    _write_handoffs(user_id, session_id, result)
    result["memory"] = _memory_snapshot(user_id)
    result["facts"]["episode_id"] = episode_id
    return result


def blast_radius(chosen: Plan, user_id: str) -> dict:
    service_id = chosen.service_id
    if not service_id:
        return _empty("blast_radius", chosen, "Name the service. For example: what breaks if the ledger goes down?")
    service = _one(
        "MATCH (s:Service {id: $id}) RETURN s.id AS id, s.name AS name, s.tier AS tier",
        {"id": service_id},
    )
    if not service:
        return _empty("blast_radius", chosen, f"No service with id {service_id} is in the Harbor Pay graph.")

    cypher: list[str] = []
    dependent_ids, algorithm, algo_cypher, algo_error = _dependent_ids(service_id)
    cypher.extend(algo_cypher)
    details = _service_details(dependent_ids)
    dependent_ids = {item["id"] for item in details}
    try:
        paths = _dependency_paths(service_id, dependent_ids, cypher)
    except Exception as exc:
        paths = []
        cypher.append(f"-- display path failed: {exc}")

    on_call = _role_people(service_id, "ON_CALL_FOR")
    owners = _role_people(service_id, "OWNS")
    override = _read_override(user_id, service_id)
    prior = _human_decision(service_id)
    procedure = None
    if service_id == "ledger":
        procedure = _one(
            "MATCH (p:Procedure {id: 'PROC-ledger'}) RETURN p.id AS id, p.steps AS steps, p.name AS name",
            {},
        )

    page_reason = None
    paged = None
    if override:
        paged = _one(
            "MATCH (p:Person {id: $id}) RETURN p.id AS id, p.name AS name, p.role AS role",
            {"id": override["person_id"]},
        )
        page_reason = "PROCEDURE_OVERRIDE"
    elif on_call:
        paged = on_call[0]
        page_reason = "ON_CALL_FOR"
    elif owners:
        paged = owners[0]
        page_reason = "OWNS"

    actions = []
    incident_id = None
    severity = None
    if dependent_ids and paged:
        severity = "sev1" if any(int(item["tier"]) == 0 for item in details) else "sev2"
        incident_id = f"INC-agent-{service_id}"
        decision_id = f"DEC-agent-{service_id}"
        title = f"{service['name']} blast radius"
        summary = (
            f"{len(dependent_ids)} services fail if {service['name']} goes down. "
            f"Paged {paged['name']} because {page_reason}."
        )
        ts = _now()
        written, shown = _run(
            "MERGE (i:Incident {id: $id}) "
            "SET i.title = $title, i.severity = $severity, i.status = 'open', "
            "i.opened_at = $ts, i.source = 'agent', i.opened_by = 'impact' "
            "WITH i "
            "MATCH (s:Service {id: $service}) "
            "MERGE (i)-[:AFFECTS]->(s) "
            "WITH i "
            "MATCH (p:Person {id: $person}) "
            "MERGE (i)-[:ASSIGNED_TO]->(p)",
            {
                "id": incident_id,
                "title": title,
                "severity": severity,
                "ts": ts,
                "service": service_id,
                "person": paged["id"],
            },
        )
        cypher.append(shown)
        cite = (
            "WITH d MATCH (proc:Procedure {id: 'PROC-ledger'}) MERGE (d)-[:CITES]->(proc)"
            if service_id == "ledger"
            else ""
        )
        _, shown = _run(
            "MERGE (d:Decision {id: $id}) "
            "SET d.summary = $summary, d.decided_at = $ts, d.source = 'agent' "
            "WITH d "
            "MATCH (i:Incident {id: $incident}) "
            "MERGE (d)-[:ABOUT]->(i) "
            "WITH d "
            "MATCH (agent:Agent {id: 'impact'}) "
            "MERGE (d)-[:DECIDED_BY]->(agent) "
            "WITH d "
            "MATCH (p:Person {id: $person}) "
            "MERGE (d)-[:PAGES]->(p) "
            + cite,
            {
                "id": decision_id,
                "summary": summary,
                "ts": ts,
                "incident": incident_id,
                "person": paged["id"],
            },
        )
        cypher.append(shown)
        actions.append(
            {
                "type": "OPEN_INCIDENT",
                "id": incident_id,
                "severity": severity,
                "person_id": paged["id"],
            }
        )
        actions.append({"type": "PAGE", "person_id": paged["id"], "reason": page_reason})
        actions.append({"type": "RECORD_DECISION", "id": decision_id})
        _write_fact(
            user_id,
            f"FACT-{service_id}-blast",
            f"If {service['name']} fails, these services fail too: {', '.join(sorted(dependent_ids))}.",
        )

    if paged:
        edge = page_reason or "PAGES"
        paths.append(
            {
                "kind": "path",
                "title": "Who gets paged",
                "nodes": [
                    _node(paged["id"], "Person", paged["name"]),
                    _node(service_id, "Service", service["name"]),
                ],
                "edges": [{"source": paged["id"], "target": service_id, "type": edge}],
            }
        )
    if on_call and page_reason == "PROCEDURE_OVERRIDE":
        person = on_call[0]
        paths.append(
            {
                "kind": "path",
                "title": "On call in the company graph",
                "nodes": [
                    _node(person["id"], "Person", person["name"]),
                    _node(service_id, "Service", service["name"]),
                ],
                "edges": [{"source": person["id"], "target": service_id, "type": "ON_CALL_FOR"}],
            }
        )

    names = [item["name"] for item in sorted(details, key=lambda item: item["name"])]
    if not dependent_ids:
        answer = (
            f"Nothing in Harbor Pay depends on {service['name']}. "
            f"I did not open an incident. Algorithm: {algorithm}."
        )
    else:
        route = ""
        if paths:
            first = next((path for path in paths if path.get("title") == "Dependency"), None)
            if first:
                route = " One shortest path: " + " DEPENDS_ON ".join(
                    node["name"] for node in first["nodes"]
                ) + "."
        override_line = ""
        if page_reason == "PROCEDURE_OVERRIDE" and on_call:
            override_line = (
                f" Company procedure still has {on_call[0]['name']} ON_CALL_FOR {service['name']}, "
                f"but your memory graph says to page {paged['name']} first, so I followed that."
            )
        elif paged:
            override_line = f" I paged {paged['name']} because the graph has {page_reason}."
        prior_line = ""
        if prior:
            prior_line = (
                f" Last human decision on this service ({prior['id']}, {prior['decided_at']}, "
                f"{prior['person']}): {prior['summary']}"
            )
        proc_line = f" Procedure {procedure['id']}: {procedure['steps']}" if procedure else ""
        answer = (
            f"If {service['name']} goes down, {len(dependent_ids)} services fail with it: "
            f"{_join(names)}.{route}{override_line}{proc_line}{prior_line} "
            f"Reachability used {algorithm}."
        )

    handoffs = [{"from": "coordinator", "to": "impact", "reason": "blast radius"}]
    agents = ["coordinator", "impact", "memory"]
    if paged:
        handoffs.append({"from": "impact", "to": "people", "reason": f"page {paged['name']}"})
        agents.insert(2, "people")

    return {
        "answer": " ".join(answer.split()),
        "tool": "blast_radius",
        "agents": agents,
        "handoffs": handoffs,
        "cypher": cypher,
        "paths": paths,
        "actions": actions,
        "facts": {
            "service_id": service_id,
            "service_name": service["name"],
            "dependent_ids": sorted(dependent_ids),
            "algorithm": algorithm,
            "algorithm_error": algo_error,
            "paged_person_id": paged["id"] if paged else None,
            "on_call_person_id": on_call[0]["id"] if on_call else None,
            "page_reason": page_reason,
            "incident_id": incident_id,
            "severity": severity,
            "prior_decision_id": prior["id"] if prior else None,
        },
    }


def who_knows(chosen: Plan, user_id: str) -> dict:
    del user_id
    service_id = chosen.service_id
    if not service_id:
        return _empty("who_knows", chosen, "Name a service. For example: who has worked on payments-api?")
    service = _one(
        "MATCH (s:Service {id: $id}) RETURN s.id AS id, s.name AS name",
        {"id": service_id},
    )
    if not service:
        return _empty("who_knows", chosen, f"No service with id {service_id} is in the Harbor Pay graph.")

    worked, shown = _run(
        "MATCH (p:Person)-[:WORKED_ON]->(proj:Project)-[:USES]->(s:Service {id: $id}) "
        "RETURN p.id AS person_id, p.name AS person, p.role AS role, "
        "proj.id AS project_id, proj.name AS project",
        {"id": service_id},
    )
    cypher = [shown]
    grouped: dict[str, dict] = {}
    for row in worked:
        slot = grouped.setdefault(
            row["person_id"],
            {"id": row["person_id"], "name": row["person"], "role": row["role"], "projects": []},
        )
        if row["project_id"] not in {item["id"] for item in slot["projects"]}:
            slot["projects"].append({"id": row["project_id"], "name": row["project"]})
    ranked = sorted(grouped.values(), key=lambda person: (-len(person["projects"]), person["name"]))

    on_call = _role_people(service_id, "ON_CALL_FOR")
    owners = _role_people(service_id, "OWNS")
    scores, score_cypher, algorithm, algo_error = _page_rank()
    cypher.append(score_cypher)

    page_reason = None
    paged = None
    if on_call:
        paged = on_call[0]
        page_reason = "ON_CALL_FOR"
    elif owners:
        paged = owners[0]
        page_reason = "OWNS"
    elif ranked and algorithm == "algo.pageRank":
        paged = sorted(ranked, key=lambda person: (-float(scores.get(person["id"], 0.0)), person["name"]))[0]
        page_reason = "pageRank"
    elif ranked:
        paged = ranked[0]
        page_reason = "WORKED_ON"

    paths = []
    for person in ranked[:4]:
        for project in person["projects"][:2]:
            paths.append(
                {
                    "kind": "path",
                    "title": person["name"],
                    "nodes": [
                        _node(person["id"], "Person", person["name"]),
                        _node(project["id"], "Project", project["name"]),
                        _node(service_id, "Service", service["name"]),
                    ],
                    "edges": [
                        {"source": person["id"], "target": project["id"], "type": "WORKED_ON"},
                        {"source": project["id"], "target": service_id, "type": "USES"},
                    ],
                }
            )
    if on_call:
        paths.append(
            {
                "kind": "path",
                "title": "On call",
                "nodes": [
                    _node(on_call[0]["id"], "Person", on_call[0]["name"]),
                    _node(service_id, "Service", service["name"]),
                ],
                "edges": [{"source": on_call[0]["id"], "target": service_id, "type": "ON_CALL_FOR"}],
            }
        )

    actions = []
    if paged:
        actions.append({"type": "PAGE", "person_id": paged["id"], "reason": page_reason})

    if not ranked and not on_call and not owners:
        answer = f"Nobody in the graph has worked on a project that uses {service['name']}, and nobody owns or covers it."
    else:
        worked_line = _join(
            f"{person['name']} ({len(person['projects'])} project{'s' if len(person['projects']) != 1 else ''})"
            for person in ranked
        ) or "nobody"
        score_line = ""
        if scores and ranked:
            ordered = sorted(ranked, key=lambda person: -float(scores.get(person["id"], 0.0)))
            score_line = " PageRank on Person-KNOWS, among those people: " + ", ".join(
                f"{person['name']} {float(scores.get(person['id'], 0.0)):.3f}" for person in ordered
            ) + "."
        why = f"I paged {paged['name']} because of {page_reason}, not because of the score." if paged else ""
        on_call_line = f" On call: {on_call[0]['name']}." if on_call else " Nobody is ON_CALL_FOR this service."
        answer = (
            f"People who WORKED_ON a project that USES {service['name']}: {worked_line}.{on_call_line}{score_line} {why}"
        )

    handoffs = [{"from": "coordinator", "to": "people", "reason": "find an owner"}]
    return {
        "answer": " ".join(answer.split()),
        "tool": "who_knows",
        "agents": ["coordinator", "people", "memory"],
        "handoffs": handoffs,
        "cypher": cypher,
        "paths": paths[:6],
        "actions": actions,
        "facts": {
            "service_id": service_id,
            "person_ids": [person["id"] for person in ranked],
            "project_counts": {person["id"]: len(person["projects"]) for person in ranked},
            "paged_person_id": paged["id"] if paged else None,
            "page_reason": page_reason,
            "on_call_person_id": on_call[0]["id"] if on_call else None,
            "scores": {person["id"]: float(scores.get(person["id"], 0.0)) for person in ranked},
            "algorithm": algorithm,
            "algorithm_error": algo_error,
        },
    }


def fraud_ring(chosen: Plan, user_id: str) -> dict:
    cypher = []
    transaction_id = chosen.transaction_id
    if not transaction_id:
        found, shown = _run(
            "MATCH (t:Transaction) WHERE t.flagged = true "
            "RETURN t.id AS id ORDER BY t.ts DESC LIMIT 1",
            {},
        )
        cypher.append(shown)
        if not found:
            return _empty("fraud_ring", chosen, "The graph has no flagged transaction.", cypher)
        transaction_id = found[0]["id"]

    tx = _one(
        "MATCH (t:Transaction {id: $id})-[:FROM_ACCOUNT]->(src:Account) "
        "MATCH (t)-[:TO_ACCOUNT]->(dst:Account) "
        "RETURN t.id AS id, t.amount AS amount, t.currency AS currency, "
        "src.id AS src_id, src.name AS src_name, dst.id AS dst_id, dst.name AS dst_name",
        {"id": transaction_id},
    )
    if not tx:
        return _empty("fraud_ring", chosen, f"{transaction_id} is not in the graph, or it has no account edges.")

    component, algorithm, algo_cypher, component_id, algo_error = _fraud_component(tx["src_id"])
    cypher.extend(algo_cypher)
    ids = sorted(component)
    owner = _one(
        "MATCH (p:Person)-[:OWNS]->(:Domain {id: 'fraud-review'}) "
        "RETURN p.id AS id, p.name AS name ORDER BY p.name LIMIT 1",
        {},
    ) or {"id": "leela", "name": "Leela Nair"}
    ts = _now()
    frozen_rows, shown = _run(
        "UNWIND $ids AS acctId "
        "MATCH (a:Account {id: acctId}) "
        "SET a.status = 'frozen', a.frozen_at = $ts, a.frozen_reason = $reason "
        "RETURN a.id AS id, a.status AS status",
        {"ids": ids, "ts": ts, "reason": transaction_id},
    )
    cypher.append(shown)
    decision_id = f"DEC-agent-{transaction_id}"
    summary = f"Froze the {transaction_id} component: {', '.join(ids)}."
    _, shown = _run(
        "MERGE (d:Decision {id: $id}) "
        "SET d.summary = $summary, d.decided_at = $ts, d.source = 'agent' "
        "WITH d "
        "MATCH (t:Transaction {id: $tx}) "
        "MERGE (d)-[:ABOUT]->(t) "
        "WITH d "
        "MATCH (agent:Agent {id: 'fraud'}) "
        "MERGE (d)-[:DECIDED_BY]->(agent) "
        "WITH d "
        "MATCH (p:Person {id: $person}) "
        "MERGE (d)-[:PAGES]->(p)",
        {
            "id": decision_id,
            "summary": summary,
            "ts": ts,
            "tx": transaction_id,
            "person": owner["id"],
        },
    )
    cypher.append(shown)
    _write_fact(user_id, f"FACT-{transaction_id}", summary)

    edges, shown = _run(
        "MATCH (a:Account)-[r:LINKED_TO]->(b:Account) "
        "WHERE a.id IN $ids AND b.id IN $ids "
        "RETURN a.id AS source, a.name AS source_name, b.id AS target, b.name AS target_name, type(r) AS type",
        {"ids": ids},
    )
    cypher.append(shown)
    nodes = [_node(row_id, "Account", component[row_id]) for row_id in ids]
    nodes.append(_node(transaction_id, "Transaction", transaction_id))
    graph_edges = [
        {"source": row["source"], "target": row["target"], "type": row["type"]} for row in edges
    ]
    graph_edges.append({"source": transaction_id, "target": tx["src_id"], "type": "FROM_ACCOUNT"})
    graph_edges.append({"source": transaction_id, "target": tx["dst_id"], "type": "TO_ACCOUNT"})

    open_rows, _ = _run(
        "MATCH (a:Account) WHERE a.status = 'open' RETURN a.id AS id ORDER BY a.id",
        {},
    )
    answer = (
        f"{transaction_id} ({tx['amount']} {tx['currency']}) goes FROM_ACCOUNT {tx['src_name']} "
        f"TO_ACCOUNT {tx['dst_name']}. {algorithm} put { _join(ids) } in the same component"
        + (f" ({component_id})" if component_id is not None else "")
        + f". I froze those accounts and left {_join(row['id'] for row in open_rows)} open. "
        f"Handed the freeze to {owner['name']}, who OWNS fraud review."
    )
    return {
        "answer": " ".join(answer.split()),
        "tool": "fraud_ring",
        "agents": ["coordinator", "fraud", "people", "memory"],
        "handoffs": [
            {"from": "coordinator", "to": "fraud", "reason": "flagged transfer"},
            {"from": "fraud", "to": "people", "reason": f"{owner['name']} owns fraud review"},
        ],
        "cypher": cypher,
        "paths": [
            {
                "kind": "graph",
                "title": "Flagged component",
                "nodes": nodes,
                "edges": graph_edges,
            }
        ],
        "actions": [
            {"type": "FREEZE", "account_ids": ids},
            {"type": "RECORD_DECISION", "id": decision_id},
            {"type": "PAGE", "person_id": owner["id"], "reason": "OWNS"},
        ],
        "facts": {
            "transaction_id": transaction_id,
            "source_account": tx["src_id"],
            "frozen_ids": ids,
            "left_open_ids": [row["id"] for row in open_rows],
            "algorithm": algorithm,
            "algorithm_error": algo_error,
            "component_id": component_id,
            "handoff_person_id": owner["id"],
        },
    }


def customer_history(chosen: Plan, user_id: str) -> dict:
    del user_id
    customer_id = chosen.customer_id
    if not customer_id:
        return _empty("customer_history", chosen, "Name the customer. Mira Shah and Rahul Sen are in the graph.")
    rows_found, shown = _run(
        "MATCH (c:Customer {id: $id})-[:FILED]->(t:Ticket) "
        "WHERE t.opened_at >= $start AND t.opened_at < $end "
        "OPTIONAL MATCH (t)-[:ABOUT]->(s:Service) "
        "OPTIONAL MATCH (s)<-[:OWNS]-(owner:Person) "
        "OPTIONAL MATCH (t)-[:OWNED_BY]->(support:Person) "
        "RETURN t.id AS ticket_id, t.title AS title, t.status AS status, t.opened_at AS opened_at, "
        "c.name AS customer, s.id AS service_id, s.name AS service, "
        "owner.id AS owner_id, owner.name AS owner, support.name AS support "
        "ORDER BY t.opened_at",
        {"id": customer_id, "start": LAST_MONTH_START, "end": LAST_MONTH_END},
    )
    if not rows_found:
        known = _one("MATCH (c:Customer {id: $id}) RETURN c.name AS name", {"id": customer_id})
        if not known:
            return _empty("customer_history", chosen, f"No customer {customer_id} is in the graph.", [shown])
        return {
            "answer": (
                f"{known['name']} filed nothing between {LAST_MONTH_START} and {LAST_MONTH_END}. "
                "Older tickets stay in the graph, and this window does not include them."
            ),
            "tool": "customer_history",
            "agents": ["coordinator", "support", "memory"],
            "handoffs": [{"from": "coordinator", "to": "support", "reason": "customer history"}],
            "cypher": [shown],
            "paths": [],
            "actions": [],
            "facts": {
                "customer_id": customer_id,
                "ticket_ids": [],
                "open_ticket_ids": [],
                "handoff_person_id": None,
            },
        }

    paths = []
    for row in rows_found:
        nodes = [
            _node(customer_id, "Customer", row["customer"]),
            _node(row["ticket_id"], "Ticket", row["title"]),
        ]
        edges = [{"source": customer_id, "target": row["ticket_id"], "type": "FILED"}]
        if row.get("service_id"):
            nodes.append(_node(row["service_id"], "Service", row["service"]))
            edges.append({"source": row["ticket_id"], "target": row["service_id"], "type": "ABOUT"})
        paths.append({"kind": "path", "title": row["ticket_id"], "nodes": nodes, "edges": edges})

    open_rows = [row for row in rows_found if row["status"] == "open"]
    handoff = None
    actions = []
    if open_rows and open_rows[-1].get("owner_id"):
        target = open_rows[-1]
        handoff = target["owner_id"]
        actions.append(
            {
                "type": "HANDOFF",
                "person_id": target["owner_id"],
                "ticket_id": target["ticket_id"],
                "reason": "OWNS",
            }
        )
        paths.append(
            {
                "kind": "path",
                "title": "Open ticket owner",
                "nodes": [
                    _node(target["owner_id"], "Person", target["owner"]),
                    _node(target["service_id"], "Service", target["service"]),
                ],
                "edges": [{"source": target["owner_id"], "target": target["service_id"], "type": "OWNS"}],
            }
        )

    bits = [
        f"{row['ticket_id']} ({row['opened_at']}, {row['status']}) about {row['service']}: {row['title']}"
        for row in rows_found
    ]
    handoff_line = ""
    if handoff:
        owner = open_rows[-1]
        handoff_line = (
            f" I handed the open ticket to {owner['owner']}, who OWNS {owner['service']}."
        )
    answer = (
        f"In September 2026, {rows_found[0]['customer']} asked: {_join(bits)}.{handoff_line}"
    )
    handoffs = [{"from": "coordinator", "to": "support", "reason": "customer history"}]
    agents = ["coordinator", "support", "memory"]
    if handoff:
        handoffs.append({"from": "support", "to": "people", "reason": "service owner"})
        agents.insert(2, "people")
    return {
        "answer": answer,
        "tool": "customer_history",
        "agents": agents,
        "handoffs": handoffs,
        "cypher": [shown],
        "paths": paths,
        "actions": actions,
        "facts": {
            "customer_id": customer_id,
            "ticket_ids": [row["ticket_id"] for row in rows_found],
            "open_ticket_ids": [row["ticket_id"] for row in open_rows],
            "handoff_person_id": handoff,
        },
    }


def past_decision(chosen: Plan, user_id: str) -> dict:
    del user_id
    service_id = chosen.service_id or "ledger"
    found, shown = _run(
        "MATCH (d:Decision {source: 'human'})-[:ABOUT]->(:Incident)-[:AFFECTS]->(s:Service {id: $id}) "
        "MATCH (d)-[:DECIDED_BY]->(p:Person) "
        "OPTIONAL MATCH (d)-[:CITES]->(doc:Document) "
        "RETURN d.id AS id, d.summary AS summary, d.decided_at AS decided_at, "
        "p.id AS person_id, p.name AS person, doc.id AS document_id, doc.title AS document, "
        "s.name AS service "
        "ORDER BY d.decided_at DESC LIMIT 1",
        {"id": service_id},
    )
    if not found:
        return _empty(
            "past_decision",
            chosen,
            f"No human decision in the graph touches {service_id}.",
            [shown],
        )
    row = found[0]
    return {
        "answer": (
            f"{row['person']} decided on {row['decided_at']} ({row['id']}) about {row['service']}: "
            f"{row['summary']} Source: {row['document']}."
        ),
        "tool": "past_decision",
        "agents": ["coordinator", "company", "memory"],
        "handoffs": [{"from": "coordinator", "to": "company", "reason": "decision trace"}],
        "cypher": [shown],
        "paths": [
            {
                "kind": "graph",
                "title": "Decision trace",
                "nodes": [
                    _node(row["id"], "Decision", row["id"]),
                    _node(row["person_id"], "Person", row["person"]),
                    _node(service_id, "Service", row["service"]),
                    _node(row["document_id"], "Document", row["document"]),
                ],
                "edges": [
                    {"source": row["id"], "target": row["person_id"], "type": "DECIDED_BY"},
                    {"source": row["id"], "target": service_id, "type": "ABOUT incident AFFECTS"},
                    {"source": row["id"], "target": row["document_id"], "type": "CITES"},
                ],
            }
        ],
        "actions": [],
        "facts": {
            "decision_id": row["id"],
            "summary": row["summary"],
            "decided_by": row["person_id"],
            "document": row["document"],
            "service_id": service_id,
        },
    }


def recall(chosen: Plan, user_id: str) -> dict:
    del chosen
    memory = connect().select_graph(memory_name(user_id))
    episodes, shown_e = _run_on(
        memory,
        "MATCH (u:User {id: $uid})-[:HAD_EPISODE]->(e:Episode) "
        "RETURN e.id AS id, e.session_id AS session_id, e.question AS question, "
        "e.answer AS answer, e.tool AS tool, e.ts AS ts "
        "ORDER BY e.ts DESC LIMIT 6",
        {"uid": user_id},
    )
    procedures, shown_p = _run_on(
        memory,
        "MATCH (u:User {id: $uid})-[:FOLLOWS]->(p:Procedure) "
        "RETURN p.service_id AS service_id, p.person_id AS person_id, p.steps AS steps, p.ts AS ts "
        "ORDER BY p.ts DESC",
        {"uid": user_id},
    )
    facts, shown_f = _run_on(
        memory,
        "MATCH (u:User {id: $uid})-[:REMEMBERS]->(f:Fact) "
        "RETURN f.id AS id, f.text AS text, f.ts AS ts ORDER BY f.ts DESC LIMIT 6",
        {"uid": user_id},
    )
    if not episodes and not procedures and not facts:
        answer = "This operator has no episodes, facts, or standing orders in their memory graph yet."
    else:
        lines = []
        for episode in reversed(episodes):
            lines.append(
                f"Session {episode['session_id']} at {episode['ts']}: \"{episode['question']}\""
            )
        for procedure in procedures:
            person = _one(
                "MATCH (p:Person {id: $id}) RETURN p.name AS name",
                {"id": procedure["person_id"]},
            )
            name = person["name"] if person else procedure["person_id"]
            lines.append(f"Standing order: page {name} first when {procedure['service_id']} fails.")
        if facts:
            lines.append("Semantic facts: " + " ".join(row["text"] for row in facts))
        answer = " ".join(lines)
    return {
        "answer": answer,
        "tool": "recall",
        "agents": ["coordinator", "memory"],
        "handoffs": [{"from": "coordinator", "to": "memory", "reason": "read this operator's graph"}],
        "cypher": [shown_e, shown_p, shown_f],
        "paths": [],
        "actions": [],
        "facts": {
            "episodes": episodes,
            "episode_questions": [row["question"] for row in episodes],
            "procedures": procedures,
        },
    }


def set_procedure(chosen: Plan, user_id: str) -> dict:
    service_id = chosen.service_id or "ledger"
    person_id = chosen.person_id
    if not person_id:
        return _empty("set_procedure", chosen, "Say who to page. For example: next time the ledger fails, page Rohan first.")
    person = _one(
        "MATCH (p:Person {id: $id}) RETURN p.id AS id, p.name AS name, p.role AS role",
        {"id": person_id},
    )
    service = _one(
        "MATCH (s:Service {id: $id}) RETURN s.id AS id, s.name AS name",
        {"id": service_id},
    )
    if not person or not service:
        return _empty("set_procedure", chosen, "That person or service is not in the Harbor Pay graph.")
    steps = f"When {service['name']} fails, page {person['name']} before the company on-call."
    ts = _now()
    memory = connect().select_graph(memory_name(user_id))
    _, shown = _run_on(
        memory,
        "MERGE (u:User {id: $uid}) "
        "MERGE (p:Procedure {id: $pid}) "
        "SET p.service_id = $sid, p.person_id = $person, p.steps = $steps, p.ts = $ts "
        "MERGE (u)-[:FOLLOWS]->(p)",
        {
            "uid": user_id,
            "pid": f"PROC-override-{service_id}",
            "sid": service_id,
            "person": person_id,
            "steps": steps,
            "ts": ts,
        },
    )
    return {
        "answer": (
            f"Stored a standing order in memory_{user_id}: page {person['name']} first "
            f"when {service['name']} fails. The company graph is unchanged, so the on-call edge stays put. "
            "The next blast-radius question from this operator will follow the standing order."
        ),
        "tool": "set_procedure",
        "agents": ["coordinator", "memory"],
        "handoffs": [{"from": "coordinator", "to": "memory", "reason": "write procedural memory"}],
        "cypher": [shown],
        "paths": [
            {
                "kind": "path",
                "title": "Procedural memory",
                "nodes": [
                    _node(user_id, "User", user_id),
                    _node(person_id, "Person", person["name"]),
                    _node(service_id, "Service", service["name"]),
                ],
                "edges": [
                    {"source": user_id, "target": person_id, "type": "FOLLOWS page order"},
                    {"source": person_id, "target": service_id, "type": "PAGE_FIRST"},
                ],
            }
        ],
        "actions": [
            {"type": "WRITE_PROCEDURE", "service_id": service_id, "person_id": person_id}
        ],
        "facts": {"service_id": service_id, "person_id": person_id, "person_name": person["name"]},
    }


def search(chosen: Plan, user_id: str) -> dict:
    del user_id, chosen
    return {
        "answer": (
            "I only answer from the Harbor Pay graph. Ask what breaks if a service goes down, "
            "who worked on it, which accounts link to a flagged transaction, what a customer asked "
            "last month, what was decided last time, or what this operator already did."
        ),
        "tool": "search",
        "agents": ["coordinator"],
        "handoffs": [],
        "cypher": [],
        "paths": [],
        "actions": [],
        "facts": {},
    }


def _dependent_ids(service_id: str):
    """Prefer algo.SSpaths when it finds the same dependents as the stored DEPENDS_ON edges."""
    attempts = []
    error = None
    ss_ids: set[str] = set()
    query = (
        "MATCH (s:Service {id: $id}) "
        "CALL algo.SSpaths({sourceNode: s, relTypes: ['DEPENDS_ON'], relDirection: 'incoming', "
        "maxLen: 6, pathCount: $count}) "
        "YIELD path "
        "RETURN [n IN nodes(path) | n.id] AS node_ids"
    )
    for count in (0, 30):
        try:
            found, shown = _run(query, {"id": service_id, "count": count})
            attempts.append(shown)
            for row in found:
                for node_id in row.get("node_ids") or []:
                    if node_id and node_id != service_id:
                        ss_ids.add(node_id)
            if ss_ids:
                break
        except Exception as exc:
            error = str(exc)
            attempts.append(f"-- algo.SSpaths failed: {exc}")
            break
    found, shown = _run(
        "MATCH path = (dep:Service)-[:DEPENDS_ON*1..6]->(s:Service {id: $id}) "
        "RETURN [n IN nodes(path) | n.id] AS node_ids",
        {"id": service_id},
    )
    attempts.append(shown)
    var_ids: set[str] = set()
    for row in found:
        for node_id in row.get("node_ids") or []:
            if node_id and node_id != service_id:
                var_ids.add(node_id)
    if ss_ids and ss_ids == var_ids:
        return ss_ids, "algo.SSpaths", attempts, error
    if ss_ids and not var_ids:
        return ss_ids, "algo.SSpaths", attempts, error
    return var_ids, "cypher-variable-length", attempts, error


def _dependency_paths(service_id: str, dependent_ids: set[str], cypher: list[str]) -> list[dict]:
    if not dependent_ids:
        return []
    found, shown = _run(
        "MATCH path = (dep:Service)-[:DEPENDS_ON*1..6]->(s:Service {id: $id}) "
        "RETURN [n IN nodes(path) | n.id] AS node_ids, "
        "[n IN nodes(path) | n.name] AS node_names, "
        "[n IN nodes(path) | labels(n)[0]] AS node_labels, "
        "[r IN relationships(path) | type(r)] AS rel_types",
        {"id": service_id},
    )
    cypher.append(shown)
    best: dict[str, dict] = {}
    for row in found:
        ids = row.get("node_ids") or []
        if not ids or ids[-1] != service_id or ids[0] == service_id:
            continue
        if ids[0] not in dependent_ids:
            continue
        current = best.get(ids[0])
        if current is not None and len(current["nodes"]) <= len(ids):
            continue
        nodes = [
            _node(node_id, label, name)
            for node_id, label, name in zip(ids, row["node_labels"], row["node_names"])
        ]
        edges = [
            {"source": ids[index], "target": ids[index + 1], "type": rel}
            for index, rel in enumerate(row.get("rel_types") or [])
        ]
        best[ids[0]] = {"kind": "path", "title": "Dependency", "nodes": nodes, "edges": edges}
    return list(best.values())


def _fraud_component(account_id: str):
    attempts = []
    error = None
    component_id = None
    try:
        found, shown = _run(
            "CALL algo.WCC({nodeLabels: ['Account'], relationshipTypes: ['LINKED_TO']}) "
            "YIELD node, componentId "
            "RETURN node.id AS id, node.name AS name, componentId",
            {},
        )
        attempts.append(shown)
        component = _component_from_rows(found, account_id)
        _require_same_component(component, account_id, attempts)
        return component, "algo.WCC", attempts, _component_id(found, account_id), None
    except Exception as exc:
        error = str(exc)
        attempts.append(f"-- algo.WCC config failed: {exc}")
    try:
        found, shown = _run(
            "CALL algo.WCC(null) YIELD node, componentId "
            "RETURN node.id AS id, node.name AS name, labels(node)[0] AS label, componentId",
            {},
        )
        attempts.append(shown)
        accounts = [row for row in found if row.get("label") in (None, "Account") and str(row.get("id", "")).startswith("A-")]
        component = _component_from_rows(accounts, account_id)
        _require_same_component(component, account_id, attempts)
        return component, "algo.WCC", attempts, _component_id(accounts, account_id), None
    except Exception as exc:
        error = str(exc)
        attempts.append(f"-- algo.WCC failed: {exc}")
    found, shown = _run(
        "MATCH (a:Account {id: $id})-[:LINKED_TO*0..6]-(b:Account) "
        "RETURN DISTINCT b.id AS id, b.name AS name",
        {"id": account_id},
    )
    attempts.append(shown)
    component = {row["id"]: row["name"] for row in found}
    component.setdefault(account_id, account_id)
    return component, "cypher-variable-length", attempts, component_id, error


def _require_same_component(component: dict, account_id: str, attempts: list[str]) -> None:
    """Reject a WCC result that does not match the LINKED_TO neighborhood."""
    if account_id not in component:
        raise RuntimeError("WCC result did not include the source account")
    found, shown = _run(
        "MATCH (a:Account {id: $id})-[:LINKED_TO*0..6]-(b:Account) "
        "RETURN DISTINCT b.id AS id",
        {"id": account_id},
    )
    attempts.append(shown)
    walk = {row["id"] for row in found}
    walk.add(account_id)
    if set(component) != walk:
        raise RuntimeError(f"WCC {sorted(component)} disagrees with LINKED_TO {sorted(walk)}")


def _component_from_rows(found, account_id: str) -> dict[str, str]:
    wanted = _component_id(found, account_id)
    if wanted is None:
        return {}
    return {
        row["id"]: row.get("name") or row["id"]
        for row in found
        if row.get("componentId") == wanted and row.get("id")
    }


def _component_id(found, account_id: str):
    for row in found:
        if row.get("id") == account_id:
            return row.get("componentId")
    return None


def _page_rank():
    query = (
        "CALL algo.pageRank('Person', 'KNOWS') YIELD node, score "
        "RETURN node.id AS person_id, score"
    )
    try:
        found, shown = _run(query, {})
        scores = {row["person_id"]: float(row["score"]) for row in found if row.get("person_id")}
        return scores, shown, "algo.pageRank", None
    except Exception as exc:
        return {}, f"-- algo.pageRank failed: {exc}", "unavailable", str(exc)


def _service_details(ids: set[str]) -> list[dict]:
    if not ids:
        return []
    found, _ = _run(
        "UNWIND $ids AS sid MATCH (s:Service {id: sid}) "
        "RETURN s.id AS id, s.name AS name, s.tier AS tier ORDER BY s.name",
        {"ids": sorted(ids)},
    )
    return found


def _role_people(service_id: str, rel: str) -> list[dict]:
    if rel not in {"ON_CALL_FOR", "OWNS"}:
        raise ValueError(rel)
    found, _ = _run(
        f"MATCH (p:Person)-[:{rel}]->(s:Service {{id: $id}}) "
        "RETURN p.id AS id, p.name AS name, p.role AS role ORDER BY p.name",
        {"id": service_id},
    )
    return found


def _human_decision(service_id: str):
    return _one(
        "MATCH (d:Decision {source: 'human'})-[:ABOUT]->(:Incident)-[:AFFECTS]->(s:Service {id: $id}) "
        "MATCH (d)-[:DECIDED_BY]->(p:Person) "
        "RETURN d.id AS id, d.summary AS summary, d.decided_at AS decided_at, p.name AS person "
        "ORDER BY d.decided_at DESC LIMIT 1",
        {"id": service_id},
    )


def _read_override(user_id: str, service_id: str):
    memory = connect().select_graph(memory_name(user_id))
    try:
        found, _ = _run_on(
            memory,
            "MATCH (u:User {id: $uid})-[:FOLLOWS]->(p:Procedure {service_id: $sid}) "
            "RETURN p.person_id AS person_id, p.steps AS steps, p.ts AS ts "
            "ORDER BY p.ts DESC LIMIT 1",
            {"uid": user_id, "sid": service_id},
        )
    except Exception:
        return None
    return found[0] if found else None


def _write_fact(user_id: str, fact_id: str, text: str) -> None:
    memory = connect().select_graph(memory_name(user_id))
    _run_on(
        memory,
        "MERGE (u:User {id: $uid}) "
        "MERGE (f:Fact {id: $id}) "
        "SET f.text = $text, f.ts = $ts "
        "MERGE (u)-[:REMEMBERS]->(f)",
        {"uid": user_id, "id": fact_id, "text": text, "ts": _now()},
    )


def _write_episode(user_id: str, session_id: str, question: str, result: dict) -> str:
    episode_id = "E-" + uuid.uuid4().hex[:12]
    memory = connect().select_graph(memory_name(user_id))
    _run_on(
        memory,
        "MERGE (u:User {id: $uid}) "
        "CREATE (e:Episode {id: $id, session_id: $sid, question: $question, answer: $answer, tool: $tool, ts: $ts}) "
        "MERGE (u)-[:HAD_EPISODE]->(e)",
        {
            "uid": user_id,
            "id": episode_id,
            "sid": session_id,
            "question": question,
            "answer": result.get("answer", ""),
            "tool": result.get("tool", ""),
            "ts": _now(),
        },
    )
    return episode_id


def _write_handoffs(user_id: str, session_id: str, result: dict) -> None:
    if not result.get("handoffs"):
        return
    coord = connect().select_graph(coord_name())
    run_id = "RUN-" + uuid.uuid4().hex[:12]
    ts = _now()
    for hop in result["handoffs"]:
        _run_on(
            coord,
            "MERGE (a:Agent {name: $frm}) "
            "MERGE (b:Agent {name: $to}) "
            "CREATE (a)-[:HANDED_OFF {run_id: $run, reason: $reason, ts: $ts, user_id: $uid, session_id: $sid}]->(b)",
            {
                "frm": hop["from"],
                "to": hop["to"],
                "run": run_id,
                "reason": hop["reason"],
                "ts": ts,
                "uid": user_id,
                "sid": session_id,
            },
        )


def _memory_snapshot(user_id: str) -> dict:
    memory = connect().select_graph(memory_name(user_id))
    episodes, _ = _run_on(
        memory,
        "MATCH (u:User {id: $uid})-[:HAD_EPISODE]->(e:Episode) "
        "RETURN e.session_id AS session_id, e.question AS question, e.tool AS tool, e.ts AS ts "
        "ORDER BY e.ts DESC LIMIT 5",
        {"uid": user_id},
    )
    procedures, _ = _run_on(
        memory,
        "MATCH (u:User {id: $uid})-[:FOLLOWS]->(p:Procedure) "
        "RETURN p.service_id AS service_id, p.person_id AS person_id, p.steps AS steps "
        "ORDER BY p.ts DESC",
        {"uid": user_id},
    )
    return {"episodes": episodes, "procedures": procedures}


def _empty(tool: str, chosen: Plan, answer: str, cypher: list[str] | None = None) -> dict:
    del chosen
    return {
        "answer": answer,
        "tool": tool,
        "agents": ["coordinator"],
        "handoffs": [],
        "cypher": cypher or [],
        "paths": [],
        "actions": [],
        "facts": {},
    }


def _one(query: str, params: dict):
    found, _ = _run(query, params)
    return found[0] if found else None


def _run(query: str, params: dict):
    return _run_on(connect().select_graph(harbor_name()), query, params)


def _run_on(graph, query: str, params: dict):
    if params:
        result = graph.query(query, params)
    else:
        result = graph.query(query)
    return rows(result), _shown(query, params)


def _shown(query: str, params: dict) -> str:
    text = " ".join(query.split())
    if params:
        text += "\n-- params " + json.dumps(params, default=str)
    return text


def _node(node_id: str, label: str, name: str) -> dict:
    return {"id": node_id, "label": label, "name": name}


def _join(items) -> str:
    values = [str(item) for item in items if item]
    if not values:
        return "none"
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " and " + values[-1]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _session(session_id: str) -> str:
    session_id = session_id or "session"
    if len(session_id) > 40 or not all(ch.isalnum() or ch in "_-" for ch in session_id):
        raise ValueError("session_id must be 1-40 letters, numbers, _ or -")
    return session_id
