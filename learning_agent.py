"""Adaptive scenario learner for paper trading only.
Uses bounded EWMA rewards and equal priors; it is not a guarantee or an autonomous trader.
"""
import math

SCENARIOS = ('momentum', 'mean_reversion', 'breakout', 'liquidity')

def ensure_table(con):
    con.execute('create table if not exists scenario_learning(scenario text primary key, n integer, avg_reward real, weight real)')
    for s in SCENARIOS:
        con.execute('insert or ignore into scenario_learning values(?,?,?,?)',(s,0,0.0,1.0))
    con.commit()

def get_weights(con):
    ensure_table(con)
    return {r[0]: max(0.15, min(2.0, float(r[3]))) for r in con.execute('select scenario,n,avg_reward,weight from scenario_learning')}

def _features(row):
    chg=(row['last']/row['prev']-1) if row['prev'] else 0
    intraday=(row['last']/row['close']-1) if row['close'] else 0
    rng=(row['high']-row['low'])/row['close'] if row.get('high') and row.get('low') and row['close'] else 0
    pos=(row['last']-row['low'])/(row['high']-row['low']) if row.get('high') and row.get('low') and row['high']>row['low'] else 0.5
    liquidity=min(1.0, math.log10(max(row.get('value',0),1))/11)
    return chg,intraday,rng,pos,liquidity

def score_scenarios(row, weights=None):
    w=weights or {s:1.0 for s in SCENARIOS}; chg,intraday,rng,pos,liq=_features(row)
    raw={
      'momentum': max(0,min(1,0.5+chg/0.08+intraday/0.04)),
      'mean_reversion': max(0,min(1,0.5-abs(chg)/0.08+(0.5-pos)*0.25)),
      'breakout': max(0,min(1,0.35+pos*0.45+rng/0.15)),
      'liquidity': max(0,min(1,liq))
    }
    adjusted={s:raw[s]*max(0.15,min(2.0,float(w.get(s,1.0)))) for s in SCENARIOS}
    scenario=max(adjusted,key=adjusted.get)
    return scenario, adjusted[scenario], adjusted

def record_result(con, scenario, reward):
    if scenario not in SCENARIOS: return
    ensure_table(con)
    row=con.execute('select n,avg_reward,weight from scenario_learning where scenario=?',(scenario,)).fetchone()
    n,avg,weight=row; n+=1; avg=0.85*avg+0.15*max(-1.0,min(1.0,float(reward)))
    # bounded adaptation; priors prevent one lucky trade from dominating
    new_weight=max(0.15,min(2.0,1.0+avg))
    con.execute('update scenario_learning set n=?,avg_reward=?,weight=? where scenario=?',(n,avg,new_weight,scenario))
