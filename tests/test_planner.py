from app.planner import rule_plan


def test_blast_question():
    plan = rule_plan("What breaks if the ledger service goes down?")
    assert plan.tool == "blast_radius"
    assert plan.service_id == "ledger"


def test_who_payments():
    plan = rule_plan("Who on the team has worked on payments-api before?")
    assert plan.tool == "who_knows"
    assert plan.service_id == "payments-api"


def test_who_notifications():
    plan = rule_plan("Who on the team has worked on notifications before?")
    assert plan.tool == "who_knows"
    assert plan.service_id == "notifications"


def test_fraud_question():
    plan = rule_plan("Which accounts are linked to flagged transaction TX-1042?")
    assert plan.tool == "fraud_ring"
    assert plan.transaction_id == "TX-1042"


def test_customer_question():
    plan = rule_plan("What did Mira Shah ask for last month, and was it resolved?")
    assert plan.tool == "customer_history"
    assert plan.customer_id == "mira"


def test_past_decision_is_not_memory():
    plan = rule_plan("What did we decide the last time ledger failed?")
    assert plan.tool == "past_decision"
    assert plan.service_id == "ledger"


def test_recall_sessions():
    plan = rule_plan("What did we decide in earlier sessions?")
    assert plan.tool == "recall"


def test_standing_order_names_rohan_not_sara():
    plan = rule_plan("Next time the ledger fails, page Rohan first")
    assert plan.tool == "set_procedure"
    assert plan.person_id == "rohan"
    assert plan.service_id == "ledger"


def test_status_page_alias():
    plan = rule_plan("What breaks if the status page goes down?")
    assert plan.tool == "blast_radius"
    assert plan.service_id == "status-page"
