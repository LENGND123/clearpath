"""Pick a graph tool. Rules handle the demo questions. Grok is only a fallback picker."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass

SERVICE_ALIASES = [
    ("postgres-primary", ["postgres-primary", "postgres"]),
    ("payments-api", ["payments-api", "payments api", "payment api"]),
    ("checkout-api", ["checkout-api", "checkout"]),
    ("card-network", ["card-network", "card network"]),
    ("feature-store", ["feature-store", "feature store"]),
    ("risk-api", ["risk-api", "risk api"]),
    ("mobile-app", ["mobile-app", "mobile app"]),
    ("marketing-site", ["marketing-site", "marketing site", "marketing"]),
    ("status-page", ["status-page", "status page"]),
    ("notifications", ["notifications", "notification"]),
    ("settlement", ["settlement"]),
    ("ledger", ["ledger"]),
]

# Longest alias wins, so "mobile-app" beats a shorter token inside it.
_ALIAS_ORDER = sorted(
    ((alias, service_id) for service_id, aliases in SERVICE_ALIASES for alias in aliases),
    key=lambda item: len(item[0]),
    reverse=True,
)

STAFF = {
    "anika shah": "anika",
    "rohan mehta": "rohan",
    "sara iqbal": "sara",
    "dev patel": "dev",
    "kabir das": "kabir",
    "leela nair": "leela",
    "nia joseph": "nia",
    "ishan rao": "ishan",
    "anika": "anika",
    "rohan": "rohan",
    "sara": "sara",
    "kabir": "kabir",
    "leela": "leela",
    "nia": "nia",
    "ishan": "ishan",
    "dev": "dev",
}

CUSTOMERS = {
    "mira shah": "mira",
    "mira": "mira",
    "rahul sen": "rahul",
    "rahul": "rahul",
}

TOOLS = {
    "blast_radius",
    "who_knows",
    "fraud_ring",
    "customer_history",
    "past_decision",
    "recall",
    "set_procedure",
    "search",
}


@dataclass
class Plan:
    tool: str
    planner: str = "rules"
    service_id: str | None = None
    person_id: str | None = None
    customer_id: str | None = None
    transaction_id: str | None = None


def plan(question: str) -> Plan:
    ruled = rule_plan(question)
    if ruled.tool != "search":
        return ruled
    grok = grok_plan(question)
    if grok is not None and grok.tool in TOOLS and grok.tool != "search":
        grok.planner = "grok"
        return grok
    return ruled


def rule_plan(question: str) -> Plan:
    q = " ".join(question.lower().split())
    service_id = find_service(q)
    person_id = person_to_page(q)
    customer_id = find_customer(q)
    transaction_id = find_transaction(q)

    if person_id and any(token in q for token in ("next time", "standing order", "from now")):
        return Plan("set_procedure", service_id=service_id or "ledger", person_id=person_id)
    if "remember" in q and "page" in q and person_id:
        return Plan("set_procedure", service_id=service_id or "ledger", person_id=person_id)

    if any(token in q for token in ("earlier session", "previous session", "across sessions", "already ask", "did i ask")):
        return Plan("recall")
    if "session" in q and "decid" in q:
        return Plan("recall")

    if any(token in q for token in ("decid", "decision", "failover", "runbook")) and any(
        token in q for token in ("ledger", "incident", "failed", "last time", "service")
    ):
        return Plan("past_decision", service_id=service_id or "ledger")

    if any(token in q for token in ("break", "goes down", "go down", "blast", "outage", "depend")):
        return Plan("blast_radius", service_id=service_id)

    if "who" in q and any(token in q for token in ("worked", "know", "on call", "on-call", "page", "expert")):
        return Plan("who_knows", service_id=service_id)

    if transaction_id or any(token in q for token in ("account", "flagged", "transaction", "fraud", "mule", "linked")):
        return Plan("fraud_ring", transaction_id=transaction_id)

    if customer_id or any(token in q for token in ("ask", "asked", "ticket", "customer", "refund", "last month")):
        return Plan("customer_history", customer_id=customer_id)

    return Plan("search")


def find_service(question: str) -> str | None:
    q = question.lower()
    for alias, service_id in _ALIAS_ORDER:
        if alias in q:
            return service_id
    return None


def find_customer(question: str) -> str | None:
    q = question.lower()
    for alias, customer_id in sorted(CUSTOMERS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return customer_id
    return None


def find_transaction(question: str) -> str | None:
    match = re.search(r"\btx-\d+\b", question.lower())
    if not match:
        return None
    return match.group(0).upper()


def person_to_page(question: str) -> str | None:
    match = re.search(r"\bpage\s+([a-z]+(?:\s+[a-z]+)?)", question.lower())
    if not match:
        return None
    phrase = match.group(1)
    if phrase in STAFF:
        return STAFF[phrase]
    first = phrase.split()[0]
    return STAFF.get(first)


def grok_plan(question: str) -> Plan | None:
    key = os.getenv("XAI_API_KEY")
    if not key:
        return None
    prompt = (
        "Choose one tool for a graph agent. Do not answer the question. "
        "Return JSON only with keys tool, service_id, person_id, customer_id, transaction_id. "
        "tool must be one of: blast_radius, who_knows, fraud_ring, customer_history, "
        "past_decision, recall, set_procedure, search. Use null for unknown ids.\n"
        f"Question: {question}"
    )
    body = json.dumps({"model": "grok-4.7", "input": prompt}).encode()
    request = urllib.request.Request(
        "https://api.x.ai/v1/responses",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode())
    except Exception:
        return None
    text = _output_text(payload)
    parsed = _parse_json(text)
    if not isinstance(parsed, dict):
        return None
    tool = parsed.get("tool")
    if tool not in TOOLS:
        return None
    return Plan(
        tool=tool,
        planner="grok",
        service_id=_clean(parsed.get("service_id")),
        person_id=_clean(parsed.get("person_id")),
        customer_id=_clean(parsed.get("customer_id")),
        transaction_id=_clean(parsed.get("transaction_id")),
    )


def _clean(value):
    if value in (None, "", "null"):
        return None
    return str(value)


def _output_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _parse_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
