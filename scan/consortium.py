#!/usr/bin/env python3
"""낙찰 건의 공동수급(컨소시엄) 구성원·지분율을 전수 확인하고, 업체별 지분 반영 실적을 만든다.

원천(우선순위)
  1) 나라장터 계약정보 — work/road3/details/{공고번호}.json, work/g5/details/{공고번호}.json 의
     contracts[].corps[] (role·name·share). 필요하면 work-api.00data.kr 에서 추가 조회해
     registry/consortium_raw/ 에 캐시한다.
  2) 엑셀 '공동수급 구성(지분)' 열 — work/도로대장_최근3년_…xlsx, work/공간정보_최근5년_…xlsx
  3) 공고의 공동수급 조건(jointMethod) — '공동수급불허' 면 단독 수행이 확정된다(계약 상세가 없어도).

판정 구분(share_status)
  단독            — 계약 상세상 구성원 1인 100%, 또는 공고가 공동수급불허
  지분확인        — 구성원 전원의 지분율이 확인되고 합계가 100%
  지분미확인(구성원) — 공동수급 구성원은 확인되나 지분율이 기재되지 않음
  지분미확인(계약정보없음) — 공고가 공동수급을 허용하는데 계약 구성 정보 자체가 없음

금액 규칙
  · 확정 실적 = 낙찰금액 × (지분율/100)  ← 지분확인·단독만 합산
  · 미확인 실적 = 낙찰금액 전액(총액 기준, 상한) ← 지분미확인 건. 확정 실적과 섞지 않는다.

출력
  registry/consortium_shares.json — 공고번호별 구성원·지분·판정
사용법
  python3 consortium.py            # 캐시 사용, 부족분만 API 조회
  python3 consortium.py --no-fetch # API 조회 없이 로컬 데이터만
  python3 consortium.py --self     # ㈜웨이즈원 분야별 내역 출력
"""
import json, pathlib, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

import openpyxl

HERE = pathlib.Path(__file__).parent
WORK = HERE.parent.parent            # /workspace/work
REG = HERE / "registry"
RAW = REG / "consortium_raw"
OUT = REG / "consortium_shares.json"
KST = timezone(timedelta(hours=9))

ROAD_XLSX = WORK / "도로대장_최근3년_낙찰자별_정량평가기준.xlsx"
SPACE_XLSX = WORK / "공간정보_최근5년_토적·용도지역·연속도면_낙찰자별_정량기준.xlsx"
DETAIL_DIRS = [WORK / "road3" / "details", WORK / "g5" / "details"]

API = "https://work-api.00data.kr/api/rebrand/notice/{}"
UA = {"User-Agent": "Mozilla/5.0"}


# ---------------------------------------------------------------- 이름 정규화
def norm(name):
    import unicodedata
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = s.replace("(주)", "").replace("（주）", "").replace("㈜", "")
    s = s.replace("주식회사", "").replace("유한회사", "")
    s = re.sub(r"[\s\.·,\-_/]", "", s)
    return s.lower()


# ---------------------------------------------------------------- 원천 읽기
def _rows(path, sheet):
    if not path.exists():
        return []
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet]
    it = ws.iter_rows(min_row=2, values_only=True)
    hdr = [str(c).strip() if c is not None else "" for c in next(it)]
    out = [dict(zip(hdr, r)) for r in it if not all(c is None for c in r)]
    wb.close()
    return out


def xlsx_wins():
    """엑셀 2종의 낙찰 확정 행 — (공고번호, 분야, 낙찰자, 낙찰금액, 발주기관, 공고일, 사업명, 엑셀 지분문자열)."""
    out = []
    for d in _rows(ROAD_XLSX, "2.전체공고_낙찰·정량기준"):
        if not (d.get("낙찰자") and d.get("낙찰금액")):
            continue
        out.append({"no": str(d.get("공고번호") or "").strip(), "field": "도로대장",
                    "winner": str(d["낙찰자"]).strip(), "amount": int(d["낙찰금액"]),
                    "org": d.get("발주기관"), "date": str(d.get("공고일") or "")[:10],
                    "title": d.get("사업명"), "xlsx_joint": d.get("공동수급 구성(지분)"),
                    "src": "xlsx:도로대장3년"})
    for d in _rows(SPACE_XLSX, "2.전체공고_낙찰·정량기준"):
        if not (d.get("낙찰자") and d.get("낙찰금액")):
            continue
        f = str(d.get("분야") or "").strip() or "공간정보"
        for pre in ("②-b ", "②-c ", "② ", "③ ", "① "):
            f = f.replace(pre, "")
        out.append({"no": str(d.get("공고번호") or "").strip(), "field": f,
                    "winner": str(d["낙찰자"]).strip(), "amount": int(d["낙찰금액"]),
                    "org": d.get("발주기관"), "date": str(d.get("공고일") or "")[:10],
                    "title": d.get("사업명"), "xlsx_joint": d.get("공동수급 구성(지분)"),
                    "src": "xlsx:공간정보5년"})
    return out


def load_notice(no, fetch=True):
    """공고 상세(계약·공고 메타) — 로컬 캐시 우선, 없으면 API 1회 조회 후 캐시."""
    for d in DETAIL_DIRS:
        fp = d / f"{no}.json"
        if fp.exists() and fp.stat().st_size > 200:
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except Exception:                            # noqa: BLE001
                pass
    RAW.mkdir(parents=True, exist_ok=True)
    fp = RAW / f"{no}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:                                # noqa: BLE001
            pass
    if not fetch:
        return None
    try:
        req = urllib.request.Request(API.format(no), headers=UA)
        with urllib.request.urlopen(req, timeout=40) as r:
            doc = json.load(r)
        fp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.3)
        return doc
    except Exception:                                    # noqa: BLE001
        fp.write_text("{}", encoding="utf-8")
        return None


def uniq_contracts(contracts):
    """같은 계약이 목록에 두 번 실린 경우 제거(금액·구성원 시그니처 기준)."""
    seen, out = set(), []
    for c in contracts or []:
        k = (c.get("amount"), tuple(sorted((x.get("name") or "", str(x.get("share")))
                                          for x in (c.get("corps") or []))))
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


# ---------------------------------------------------------------- 판정
def resolve(win, notice):
    """낙찰 1건 → {mode, members, share_src, joint, note}."""
    joint = ((notice or {}).get("notice") or {}).get("jointMethod")
    cs = uniq_contracts((notice or {}).get("contracts"))
    res = {"mode": None, "members": [], "share_src": None, "joint": joint, "note": None,
           "contract_amount": None}

    if cs:
        c = max(cs, key=lambda x: (x.get("totalAmount") or 0))
        corps = c.get("corps") or []
        res["contract_amount"] = c.get("totalAmount") or c.get("amount")
        members = []
        for x in corps:
            members.append({"name": x.get("name"), "key": norm(x.get("name")),
                            "role": x.get("role"), "share": x.get("share")})
        res["members"] = members
        shares = [m["share"] for m in members]
        if len(members) == 1 and shares[0] == 100:
            res["mode"], res["share_src"] = "단독", "나라장터 계약정보"
        elif len(members) == 1 and shares[0] is None:
            res["mode"] = "지분미확인(구성원)"
            res["share_src"] = "나라장터 계약정보"
            res["note"] = "계약상대자 1인·지분율 미기재"
        elif all(s is not None for s in shares) and abs(sum(shares) - 100) <= 1:
            res["mode"], res["share_src"] = "지분확인", "나라장터 계약정보"
        else:
            res["mode"], res["share_src"] = "지분미확인(구성원)", "나라장터 계약정보"
            res["note"] = (f"구성원 {len(members)}곳 중 지분율 미기재"
                           if any(s is None for s in shares) else
                           f"지분율 합계 {sum(s or 0 for s in shares)}%")
        return res

    # 계약정보 없음 → 엑셀 '공동수급 구성(지분)' 열
    xj = win.get("xlsx_joint")
    if xj:
        members = []
        for m in re.finditer(r"([^,\[\]]+?)\[(주계약업체|도급업체)(?:,\s*(\d{1,3})\s*%)?\]", str(xj)):
            members.append({"name": m.group(1).strip(), "key": norm(m.group(1)),
                            "role": m.group(2),
                            "share": int(m.group(3)) if m.group(3) else None})
        if members:
            res["members"] = members
            shares = [m["share"] for m in members]
            if len(members) == 1 and shares[0] in (100, None):
                res["mode"] = "단독" if shares[0] == 100 else "지분미확인(구성원)"
                if shares[0] is None:
                    res["note"] = "낙찰자 1인·지분율 미기재"
            elif all(s is not None for s in shares) and abs(sum(shares) - 100) <= 1:
                res["mode"] = "지분확인"
            else:
                res["mode"] = "지분미확인(구성원)"
                res["note"] = (f"구성원 {len(members)}곳 중 지분율 미기재"
                               if any(s is None for s in shares) else
                               f"지분율 합계 {sum(s or 0 for s in shares)}%")
            res["share_src"] = "엑셀 공동수급 구성(지분) 열"
            return res

    # 계약·지분 정보가 전혀 없음 → 공고의 공동수급 조건으로 단독 여부만 판정
    if joint and "불허" in joint:
        res["mode"], res["share_src"] = "단독", "공고 공동수급 불허(단독 확정)"
        res["members"] = [{"name": win.get("winner"), "key": norm(win.get("winner")),
                           "role": "주계약업체", "share": 100}]
        res["note"] = "계약 상세 없음 — 공고가 공동수급을 불허해 단독 수행으로 확인"
        return res
    res["mode"] = "지분미확인(계약정보없음)"
    res["share_src"] = "확인 불가"
    res["members"] = [{"name": win.get("winner"), "key": norm(win.get("winner")),
                       "role": "주계약업체", "share": None}]
    res["note"] = ("공고가 공동수급을 허용(" + str(joint or "조건 미상") + ")하나 "
                   "계약 구성원·지분 정보가 공개돼 있지 않음")
    return res


# ---------------------------------------------------------------- 전체 빌드
def build(fetch=True):
    wins = xlsx_wins()
    items, stats = {}, {"wins": 0, "단독": 0, "지분확인": 0,
                        "지분미확인(구성원)": 0, "지분미확인(계약정보없음)": 0}
    for w in wins:
        no = w["no"]
        if not no or no in items:
            continue
        doc = load_notice(no, fetch=fetch)
        r = resolve(w, doc)
        alloc = []
        base = w["amount"]
        for m in r["members"]:
            amt = round(base * m["share"] / 100) if m["share"] is not None else None
            alloc.append({**m, "amount": amt})
        items[no] = {
            "no": no, "title": w["title"], "org": w["org"], "date": w["date"],
            "field": w["field"], "winner": w["winner"], "amount": base,
            "mode": r["mode"], "share_src": r["share_src"], "joint": r["joint"],
            "note": r["note"], "contract_amount": r["contract_amount"],
            "members": alloc, "src": w["src"],
        }
        stats["wins"] += 1
        stats[r["mode"]] = stats.get(r["mode"], 0) + 1

    # 업체별 집계 — 확정 실적(지분 반영)과 미확인 실적(총액 기준) 분리
    comp = {}
    for no, it in items.items():
        for m in it["members"]:
            e = comp.setdefault(m["key"], {"name": m["name"], "wins": [],
                                           "amount": 0, "amount_unknown": 0,
                                           "n_confirmed": 0, "n_unknown": 0,
                                           "n_partial": 0})
            row = {"no": no, "field": it["field"], "date": it["date"], "org": it["org"],
                   "title": it["title"], "role": m["role"], "share": m["share"],
                   "mode": it["mode"], "amount": m["amount"], "total": it["amount"]}
            e["wins"].append(row)
            if it["mode"] in ("단독", "지분확인") and m["amount"] is not None:
                e["amount"] += m["amount"]
                e["n_confirmed"] += 1
            else:
                # 미확인 — 주계약업체는 총액을 상한으로 기록, 그 외 구성원은 참여만 기록
                if m["role"] == "주계약업체" or it["mode"] == "지분미확인(구성원)":
                    e["amount_unknown"] += it["amount"]
                e["n_unknown"] += 1
    for e in comp.values():
        e["wins"].sort(key=lambda x: x["date"] or "", reverse=True)

    doc = {
        "built_at": datetime.now(KST).isoformat(timespec="seconds"),
        "as_of": "2026-11-28",
        "rule": {
            "확정 실적": "낙찰금액 × (지분율/100) — 단독·지분확인 건만",
            "미확인 실적": "낙찰금액 전액(총액 기준·상한) — 지분미확인 건",
            "단독 판정": "계약 구성원 1인 100% 또는 공고 공동수급 불허",
        },
        "sources": {
            "나라장터 계약정보": "work-api.00data.kr/api/rebrand/notice/{공고번호}.contracts (role·name·share)",
            "엑셀 지분 열": [str(ROAD_XLSX.relative_to(WORK)), str(SPACE_XLSX.relative_to(WORK))],
            "공고 공동수급 조건": "notice.jointMethod — 공동수급불허면 단독 확정",
        },
        "stats": stats,
        "companies": comp,
        "items": items,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def self_report(doc, key=None):
    key = key or norm("웨이즈원")
    e = doc["companies"].get(key)
    if not e:
        print("해당 업체 없음")
        return
    print(f"■ {e['name']} — 확인 {e['n_confirmed']}건 {e['amount'] / 1e8:.1f}억 / "
          f"미확인 {e['n_unknown']}건 총액 {e['amount_unknown'] / 1e8:.1f}억")
    by = {}
    for w in e["wins"]:
        b = by.setdefault(w["field"], {"cf": 0, "cf_amt": 0, "un": 0, "un_amt": 0})
        if w["mode"] in ("단독", "지분확인") and w["amount"] is not None:
            b["cf"] += 1
            b["cf_amt"] += w["amount"]
        else:
            b["un"] += 1
            b["un_amt"] += w["total"]
    for f, b in sorted(by.items(), key=lambda kv: -kv[1]["cf_amt"]):
        print(f"  [{f}] 확인 {b['cf']}건 {b['cf_amt'] / 1e8:.2f}억 / 미확인 {b['un']}건 {b['un_amt'] / 1e8:.2f}억")
    print("  --- 건별")
    for w in e["wins"]:
        sh = f"{w['share']}%" if w["share"] is not None else "지분 미기재"
        print(f"  {w['date']} {w['no']} {w['mode']:>18s} {w['role']} {sh:>8s} "
              f"{(w['amount'] if w['amount'] is not None else 0) / 1e8:6.2f}억(총 {w['total'] / 1e8:6.2f}억) {w['org']} — {(w['title'] or '')[:34]}")


if __name__ == "__main__":
    doc = build(fetch="--no-fetch" not in sys.argv)
    s = doc["stats"]
    print(f"[consortium] 낙찰 {s['wins']}건 — 단독 {s.get('단독', 0)} · 지분확인 {s.get('지분확인', 0)} · "
          f"지분미확인(구성원) {s.get('지분미확인(구성원)', 0)} · 지분미확인(계약정보없음) {s.get('지분미확인(계약정보없음)', 0)}")
    print(f"  → {OUT}")
    if "--self" in sys.argv:
        self_report(doc)
