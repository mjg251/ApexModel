#!/usr/bin/env python3
r"""
Inspect selected FBS tabs in Bill Connelly's 2023 public SP+ workbook and compare
the Week 5 tab to the approved Week 5 normalized snapshot.

Run from C:\Projects\ApexModel:
    py .\scripts\inspect_2023_spplus_fbs_tabs.py
"""

from __future__ import annotations
import csv, re, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT/"data"/"replays"/"ncaaf_v0_6"/"source_discovery"/"bill_connelly_2023_spplus_public.xlsx"
APPROVED = ROOT/"data"/"replays"/"ncaaf_v0_6"/"ratings"/"2023"/"week_05"/"normalized.csv"
M="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P="http://schemas.openxmlformats.org/package/2006/relationships"

def ci(ref):
    m=re.match(r"([A-Z]+)",ref or ""); n=0
    for ch in (m.group(1) if m else ""): n=n*26+ord(ch)-64
    return n-1

def shared(z):
    if "xl/sharedStrings.xml" not in z.namelist(): return []
    root=ET.fromstring(z.read("xl/sharedStrings.xml")); out=[]
    for si in root.findall(f"{{{M}}}si"):
        out.append("".join((t.text or "") for t in si.iter(f"{{{M}}}t")))
    return out

def smap(z):
    wb=ET.fromstring(z.read("xl/workbook.xml"))
    rs=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets={x.attrib["Id"]:x.attrib["Target"] for x in rs.findall(f"{{{P}}}Relationship")}
    out={}
    for s in wb.findall(f"{{{M}}}sheets/{{{M}}}sheet"):
        t=targets[s.attrib[f"{{{R}}}id"]].lstrip("/")
        if not t.startswith("xl/"): t="xl/"+t
        out[s.attrib["name"]]=t
    return out

def readtab(z,target,ss):
    root=ET.fromstring(z.read(target)); out=[]
    for row in root.findall(f"{{{M}}}sheetData/{{{M}}}row"):
        d={}
        for c in row.findall(f"{{{M}}}c"):
            j=ci(c.attrib.get("r","")); typ=c.attrib.get("t")
            v=c.find(f"{{{M}}}v"); val="" if v is None else (v.text or "")
            if typ=="s" and val: val=ss[int(val)]
            elif typ=="inlineStr":
                t=c.find(f"{{{M}}}is/{{{M}}}t"); val="" if t is None else (t.text or "")
            d[j]=val
        if d: out.append([d.get(k,"") for k in range(max(d)+1)])
    return out

def trim(r):
    r=list(r)
    while r and str(r[-1]).strip()=="": r.pop()
    return r

def main():
    if not XLSX.exists(): raise SystemExit(f"Missing {XLSX}")
    with zipfile.ZipFile(XLSX) as z:
        ss=shared(z); sm=smap(z)
        for name in ["FBS week 1","FBS week 5","FBS week 14","FBS week 15 (BOWLS)"]:
            print("="*80); print(name); print("="*80)
            tab=readtab(z,sm[name],ss)
            for r in tab[:8]: print(trim(r))
            print()

        tab=readtab(z,sm["FBS week 5"],ss)
        hi=tc=rc=None
        for i,row in enumerate(tab[:12]):
            vals=[str(x).strip() for x in row]
            t=None; rr=None
            for j,v in enumerate(vals):
                vl=v.lower()
                if vl in {"team","teams"}: t=j
                if vl in {"sp+","sp+ rating","rating","sp rating"}: rr=j
            if t is not None and rr is not None:
                hi=i; tc=t; rc=rr; break

        print("="*80); print("WEEK 5 VECTOR COMPARISON"); print("="*80)
        print("Detected header row:",hi)
        print("Detected team column:",tc)
        print("Detected rating column:",rc)
        if hi is None: return

        wb={}
        for row in tab[hi+1:]:
            if max(tc,rc)>=len(row): continue
            team=str(row[tc]).strip(); val=str(row[rc]).strip()
            if not team or not val: continue
            try: wb[team]=float(val)
            except ValueError: pass

        ap={}
        with APPROVED.open(newline="",encoding="utf-8-sig") as f:
            for r in csv.DictReader(f): ap[r["team"].strip()]=float(r["rating"])

        sh=sorted(set(wb)&set(ap))
        exact=sum(abs(wb[t]-ap[t])<1e-9 for t in sh)
        diffs=sorted((abs(wb[t]-ap[t]),t,wb[t],ap[t]) for t in sh)[::-1]
        print("Workbook vector teams parsed:",len(wb))
        print("Approved Week 5 teams:",len(ap))
        print("Shared exact-name teams:",len(sh))
        print("Exact rating matches among shared:",exact)
        if diffs:
            print("Maximum absolute rating difference:",diffs[0][0])
            print("Largest five differences:")
            for d in diffs[:5]: print(d)

if __name__=="__main__":
    main()
