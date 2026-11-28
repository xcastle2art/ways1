#!/usr/bin/env python3
"""공고별 입찰참가자격을 파싱하고, company_registry.json 과 대조해
   ㈜웨이즈원 입찰 가능 여부와 기존 낙찰사 중 단독 입찰 가능 업체를 산출한다.

요건 소스(우선순위)
  1) 나라장터 공고 메타 — industry_limit(업종제한), region_limit(지역제한), conditions(공동수급)
  2) 첨부 공고문·과업지시서 텍스트 — scan/att/*.pdf/*.hwpx (PyMuPDF·zip+xml 추출, 결과 캐시)
  3) scan/build_data.py 의 NOTES — 공고문을 직접 읽고 정리해 둔 자격·지역·공동수급 서술

판정
  가능 / 조건부(컨소시엄·지역) / 불가 / 요건미확인
출력
  scan/eligibility.json
"""
import ast, json, gzip, os, re, pathlib, zipfile
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).parent
WORK = HERE.parent
REG = HERE / "registry"
DATA = WORK / "data.json"
OUT = HERE / "eligibility.json"
ATTTXT = REG / "att_text"
KST = timezone(timedelta(hours=9))
SELF_KEY = "웨이즈원"
SELF_LABEL = "㈜웨이즈원"

# ------------------------------------------------------------------ 첨부 텍스트
def pdf_text(fp):
    try:
        try:
            import pymupdf as fitz          # PyMuPDF 1.24+ (fitz 경고 없이)
        except ImportError:
            import fitz
        doc = fitz.open(fp)
        t = "\n".join(p.get_text() for p in doc)
        doc.close()
        return t
    except Exception:                                  # noqa: BLE001
        return ""


def hwpx_text(fp):
    try:
        out = []
        with zipfile.ZipFile(fp) as z:
            for n in z.namelist():
                if n.startswith("Contents/") and n.endswith(".xml") and "section" in n:
                    x = z.read(n).decode("utf-8", "replace")
                    x = re.sub(r"<[^>]+>", " ", x)
                    out.append(re.sub(r"[ \t]+", " ", x))
        return "\n".join(out)
    except Exception:                                  # noqa: BLE001
        return ""


def att_texts():
    ATTTXT.mkdir(parents=True, exist_ok=True)
    got = {}
    for fp in sorted((HERE / "att").rglob("*")):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in (".pdf", ".hwpx", ".hwp"):
            continue
        cache = ATTTXT / (fp.stem + ".txt")
        if cache.exists():
            got[fp.name] = cache.read_text(encoding="utf-8")
            continue
        t = pdf_text(fp) if fp.suffix.lower() == ".pdf" else hwpx_text(fp)
        cache.write_text(t, encoding="utf-8")
        got[fp.name] = t
    return got


# ------------------------------------------------------------------ NOTES 파싱
def load_notes():
    src = (HERE / "build_data.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "NOTES" for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except Exception:                          # noqa: BLE001
                return {}
    return {}


# ------------------------------------------------------------------ 업종 토큰 → 근거
SUR_MAP = {
    "측지측량업": "측지측량업", "연안조사측량업": "연안조사측량업", "항공촬영업": "항공촬영업",
    "공간영상도화업": "공간영상도화업", "지도제작업": "지도제작업", "수치지도제작업": "수치지도제작업",
    "지하시설물측량업": "지하시설물측량업", "공공측량업": "공공측량업", "영상처리업": "영상처리업",
    "일반측량업": "일반측량업", "지적측량업": "지적측량업",
}
ENG_FIELD = {"도로공항": "도로공항", "도로·공항": "도로공항", "도로공항·교통": "도로공항",
             "도시계획": "도시계획", "교통": "교통", "측량지적": "측량지적", "토질지질": "토질지질",
             "수자원개발": "수자원개발", "상하수도": "상하수도", "조경": "조경", "구조": "구조",
             "농어업토목": "농어업토목", "정보통신": "정보통신", "설비": "설비", "전력": "전력"}
OUT_OF_SCOPE = ("전기자동차충전", "폐기물", "소독업", "제작자", "학술", "연구용역", "감리법인",
                "정보통신공사업", "건설엔지니어링", "기술사사무소")


def kinds_of(token: str):
    """업종 문자열 하나를 근거 토큰 목록으로."""
    t = token.replace(" ", "")
    if not t:
        return []
    if "소프트웨어사업자" in t or "SW사업자" in t:
        return ["sw"]
    m = re.match(r"엔지니어링사업\(([^)]+)\)", t) or re.match(r"엔지니어링\(([^)]+)\)", t)
    if m:
        f = m.group(1).replace("건설-", "")
        return ["eng:" + ENG_FIELD.get(f, f)]
    if t.startswith("기술사사무소"):
        m = re.search(r"\(([^)]+)\)", t)
        f = m.group(1) if m else ""
        return ["eng:" + ENG_FIELD.get(f, f)] if f in ENG_FIELD else ["unknown:기술사사무소"]
    if t.startswith("측량업"):
        for name in SUR_MAP:
            if name in t:
                return [name]
        return ["unknown:측량업"]
    if "정보통신공사업" in t:
        return ["unknown:정보통신공사업"]
    if "감리법인" in t:
        return ["unknown:감리법인"]
    for k in OUT_OF_SCOPE:
        if k in t:
            return ["out"]
    return ["unknown:" + t[:20]]


def tok_label(kind):
    if kind == "sw":
        return "SW사업자 신고"
    if kind.startswith("eng:"):
        return "엔지니어링·" + kind[4:]
    if kind.startswith("unknown:"):
        return "원부 미연결·" + kind.split(":", 1)[1]
    if kind == "out":
        return "업종요건 아님(사업 유형)"
    return "측량업·" + kind


def kinds_of_text(txt: str):
    """공고문·NOTE 문장에서 업종 근거 토큰 뽑기."""
    t = txt.replace("\n", " ")
    out = []
    for m in re.finditer(r"엔지니어링\s*\(?([가-힣·,\s]+?)\)?\(?(?:신고|업체|사업자)?", t):
        pass
    for f, k in ENG_FIELD.items():
        if re.search(r"엔지니어링[^.\n]{0,20}?" + re.escape(f), t) and k not in out:
            out.append("eng:" + k)
    if re.search(r"SW\s*사업자|소프트웨어사업자", t) and "sw" not in out:
        out.append("sw")
    for name in SUR_MAP:
        if name in t and name not in out:
            out.append(name)
    return out


# ------------------------------------------------------------------ 지역
SIDO_ALIASES = {
    "서울": "서울특별시", "서울특별시": "서울특별시", "부산": "부산광역시", "부산광역시": "부산광역시",
    "대구": "대구광역시", "대구광역시": "대구광역시", "인천": "인천광역시", "인천광역시": "인천광역시",
    "광주": "광주광역시", "광주광역시": "광주광역시", "대전": "대전광역시", "대전광역시": "대전광역시",
    "울산": "울산광역시", "울산광역시": "울산광역시", "세종": "세종특별자치시", "세종특별자치시": "세종특별자치시",
    "경기": "경기도", "경기도": "경기도", "강원": "강원특별자치도", "강원도": "강원특별자치도",
    "강원특별자치도": "강원특별자치도", "충북": "충청북도", "충청북도": "충청북도", "충남": "충청남도",
    "충청남도": "충청남도", "전북": "전북특별자치도", "전라북도": "전북특별자치도",
    "전북특별자치도": "전북특별자치도", "전남": "전라남도", "전라남도": "전라남도",
    "전남광주통합특별시": "전남광주통합특별시", "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도", "제주": "제주특별자치도", "제주특별자치도": "제주특별자치도",
}


def parse_region(text):
    if not text:
        return []
    if re.search(r"없음|전국|제한\s*없|미적용", text):
        return []
    parts = [p.strip() for p in re.split(r"[,/·]| 및 | 또는 ", text) if p.strip()]
    out = []
    for p in parts:
        m = re.match(r"^(.+?(?:시|도|특별시|광역시|특별자치도|특별자치시))(?:\s+(.+))?$", p)
        if m and m.group(1) in SIDO_ALIASES:
            out.append({"raw": p, "sido": SIDO_ALIASES[m.group(1)],
                        "sigungu": (m.group(2) or "").strip() or None})
        elif p in SIDO_ALIASES:
            out.append({"raw": p, "sido": SIDO_ALIASES[p], "sigungu": None})
        else:
            out.append({"raw": p, "sido": None, "sigungu": None})
    return out


def region_ok(comp, regions):
    if not regions:
        return None
    for r in regions:
        if r["sido"] and comp.get("sido") and r["sido"] == comp["sido"]:
            if not r["sigungu"]:
                return True
            if comp.get("sigungu") and r["sigungu"] and (
                    comp["sigungu"] == r["sigungu"] or comp["sigungu"] in r["sigungu"]):
                return True
        if not r["sido"] and r["raw"] and comp.get("addr") and r["raw"] in comp["addr"]:
            return True
    return False


# ------------------------------------------------------------------ 요건 조립
def build_req(item, notes, atts):
    req = {"items": [], "regions": [], "regions_src": None, "consortium": "미확인",
           "extras": [], "sources": set(), "raw": {}, "no_industry": False}

    def add_item(kinds, op, src, label=""):
        ded = []
        for k in kinds:
            if k and k not in ded:
                ded.append(k)
        if not ded:
            return
        for it in req["items"]:
            if it["kinds"] == ded and it["op"] == op:
                if src not in it["src"]:
                    it["src"] += "+" + src if it["src"] else src
                return
        # note가 field보다 강한(AND) 요건을 주면 field의 OR 요건은 버린다
        if op == "all":
            req["items"] = [it for it in req["items"] if not (it["op"] == "any" and set(it["kinds"]) <= set(ded))]
        req["items"].append({"kinds": ded, "op": op, "src": src, "label": label})

    ind = (item.get("industry_limit") or "").strip()
    if ind:
        kinds = []
        for tok in re.split(r"[,、]", ind):
            kinds += kinds_of(tok)
        add_item(kinds, "any", "field")
        req["raw"]["industry_limit"] = ind
        req["sources"].add("field")

    reg = (item.get("region_limit") or "").strip()
    if reg:
        req["regions"] = parse_region(reg)
        req["regions_src"] = "field"
        req["raw"]["region_limit"] = reg
        req["sources"].add("field")

    cond = item.get("conditions") or ""
    if "업종 제한 없음" in cond or "업종제한 없음" in cond:
        req["no_industry"] = True
        req["sources"].add("field")
    if "공동수급" in cond or "공동도급" in cond:
        req["consortium"] = "허용" if ("허용" in cond or "가능" in cond) else (
            "불허" if ("불허" in cond or "금지" in cond or "단독" in cond) else "미확인")

    # 2) NOTES
    note = notes.get(item.get("no") or "", "") or item.get("note") or ""
    if note:
        req["raw"]["note"] = note[:400]
        k_all = kinds_of_text(note)
        # "엔지니어링(도시계획) … + SW사업자" 처럼 +로 이어진 경우는 AND 요건
        m_and = re.search(r"(엔지니어링[^+\n]{0,40})\+\s*(SW\s*사업자|소프트웨어사업자)", note) or \
                re.search(r"(SW\s*사업자|소프트웨어사업자)[^+\n]{0,20}\+\s*(엔지니어링[^+\n]{0,40})", note)
        if m_and:
            add_item(k_all, "all", "note") if len(k_all) > 1 else None
            req["sources"].add("note")
        elif not ind:
            if k_all:
                add_item(k_all, "all" if len(k_all) > 1 else "any", "note")
                req["sources"].add("note")
        if not req["regions"]:
            m = re.search(r"지역제한\s*([가-힣]+(?:특별시|광역시|특별자치도|특별자치시|도)?(?:[^,.\n]{0,14}?)(?:시|군|구)?)(?=\s|,|\.|·)", note)
            if m:
                r = parse_region(m.group(1).strip())
                if r and any(x["sido"] or x["raw"] for x in r):
                    req["regions"] = r
                    req["regions_src"] = "note"
                    req["sources"].add("note")
        if req["consortium"] == "미확인":
            if re.search(r"공동(?:도급|수급)?\s*불허", note):
                req["consortium"] = "불허"
            elif re.search(r"공동(?:도급|수급)?\s*(?:허용|가능)", note):
                req["consortium"] = "허용"
        for m in re.finditer(r"직접생산확인\(([^)]{2,40})\)", note):
            req["extras"].append("직접생산확인(" + m.group(1) + ")")
        if re.search(r"중소기업\s*확인서|중소기업\s*업체|중소기업만", note):
            req["extras"].append("중소기업 확인서")

    # 3) 첨부 공고문 텍스트 — 이 공고의 첨부만
    mine = {}
    for a in item.get("attachments") or []:
        nm = a.get("name") or ""
        stem = pathlib.Path(nm).stem
        for k, v in atts.items():
            if not v:
                continue
            if nm == k or pathlib.Path(k).stem == stem:
                mine[nm or k] = v
    for name, txt in mine.items():
        if not txt:
            continue
        seg = txt[:200000]
        probe = re.escape(ind[:12]) if ind else "입찰참가자격"
        if re.search(probe, seg):
            req["sources"].add("att:" + name)
        if not req["regions"]:
            m = re.search(r"지역제한[^.\n]{0,10}([가-힣]{2,10}(?:시|도|군|구)[^.\n]{0,20})", seg)
            if m:
                r = parse_region(m.group(1))
                if r and any(x["sido"] or x["raw"] for x in r):
                    req["regions"] = r
                    req["regions_src"] = "att:" + name
        for m in re.finditer(r"직접생산확인\(([^)]{2,40})\)", seg):
            req["extras"].append("직접생산확인(" + m.group(1) + ")")

    req["extras"] = sorted(set(req["extras"]))
    req["sources"] = sorted(req["sources"])
    req["parsed"] = bool(req["items"] or req["regions"] or req["extras"] or req["no_industry"])
    return req


# ------------------------------------------------------------------ 판정
def evidence(comp, kind):
    """근거 토큰 → 'ok' / 'no' / 'unknown'."""
    inds = comp.get("inds") or []
    if kind == "sw":
        if not comp.get("sw_linked", True):
            return "unknown"
        return "ok" if "SW사업자" in inds else "no"
    if kind.startswith("eng:"):
        if not comp.get("eng_linked", True):
            return "unknown"
        return "ok" if ("엔지니어링:" + kind[4:]) in inds else "no"
    if kind.startswith("unknown:") or kind == "out":
        return "unknown"
    return "ok" if kind in inds else "no"


def judge(comp, req):
    """(판정, 사유목록) 반환."""
    if not req["parsed"]:
        return "요건미확인", ["공고문·메타에서 입찰참가자격 업종을 확인하지 못함"]
    reasons, met, unmet_hard, unmet_unknown = [], [], [], []
    for it in req["items"]:
        st = [evidence(comp, k) for k in it["kinds"]]
        label = " 또는 ".join(tok_label(k) for k in it["kinds"]) if it["op"] == "any" else \
                " + ".join(tok_label(k) for k in it["kinds"])
        if it["op"] == "any":
            if "ok" in st:
                met.append(label)
            elif all(s == "no" for s in st):
                unmet_hard.append(label)
            else:
                unmet_unknown.append(label)
        else:
            if all(s == "ok" for s in st):
                met.append(label)
            elif "no" in st:
                unmet_hard.append(label)
            else:
                unmet_unknown.append(label)
    rok = region_ok(comp, req["regions"]) if req["regions"] else None
    cons = req["consortium"]

    if unmet_hard:
        if cons == "허용":
            return "조건부", [f"보유 업종 부족: {', '.join(unmet_hard)} — 공동수급으로 보완 필요"]
        return "불가", [f"보유 업종 미충족: {', '.join(unmet_hard)}" + ("" if cons == "불허" else " (공동수급 여부 미확인)")]
    if rok is False:
        where = ", ".join(r["raw"] for r in req["regions"])
        if cons == "허용":
            return "조건부", [f"지역제한({where}) — 당사 소재지({comp.get('sido')} {comp.get('sigungu') or ''}) 미해당, 지역업체 공동수급 필요"]
        return "불가", [f"지역제한({where}) — 당사 소재지 미해당" + ("" if cons == "불허" else " (공동수급 여부 미확인)")]
    if unmet_unknown:
        return "요건미확인", [f"원부로 확인되지 않는 업종: {', '.join(unmet_unknown)}"]
    if req.get("no_industry") and not req["items"]:
        extra = f" — 지역제한({', '.join(r['raw'] for r in req['regions'])}) 충족" if rok else ""
        return "가능", ["업종 제한 없음" + extra + " · 실적·정량 요건은 공고문 확인"]
    return "가능", (["업종·지역 요건 충족"] if met or rok else ["업종 제한 없음"])


def eligible_list(registry, req):
    ok, comp_need = [], 0
    for c in registry:
        v, _ = judge(c, req)
        if v == "가능":
            ok.append(c)
        elif v == "조건부":
            comp_need += 1
    ok.sort(key=lambda c: (-c["win_count"], c["display"]))
    return ok, comp_need


# ------------------------------------------------------------------ 공용 진입점
def prepare(companies):
    for c in companies:
        c["sw_linked"] = bool(c.get("sw_used"))
        c["eng_linked"] = bool(c.get("etis_used"))
    return companies


def load_registry():
    doc = json.loads((REG / "company_registry.json").read_text(encoding="utf-8"))
    return prepare(doc["companies"]), doc


def card(c, why=None, ratio=None, score=None, max_score=None):
    top = max(c["by_field"].items(), key=lambda kv: kv[1]["n"])[0] if c["by_field"] else None
    out = {"key": c["key"], "name": c["display"],
           "area": " ".join(x for x in (c.get("sido"), c.get("sigungu")) if x),
           "inds": (c.get("inds") or [])[:3], "wins": c["win_count"], "field": top,
           "last": c.get("last_win")}
    if why:
        out["why"] = why
    if ratio is not None:
        out["ratio"] = ratio
    if score is not None:
        out["qscore"] = score
    if max_score is not None:
        out["qmax"] = max_score
    return out


def block(item, companies, selfc, notes, atts, qc=None, quant_cache=None):
    """공고 1건의 입찰참가자격 + 정량평가 기준 매칭 결과 블록."""
    req = build_req(item, notes, atts)
    verdict, reasons = judge(selfc, req)
    elig_all, comp_need = eligible_list(companies, req)
    by_key = {c["key"]: c for c in elig_all}

    quant = None
    qsum = None
    if qc is not None and item.get("kind") == "bid":
        try:
            q, qres = qc.quant_block(item, companies, cache=quant_cache)
            qsum = qc.summary(q, qres)
            quant = qres
        except Exception as e:                          # noqa: BLE001
            qsum = {"status": "error", "note": f"{type(e).__name__}: {e}"}

    if quant and qsum and qsum.get("state") == "fit":
        fit_rows = [r for r in quant["fit"] if r["key"] in by_key]
        near_rows = [r for r in quant["near"] if r["key"] in by_key]
        low_rows = [r for r in quant["low"] if r["key"] in by_key]

        def pick(rows, n=10):
            out = []
            for r in rows:
                c = by_key.get(r["key"])
                if not c:
                    continue
                out.append(card(c, r.get("why"), r.get("ratio"), r.get("score"), r.get("max_score")))
                if len(out) >= n:
                    break
            return out
        fit_cards = pick(fit_rows, 10)
        near = pick(near_rows, 6)
        low = pick(low_rows, 6)
        unknown_n = sum(1 for r in quant["unknown"] if r["key"] in by_key)
        out = {
            "verdict": verdict, "reasons": reasons,
            "req": {"industries": [(" 또는 ".join(tok_label(k) for k in i["kinds"]) if i["op"] == "any"
                                    else " + ".join(tok_label(k) for k in i["kinds"])) for i in req["items"]],
                    "region": [r["raw"] for r in req["regions"]],
                    "consortium": req["consortium"], "extras": req["extras"],
                    "sources": req["sources"], "parsed": req["parsed"]},
            "eligibility_count": len(elig_all),
            "eligible_count": len(fit_rows),
            "eligible": fit_cards,
            "near_count": len(near_rows),
            "near": near,
            "qual_only_count": len(low_rows),
            "qual_only": low,
            "quant_unknown_count": unknown_n,
            "complement_count": comp_need,
            "quant": qsum,
        }
        return out, req

    # 정량기준은 확인했지만 우리 실적DB 범위 밖이거나, 정량기준 자체가 없는 공고
    out = []
    for c in elig_all[:8]:
        kinds_needed = [("엔지니어링:" + k[4:] if k.startswith("eng:") else k)
                        for k in sum([x["kinds"] for x in req["items"]], [])]
        matched = ([i for i in c["inds"] if i in kinds_needed] +
                   [i for i in c["inds"] if i.startswith("SW") and i not in kinds_needed])[:4] or c["inds"][:3]
        out.append({"key": c["key"], "name": c["display"],
                    "area": " ".join(x for x in (c.get("sido"), c.get("sigungu")) if x),
                    "inds": matched, "wins": c["win_count"],
                    "field": (max(c["by_field"].items(), key=lambda kv: kv[1]["n"])[0]
                              if c["by_field"] else None),
                    "last": c.get("last_win")})
    return {
        "verdict": verdict,
        "reasons": reasons,
        "req": {
            "industries": [(" 또는 ".join(tok_label(k) for k in i["kinds"]) if i["op"] == "any"
                            else " + ".join(tok_label(k) for k in i["kinds"])) for i in req["items"]],
            "region": [r["raw"] for r in req["regions"]],
            "consortium": req["consortium"],
            "extras": req["extras"],
            "sources": req["sources"],
            "parsed": req["parsed"],
        },
        "eligibility_count": len(elig_all),
        "eligible_count": len(elig_all),
        "complement_count": comp_need,
        "eligible": out,
        "near_count": 0, "near": [], "qual_only_count": 0, "qual_only": [],
        "quant_unknown_count": 0,
        "quant": qsum,
    }, req


def attach(items, companies, selfc, notes, atts, qc=None):
    res, tally, parsed_n, src_tally = {}, {"가능": 0, "조건부": 0, "불가": 0, "요건미확인": 0}, 0, {}
    qstate = {"fit": 0, "parsed_out": 0, "unparsed": 0}
    qfit_items = 0
    cache = {}
    for it in items:
        b, req = block(it, companies, selfc, notes, atts, qc=qc, quant_cache=cache)
        res[it["id"]] = b
        tally[b["verdict"]] += 1
        parsed_n += 1 if req["parsed"] else 0
        for s in req["sources"]:
            src_tally[s.split(":")[0]] = src_tally.get(s.split(":")[0], 0) + 1
        st = (b.get("quant") or {}).get("state")
        if st:
            qstate[st] = qstate.get(st, 0) + 1
            if st == "fit" and b.get("eligible_count"):
                qfit_items += 1
    summary = {"items": len(items), "parsed": parsed_n, "verdicts": tally,
               "requirement_sources": src_tally, "registry_companies": len(companies),
               "quant": qstate, "quant_fit_items": qfit_items}
    return res, summary


def registry_block(reg_doc):
    """웹 표시용 낙찰사 업등록 DB."""
    com = []
    for c in reg_doc["companies"]:
        com.append({
            "key": c["key"], "name": c["display"],
            "area": " ".join(x for x in (c.get("sido"), c.get("sigungu")) if x),
            "addr": c.get("addr"),
            "inds": c["inds"],
            "wins": c["win_count"], "amount": c.get("win_amount"),
            "fields": {k: v["n"] for k, v in (c.get("by_field") or {}).items()},
            "last": c.get("last_win"),
            "sw": (c.get("sw") or {}).get("size"),
            "kasm": (c.get("kasm") or {}).get("name"),
            "etis": (c.get("etis") or {}).get("name") if c.get("etis_used") else None,
            "flag": c.get("identity_conflict"),
            "self": c.get("is_self"),
        })
    return {"updated_at": reg_doc["updated_at"], "sources": reg_doc["sources"],
            "stats": reg_doc["stats"], "companies": com}


def main():
    companies, reg_doc = load_registry()
    by_key = {c["key"]: c for c in companies}
    selfc = by_key.get("웨이즈원") or {"key": "웨이즈원", "display": SELF_LABEL, "inds": [],
                                      "addr": "경기도 의왕시", "sido": "경기도", "sigungu": "의왕"}
    data = json.loads(DATA.read_text(encoding="utf-8"))
    notes = load_notes()
    atts = att_texts()
    res, summary = attach(data["items"], companies, selfc, notes, atts)
    doc = {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "self": {"name": SELF_LABEL, "addr": selfc.get("addr"), "inds": selfc.get("inds")},
        "summary": summary,
        "items": res,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] {OUT}")
    print(f"  공고 {summary['items']}건 중 요건 파싱 {summary['parsed']}건 / 판정 {summary['verdicts']}")
    print(f"  요건 소스 {summary['requirement_sources']}")


if __name__ == "__main__":
    main()
