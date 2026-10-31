#!/usr/bin/env python3
import argparse, json, os, sqlite3, time, math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import learning_agent

ROOT = os.path.dirname(os.path.abspath(__file__))

def load_config():
    with open(os.path.join(ROOT, 'config.json'), encoding='utf-8') as f: return json.load(f)

def now(): return datetime.now(timezone.utc).isoformat()

def num(x):
    try: return float(str(x).replace(',', '').replace('٬',''))
    except: return None

def pick(d, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ''): return d[k]
    return None

def normalize_items(payload):
    items = payload if isinstance(payload, list) else (payload.get('items') or payload.get('marketWatch') or payload.get('data') or [])
    out=[]
    for x in items:
        if not isinstance(x, dict): continue
        name=pick(x,'instrumentName','instrument_Name','lVal18AFC','symbol','name')
        iid=pick(x,'instrumentId','instrumentid','insCode','insCode18')
        last=num(pick(x,'lastPrice','lastprice','qTotTran5JAvg','price'))
        close=num(pick(x,'closingPrice','closingprice','priceYesterday'))
        prev=num(pick(x,'yesterdayPrice','yesterdayprice','priceYesterday'))
        vol=num(pick(x,'tradeVolume','tradevolume','qTotTran5J')) or 0
        value=num(pick(x,'tradeValue','tradevalue','qTotCap')) or 0
        low=num(pick(x,'minValue','minvalue','priceMin'))
        high=num(pick(x,'maxValue','maxvalue','priceMax'))
        if iid and name and last and last > 0:
            out.append({'id':str(iid),'name':str(name),'last':last,'close':close or last,'prev':prev or close or last,'volume':vol,'value':value,'low':low,'high':high,'observed_at':now()})
    return out

def fetch_market(cfg, fixture=None):
    if fixture:
        with open(fixture, encoding='utf-8') as f: return normalize_items(json.load(f))
    req = Request(cfg['market_watch_url'], headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    with urlopen(req, timeout=20) as r: return normalize_items(json.loads(r.read().decode('utf-8-sig')))

def setup_db(cfg, db_path=None):
    os.makedirs(os.path.join(ROOT,cfg['data_dir']), exist_ok=True)
    path=db_path or os.path.join(ROOT,cfg['data_dir'],'paper.db')
    con=sqlite3.connect(path)
    con.execute('create table if not exists snapshots(ts text, id text, name text, last real, close real, prev real, volume real, value real, low real, high real)')
    con.execute('create table if not exists trades(ts text, id text, name text, side text, qty real, price real, fee real, reason text, hypothetical integer)')
    con.execute('create table if not exists positions(id text primary key, name text, qty real, entry real, stop real, target real, opened_at text, scenario text)')
    con.execute('create table if not exists state(key text primary key, value text)')
    learning_agent.ensure_table(con)
    con.commit(); return con

def technical_agent(row):
    chg=(row['last']/row['prev']-1) if row['prev'] else 0
    intraday=(row['last']/row['close']-1) if row['close'] else 0
    spread=abs(row['last']-row['close'])/row['close'] if row['close'] else 1
    volume_score=min(1, math.log10(max(row['volume'],1))/7)
    score=0.35*max(0,min(1,(chg+0.03)/0.06))+0.25*max(0,min(1,(intraday+0.02)/0.04))+0.25*volume_score+0.15*(1-min(1,spread/0.05))
    return score, chg

def swing_agent(row):
    score, chg=technical_agent(row)
    liquid = 1 if row['value'] >= 5_000_000_000 else 0.35
    not_extreme = 1 if -0.025 <= chg <= 0.045 else 0.25
    return 0.65*score + 0.2*liquid + 0.15*not_extreme

def supervisor(row, cfg, weights=None):
    tscore, chg=technical_agent(row); sscore=swing_agent(row)
    scenario, scenario_score, scenario_scores=learning_agent.score_scenarios(row, weights)
    final=0.30*tscore+0.35*sscore+0.35*scenario_score
    ok = final >= cfg['min_score'] and row['value'] >= 5_000_000_000 and -0.03 <= chg <= 0.05
    return {'score':round(final,4),'technical':round(tscore,4),'swing':round(sscore,4),'scenario':scenario,'scenario_score':round(scenario_score,4),'scenario_scores':scenario_scores,'change':round(chg,4),'action':'BUY_CANDIDATE' if ok else 'WATCH'}

def state_num(con,key,default):
    r=con.execute('select value from state where key=?',(key,)).fetchone()
    return float(r[0]) if r else default

def set_state(con,key,value): con.execute('insert or replace into state values(?,?)',(key,str(value)))

def mark_and_exit(con, rows, cfg):
    by_id={r['id']:r for r in rows}; exits=[]
    for p in con.execute('select id,name,qty,entry,stop,target,opened_at,scenario from positions').fetchall():
        iid,name,qty,entry,stop,target,opened,scenario=p; row=by_id.get(iid)
        if not row: continue
        reason=None
        if row['last'] <= stop: reason='stop_loss'
        elif row['last'] >= target: reason='take_profit'
        if reason:
            price=row['last']*(1-cfg['slippage_bps']/10000); gross=qty*price; fee=gross*cfg['fee_rate']
            con.execute('insert into trades values(?,?,?,?,?,?,?,?,?)',(now(),iid,name,'SELL',qty,price,fee,reason,1))
            set_state(con,'cash',state_num(con,'cash',cfg['initial_cash_rial'])+gross-fee)
            learning_agent.record_result(con,scenario,(price-entry)/entry)
            con.execute('delete from positions where id=?',(iid,)); exits.append({'name':name,'reason':reason})
    return exits

def run_once(cfg, con, fixture=None):
    ts=now(); rows=fetch_market(cfg,fixture)
    for r in rows: con.execute('insert into snapshots values(?,?,?,?,?,?,?,?,?,?)',(ts,r['id'],r['name'],r['last'],r['close'],r['prev'],r['volume'],r['value'],r['low'],r['high']))
    exits=mark_and_exit(con,rows,cfg); cash=state_num(con,'cash',cfg['initial_cash_rial']); set_state(con,'cash',cash)
    held={x[0] for x in con.execute('select id from positions').fetchall()}; candidates=[]
    weights=learning_agent.get_weights(con)
    for r in rows:
        d=supervisor(r,cfg,weights)
        if d['action']=='BUY_CANDIDATE' and r['id'] not in held: candidates.append((d['score'],r,d))
    candidates.sort(reverse=True,key=lambda z:z[0]); buys=[]
    slots=max(0,cfg['max_positions']-len(held))
    for score,r,d in candidates[:slots]:
        risk_budget=cash*cfg['max_risk_per_trade_fraction']
        stop_distance=max(0.015*r['last'], r['last']-r['low'] if r['low'] and r['low']<r['last'] else 0.02*r['last'])
        qty=math.floor(risk_budget/stop_distance/10)*10; gross=qty*r['last']
        if qty<=0 or gross<cfg['min_trade_value_rial'] or gross>cash*0.35: continue
        fill=r['last']*(1+cfg['slippage_bps']/10000); fee=gross*cfg['fee_rate']
        stop=fill-stop_distance; target=fill+2*stop_distance
        reason=f"scenario={d['scenario']};supervisor={d['score']};technical={d['technical']};swing={d['swing']};hypothetical only"
        con.execute('insert into trades values(?,?,?,?,?,?,?,?,?)',(ts,r['id'],r['name'],'BUY',qty,fill,fee,reason,1))
        con.execute('insert into positions values(?,?,?,?,?,?,?,?)',(r['id'],r['name'],qty,fill,stop,target,ts,d['scenario']))
        cash-=gross+fee; set_state(con,'cash',cash); buys.append({'name':r['name'],'qty':qty,'score':d['score']})
    con.commit(); os.makedirs(os.path.join(ROOT,cfg['report_dir']),exist_ok=True)
    result={'observed_at':ts,'rows':len(rows),'buys':buys,'exits':exits,'cash':cash,'open_positions':con.execute('select count(*) from positions').fetchone()[0],'hypothetical':True}
    with open(os.path.join(ROOT,cfg['report_dir'],'latest.json'),'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False)); return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--once',action='store_true'); ap.add_argument('--poll-seconds',type=int); ap.add_argument('--fixture'); ap.add_argument('--db')
    args=ap.parse_args(); cfg=load_config(); con=setup_db(cfg,args.db); interval=args.poll_seconds or cfg['poll_seconds']
    while True:
        try: run_once(cfg,con,args.fixture)
        except Exception as e: print(json.dumps({'error':str(e),'hypothetical':True},ensure_ascii=False))
        if args.once: break
        time.sleep(interval)

if __name__=='__main__': main()
