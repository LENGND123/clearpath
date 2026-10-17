# Submission sheet

Register and submit at https://www.wemakedevs.org/hackathons/falkordb before **18 October 2026, 11:59 PM IST**. Luma reminders do not count. The form is on the WeMakeDevs page after you sign in and register.

## Paste into the form

**Project name:** Clearpath

**Tagline:** An on-call agent that pages, freezes, and remembers only from a FalkorDB graph.

**Tracks:** Agents That Act on Connected Data; Agent Memory and Coordination; Company Brain

**Repository:** https://github.com/LENGND123/clearpath

**Live app:** https://nikon-age-quotations-arlington.trycloudflare.com

That address reaches the desk on this PC. It stays up while the computer is awake and the tunnel is running. Local fallback: `docker compose up --build`, then http://localhost:8080. FalkorDB Browser is http://localhost:3000.

**Demo video:** https://github.com/LENGND123/clearpath/raw/refs/heads/main/demo/clearpath-demo.webm

The file is also at `demo/clearpath-demo.webm`. It is about one minute, with captions, and follows the shot list below.

**Short description:**

Clearpath is the on-call desk for Harbor Pay, a fictional payments company. FalkorDB holds the company graph, one private memory graph per operator, and a coordination graph for agent handoffs. The agent computes a service blast radius with shortest paths, pages the on-call (or a standing order, or PageRank when nobody is on call), freezes the weakly connected component of a flagged transfer, and answers customer and decision questions from the edges. A new session still sees what the operator did. A different operator does not. Every sentence is backed by a query shown in the UI. All seed data is synthetic. Grok was used as a coding assistant and is not required to run the demo.

**AI disclosure:**

Grok, in Grok Build, assisted with the code, tests, README, and this text on 17 October 2026. I reviewed the graph model and the queries. The running demo does not call an LLM. If XAI_API_KEY is set, Grok may only choose a tool when the rule planner does not recognize the question. FalkorDB still produces the rows.

## Shot list for the video

1. Show the desk and say Harbor Pay is synthetic and FalkorDB is the source of every action.
2. Ask what breaks if the ledger goes down. Point at Sara, the on-call edge, and the new incident.
3. Say "next time the ledger fails, page Rohan first." Open a new session and ask again. Point at Rohan being paged while Sara remains on call.
4. Change the operator to priya and show that she still pages Sara.
5. Ask about TX-1042 and show A-100 still open.
6. Ask what Mira asked last month, then what was decided the last time ledger failed.
7. Open http://localhost:3000 and show the `harbor` graph, or show the Cypher panel.

Keep it under three minutes. Talk over the clicks. The judges need to see the graph change the action.

## Before you hit submit

- Tests on the public repo are green: the GitHub Actions run named `test`.
- You can explain, without reading the code line by line: separate graphs, `DEPENDS_ON` direction, on-call versus PageRank, WCC freeze, per-operator memory, human versus agent decisions.
- Publish `BLOG.md` if you want the blog prize, and put that URL in the form.
- Ship address for the t-shirt is collected by the organizers if you place in the top 50. Use the address you want a parcel sent to.
