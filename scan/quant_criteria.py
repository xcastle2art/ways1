#!/usr/bin/env python3
"""공고별 정량평가 기준 파싱 + 낙찰사 정량 역량 프로필 + 부합 판정.

원천
  · 제안요청서·공고문 텍스트 (scan/fetch_rfp.py 가 받아 둔 registry/att_text/rfp_*.txt)
  · 공고 메타 (추정가격·계약방식·공고일)
  · 낙찰사 업등록 DB (registry/company_registry.json 의 wins — 엑셀 2종·road3 실적)

원칙
  · 공고문 원문에서 확인된 배점·기준선만 쓴다. 없으면 '정량기준 미확인'으로 남긴다.
  · 신용등급·보유기술인력 수는 원부(KASM·ETIS·SWIT)에 공개되지 않아 점수 산정에서 제외하고
    '미확인'으로 표시한다.
  · 실적은 우리 DB 에 수집된 낙찰 실적만 집계한다. 수집 범위 밖 분야(유지관리·자율주행 등)는
    '실적 없음'이 아니라 '실적 데이터 범위 밖'으로 구분한다.
"""
import json, pathlib, re
from datetime import date, datetime, timedelta

HERE = pathlib.Path(__file__).parent
TXT = HERE / "registry" / "att_text"
MAN = TXT / "_manifest.json"
REG = HERE / "registry" / "company_registry.json"
PROF = HERE / "registry" / "quant_profiles.json"

# 실적 인정분야 문구 → 낙찰사 DB 분야
FIELD_MAP = {
    "도로대장": ["도로대장"],
    "도로 GIS": ["도로대장"],
    "GIS DB": ["UPIS·KLIP DB", "연속도면·연속주제도", "용도지역지구 DB정비", "기초조사정보체계"],
    "GISDB": ["UPIS·KLIP DB", "연속도면·연속주제도", "용도지역지구 DB정비", "기초조사정보체계"],
    "공간정보 DB": ["도로대장", "UPIS·KLIP DB", "연속도면·연속주제도", "용도지역지구 DB정비", "기초조사정보체계"],
    "토지적성": ["토적·재취"],
    "재해취약": ["토적·재취"],
    "연속도면": ["연속도면·연속주제도", "용도지역지구 DB정비"],
    "연속주제도": ["연속도면·연속주제도", "용도지역지구 DB정비"],
    "용도지역": ["용도지역지구 DB정비", "연속도면·연속주제도"],
    "지적재조사": ["용도지역지구 DB정비"],
}
ALL_FIELDS = ["도로대장", "UPIS·KLIP DB", "연속도면·연속주제도", "용도지역지구 DB정비",
              "기초조사정보체계", "토적·재취"]
SIDO = ["서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시",
        "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도",
        "전라남도", "경상북도", "경상남도", "제주특별자치도", "전남광주통합특별시"]


def flat(t):
    t = t.replace("|", " ").replace("～", "~").replace("－", "-")
    return re.sub(r"\s+", " ", t)


# ---------------------------------------------------------------- 배점표 파싱
BAND_HEAD = re.compile(r"(\d{1,3})\s*%\s*이상")


def table_end(text, start):
    """배점표 끝 — 다음 번호 항목(4) 상생협력 등) 또는 정성적 평가 직전."""
    m = re.search(r"\d\s*\)\s*(?:제안사\s*)?(?:경영상태|상생협력|안전관리자|기술인력|보유인원|핵심인력)",
                  text[start:start + 2500])
    e1 = start + m.start() if m else start + 1400
    m2 = re.search(r"정성적\s*평가", text[start:start + 2500])
    e2 = start + m2.start() if m2 else start + 1400
    return min(e1, e2, start + 1400)


def find_perf_table(text):
    """실적 배점표(비율 구간표) 위치. (start, end) 반환."""
    best = None
    f = text
    for m in BAND_HEAD.finditer(f):
        before = f[max(0, m.start() - 300): m.start()]
        if not re.search(r"실적|수행경험|이행", before[-260:]):
            continue
        if re.search(r"지역업체\s*합산|지역업체\s*지분|상생협력\s*\[", before[-60:]):
            continue
        seg = f[m.start(): m.start() + 700]
        heads = len(BAND_HEAD.findall(seg))
        if heads < 2:
            continue
        score = heads * 3
        score += 6 if re.search(r"수행실적|수행경험|사업이행실적|이행실적", before[-260:]) else 0
        if best is None or score > best[0]:
            best = (score, m.start(), table_end(f, m.start()))
    return (best[1], best[2]) if best else None


def _num_row(tail, n=4):
    """점수 행 — '배 점 | 6.0 | 5.4 ...' 또는 '3.0 2.7 2.4 2.1' (앞 n개)."""
    tail = re.sub(r"\s*\|\s*", " ", tail)          # 표 셀 구분자도 열 간격으로 본다
    for pat in (r"(?:배\s*점|평\s*점|점\s*수|배점의)\s*((?:\d{1,2}(?:\.\d{1,2})?\s*){2,})",
                r"((?:\d{1,2}(?:\.\d{1,2})?\s*){2,})"):
        m = re.search(pat, tail)
        if m:
            vals = [float(x) for x in re.findall(r"\d{1,2}(?:\.\d{1,2})?", m.group(1))]
            if len(vals) >= n:
                return vals[:n]
    return []


def _score(val, pct, item_score):
    if pct:
        return round(item_score * val / 100, 2) if item_score else None
    return val


def column_bands(f, item_score=None):
    """'100% 이상 | 70% 이상 | 40% 이상 | 40% 미만  /  배 점 | 6.0 | 5.4 | 4.8 | 4.2' 열 맞춤 표."""
    toks = [(m.start(), m.end(), int(m.group(1)), m.group(2))
            for m in re.finditer(r"(\d{1,3})\s*%\s*(이상|미만)", f)]
    if len(toks) < 3:
        return []
    # 첫 토큰부터 이어지는 토큰만 (같은 표) — 사이 간격이 벌어지면 다른 표로 본다
    first = toks[0]
    toks = [t for t in toks if t[0] - first[0] < 350]
    run = [toks[0]]
    for t in toks[1:]:
        if t[0] - run[-1][1] > 60:
            break
        run.append(t)
    toks = run
    spans = token_spans([(v, k) for _, _, v, k in toks])
    if len(spans) < 3:
        return []
    tail = f[max(t[1] for t in toks): max(t[1] for t in toks) + 220]
    vals = _num_row(tail, len(spans))
    if len(vals) != len(spans):
        return []
    out = []
    for (lo, hi), val in zip(spans, vals):
        if val > 20:
            return []
        out.append({"min": lo, "max": hi, "score": val})
    for i, b in enumerate(out):
        if b["max"] is None and i > 0:
            b["max"] = out[i - 1]["min"]
    return out


def pair_bands(f, item_score=None):
    out = []
    # '배점의 N%' 방식 — 100% 이상 = 배점의 100% ...
    pct_rows = []
    last_end = -1
    for m in re.finditer(r"(\d{1,3})\s*%\s*(이상|미만)[^배]{0,30}?배점의\s*(\d{1,3})\s*%", f):
        if m.start() < last_end:
            continue
        last_end = m.end()
        v, kind, pc = int(m.group(1)), m.group(2), float(m.group(3))
        sc = round(item_score * pc / 100, 2) if item_score else None
        if sc is not None and sc > 20:
            continue
        row = {"min": v, "max": None, "pct": pc} if kind == "이상" else {"min": 0, "max": v, "pct": pc}
        row["score"] = sc
        pct_rows.append(row)
    if len(pct_rows) >= 3:
        pct_rows.sort(key=lambda x: -x["min"])
        for i, b in enumerate(pct_rows):
            if b["max"] is None and i > 0:
                b["max"] = pct_rows[i - 1]["min"]
        return pct_rows
    pat_a = re.compile(r"([A-D])?\.?\s*(\d{1,3})\s*%\s*이상\s*(?:~\s*(\d{1,3})\s*%\s*미만)?\s*"
                       r"(?:배점의\s*)?(\d{1,2}(?:\.\d{1,2})?)\s*(%)?")
    pat_b = re.compile(r"([A-D])?\.?\s*(\d{1,3})\s*%\s*미만\s*(?:배점의\s*)?(\d{1,2}(?:\.\d{1,2})?)\s*(%)?")
    for m in pat_a.finditer(f):
        lo, hi, val = int(m.group(2)), m.group(3), float(m.group(4))
        if not (0 < lo <= 300):
            continue
        sc = _score(val, m.group(5) == "%", item_score)
        if sc is None or sc > 20:
            continue
        out.append({"min": lo, "max": int(hi) if hi else None, "score": sc})
    for m in pat_b.finditer(f):
        hi, val = int(m.group(2)), float(m.group(3))
        if not (0 < hi <= 100):
            continue
        if re.search(r"이상\s*~\s*$", f[max(0, m.start() - 14): m.start()]):
            continue
        sc = _score(val, m.group(4) == "%", item_score)
        if sc is None or sc > 20:
            continue
        out.append({"min": 0, "max": hi, "score": sc})
    ded = {}
    for b in out:
        k = (b["min"], b["max"])
        if k not in ded or b["score"] > ded[k]["score"]:
            ded[k] = b
    return sorted(ded.values(), key=lambda x: -x["min"])


def parse_bands(region, item_score=None):
    f = flat(region)
    col = column_bands(f, item_score)
    if len(col) >= 3:
        return col
    out = pair_bands(f, item_score)
    out.sort(key=lambda x: -x["min"])
    for i, b in enumerate(out):
        if b["max"] is None and i > 0:
            b["max"] = out[i - 1]["min"]
    return out


def parse_people(region):
    f = flat(region)
    toks = [(m.start(), m.end(), int(m.group(1)), m.group(2))
            for m in re.finditer(r"(\d{1,3})\s*명\s*(이상|미만)", f)]
    out = []
    if len(toks) >= 4:
        first = toks[0]
        toks = [t for t in toks if t[0] - first[0] < 350]
        spans = token_spans([(v, k) for _, _, v, k in toks])
        tail = f[max(t[1] for t in toks): max(t[1] for t in toks) + 220]
        vals = _num_row(tail, len(spans))
        if len(vals) == len(spans) and all(v <= 20 for v in vals):
            for (lo, hi), val in zip(spans, vals):
                out.append({"min": lo, "max": hi, "score": val})
    if not out:
        for m in re.finditer(r"(\d{1,3})\s*명\s*이상\s*(?:~\s*(\d{1,3})\s*명\s*미만)?\s*"
                             r"([0-9]{1,2}(?:\.[0-9]{1,2})?)", f):
            n, val = int(m.group(1)), float(m.group(3))
            if 0 < n <= 500 and 0 <= val <= 20:
                out.append({"min": n, "max": int(m.group(2)) if m.group(2) else None, "score": val})
    return sorted(out, key=lambda x: -x["min"])


def token_spans(toks):
    """[('20','이상'),('20','미만'),('15','이상'),...] → [(20,None),(15,20),(10,15),(0,10)]"""
    spans, i = [], 0
    while i < len(toks):
        v, k = toks[i]
        if k == "이상":
            if i + 1 < len(toks) and toks[i + 1][1] == "미만" and toks[i + 1][0] > v:
                spans.append((v, toks[i + 1][0]))
                i += 2
            else:
                spans.append((v, None))
                i += 1
        else:  # 미만 단독
            if i + 1 < len(toks) and toks[i + 1][1] == "이상" and toks[i + 1][0] < v:
                spans.append((toks[i + 1][0], v))
                i += 2
            else:
                spans.append((0, v))
                i += 1
    # 중복 제거
    ded = []
    for s in spans:
        if s not in ded:
            ded.append(s)
    return ded


def parse_share_bands(region):
    """지역업체 지분·참여비율 구간 — '지분율/참여비율 X% 이상 ... N.N' 표·문장."""
    f = flat(region)
    # 1) 표 형식 — '지역업체(시·도) 참여 비율 | 30% 이상 | 25% 이상 | 20% 이상 | 20% 미만 / 점 수 | 3.0 | 2.7 ...'
    for m in re.finditer(r"지역\s*업체[^|]{0,40}(?:참여|지분)", f):
        bands = column_bands(f[m.start(): m.start() + 420])
        if len(bands) >= 3:
            return bands
    out = []
    for m in re.finditer(r"(\d{1,3})\s*%\s*(이상|미만)", f):
        ctx = f[max(0, m.start() - 40): m.start()]
        if not re.search(r"지분|참여\s*비율|참여비율|참여도", ctx):
            continue
        tail = f[m.end(): m.end() + 60]
        ms = re.search(r"([0-9]{1,2}(?:\.[0-9]{1,2})?)", tail)
        if not ms:
            continue
        val = float(ms.group(1))
        if val > 20:
            continue
        v, kind = int(m.group(1)), m.group(2)
        out.append({"min": v, "max": None, "score": val} if kind == "이상"
                   else {"min": 0, "max": v, "score": val})
    out.sort(key=lambda x: -x["min"])
    for i, b in enumerate(out):
        if b["max"] is None and i > 0:
            b["max"] = out[i - 1]["min"]
    return out


def region_name(f):
    for s in SIDO:
        short = (s.replace("특별자치도", "").replace("특별자치시", "")
                  .replace("광역시", "").replace("특별시", "").replace("도", ""))
        if re.search(re.escape(s) + r"\s*(?:관내|소재|에\s*소재)", f) or \
           re.search(re.escape(short) + r"(?:도|시)?\s*(?:관내|소재|에\s*소재)", f) or \
           re.search(re.escape(s) + r"[^.]{0,25}지역\s*업체", f) or \
           re.search(r"지역\s*업체\s*[\(\[]?\s*" + re.escape(s), f) or \
           re.search(r"지역\s*업체\s*[\(\[]?\s*" + re.escape(short) + r"(?:도|시)?[\s\)\]]", f):
            return s, short
    return None, None


def find_fields_near(text, s, e):
    """실적 배점표 주변에서 '실적/인정' 문장만 골라 인정분야를 뽑는다."""
    win = text[max(0, s - 700): e + 300]
    parts = re.split(r"(?<=[.。])\s|\n|◇|○|\*", win)
    cand = [x for x in parts if ("실적" in x or "인정" in x)]
    return find_fields(" ".join(cand))


def find_fields(para):
    f = flat(para)
    fields, keys, names = [], [], []
    for kw, ks in FIELD_MAP.items():
        if kw in f:
            names.append(kw)
            for k in ks:
                if k not in keys:
                    keys.append(k)
    # 'GIS DB' 와 'GISDB' 중복 정리
    if "GIS DB" in names and "GISDB" in names:
        names.remove("GISDB")
    fields = names
    return fields, keys


ITEMWORD = re.compile(r"수행|경영|인력|실적|상생|안전|기술개발|신인도|핵심|사회적")


def table_items(text, total=None):
    """'N. 항목 | 세부 | 배점' 열 표에서 항목 배점을 순번대로 뽑는다(합계 검증)."""
    pat = re.compile(r"(\d{1,2})\.\s*([^\n|]{2,22}?)\s*\n?\s*\|\s*[^\n|]{0,90}?\s*\n?\s*\|\s*"
                     r"([0-9]{1,2}(?:\.[0-9])?)\s*(?:\n|\|)")
    out, expect = [], 1
    for n, name, sc in pat.findall(text):
        nm = " ".join(name.split())
        v = float(sc)
        if int(n) != expect or not ITEMWORD.search(nm) or v > 20:
            continue
        out.append({"name": nm, "score": v})
        expect += 1
    if not out:
        return []
    if total and abs(sum(i["score"] for i in out) - total) > 0.6:
        return []
    return out


def item_scores(text):
    """정량 항목별 배점. 요약표 우선, 없으면 본문 표기."""
    out = {}
    for m in re.finditer(r"(\d{1,2})\s*[\.\)]\s*(회사\s*수행실적|수행실적|수행경험|기술인력\s*보유|기술인력보유|"
                         r"보유인원|회사의\s*인력보유|핵심인력|사업책임기술자|경영상태|상생협력|안전관리자)"
                         r"\s*(?:소\s*계)?\s*[\[\()]?\s*([0-9]{1,2}(?:\.[0-9])?)", flat(text)):
        nm = re.sub(r"\s+", "", m.group(2))
        out.setdefault(nm, float(m.group(3)))
    for m in re.finditer(r"(회사\s*수행실적|수행실적|수행경험|보유인원|기술인력보유|경영상태|상생협력|안전관리자)"
                         r"\s*[\[\(]\s*([0-9]{1,2}(?:\.[0-9])?)\s*[\]\)]", flat(text)):
        nm = re.sub(r"\s+", "", m.group(1))
        out[nm] = max(out.get(nm, 0), float(m.group(2)))
    return out


def perf_score_of(items):
    for k, v in items.items():
        if "실적" in k or "경험" in k:
            return v
    return None


def parse_negotiation(text, item):
    f = flat(text)
    q = {"status": "no_criteria", "kind": "협상", "total": None, "items": [],
         "perf": None, "people": None, "region": None, "credit": None,
         "sources": [], "notes": []}
    m = re.search(r"정량(?:적)?\s*평가\s*\(?\s*(\d{1,2})\s*점", f)
    if m:
        q["total"] = int(m.group(1))
    it = item_scores(text)
    ti = table_items(text, q["total"])
    if ti:
        q["items"] = ti
    else:
        q["items"] = [{"name": k, "score": v} for k, v in it.items()]
    pscore = perf_score_of(it)

    # ---- 수행실적
    loc = find_perf_table(text)
    if loc:
        s, e = loc
        tbl = text[s:e]
        para = text[max(0, s - 1000): s]
        bands = parse_bands(tbl, pscore)
        if bands:
            near = flat(text[max(0, s - 800): e + 800])
            rel = s - max(0, s - 800)
            mw = [m for m in re.finditer(r"최근\s*(?:공고일\s*기준\s*(?:전\s*)?)?(\d)\s*년", near)
                  if int(m.group(1)) in (3, 5) and "창업" not in near[max(0, m.start() - 30): m.start()]]
            yrs = int(min(mw, key=lambda m: abs(m.start() - rel)).group(1)) if mw else 3
            denom, dsrc = None, None
            md = re.search(r"÷\s*([\d,]{9,})\s*원", flat(para + tbl))
            if md:
                denom, dsrc = int(md.group(1).replace(",", "")), "공고문 명시 기준금액"
            else:
                est = item.get("price_est") or item.get("budget")
                try:
                    denom = int(str(est)) if est else None
                except ValueError:
                    denom = None
                dsrc = "추정가격"
            fields, keys = find_fields_near(text, s, e)
            if not fields:
                for kw in item.get("keywords") or []:
                    if kw in FIELD_MAP:
                        fields, keys = [kw], list(FIELD_MAP[kw])
            # 유지관리·운영 전용이면 우리 실적DB 범위 밖
            maintain = bool(re.search(r"유지관리|유지보수|운영\s*용역|운영사업", flat(para))) and \
                not re.search(r"구축|전산화|DB\s*정비|DB구축", flat(para))
            q["perf"] = {"window_years": yrs, "denom": denom, "denom_src": dsrc,
                         "bands": bands, "top_score": max((b.get("score") or 0) for b in bands),
                         "top_min": max(b["min"] for b in bands),
                         "max_score": max((b.get("score") or 0) for b in bands) or pscore, "fields": fields or [], "field_keys": keys,
                         "in_scope": bool(keys) and not maintain,
                         "note": flat(para)[-320:]}

    # 실적 항목 배점은 상세 구간표의 최고 배점을 따른다(요약표 오기 보정)
    if q["perf"] and q["perf"].get("max_score"):
        for itm in q["items"]:
            if "실적" in itm["name"] or "경험" in itm["name"]:
                itm["score"] = q["perf"]["max_score"]

    # ---- 보유인력
    bestp = None
    for m in re.finditer(r"보유인원|인력보유|기술인력\s*보유|기술인력보유", text):
        seg = text[m.start(): m.start() + 1500]
        bp = parse_people(seg)
        if bp and (bestp is None or max(b["score"] for b in bp) > bestp[0]):
            bestp = (max(b["score"] for b in bp), bp, seg)
    if bestp:
        q["people"] = {"bands": bestp[1], "max_score": bestp[0], "note": flat(bestp[2])[:200]}

    # ---- 지역상생 — 시·도가 확인되고 비율 구간표까지 나오는 문단을 고른다
    best = None
    for m in re.finditer(r"상생협력|지역\s*업체", text):
        seg = text[max(0, m.start() - 300): m.start() + 1800]
        shares = parse_share_bands(seg)
        sido, short = region_name(flat(seg))
        if not (shares or sido):
            continue
        score = (2 if sido else 0) + (3 if shares else 0)
        if best is None or score > best[0]:
            best = (score, sido, short, shares, seg)
        if score >= 5:
            break
    if best:
        _, sido, short, shares, seg = best
        q["region"] = {"sido": sido, "keyword": short, "share_bands": shares,
                       "note": flat(seg)[:240]}

    for m in re.finditer(r"(\d)\s*\)\s*(기술인력\s*보유|기술인력보유|회사\s*수행실적|수행실적|수행경험|"
                         r"보유인원|핵심인력|사업관리자|경영상태|상생협력|안전관리자)[^0-9]{0,24}?"
                         r"([0-9]{1,2}(?:\.[0-9])?)\s*점", f):
        nm = re.sub(r"\s+", "", m.group(2))
        it.setdefault(nm, float(m.group(3)))
    if not q["items"]:
        q["items"] = [{"name": k, "score": v} for k, v in it.items()]
    mc = re.search(r"경영상태\s*[\[\(]\s*([0-9]{1,2}(?:\.[0-9])?)\s*[\]\)]", f)
    if mc:
        q["credit"] = {"max_score": float(mc.group(1))}
    q["status"] = "parsed" if (q["perf"] or q["people"] or q["region"]) else "no_criteria"
    return q


def parse_qualification(text, item):
    """적격심사(지방계약 예규 별표2 기술용역) — 이행실적 비율 기준만 확인."""
    f = flat(text)
    q = {"status": "no_criteria", "kind": "적격심사", "total": None, "items": [],
         "perf": None, "people": None, "region": None, "credit": None,
         "sources": [], "notes": []}
    m = re.search(r"이행실적은?\s*[^.]{0,120}?추정가격\s*대비\s*최근\s*(\d)\s*년", f) or \
        re.search(r"추정가격\s*대비\s*최근\s*(\d)\s*년[^.]{0,80}?실적", f)
    if not m:
        return q
    yrs = int(m.group(1))
    md = re.search(r"평가기준\s*규모\s*:?\s*([\d,]{7,})\s*원", f)
    denom = int(md.group(1).replace(",", "")) if md else None
    if not denom:
        try:
            denom = int(str(item.get("price_est") or item.get("budget")))
        except (TypeError, ValueError):
            denom = None
    mf = re.search(r"인정범위\s*:?\s*([^.*]{4,80})", f)
    ftext = mf.group(1).strip() if mf else ""
    fields, keys = find_fields(ftext or f[:4000])
    q["perf"] = {"window_years": yrs, "denom": denom, "denom_src": "평가기준 규모" if md else "추정가격",
                 "bands": [], "top_score": None, "top_min": 100,
                 "max_score": None, "fields": fields or [], "field_keys": keys,
                 "in_scope": bool(keys), "mode": "적격심사",
                 "note": f[m.start(): m.start() + 260]}
    q["status"] = "parsed"
    return q


def parse_item(item, texts):
    q = {"status": "no_attachment", "kind": None, "total": None, "items": [],
         "perf": None, "people": None, "region": None, "credit": None,
         "sources": [], "notes": []}
    contract = item.get("contract") or ""
    q["kind"] = "협상" if "협상" in contract else ("적격심사" if "적격심사" in contract else
                                                   ("소액수의" if ("소액" in contract or "수의" in contract) else contract or None))
    if not texts:
        return q
    if q["kind"] == "적격심사":
        cand = sorted(texts, key=lambda x: -(x[1].count("이행실적") + x[1].count("적격심사")))
        for name, t in cand:
            q2 = parse_qualification(t, item)
            if q2["status"] == "parsed":
                q2["sources"] = [name]
                return q2
        return q
    best = None
    for name, t in texts:
        f = flat(t)
        its = item_scores(t)
        pscore = perf_score_of(its)
        loc = find_perf_table(t)
        rows = len(parse_bands(t[loc[0]:loc[1]], pscore)) if loc else 0
        if rows < 2:
            continue
        score = 10 + rows
        score += 6 if re.search(r"정량(?:적)?\s*평가\s*\(?\s*\d{1,2}\s*점", f) else 0
        score += 3 if "경영상태" in f else 0
        if best is None or score > best[0]:
            best = (score, name, t)
    if not best or best[0] < 4:
        return q
    _, name, text = best
    if q["kind"] == "적격심사":
        q2 = parse_qualification(text, item)
    else:
        q2 = parse_negotiation(text, item)
    q2["sources"] = [name]
    return q2


# ---------------------------------------------------------------- 낙찰사 프로필
def load_companies():
    doc = json.loads(REG.read_text(encoding="utf-8"))
    return doc["companies"]


def build_profiles(comps, asof=None):
    """낙찰사별 분야 실적 프로필(최근 3년·5년 합계/최대 단일/건수).

    금액은 지분율 반영(확정) 실적이고, 지분 미확인 건은 amount_unknown(총액 기준)으로 따로 센다.
    """
    asof = asof or date.today().isoformat()
    base = datetime.strptime(asof[:10], "%Y-%m-%d").date()
    out = []
    for c in comps:
        prof = {"key": c["key"], "name": c["display"],
                "area": " ".join(x for x in (c.get("sido"), c.get("sigungu")) if x),
                "sido": c.get("sido"), "sigungu": c.get("sigungu"),
                "inds": c.get("inds") or [], "win_count": c.get("win_count"),
                "win_amount": c.get("win_amount"), "last_win": c.get("last_win"),
                "win_amount_unknown": c.get("win_amount_unknown"),
                "share_unknown_wins": c.get("share_unknown_wins"),
                "fields": {}, "people": None, "credit": None}
        for yrs in (3, 5):
            start = base - timedelta(days=365 * yrs + 2)
            agg = {}
            for w in c.get("wins") or []:
                try:
                    d = datetime.strptime((w.get("date") or "")[:10], "%Y-%m-%d").date()
                except Exception:                    # noqa: BLE001
                    continue
                if d < start or d > base:
                    continue
                fl = w.get("field") or "기타"
                a = agg.setdefault(fl, {"n": 0, "amount": 0, "max_single": 0,
                                        "amount_unknown": 0, "n_unknown": 0})
                a["n"] += 1
                if w.get("amount") is not None:
                    a["amount"] += int(w.get("amount") or 0)
                    a["max_single"] = max(a["max_single"], int(w.get("amount") or 0))
                if w.get("amount_unknown"):
                    a["amount_unknown"] += int(w["amount_unknown"])
                if (w.get("mode") or "").startswith("지분미확인"):
                    a["n_unknown"] += 1
            prof["fields"][f"{yrs}y"] = agg
        out.append(prof)
    return out


def perf_of(comp, q, asof):
    p = q.get("perf")
    if not p or not p.get("field_keys"):
        return None
    yrs = p["window_years"]
    try:
        base = datetime.strptime(asof[:10], "%Y-%m-%d").date()
    except Exception:                                # noqa: BLE001
        base = date.today()
    start = base - timedelta(days=365 * yrs + 2)
    amt, n, rows = 0, 0, []
    amt_unk, n_unk = 0, 0
    for w in comp.get("wins") or []:
        if w.get("field") not in p["field_keys"]:
            continue
        try:
            d = datetime.strptime((w.get("date") or "")[:10], "%Y-%m-%d").date()
        except Exception:                            # noqa: BLE001
            continue
        if d < start or d > base:
            continue
        n += 1
        rows.append(w)
        if w.get("amount") is not None:
            amt += int(w.get("amount") or 0)
        if w.get("amount_unknown"):
            amt_unk += int(w["amount_unknown"])
        if (w.get("mode") or "").startswith("지분미확인"):
            n_unk += 1
    ratio = amt / p["denom"] if p.get("denom") else 0
    ratio_max = (amt + amt_unk) / p["denom"] if p.get("denom") else 0
    band = None
    for b in p.get("bands") or []:
        if ratio * 100 >= b["min"]:
            band = b
            break
    band_max = None
    for b in p.get("bands") or []:
        if ratio_max * 100 >= b["min"]:
            band_max = b
            break
    return {"amt": amt, "n": n, "ratio": round(ratio * 100, 1),
            "amt_unknown": amt_unk, "n_unknown": n_unk,
            "ratio_max": round(ratio_max * 100, 1), "band_max": band_max,
            "band": band, "score": (band or {}).get("score"),
            "max_score": p.get("max_score") or p.get("top_score"),
            "window": yrs, "denom": p.get("denom"),
            "recent": sorted(rows, key=lambda x: x.get("date") or "", reverse=True)[:2]}


def quant_verdict(comp, q, asof):
    """(판정, 근거문장, 상세) — 판정: 부합/근접/부족/미달/확인불가"""
    p = q.get("perf")
    if not p:
        return "확인불가", "공고문에서 정량 실적 기준선을 확인하지 못함", None
    if not p.get("field_keys"):
        return "확인불가", "실적 인정분야가 우리 실적DB 수집 분야 밖(유지관리·연구 등)", None
    if not p.get("in_scope"):
        return "확인불가", "실적 인정분야가 우리 실적DB 수집 분야 밖(유지관리·운영 등)", None
    if not p.get("denom"):
        return "확인불가", "사업규모(추정가격) 확인 불가", None
    pr = perf_of(comp, q, asof)
    if pr is None:
        return "확인불가", "실적 기준선 확인 불가", None
    head = (f"최근 {pr['window']}년 {'·'.join(p['fields'][:3])} 실적 {pr['amt']/1e8:.1f}억"
            f"({pr['n']}건) · 기준 {pr['denom']/1e8:.2f}억의 {pr['ratio']:.0f}%")
    if pr["band"]:
        head += f" · 배점 {pr['score']}/{pr['max_score']}"
    if pr["n_unknown"]:
        head += (f" · 지분 미확인 {pr['n_unknown']}건 {pr['amt_unknown']/1e8:.1f}억(총액 기준,"
                 f" 포함 시 최대 {pr['ratio_max']:.0f}%)")
    if pr["ratio"] >= p["top_min"]:
        return "부합", head, pr
    if pr["ratio"] >= 70:
        return "근접", head, pr
    if pr["ratio"] >= 40:
        return "부족", head, pr
    return "미달", head, pr


SIDO_EQUIV = {
    "전남광주통합특별시": {"전남광주통합특별시", "광주광역시", "전라남도"},
    "광주광역시": {"광주광역시", "전남광주통합특별시"},
    "전라남도": {"전라남도", "전남광주통합특별시"},
    "강원특별자치도": {"강원특별자치도", "강원도"},
    "전북특별자치도": {"전북특별자치도", "전라북도"},
}


def same_sido(a, b):
    if not a or not b:
        return False
    return a == b or a in SIDO_EQUIV.get(b, set()) or b in SIDO_EQUIV.get(a, set())


def ind_label(kind):
    if kind == "sw":
        return "SW사업자"
    if kind.startswith("eng:"):
        return "엔지니어링·" + kind[4:]
    return kind


def holds_kind(comp, kind):
    inds = comp.get("inds") or []
    if kind == "sw":
        return "SW사업자" in inds
    if kind.startswith("eng:"):
        return ("엔지니어링:" + kind[4:]) in inds
    if kind.startswith("unknown:") or kind == "out":
        return None                       # 원부로 판정할 수 없는 요건
    return kind in inds


def local_region_candidates(q, comps, req_kinds=None, asof=None, limit=8):
    """지역상생 배점이 걸린 공고 — 그 시·도에 본사를 둔 유력 업체를 실적으로 추린다.

    조건: ① 원부 소재지 시·도 일치 ② 공고 입찰참가자격 업종 중 1개 이상 보유(요건 파싱된 경우)
          ③ 우리 실적DB에 낙찰 실적이 있음 — 인정분야 실적을 우선하고, 모자라면 타 분야로 보충
    """
    reg = q.get("region") or {}
    sido = reg.get("sido")
    field_keys = (q.get("perf") or {}).get("field_keys") or []
    fields_txt = (q.get("perf") or {}).get("fields") or []
    if not sido:
        return {"sido": None, "keyword": reg.get("keyword"), "companies": [],
                "basis": "공고문에서 지역(시·도)을 특정하지 못함"}
    try:
        base = datetime.strptime((asof or date.today().isoformat())[:10], "%Y-%m-%d").date()
    except Exception:                                  # noqa: BLE001
        base = date.today()
    start = base - timedelta(days=365 * 3 + 2)
    kinds = [k for k in (req_kinds or []) if k]
    out = []
    for c in comps:
        if not same_sido(c.get("sido"), sido):
            continue
        held = [k for k in kinds if holds_kind(c, k) is True]
        unknown_k = [k for k in kinds if holds_kind(c, k) is None]
        if kinds and not held and len(unknown_k) < len(kinds):
            continue                       # 보유 업종이 하나도 없으면 제외
        f_amt = f_n = f_unk_n = f_unk_amt = 0
        other = {}
        for w in c.get("wins") or []:
            try:
                d = datetime.strptime((w.get("date") or "")[:10], "%Y-%m-%d").date()
            except Exception:                          # noqa: BLE001
                continue
            if d < start or d > base:
                continue
            if w.get("field") in field_keys:
                f_n += 1
                f_amt += int(w.get("amount") or 0)
                if w.get("amount_unknown"):
                    f_unk_amt += int(w["amount_unknown"])
                    f_unk_n += 1
            else:
                o = other.setdefault(w.get("field") or "기타", {"n": 0, "amount": 0})
                o["n"] += 1
                o["amount"] += int(w.get("amount") or 0)
        if not f_n and not other:
            continue
        out.append({"key": c["key"], "name": c["display"], "addr": c.get("addr"),
                    "area": " ".join(x for x in (c.get("sido"), c.get("sigungu")) if x),
                    "inds": held[:4], "inds_unknown": unknown_k[:2],
                    "field_amt": f_amt, "field_n": f_n,
                    "field_unknown_amt": f_unk_amt, "field_unknown_n": f_unk_n,
                    "other": other, "last": c.get("last_win"),
                    "wins_total": c.get("win_count")})
    out.sort(key=lambda x: (-x["field_amt"], -x["field_n"], -sum(o["amount"] for o in x["other"].values()),
                            x["name"]))
    picked = [x for x in out if x["field_n"]][:limit]
    if len(picked) < min(5, len(out)):
        picked += [x for x in out if not x["field_n"]][:limit - len(picked)]
    for x in picked:
        why = [f"{x['area']} 소재(원부)"]
        if x["field_n"]:
            why.append(f"{'·'.join(fields_txt[:2]) or '인정분야'} 실적 {x['field_amt'] / 1e8:.1f}억({x['field_n']}건)")
            if x["field_unknown_n"]:
                why.append(f"지분 미확인 {x['field_unknown_n']}건 {x['field_unknown_amt'] / 1e8:.1f}억 포함(총액 기준)")
        else:
            top = max(x["other"].items(), key=lambda kv: kv[1]["amount"])
            why.append(f"인정분야 실적 없음 — {top[0]} {top[1]['amount'] / 1e8:.1f}억({top[1]['n']}건)")
        if x["inds"]:
            why.append("보유 " + ", ".join(ind_label(k) for k in x["inds"][:3]))
        else:
            core = [i for i in (next((cc.get("inds") for cc in comps if cc["key"] == x["key"]), []) or [])
                    if i in ("SW사업자", "공간정보사업자", "공공측량업", "직지측량업", "수치지도제작업",
                             "공간영상도화업", "지하시설물측량업", "지도제작업", "일반측량업")]
            if core:
                why.append("보유(참고) " + ", ".join(core[:3]))
        x["why"] = why
    return {"sido": sido, "keyword": reg.get("keyword"),
            "basis": "본사 소재지(협회·엔지니어링 원부) 시·도 일치 · 최근 3년 낙찰 실적순",
            "fields": fields_txt, "companies": picked,
            "pool_n": len(out),
            "note": ("공동수급 지분 배점용 — 인정분야 실적은 지분 반영 금액 기준"
                     if field_keys else "공고 실적 인정분야 미확인 — 전체 실적 기준")}


def quant_block(item, comps, asof=None, man=None, cache=None, req_kinds=None):
    key = f"{item['no']}-{item.get('order') or '000'}"
    if cache is not None and key in cache:
        return cache[key]
    man = man if man is not None else (json.loads(MAN.read_text(encoding="utf-8")) if MAN.exists() else {})
    texts = []
    for f in man.get(key) or []:
        p = f.get("text")
        if p and pathlib.Path(p).exists():
            texts.append((f.get("file") or pathlib.Path(p).name,
                          pathlib.Path(p).read_text(encoding="utf-8")))
    q = parse_item(item, texts)
    asof = asof or item.get("posted") or ""
    res = {"fit": [], "near": [], "low": [], "unknown": [], "cap": []}
    p = q.get("perf") or {}
    top_min = p.get("top_min")
    for c in comps:
        v, why, pr = quant_verdict(c, q, asof)
        row = {"key": c["key"], "name": c["display"],
               "area": " ".join(x for x in (c.get("sido"), c.get("sigungu")) if x),
               "why": why, "ratio": (pr or {}).get("ratio"), "amt": (pr or {}).get("amt"),
               "n": (pr or {}).get("n"), "score": (pr or {}).get("score"),
               "ratio_max": (pr or {}).get("ratio_max"),
               "n_unknown": (pr or {}).get("n_unknown"),
               "max_score": (pr or {}).get("max_score")}
        bucket = {"부합": "fit", "근접": "near", "부족": "low", "미달": "low",
                  "확인불가": "unknown"}[v]
        # 확정 실적으로는 기준선 미달이나, 지분 미확인 건을 총액으로 보면 넘는 경우
        if (bucket in ("near", "low") and top_min and pr and pr.get("n_unknown")
                and (pr.get("ratio") or 0) < top_min and (pr.get("ratio_max") or 0) >= top_min):
            bucket = "cap"
        res[bucket].append(row)
    for k in ("fit", "near", "low"):
        res[k].sort(key=lambda r: -(r["ratio"] or 0))
    res["cap"].sort(key=lambda r: -(r["ratio_max"] or 0))
    if q.get("region"):
        res["region_local"] = local_region_candidates(q, comps, req_kinds=req_kinds, asof=asof)
    if cache is not None:
        cache[key] = (q, res)
    return q, res


def summary(q, res):
    """웹 표시용 정량 블록(간결)."""
    p = q.get("perf") or {}
    if q.get("status") == "parsed" and p.get("in_scope"):
        state = "fit"
    elif q.get("status") == "parsed":
        state = "parsed_out"
    else:
        state = "unparsed"
    perf = None
    if p:
        perf = {"window": p.get("window_years"), "denom": p.get("denom"),
                "denom_src": p.get("denom_src"), "fields": p.get("fields") or [],
                "bands": p.get("bands") or [], "top_min": p.get("top_min"),
                "top_score": p.get("top_score"), "max_score": p.get("max_score"),
                "mode": p.get("mode"), "in_scope": bool(p.get("in_scope")),
                "note": (p.get("note") or "")[:240]}
    return {"state": state, "status": q.get("status"), "kind": q.get("kind"),
            "total": q.get("total"), "items": q.get("items") or [],
            "perf": perf,
            "people": q.get("people"), "region": q.get("region"), "credit": q.get("credit"),
            "sources": q.get("sources") or [],
            "region_local": res.get("region_local"),
            "counts": {"fit": len(res["fit"]), "near": len(res["near"]),
                       "low": len(res["low"]), "unknown": len(res["unknown"]),
                       "cap": len(res.get("cap") or [])}}


if __name__ == "__main__":
    data = json.loads((HERE.parent / "data.json").read_text(encoding="utf-8"))
    comps = load_companies()
    man = json.loads(MAN.read_text(encoding="utf-8"))
    profs = build_profiles(comps, data["updated_at"][:10])
    PROF.write_text(json.dumps({"built_at": datetime.now().isoformat(timespec="seconds"),
                                "asof": data["updated_at"][:10], "count": len(profs),
                                "companies": profs}, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = inc = 0
    for it in data["items"]:
        if it["kind"] != "bid":
            continue
        key = f"{it['no']}-{it.get('order') or '000'}"
        if key not in man:
            continue
        q, res = quant_block(it, comps)
        p = q.get("perf") or {}
        bands = "/".join(f"{b['min']}:{b['score']}" for b in (p.get("bands") or []))
        print(f"{it['no']} {q['status']:12s} {q['kind'] or '-':4s} t={q['total']} "
              f"perf={p.get('window_years')}y denom={p.get('denom')} bands={bands} "
              f"f={','.join(p.get('fields') or [])} scope={p.get('in_scope')} "
              f"fit={len(res['fit'])} near={len(res['near'])} low={len(res['low'])} unk={len(res['unknown'])} "
              f"| {it['title'][:30]}")
        ok += q["status"] == "parsed"
        inc += bool(p.get("in_scope"))
    print("parsed", ok, "in_scope", inc, "profiles", len(profs))
