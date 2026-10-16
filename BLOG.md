# The on-call question is a path, not a paragraph

Draft for the Graph Hacks blog prize. Publish it in your own words, with the repo link, then put that URL in the submission.

---

I spent the weekend building Clearpath, a small on-call desk for a fake company called Harbor Pay. The brief from Graph Hacks was specific: an agent is only useful if it can follow connections, remember a previous session, and show why it acted. I put all three in FalkorDB and then tried to take the database away. The product stops.

Harbor Pay does not exist. The people, accounts, and tickets are generated. That was a rule, and it also made the demo honest. I can tell you exactly why Sara Iqbal gets paged and why Mira Shah's household account does not get frozen.

## The question that looks easy

"What breaks if the ledger goes down?" is not a lookup. Ledger has one outgoing dependency, Postgres. The damage runs the other direction. Payments and risk call ledger. Checkout calls both of those. Mobile calls checkout. Settlement and notifications call payments. Card-network is a dependency of payments, so a ledger outage does not take the card network down. A card-network outage does take payments down. The arrow is the answer.

Clearpath asks FalkorDB's single-source shortest paths to walk incoming `DEPENDS_ON` edges from the failed service. It also runs the same pattern as a variable-length Cypher match. When the two sets agree, that set is the blast radius. The agent then opens one incident, pages a person, and writes a decision that cites the ledger procedure. Asking again updates that incident instead of stacking a second one.

Who gets paged is also an edge. Sara is `ON_CALL_FOR` ledger. Rohan `OWNS` it. The agent pages Sara. PageRank on the `KNOWS` graph is visible in the trace and is not allowed to overrule the on-call edge.

Notifications is the case where the score earns its keep. Nobody is on call, and nobody owns it. Two people worked on the revamp. Leela is the person other people ask for help. PageRank on `Person-[:KNOWS]->Person` ranks her above Nia, and that is why she is paged. The desk says so in the same sentence as the query.

## A freeze has to know where to stop

TX-1042 is a flagged transfer out of account A-880. A-880 links to A-221, A-334, and A-902. Mira's two accounts link to each other and to nobody in that ring. Weakly connected components, restricted to `Account` and `LINKED_TO`, names the ring. Clearpath freezes that component and leaves the others open. Leela owns fraud review, so the handoff goes to her, again because of an edge.

If the component procedure ever returns a set that does not match the link traversal, the desk refuses it and shows both results. A wrong component is worse than a fallback.

## Memory that can change the next page

Company knowledge and operator memory are different graphs in the same FalkorDB process. `harbor` holds the on-call rota. `memory_aditya` holds a standing order: next time ledger fails, page Rohan first. The next blast-radius question from Aditya pages Rohan, and the trace still draws Sara's `ON_CALL_FOR` edge so the override is visible. Priya's graph does not have the order, so the same question pages Sara.

Episodes are written after the answer is chosen, in that operator's graph. A new session can ask what already happened and get the earlier question back. Facts and procedures sit beside the episodes, which is the split people mean by semantic and procedural memory. The handoff between the impact agent and the people agent is a third graph, `coord`, so shared state is not stuffed into somebody's private memory.

The September ledger decision stays put. It is a human decision that cites a runbook. Agent decisions are marked `source: 'agent'`. "What did we decide the last time ledger failed?" filters on the human source. The agent can open a new incident without rewriting history.

## What I would keep

The useful constraint was: if the sentence is not backed by a row, do not say it. That made the UI a trace instead of a chat transcript. The Cypher stays on the screen with its parameters. The path is the product.

Grok helped me write the project during the hackathon. It does not answer Harbor Pay questions. An optional key lets it pick a tool when the rule planner does not recognize the wording, and the tool still has to query FalkorDB.

Repo: https://github.com/LENGND123/clearpath
