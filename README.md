# Clearpath

Clearpath is an on-call agent for **Harbor Pay**, a fictional payments company. FalkorDB is the only place the agent reads and writes. It will not answer a question the graph cannot support.

The demo clock is **17 October 2026**. "Last month" means September 2026. Every person, account, ticket, and incident in the seed is synthetic.

Built for [Graph Hacks](https://www.wemakedevs.org/hackathons/falkordb) (WeMakeDevs × FalkorDB), 15–18 October 2026.

**Tracks:** Agents That Act on Connected Data, Agent Memory and Coordination, and Company Brain.

## Two-minute demo

1. `docker compose up --build`
2. Open http://localhost:8080
3. Ask **what breaks if the ledger goes down**. Sara Iqbal is paged because she is `ON_CALL_FOR` ledger. The incident is written into the graph.
4. Say **next time the ledger fails, page Rohan first**. That order goes into `memory_aditya` only.
5. Click **New session** and ask the ledger question again. Rohan is paged. Sara is still the on-call in the company graph.
6. Change the operator to `priya` and ask again. Priya has no standing order, so Sara is paged.
7. Ask who worked on **payments-api** (Anika is on call) and on **notifications** (nobody is on call, so PageRank picks Leela).
8. Ask which accounts are linked to **TX-1042**. The mule ring is frozen. Mira's accounts stay open.
9. Ask what **Mira Shah** asked last month. The May ticket is ignored. The open settlement ticket is handed to Ishan, who `OWNS` settlement.
10. Ask what was decided the last time ledger failed. The answer stays the September human decision, not the incident the agent just opened.
11. Open FalkorDB Browser at http://localhost:3000 and inspect `harbor`, `memory_aditya`, and `coord`.

`python -m app.demo` prints the same story in the terminal.

## Run it

Docker Desktop, or any engine that can run Compose:

```bash
docker compose up --build
```

The app is on port **8080**. FalkorDB is on **6379**. The browser UI is on **3000**.

To run the API on the host instead of in Compose:

```bash
docker compose up falkordb
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8080
```

On macOS or Linux the venv path is `.venv/bin/activate`.

Copy `.env.example` to `.env` only if you point at FalkorDB Cloud or want Grok as a fallback planner. The scripted demo does not need `XAI_API_KEY`.

GitHub Codespaces: open the repo in a codespace, wait for `postCreateCommand`, then run `uvicorn app.main:app --host 0.0.0.0 --port 8080`.

Tests need a reachable FalkorDB:

```bash
pytest -q
```

`.github/workflows/test.yml` runs that suite on GitHub against `falkordb/falkordb:latest` once it is on the default branch.

## What the graph does

There is no second database. If FalkorDB is down, `/api/ask` returns an error.

| Question | What decides the answer | What gets written |
| --- | --- | --- |
| What breaks if this service goes down? | `algo.SSpaths` over incoming `DEPENDS_ON`, checked against the stored edges | Incident, decision, page |
| Who has worked on this service? | `WORKED_ON` → `USES`, then `ON_CALL_FOR` / `OWNS`. PageRank is used only when nobody is on call or the owner | Page action |
| Which accounts touch this flagged transfer? | `algo.WCC` on `Account` / `LINKED_TO`, accepted when it matches the traversal | Those accounts set to `frozen` |
| What did this customer ask last month? | `FILED` tickets inside September 2026, then `OWNS` for the open one | Handoff |
| What did we decide last time? | Human `Decision` → `Incident` → `Service`, plus the cited runbook | Nothing |
| What did we already do? | That operator's `memory_<user>` graph | A new episode after the read |
| Next time, page this person | Person and service must exist in `harbor` | `Procedure` in that operator's graph only |

Grok is not on this path. If `XAI_API_KEY` is set and the rule planner does not recognize the question, Grok may pick one tool name. The tool still runs the Cypher above. Grok is never given the chance to invent the answer.

## Graphs

- `harbor` is the company: people, teams, services, projects, tickets, accounts, decisions.
- `memory_<operator>` is private. Aditya's standing order is invisible to Priya. Deleting a user is `memory.delete()` on that graph.
- `coord` stores `HANDED_OFF` edges between agents so a later session can see who took the work.

### Company model

```text
(Person)-[:MEMBER_OF]->(Team)
(Person)-[:WORKED_ON]->(Project)-[:USES]->(Service)
(Person)-[:OWNS]->(Service)
(Person)-[:ON_CALL_FOR]->(Service)
(Person)-[:KNOWS]->(Person)
(Service)-[:DEPENDS_ON {weight:1}]->(Service)
(Customer)-[:HAS_ACCOUNT]->(Account)
(Customer)-[:FILED]->(Ticket)-[:ABOUT]->(Service)
(Ticket)-[:OWNED_BY]->(Person)
(Account)-[:LINKED_TO]->(Account)
(Transaction)-[:FROM_ACCOUNT]->(Account)
(Transaction)-[:TO_ACCOUNT]->(Account)
(Incident)-[:AFFECTS]->(Service)
(Decision)-[:ABOUT]->(Incident|Transaction)
(Decision)-[:DECIDED_BY]->(Person|Agent)
(Decision)-[:CITES]->(Document|Procedure)
(Decision)-[:PAGES]->(Person)
(Person)-[:OWNS]->(Domain {id:'fraud-review'})
```

Operator memory:

```text
(User)-[:HAD_EPISODE]->(Episode)
(User)-[:REMEMBERS]->(Fact)
(User)-[:FOLLOWS]->(Procedure)
```

Ledger's dependents are payments-api, risk-api, settlement, checkout-api, mobile-app, and notifications. Card-network, Postgres, the feature store, and the marketing site are not in that set: the edges point the other way, or there is no path. Status page has nothing depending on it, so the agent opens no incident.

The flagged transfer TX-1042 leaves A-880 and reaches A-221, A-334, and A-902. Mira's accounts A-100 and A-101 are a different component. So are A-500 and A-501.

## Queries the product runs

Blast radius. The procedure walks incoming `DEPENDS_ON` from the failed service. The variable-length match is the check, and the fallback when the procedure disagrees:

```cypher
MATCH (s:Service {id: $id})
CALL algo.SSpaths({
  sourceNode: s,
  relTypes: ['DEPENDS_ON'],
  relDirection: 'incoming',
  maxLen: 6,
  pathCount: 0
})
YIELD path
RETURN [n IN nodes(path) | n.id] AS node_ids
```

Who has the context, and who to page when nobody is on call:

```cypher
MATCH (p:Person)-[:WORKED_ON]->(proj:Project)-[:USES]->(s:Service {id: $id})
RETURN p.id, p.name, proj.id, proj.name

CALL algo.pageRank('Person', 'KNOWS')
YIELD node, score
RETURN node.id AS person_id, score
```

Fraud component:

```cypher
CALL algo.WCC({nodeLabels: ['Account'], relationshipTypes: ['LINKED_TO']})
YIELD node, componentId
RETURN node.id AS id, node.name AS name, componentId
```

The freeze is that component when it equals the `LINKED_TO` neighborhood of the source account. A broader component is rejected and the trace says so.

Customer history is a date filter on ticket edges, not a scan of old text:

```cypher
MATCH (c:Customer {id: $id})-[:FILED]->(t:Ticket)
WHERE t.opened_at >= $start AND t.opened_at < $end
OPTIONAL MATCH (t)-[:ABOUT]->(s:Service)
OPTIONAL MATCH (s)<-[:OWNS]-(owner:Person)
RETURN t.id, t.status, s.name, owner.name
```

The traced Cypher for the last answer is on the right side of the desk, with its parameters.

## Architecture

```text
browser  ->  FastAPI ask()
               rule planner (Grok only if the question is unrecognized)
               one tool
               FalkorDB harbor / memory_<user> / coord
               episode written after the read
```

Agents in the trace are Coordinator, Impact, People, Fraud, Support, Company, and Memory. A handoff is a real edge in `coord`, not a label in the UI.

Code map:

- `app/seed.py` builds Harbor Pay
- `app/planner.py` picks a tool
- `app/agents.py` runs the queries and writes the actions
- `app/main.py` serves the desk
- `static/` is the desk

## AI disclosure

Grok (xAI), inside Grok Build, wrote this project with Aditya Raj Singh during Graph Hacks on 17 October 2026. Aditya is responsible for the architecture, the graph model, and the behavior of the queries. The optional planner calls `grok-4.7` at `https://api.x.ai/v1/responses` and may only return a tool name.

## How to explain it

The company, each operator's memory, and the agent handoffs are separate FalkorDB graphs. A question selects a fixed query. The rows decide the sentence and the write. A standing order changes who gets paged without editing the on-call edge. A second operator does not see that order. The September ledger decision stays the human decision after the agent opens a new incident, because agent decisions are stored with `source: 'agent'`.
