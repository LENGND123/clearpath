"""Print the demo story. Run after FalkorDB is up: python -m app.demo"""

from app.agents import ask
from app.seed import reset_all

STORY = [
    ("aditya", "sess-1", "What breaks if the ledger service goes down?"),
    ("aditya", "sess-1", "Next time the ledger fails, page Rohan first"),
    ("aditya", "sess-2", "What breaks if the ledger service goes down?"),
    ("priya", "sess-1", "What breaks if the ledger service goes down?"),
    ("aditya", "sess-2", "Who on the team has worked on payments-api before?"),
    ("aditya", "sess-2", "Who on the team has worked on notifications before?"),
    ("aditya", "sess-2", "Which accounts are linked to flagged transaction TX-1042?"),
    ("aditya", "sess-2", "What did Mira Shah ask for last month, and was it resolved?"),
    ("aditya", "sess-2", "What did we decide the last time ledger failed?"),
    ("aditya", "sess-3", "What did we decide in earlier sessions?"),
]


def main() -> None:
    reset_all()
    for user_id, session_id, question in STORY:
        result = ask(question, user_id, session_id)
        print("\n" + "=" * 72)
        print(f"{user_id} / {session_id}")
        print(question)
        print("-" * 72)
        print(result["answer"])
        print(f"tool={result['tool']} planner={result['planner']} actions={result['actions']}")


if __name__ == "__main__":
    main()
