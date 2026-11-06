"""Nifty paper-trading worker. Runs daily on GitHub Actions, writes docs/data.json.
Data connector: Yahoo Finance (free). To switch source later, replace load_data() only."""
import json, os, datetime as dt
import numpy as np, pandas as pd, yfinance as yf

SYMBOL = "^NSEI"          # Nifty 50 index (proxy for NIFTYBEES / Nifty futures)
CAPITAL = 100000          # Rs per day, no leverage
SLIPPAGE = 0.0002         # 0.02% per side
GAP = 0.003               # 0.3% gap threshold
OOS_YEARS = 2             # last 2 years = out-of-sample
DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")


# ---------- connector ----------
def load_data():
    df = yf.download(SYMBOL, period="12y", interval="1d", auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[df.Open > 0]


# ---------- Zerodha intraday equity charges (verify current rates on zerodha.com/charges) ----------
def charges(buy_val, sell_val):
    brk = min(20, buy_val * 0.0003) + min(20, sell_val * 0.0003)
    stt = sell_val * 0.00025
    exch = (buy_val + sell_val) * 0.0000297
    sebi = (buy_val + sell_val) * 0.000001
    gst = 0.18 * (brk + exch + sebi)
    stamp = buy_val * 0.00003
    return brk + stt + exch + sebi + gst + stamp


# ---------- features ----------
def prepare(df):
    d = df.copy()
    d["prev_close"] = d.Close.shift(1)
    d["gap"] = d.Open / d.prev_close - 1
    d["overnight"] = d.gap
    d["intraday"] = d.Close / d.Open - 1
    ma50 = d.Close.rolling(50).mean().shift(1)
    ma200 = d.Close.rolling(200).mean().shift(1)
    slope = ma50.pct_change(20)
    d["regime"] = np.where((ma50 > ma200) & (slope > 0), "up",
                   np.where((ma50 < ma200) & (slope < 0), "down", "sideways"))
    d.loc[ma200.isna(), "regime"] = "n/a"
    d["above_ma50"] = d.prev_close > ma50
    d["dow"] = d.index.dayofweek
    return d.dropna(subset=["prev_close"])


# ---------- strategies: return position in {-1,0,1}, decided at the open ----------
def gap_fade(d):
    return np.where(d.gap > GAP, -1, np.where(d.gap < -GAP, 1, 0))

def gap_follow(d):
    return -gap_fade(d)

def trend_long(d):
    return np.where(d.above_ma50 & d.regime.eq("up"), 1, 0)

STRATS = {"Gap fade": gap_fade, "Gap follow": gap_follow, "Trend-day long": trend_long}


def simulate(d, pos):
    r = d.intraday.values
    pos = np.asarray(pos)
    gross = pos * CAPITAL * r
    cost = np.zeros(len(d))
    for i, p in enumerate(pos):
        if p == 0:
            continue
        entry = CAPITAL
        exit_ = CAPITAL * (1 + r[i] * p)
        buy, sell = (entry, exit_) if p == 1 else (exit_, entry)
        cost[i] = charges(buy, sell) + 2 * SLIPPAGE * CAPITAL
    out = pd.DataFrame({"gross": gross, "cost": cost, "net": gross - cost,
                        "pos": pos, "regime": d.regime.values}, index=d.index)
    return out


def stats(x):
    traded = x[x.pos != 0]
    n = len(traded)
    if n == 0:
        return dict(trades=0, net=0, avg_pct=0, win=0, costs=0, tstat=0, maxdd=0)
    pct = traded.net / CAPITAL * 100
    t = pct.mean() / (pct.std(ddof=1) / np.sqrt(n)) if n > 2 and pct.std() > 0 else 0
    eq = x.net.cumsum()
    return dict(trades=int(n), net=round(float(x.net.sum()), 0), avg_pct=round(float(pct.mean()), 4),
                win=round(float((traded.net > 0).mean() * 100), 1), costs=round(float(x.cost.sum()), 0),
                tstat=round(float(t), 2), maxdd=round(float((eq - eq.cummax()).min()), 0))


def tstat(s):
    s = s.dropna()
    return float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))) if len(s) > 2 and s.std() > 0 else 0.0


def pattern_block(d):
    def row(label, s):
        return dict(label=label, n=int(len(s)), mean_pct=round(float(s.mean() * 100), 4),
                    t=round(tstat(s), 2), up_pct=round(float((s > 0).mean() * 100), 1))
    rows = [row("Overnight (prev close to open)", d.overnight), row("Intraday (open to close)", d.intraday)]
    for lab, m in [("Gap up > 0.3%", d.gap > GAP), ("Gap down < -0.3%", d.gap < -GAP)]:
        rows.append(row(f"Intraday after {lab}", d.intraday[m]))
    for reg in ["up", "down", "sideways"]:
        rows.append(row(f"Intraday in {reg} regime", d.intraday[d.regime == reg]))
    for i, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        rows.append(row(f"Intraday on {nm}", d.intraday[d.dow == i]))
    return rows


def main():
    os.makedirs(DOCS, exist_ok=True)
    d = prepare(load_data())
    d = d[d.regime != "n/a"]
    state_path = os.path.join(DOCS, "state.json")
    if os.path.exists(state_path):
        start = json.load(open(state_path))["paper_start"]
    else:
        start = str(dt.date.today())
        json.dump({"paper_start": start}, open(state_path, "w"))
    split = d.index[-1] - pd.DateOffset(years=OOS_YEARS)

    res = {}
    for name, fn in STRATS.items():
        sim = simulate(d, fn(d))
        ins, oos = sim[sim.index <= split], sim[sim.index > split]
        paper = sim[sim.index >= pd.Timestamp(start)]
        by_reg = {r: stats(sim[sim.regime == r]) for r in ["up", "down", "sideways"]}
        o = stats(oos)
        verdict = "possible edge (keep paper trading)" if (o["avg_pct"] > 0 and o["tstat"] > 2) \
            else "no reliable edge after costs"
        cum = sim.net.cumsum().iloc[-500:]
        res[name] = dict(all=stats(sim), in_sample=stats(ins), out_of_sample=o, by_regime=by_reg,
                         paper=stats(paper), verdict=verdict,
                         equity=[[str(i.date()), round(float(v), 0)] for i, v in cum.items()],
                         paper_trades=[dict(date=str(i.date()), pos=int(r.pos), gross=round(float(r.gross), 0),
                                            cost=round(float(r.cost), 0), net=round(float(r.net), 0))
                                       for i, r in paper[paper.pos != 0].tail(60).iterrows()])
    out = dict(updated=dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), symbol=SYMBOL, capital=CAPITAL,
               paper_start=start, last_data_date=str(d.index[-1].date()), oos_from=str(split.date()),
               current_regime=str(d.regime.iloc[-1]), patterns=pattern_block(d), strategies=res)
    json.dump(out, open(os.path.join(DOCS, "data.json"), "w"), indent=1)
    print("done", out["updated"])


if __name__ == "__main__":
    main()
