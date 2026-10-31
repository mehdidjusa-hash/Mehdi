import learning_agent as l

def row():
    return {'last':1040,'close':1035,'prev':1000,'volume':2000000,'value':8000000000,'low':980,'high':1060}

def test_all_scenarios_are_evaluated():
    name, score, scores=l.score_scenarios(row())
    assert set(scores)==set(l.SCENARIOS)
    assert name in l.SCENARIOS and 0 <= score <= 2

def test_reward_updates_weight_bounded(tmp_path):
    import sqlite3
    con=sqlite3.connect(str(tmp_path/'l.db'))
    l.ensure_table(con)
    before=l.get_weights(con)['momentum']
    l.record_result(con,'momentum',1.0); con.commit()
    after=l.get_weights(con)['momentum']
    assert after >= before and after <= 2.0
