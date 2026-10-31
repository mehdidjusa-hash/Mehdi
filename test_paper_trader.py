import json, os, sqlite3, tempfile
import paper_trader as p

def cfg(tmp):
    return {'initial_cash_rial':50000000,'market_watch_url':'unused','poll_seconds':1,'stale_after_seconds':180,'max_positions':4,'max_risk_per_trade_fraction':0.01,'max_daily_loss_fraction':0.03,'fee_rate':0.0037,'slippage_bps':25,'min_trade_value_rial':1000000,'min_score':0.3,'data_dir':tmp,'report_dir':tmp}

def test_normalize_items():
    rows=p.normalize_items([{'instrumentId':'X','instrumentName':'X','lastPrice':105,'closingPrice':100,'yesterdayPrice':100,'tradeVolume':100000,'tradeValue':6000000000}])
    assert len(rows)==1 and rows[0]['last']==105 and rows[0]['value']==6000000000

def test_buy_is_not_duplicated():
    with tempfile.TemporaryDirectory() as d:
        c=cfg(d); db=os.path.join(d,'t.db'); con=p.setup_db(c,db)
        fixture=os.path.join(os.path.dirname(__file__),'test_fixture.json')
        first=p.run_once(c,con,fixture); second=p.run_once(c,con,fixture)
        assert len(first['buys'])==1
        assert len(second['buys'])==0
        assert con.execute("select count(*) from trades where side='BUY'").fetchone()[0]==1

def test_stop_loss_exit():
    with tempfile.TemporaryDirectory() as d:
        c=cfg(d); db=os.path.join(d,'t.db'); con=p.setup_db(c,db)
        con.execute("insert into positions values('X','X',100,100,101,120,'t','momentum')")
        con.execute("insert or replace into state values('cash','0')"); con.commit()
        rows=[{'id':'X','name':'X','last':100,'close':100,'prev':100,'volume':1,'value':6000000000,'low':99,'high':101}]
        exits=p.mark_and_exit(con,rows,c); con.commit()
        assert exits and con.execute('select count(*) from positions').fetchone()[0]==0
        assert con.execute("select side from trades").fetchone()[0]=='SELL'
