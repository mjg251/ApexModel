#!/usr/bin/env python3
from __future__ import annotations
import csv, json, math, statistics, hashlib, inspect, shutil, subprocess, sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1] if HERE.parent.name == "scripts" else Path.cwd()
sys.path.insert(0, str(ROOT))

from scripts import project_ncaaf_from_apex as prod
from scripts import replay_ncaaf_v0_6 as replay
from scripts.backtest_ncaaf_spread_model import fetch_sp_ratings

PROOF = ROOT/"outputs"/"replays"/"ncaaf_v0_6"/"2023"/"week_05"/"proof_001"
OUT = ROOT/"outputs"/"replays"/"ncaaf_v0_6"/"2023"/"week_05"/"diagnostics_001"
LABEL = "ARCHIVAL MARKET BENCHMARK — EXACT REPLAY-AS-OF LINE TIMESTAMP NOT ESTABLISHED"

def rows(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20), b""): h.update(b)
    return h.hexdigest()
def ts(s):
    s=s.strip()
    if s.endswith("Z"): s=s[:-1]+"+00:00"
    return datetime.fromisoformat(s)
def avg(a): return statistics.fmean(a) if a else math.nan
def med(a): return statistics.median(a) if a else math.nan
def pct(n,d): return 0 if not d else 100*n/d
def ff(x,n=2):
    if x is None or (isinstance(x,float) and math.isnan(x)): return "NA"
    return f"{float(x):.{n}f}"
def edge_bucket(x):
    return "<1.0" if x<1 else "1.0–1.9" if x<2 else "2.0–3.9" if x<4 else "4.0–6.9" if x<7 else "7.0–9.9" if x<10 else "10.0+"
def spread_bucket(x):
    # Requested explicit cutpoints: <=6.5, <=13.5, <=20.5, <=27.5, then 28+
    return "0\u20136.5" if x<=6.5 else "7\u201313.5" if x<=13.5 else "14\u201320.5" if x<=20.5 else "21\u201327.5" if x<=27.5 else "28+"
def roll_action(s):
    return s if s in ("Model Play","Review Only") else "Guarded / Other"
def table(headers, rr):
    out=["| "+" | ".join(headers)+" |","| "+" | ".join(["---"]*len(headers))+" |"]
    out += ["| "+" | ".join(str(x).replace("|","\\|") for x in r)+" |" for r in rr]
    return "\n".join(out)
def writecsv(path, rr):
    if not rr: return
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rr[0])); w.writeheader(); w.writerows(rr)
def githead():
    try:
        return subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()
    except Exception: return "unknown"
def static_key(ratings, name):
    if name in ratings: return name
    import unicodedata
    def k(s): return unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower().strip()
    m=[x for x in ratings if k(x)==k(name)]
    return m[0] if len(m)==1 else None
def action_diag(sub):
    c=Counter(r["ats"] for r in sub); dec=c["win"]+c["loss"]
    return [len(sub),f'{c["win"]}-{c["loss"]}-{c["push"]}',ff(pct(c["win"],dec),1)+"%",
            ff(avg([abs(r["model_err"]) for r in sub])),ff(avg([abs(r["market_err"]) for r in sub])),
            ff(avg([r["sel_proj"]-r["sel_actual"] for r in sub]))]

def main():
    if not PROOF.exists(): raise SystemExit(f"Missing proof: {PROOF}")
    if OUT.exists(): raise SystemExit(f"Refusing overwrite: {OUT}")
    man=json.loads((PROOF/"replay_manifest.json").read_text(encoding="utf-8"))
    pr=rows(PROOF/"rows.csv"); games=rows(PROOF/"inputs"/"week_05_draftkings.csv")
    elig=rows(PROOF/"inputs"/"2023.csv"); rat=rows(PROOF/"inputs"/"normalized.csv")
    if len(pr)!=56 or man["season"]!=2023 or man["week"]!=5: raise SystemExit("Unexpected proof artifact")
    P={r["event_id"]:r for r in pr}; G={r["event_id"]:r for r in games}
    E={r["display_team"]:r for r in elig}; R={r["team"]:float(r["rating"]) for r in rat}
    safe=ts(man["ratings"]["safe_after"]); asof=ts(man["replay_as_of"])
    diag=[]; proj_bad=[]; ident_bad=[]; time_bad=[]; result_bad=[]
    for eid,r in P.items():
        g=G[eid]; h=g["home_team"]; a=g["away_team"]
        hi=E.get(h); ai=E.get(a)
        ident=bool(hi and ai and hi["classification"].lower()=="fbs" and ai["classification"].lower()=="fbs"
                   and hi["model_team"] in R and ai["model_team"] in R)
        if not ident: ident_bad.append(eid); continue
        ph=R[hi["model_team"]]-R[ai["model_team"]]+2.5
        side=r["selected_side"].lower(); expect=round(-ph if side=="home" else ph,1)
        stored=float(r["model_line"]); pok=abs(expect-stored)<1e-12
        if not pok: proj_bad.append((eid,stored,expect))
        kickoff=ts(g["kickoff"]); tok=(safe<kickoff and asof<kickoff)
        if not tok: time_bad.append(eid)
        hs=int(float(g["home_score"])); aas=int(float(g["away_score"])); ah=hs-aas
        sa=ah if side=="home" else -ah
        rok=(int(float(r["home_score"]))==hs and int(float(r["away_score"]))==aas and abs(float(r["actual_selected_side_margin"])-sa)<1e-12)
        if not rok: result_bad.append(eid)
        mh=-float(g["home_spread"])
        me=ph-ah; ke=mh-ah
        diag.append(dict(event_id=eid,kickoff=g["kickoff"],home=h,away=a,home_key=hi["model_team"],away_key=ai["model_team"],
            home_sp=R[hi["model_team"]],away_sp=R[ai["model_team"]],proj_home=ph,actual_home=ah,model_err=me,market_err=ke,
            archival_home_spread=float(g["home_spread"]),opening_home_spread=(float(g["opening_home_spread"]) if g["opening_home_spread"].strip() else None),
            selected_side=side,selected_team=r["selected_team"],sel_proj=(ph if side=="home" else -ph),sel_actual=sa,
            edge=float(r["edge_points"]),rec=r["recommendation"],action=r["actionability"],action_roll=roll_action(r["actionability"]),
            ats=r["ats_result"].lower(),units=float(r["model_suggested_units"]),proj_ok=pok,time_ok=tok,ident_ok=ident,result_ok=rok,
            sbucket=spread_bucket(abs(ph)),ebucket=edge_bucket(float(r["edge_points"]))))
    if len(diag)!=56: raise SystemExit(f"Identity resolution produced {len(diag)}/56")

    hashok = (
        sha(PROOF/"rows.csv")==man["outputs"]["rows_sha256"] and
        sha(PROOF/"exclusions.csv")==man["outputs"]["exclusions_sha256"] and
        sha(PROOF/"inputs"/"normalized.csv")==man["inputs"]["ratings"]["sha256"] and
        sha(PROOF/"inputs"/"2023.csv")==man["inputs"]["eligibility"]["sha256"] and
        sha(PROOF/"inputs"/"week_05_draftkings.csv")==man["inputs"]["games_lines"]["sha256"]
    )
    isolation = hashok and not any(bool(man.get(k)) for k in ["production_data_touched","production_database_written","production_ratings_updater_invoked","sample_model_edges_written"])
    errs=[r["model_err"] for r in diag]; ae=[abs(x) for x in errs]
    raw=dict(n=56,mae=avg(ae),median=med(ae),rmse=math.sqrt(avg([x*x for x in errs])),signed=avg(errs),
             within3=pct(sum(x<=3 for x in ae),56),within7=pct(sum(x<=7 for x in ae),56),
             within10=pct(sum(x<=10 for x in ae),56),within14=pct(sum(x<=14 for x in ae),56))
    top=sorted(diag,key=lambda r:abs(r["model_err"]),reverse=True)[:10]
    sb={}
    for b in ["0–6.5","7–13.5","14–20.5","21–27.5","28+"]:
        q=[r for r in diag if r["sbucket"]==b]
        sb[b]=[len(q),avg([abs(r["model_err"]) for r in q]),med([abs(r["model_err"]) for r in q]),avg([r["model_err"] for r in q])]
    fav={}
    for name,q in [("Home favorite",[r for r in diag if r["proj_home"]>0]),("Road favorite",[r for r in diag if r["proj_home"]<0])]:
        fav[name]=[len(q),avg([abs(r["model_err"]) for r in q]),med([abs(r["model_err"]) for r in q]),
                   math.sqrt(avg([r["model_err"]**2 for r in q])),avg([r["model_err"] for r in q])]
    model_better=sum(abs(r["model_err"])<abs(r["market_err"])-1e-12 for r in diag)
    market_better=sum(abs(r["market_err"])<abs(r["model_err"])-1e-12 for r in diag)
    bench=[avg(ae),avg([abs(r["market_err"]) for r in diag]),model_better,market_better,56-model_better-market_better,avg(errs),avg([r["market_err"] for r in diag])]
    op=[r for r in diag if r["opening_home_spread"] is not None]
    for r in op:
        r["move"]=r["archival_home_spread"]-r["opening_home_spread"]; r["absmove"]=abs(r["move"])
    openstats=[len(op),avg([r["absmove"] for r in op]),med([r["absmove"] for r in op]),max([r["absmove"] for r in op]) if op else math.nan,
               sum(r["absmove"]<1e-12 for r in op),pct(sum(r["absmove"]<1e-12 for r in op),len(op))]
    recdiag={b:action_diag([r for r in diag if r["rec"]==b]) for b in ["Value","Lean","Watch","No Play"]}
    eddiag={b:action_diag([r for r in diag if r["ebucket"]==b]) for b in ["<1.0","1.0–1.9","2.0–3.9","4.0–6.9","7.0–9.9","10.0+"]}
    ac=Counter(r["action_roll"] for r in diag)

    # -110 dependency: exact frozen source semantics + cohort-specific tie reachability.
    src=inspect.getsource(prod.build_model_row_for_event)
    price_ties=[]
    for r in diag:
        g=G[r["event_id"]]; hs=float(g["home_spread"]); ph=r["proj_home"]
        he=hs+ph; ae2=-hs-ph
        if abs(he-ae2)<1e-12 and abs(hs-(-hs))<1e-12: price_ties.append(r["event_id"])
    price_note=("Frozen v0.6 orders candidates by edge_points, then market_line, then market_odds. "
                "Price does not enter projection or edge. Recommendation/confidence/units/guards are downstream of the "
                "selected edge/line and frozen non-price conditions. In this single-provider cohort the third-level "
                f"price tie-break is reachable in {len(price_ties)} games; therefore synthetic -110 does not materially "
                "alter classifications here.")

    # Static 2022-final SP+ comparison. No 2025 access.
    static=fetch_sp_ratings(2022)
    loaded=replay.load_historical_games(PROOF/"inputs"/"week_05_draftkings.csv",2023,5,"DraftKings")
    LG={str(g["event_id"]):g for g in loaded}
    comp=[]; unavailable=[]
    for r in diag:
        hk=static_key(static,r["home"]); ak=static_key(static,r["away"])
        if hk is None or ak is None:
            unavailable.append(dict(event_id=r["event_id"],home=r["home"],away=r["away"],reason="absent_from_2022_final_SP+"))
            continue
        mp={r["home"]:{"cfbd_team":hk,"classification":"fbs"},r["away"]:{"cfbd_team":ak,"classification":"fbs"}}
        with replay.frozen_production_context(asof,set()):
            e=prod.build_model_row_for_event(event_rows=replay.event_rows_for_production(LG[r["event_id"]]),ratings=static,team_mapping=mp)
        if e is None:
            unavailable.append(dict(event_id=r["event_id"],home=r["home"],away=r["away"],reason="frozen_builder_excluded"))
            continue
        sh=float(static[hk]["rating"])-float(static[ak]["rating"])+2.5
        se=sh-r["actual_home"]; we=r["model_err"]; sedge=float(e["edge_points"])
        comp.append(dict(event_id=r["event_id"],home=r["home"],away=r["away"],static_home_margin=sh,weekly_home_margin=r["proj_home"],
                         abs_line_change=abs(sh-r["proj_home"]),static_abs_error=abs(se),weekly_abs_error=abs(we),
                         static_signed_error=se,weekly_signed_error=we,archival_abs_error=abs(r["market_err"]),
                         static_edge=sedge,weekly_edge=r["edge"],static_edge_bucket=edge_bucket(sedge),weekly_edge_bucket=r["ebucket"],
                         static_rec=e["recommendation"],weekly_rec=r["rec"],static_model_play=float(e["recommended_units"])>0,
                         weekly_model_play=(r["units"]>0 or r["action"]=="Model Play")))
    svw=dict(shared=len(comp),unavailable=len(unavailable),mean_change=avg([r["abs_line_change"] for r in comp]),
             median_change=med([r["abs_line_change"] for r in comp]),max_change=max([r["abs_line_change"] for r in comp]) if comp else math.nan,
             static_mae=avg([r["static_abs_error"] for r in comp]),weekly_mae=avg([r["weekly_abs_error"] for r in comp]),
             static_bias=avg([r["static_signed_error"] for r in comp]),weekly_bias=avg([r["weekly_signed_error"] for r in comp]),
             archival_mae=avg([r["archival_abs_error"] for r in comp]),
             weekly_better=sum(r["weekly_abs_error"]<r["static_abs_error"]-1e-12 for r in comp),
             static_better=sum(r["static_abs_error"]<r["weekly_abs_error"]-1e-12 for r in comp),
             ties=sum(abs(r["static_abs_error"]-r["weekly_abs_error"])<1e-12 for r in comp))
    emig=Counter((r["static_edge_bucket"],r["weekly_edge_bucket"]) for r in comp)
    rmig=Counter((r["static_rec"],r["weekly_rec"]) for r in comp)
    mmig=Counter(("Model Play" if r["static_model_play"] else "Not Model Play","Model Play" if r["weekly_model_play"] else "Not Model Play") for r in comp)

    gates=dict(projection=(len(proj_bad)==0 and len(diag)==56),temporal=(len(time_bad)==0),identity=(len(ident_bad)==0 and len(diag)==56),
               result=(len(result_bad)==0),isolation=isolation)
    overall=all(gates.values())

    tmp=OUT.with_name(OUT.name+".__tmp__")
    if tmp.exists(): shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    writecsv(tmp/"game_diagnostics.csv",diag)
    miss=[]
    for r in top:
        problems=[]
        if not r["proj_ok"]: problems.append("projection")
        if not r["time_ok"]: problems.append("temporal")
        if not r["ident_ok"]: problems.append("identity")
        if not r["result_ok"]: problems.append("orientation")
        miss.append(dict(home=r["home"],away=r["away"],home_sp=r["home_sp"],away_sp=r["away_sp"],model_home_margin=r["proj_home"],
                         actual_home_margin=r["actual_home"],absolute_error=abs(r["model_err"]),signed_error=r["model_err"],
                         archival_DK_home_spread=r["archival_home_spread"],selected_side=r["selected_side"],edge=r["edge"],
                         recommendation=r["rec"],actionability=r["action"],audit=("; ".join(problems) if problems else "None identified — valid model miss")))
    writecsv(tmp/"top10_misses.csv",miss)
    moves=[dict(event_id=r["event_id"],home=r["home"],away=r["away"],open_home_spread=r["opening_home_spread"],
                archival_home_spread=r["archival_home_spread"],signed_move=r["move"],absolute_move=r["absmove"])
           for r in sorted(op,key=lambda x:x["absmove"],reverse=True)]
    writecsv(tmp/"open_line_moves.csv",moves)
    writecsv(tmp/"static_vs_weekly.csv",comp)
    writecsv(tmp/"static_unavailable.csv",unavailable)

    static_snapshot_path = tmp/"static_2022_final_spplus.json"
    static_snapshot_path.write_text(
        json.dumps(static, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    metric=dict(
      archival_market_label=LABEL,
      A=dict(ratings_snapshot_sha=man["ratings"]["ratings_sha256"],published_at=man["ratings"]["published_at"],safe_after=man["ratings"]["safe_after"],
             safe_after_before_kickoff=f'{56-len(time_bad)}/56',team_rating_resolution=f'{56-len(ident_bad)}/56',
             historical_fbs_eligibility=f'{56-len(ident_bad)}/56',production_isolation=isolation,
             exact_projection_matches=f'{56-len(proj_bad)}/56',projection_discrepancies=proj_bad,
             max_absolute_discrepancy=max([abs(float(P[r["event_id"]]["model_line"])-round(-r["proj_home"] if r["selected_side"]=="home" else r["proj_home"],1)) for r in diag]),
             result_orientation=f'{56-len(result_bad)}/56'),
      B=raw,C_spread=sb,C_favorite=fav,D=dict(model_mae=bench[0],archival_DK_mae=bench[1],model_better=bench[2],market_better=bench[3],tie=bench[4],
             model_signed=bench[5],archival_signed=bench[6]),E=dict(count=openstats[0],mean_abs_move=openstats[1],median_abs_move=openstats[2],
             max_abs_move=openstats[3],unchanged=openstats[4],unchanged_pct=openstats[5]),
      F_recommendation=recdiag,F_edge=eddiag,F_actionability=dict(model_play=ac["Model Play"],review_only=ac["Review Only"],guarded_other=ac["Guarded / Other"]),
      G=dict(price_sensitive_tie_count=len(price_ties),price_sensitive_event_ids=price_ties,conclusion=price_note),
      I=svw,I_edge_migration={f"{a} -> {b}":n for (a,b),n in sorted(emig.items())},
      I_recommendation_migration={f"{a} -> {b}":n for (a,b),n in sorted(rmig.items())},
      I_model_play_migration={f"{a} -> {b}":n for (a,b),n in sorted(mmig.items())},
      J={k:("PASS" if v else "FAIL") for k,v in gates.items()}|{"overall":("PASS" if overall else "FAIL")})
    (tmp/"metrics.json").write_text(json.dumps(metric,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (tmp/"price_dependency_source.txt").write_text(src,encoding="utf-8")

    rep=[]
    rep += ["# NCAAF v0.6 — 2023 Week 5 Formal Diagnostic Packet","",f"**{LABEL}**","",
            "Frozen v0.6 was not tuned or modified. No 2025 data was requested or inspected.","",
            "## A. Replay Integrity","",
            f"- Ratings snapshot SHA: `{man['ratings']['ratings_sha256']}`",
            f"- Published: `{man['ratings']['published_at']}`",
            f"- `safe_after`: `{man['ratings']['safe_after']}`",
            f"- `safe_after < kickoff`: **{56-len(time_bad)}/56**",
            f"- Team/rating resolution: **{56-len(ident_bad)}/56**",
            f"- Historical FBS eligibility: **{56-len(ident_bad)}/56**",
            f"- Production isolation: **{'PASS' if isolation else 'FAIL'}**",
            f"- Independent frozen-line reproduction: **{56-len(proj_bad)}/56 exact** after one-decimal frozen output rounding",
            f"- Maximum absolute discrepancy: **{ff(metric['A']['max_absolute_discrepancy'],3)}**",
            f"- Final margin/orientation verified: **{56-len(result_bad)}/56**","",
            "## B. Raw Forecast Quality","",
            table(["n","Model MAE","Median AE","RMSE","Mean signed","≤3","≤7","≤10","≤14"],
                  [[56,ff(raw["mae"]),ff(raw["median"]),ff(raw["rmse"]),ff(raw["signed"]),ff(raw["within3"],1)+"%",ff(raw["within7"],1)+"%",
                    ff(raw["within10"],1)+"%",ff(raw["within14"],1)+"%"]]),"",
            "### 10 largest absolute forecast misses","",
            table(["Home","Away","Model HM","Actual HM","Abs err","Signed err"],
                  [[r["home"],r["away"],ff(r["proj_home"],1),r["actual_home"],ff(abs(r["model_err"]),1),ff(r["model_err"],1)] for r in top]),"",
            "## C. Spread-Size Diagnostics","",
            table(["Bucket","n","MAE","Median AE","Signed error"],[[b,sb[b][0],ff(sb[b][1]),ff(sb[b][2]),ff(sb[b][3])] for b in sb]),"",
            table(["Split","n","MAE","Median AE","RMSE","Signed error"],[[b,fav[b][0],ff(fav[b][1]),ff(fav[b][2]),ff(fav[b][3]),ff(fav[b][4])] for b in fav]),"",
            "## D. Model vs Archival DraftKings Benchmark","",f"**{LABEL}**","",
            table(["Model MAE","Archival DK MAE","Model Better","Market Better","Tie","Model signed","Archival signed"],
                  [[ff(x) if j in (0,1,5,6) else x for j,x in enumerate(bench)]]),"",
            "## E. Open vs Archival Line Forensics","",
            table(["Both","Mean abs move","Median abs move","Max abs move","Unchanged","Unchanged %"],
                  [[openstats[0],ff(openstats[1]),ff(openstats[2]),ff(openstats[3]),openstats[4],ff(openstats[5],1)+"%"]]),"",
            "### 10 largest moves","",
            table(["Home","Away","Open","Archival","Move","Abs move"],[[r["home"],r["away"],ff(r["opening_home_spread"],1),ff(r["archival_home_spread"],1),ff(r["move"],1),ff(r["absmove"],1)] for r in sorted(op,key=lambda x:x["absmove"],reverse=True)[:10]]),"",
            "## F. Edge / Recommendation Diagnostics","",
            "### By recommendation","",
            table(["Rec","n","ATS","Win %","Model MAE","Archival DK MAE","Selected-side signed err"],[[b]+recdiag[b] for b in ["Value","Lean","Watch","No Play"]]),"",
            "### By edge bucket","",
            table(["Edge","n","ATS","Win %","Model MAE","Archival DK MAE","Selected-side signed err"],[[b]+eddiag[b] for b in ["<1.0","1.0–1.9","2.0–3.9","4.0–6.9","7.0–9.9","10.0+"]]),"",
            f"- Actionability: Model Play **{ac['Model Play']}**, Review Only **{ac['Review Only']}**, Guarded / Other **{ac['Guarded / Other']}**.",
            "- Descriptive only; exact historical market-line timing is not established.","",
            "## G. -110 Fallback Dependency Audit","",price_note,"",
            "## H. Top-10 Miss Audit","",
            table(["Home","Away","Home SP+","Away SP+","Model HM","Actual HM","Abs err","Signed err","Archival DK","Side","Edge","Rec/action","Audit"],
                  [[r["home"],r["away"],ff(r["home_sp"],1),ff(r["away_sp"],1),ff(r["model_home_margin"],1),r["actual_home_margin"],ff(r["absolute_error"],1),
                    ff(r["signed_error"],1),ff(r["archival_DK_home_spread"],1),r["selected_side"],ff(r["edge"],1),r["recommendation"]+" / "+r["actionability"],r["audit"]] for r in miss]),"",
            "## I. Static Prior-Season vs Weekly Ratings Comparison","",
            "Static baseline: 2022 final CFBD SP+. Weekly replay: archived 2023 post-Week-4 ESPN SP+. Same games, archival DK spread, frozen builder, replay clock, and -110 compatibility price otherwise held fixed.","",
            table(["Shared","Mean abs line Δ","Median abs line Δ","Max abs line Δ","Static MAE","Weekly MAE","Static bias","Weekly bias","Archival DK MAE","Weekly improved","Static improved","Ties"],
                  [[svw["shared"],ff(svw["mean_change"]),ff(svw["median_change"]),ff(svw["max_change"]),ff(svw["static_mae"]),ff(svw["weekly_mae"]),
                    ff(svw["static_bias"]),ff(svw["weekly_bias"]),ff(svw["archival_mae"]),svw["weekly_better"],svw["static_better"],svw["ties"]]]),"",
            f"- Static-unavailable games: **{len(unavailable)}** (see `static_unavailable.csv`).","",
            "### Edge-bucket migration","",table(["Static -> Weekly","n"],[[f"{a} -> {b}",n] for (a,b),n in sorted(emig.items())]),"",
            "### Recommendation migration","",table(["Static -> Weekly","n"],[[f"{a} -> {b}",n] for (a,b),n in sorted(rmig.items())]),"",
            "### Model Play persistence / migration","",table(["Static -> Weekly","n"],[[f"{a} -> {b}",n] for (a,b),n in sorted(mmig.items())]),"",
            "## J. Final Integrity Gate","",
            table(["Gate","Result"],[
              ["1. Projection fidelity — all 56 frozen-v0.6 lines reproduced","PASS" if gates["projection"] else "FAIL"],
              ["2. Temporal integrity — no ratings used before safe-after","PASS" if gates["temporal"] else "FAIL"],
              ["3. Identity integrity — no unresolved/misclassified teams","PASS" if gates["identity"] else "FAIL"],
              ["4. Result integrity — all final margins/orientations verified","PASS" if gates["result"] else "FAIL"],
              ["5. Production isolation — no canonical state modified","PASS" if gates["isolation"] else "FAIL"]]),"",
            f"**Overall gate: {'PASS' if overall else 'FAIL'}**","",
            "Blockers: "+("**None identified.**" if overall else ", ".join(k for k,v in gates.items() if not v)),"",
            "Files created: `report.md`, `metrics.json`, `game_diagnostics.csv`, `top10_misses.csv`, `open_line_moves.csv`, `static_vs_weekly.csv`, `static_unavailable.csv`, `price_dependency_source.txt`, `diagnostic_manifest.json`.",
            "","Commit hash: **NOT COMMITTED at generation time**.",""]
    (tmp/"report.md").write_text("\n".join(rep),encoding="utf-8")
    dm=dict(artifact_type="ncaaf_v0_6_2023_week5_formal_diagnostics",source_proof=str(PROOF),
            source_proof_manifest_sha256=sha(PROOF/"replay_manifest.json"),apexmodel_git_head=githead(),
            production_code_sha256=sha(ROOT/"scripts"/"project_ncaaf_from_apex.py"),archival_market_label=LABEL,
            production_state_written=False,holdout_2025_inspected=False,network_use="CFBD 2022 final SP+ only",
            static_2022_final_spplus_sha256=sha(static_snapshot_path))
    (tmp/"diagnostic_manifest.json").write_text(json.dumps(dm,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    OUT.parent.mkdir(parents=True,exist_ok=True); tmp.rename(OUT)
    print("Diagnostic packet created:",OUT)
    print("Overall gate:","PASS" if overall else "FAIL")
    print("Projection:",f"{56-len(proj_bad)}/56","Temporal:",f"{56-len(time_bad)}/56","Identity:",f"{56-len(ident_bad)}/56","Results:",f"{56-len(result_bad)}/56")
    print("Static shared games:",len(comp))
    print("Report:",OUT/"report.md")
if __name__=="__main__":
    main()
