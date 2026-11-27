#!/usr/bin/env python3
"""협회·공공 원부에서 업체별 업등록 현황을 수집해 company_registry.json 을 만든다.

수집 대상(1차 원부)
  1) 한국공간정보산업협회(KASM) 측량업체 검색  — 측량업 11개 업종 + 공간정보사업자
     POST https://www.kasm.or.kr/mbi/selectEnterpriseList.do  (비로그인 조회 가능)
  2) 엔지니어링종합정보시스템(ETIS) 엔지니어링사업자 — 전문분야(도시계획·도로공항·교통·측량지적 등)
     POST https://www.etis.or.kr/webs/qry/QryChaeList.jsp?topParam=5 → QryChaeView.jsp?company_id=
  3) SW산업정보종합시스템(SWIT) SW사업자 공개검색 — 엑셀 전체목록 스냅샷(sources/swit_sw_business.json)
     (swit.or.kr 은 브라우저 TLS 지문이 아니면 연결이 끊겨, 전체목록 엑셀을 내려받아 스냅샷으로 쓴다)

pool(수집 대상 업체)은 다음에서 뽑는다.
  - work/도로대장_최근3년_낙찰자별_정량평가기준.xlsx  '2.전체공고_낙찰·정량기준'
  - work/공간정보_최근5년_토적·용도지역·연속도면_낙찰자별_정량기준.xlsx '2.전체공고_낙찰·정량기준'
  - scan/enriched.json 의 개찰결과 winner_name
  - ㈜웨이즈원(당사)

사용법
  python3 fetch_registry.py            # 캐시 사용, 없는 업체만 조회
  python3 fetch_registry.py --refresh  # 전 업체 재조회
"""
import json, re, sys, time, pathlib, unicodedata
from datetime import datetime, timezone, timedelta

import requests
import openpyxl

HERE = pathlib.Path(__file__).parent
SCAN = HERE
WORK = SCAN.parent.parent
REG = HERE / "registry"
OUT = REG / "company_registry.json"
POOL_OUT = REG / "winners_pool.json"
RAW = REG / "raw"
CACHE = REG / "cache"
SOURCES = REG / "sources"
for d in (RAW, CACHE, SOURCES):
    d.mkdir(parents=True, exist_ok=True)

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}

ROAD_XLSX = WORK / "도로대장_최근3년_낙찰자별_정량평가기준.xlsx"
SPACE_XLSX = WORK / "공간정보_최근5년_토적·용도지역·연속도면_낙찰자별_정량기준.xlsx"


# ---------------------------------------------------------------- 이름 정규화
JUNK = ["주식회사", "유한회사", "합자회사", "㈜", "(주)", "（주）", "( 유 )", "유"]
def norm(name: str) -> str:
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = s.replace("(주)", "").replace("（주）", "").replace("㈜", "")
    s = s.replace("주식회사", "").replace("유한회사", "")
    s = re.sub(r"[\s\.·,·\-_/]", "", s)
    return s.lower()


def core_name(name: str) -> str:
    """법인격 표기·괄호를 떼고 원부 검색에 쓰는 이름만 남긴다."""
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = s.replace("(주)", "").replace("（주）", "").replace("㈜", "")
    s = s.replace("주식회사", "").replace("유한회사", "")
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- 1) 낙찰사 pool
def _rows(path, sheet, header_row):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet]
    it = ws.iter_rows(min_row=header_row, values_only=True)
    hdr = [str(c).strip() if c is not None else "" for c in next(it)]
    for r in it:
        if all(c is None for c in r):
            continue
        yield dict(zip(hdr, r))
    wb.close()


def build_pool():
    pool = {}

    def add(raw, field, amount=None, org=None, date=None, no=None, title=None, src=""):
        raw = str(raw).strip()
        if not raw or raw in ("—", "-", "None"):
            return
        k = norm(raw)
        if not k:
            return
        e = pool.setdefault(k, {"key": k, "raw_names": {}, "wins": []})
        e["raw_names"][raw] = e["raw_names"].get(raw, 0) + 1
        e["wins"].append({"field": field, "amount": amount, "org": org,
                          "date": str(date)[:10] if date else None,
                          "no": no, "title": title, "src": src})

    if ROAD_XLSX.exists():
        for d in _rows(ROAD_XLSX, "2.전체공고_낙찰·정량기준", 2):
            add(d.get("낙찰자"), "도로대장", d.get("낙찰금액"), d.get("발주기관"),
                d.get("공고일"), d.get("공고번호"), d.get("사업명"), "xlsx:도로대장3년")
    if SPACE_XLSX.exists():
        for d in _rows(SPACE_XLSX, "2.전체공고_낙찰·정량기준", 2):
            f = str(d.get("분야") or "").strip() or "공간정보"
            f = f.replace("②-b ", "").replace("②-c ", "").replace("② ", "").replace("③ ", "").replace("① ", "")
            add(d.get("낙찰자"), f, d.get("낙찰금액"), d.get("발주기관"),
                d.get("공고일"), d.get("공고번호"), d.get("사업명"), "xlsx:공간정보5년")
    enr = json.loads((SCAN / "enriched.json").read_text(encoding="utf-8"))
    for no, v in enr.get("detail", {}).items():
        w = v.get("winner_name")
        if w:
            add(w, "최근 공고", v.get("winner_amount"), None, v.get("opened_at"), no, None, "enriched")
    add("㈜웨이즈원", "당사", None, None, None, None, None, "self")

    out = []
    for k, e in pool.items():
        best = max(e["raw_names"], key=lambda n: (e["raw_names"][n], len(n)))
        amts = [w["amount"] for w in e["wins"] if isinstance(w["amount"], (int, float))]
        by_field = {}
        for w in e["wins"]:
            b = by_field.setdefault(w["field"], {"n": 0, "amount": 0})
            b["n"] += 1
            if isinstance(w["amount"], (int, float)):
                b["amount"] += int(w["amount"])
        dates = sorted([w["date"] for w in e["wins"] if w["date"]])
        out.append({
            "key": k,
            "display": best,
            "raw_names": list(e["raw_names"]),
            "win_count": len(e["wins"]),
            "win_amount": int(sum(amts)),
            "by_field": by_field,
            "last_win": dates[-1] if dates else None,
            "wins": sorted(e["wins"], key=lambda w: w.get("date") or "", reverse=True)[:12],
            "is_self": k == norm("웨이즈원"),
        })
    out.sort(key=lambda x: (-x["win_count"], -x["win_amount"], x["display"]))
    return out


# ---------------------------------------------------------------- 2) KASM
KASM_UPJONG = {"01": "측지측량업", "02": "연안조사측량업", "03": "항공촬영업", "04": "공간영상도화업",
               "05": "지도제작업", "06": "수치지도제작업", "07": "지하시설물측량업", "08": "공공측량업",
               "09": "영상처리업", "10": "일반측량업", "11": "지적측량업", "12": "지적편집도간행판매업",
               "98": "공간정보사업자", "99": "특별회원"}


class Kasm:
    url_list = "https://www.kasm.or.kr/mbi/selectEnterpriseList.do"
    url_main = "https://www.kasm.or.kr/mbi/selectEnterpriseListVw.do"

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(HDRS)
        self.ready = False

    def _boot(self):
        if self.ready:
            return
        self.s.get(self.url_main, timeout=30)
        self.ready = True

    def search(self, name, cache=True):
        fp = RAW / "kasm" / (norm(name) + ".json")
        fp.parent.mkdir(parents=True, exist_ok=True)
        if cache and fp.exists():
            return json.loads(fp.read_text(encoding="utf-8"))
        self._boot()
        data = {"enteHang": core_name(name), "deleHang": "", "pageIndex": "1", "cityCode": "",
                "sigunguCode": "", "upJongCode": "", "addr": ""}
        res = {}
        try:
            r = self.s.post(self.url_list, data=data, timeout=30,
                            headers={"X-Requested-With": "XMLHttpRequest",
                                     "Referer": self.url_main})
            r.encoding = "utf-8"
            res = r.json()
        except Exception as e:                        # noqa: BLE001
            res = {"error": f"{type(e).__name__}: {e}"}
        fp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.4)
        return res

    def company(self, name):
        """업체명으로 조회해 같은 업체 레코드를 묶어 돌려준다."""
        d = self.search(name)
        lst = (d.get("resultData") or {}).get("resultList") or []
        if not lst:
            return None
        groups = {}
        for r in lst:
            g = groups.setdefault(norm(r.get("enteHang", "")), {"name": r.get("enteHang"),
                                                                "addr": r.get("addr"), "inds": {},
                                                                "enteCode": r.get("enteCode"),
                                                                "ceis": r.get("ceisEnteCode"),
                                                                "repr": r.get("deleHang"),
                                                                "tel": r.get("tellNumb")})
            code = r.get("upJongCode")
            g["inds"][r.get("upJongName") or KASM_UPJONG.get(code, code)] = {
                "no": r.get("upRegiNumb"), "date": r.get("upRegiYmd")}
        target = norm(name)
        exact = [g for k, g in groups.items() if k == target]
        if exact:
            return exact[0]
        near = [g for k, g in groups.items()
                if (k.startswith(target) or target.startswith(k)) and abs(len(k) - len(target)) <= 6]
        if len(near) == 1:
            return near[0]
        if len(groups) == 1:
            return list(groups.values())[0]
        return {"ambiguous": [g["name"] for g in groups.values()]}


# ---------------------------------------------------------------- 3) ETIS
class Etis:
    url_list = "https://www.etis.or.kr/webs/qry/QryChaeList.jsp?topParam=5"
    url_view = "https://www.etis.or.kr/webs/qry/QryChaeView.jsp"

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(HDRS)

    def search(self, name, cache=True):
        fp = RAW / "etis" / (norm(name) + ".json")
        fp.parent.mkdir(parents=True, exist_ok=True)
        if cache and fp.exists():
            return json.loads(fp.read_text(encoding="utf-8"))
        out = []
        try:
            r = self.s.post(self.url_list, timeout=30, data={
                "actcode": "1", "befpage": "/webs/qry/QryChaeList.jsp", "currentpage": "1",
                "act_nm": core_name(name), "addr": ""})
            for m in re.finditer(r'detailView\("company_id=(\d+)"\)[^>]*>([^<]+)</a>', r.text):
                out.append({"company_id": m.group(1), "name": m.group(2).strip()})
        except Exception as e:                        # noqa: BLE001
            out = [{"error": f"{type(e).__name__}: {e}"}]
        fp.write_text(json.dumps({"hits": out}, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.3)
        return {"hits": out}

    def detail(self, company_id, cache=True):
        fp = RAW / "etis" / f"view_{company_id}.json"
        if cache and fp.exists():
            return json.loads(fp.read_text(encoding="utf-8"))
        res = {}
        try:
            r = self.s.get(self.url_view, params={"company_id": company_id}, timeout=30)
            txt = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style).*?</\1>", " ", r.text, flags=re.S))
            txt = re.sub(r"\s+", " ", txt)
            res["bizno"] = (re.search(r"사업자등록번호\s*([\d-]{8,})", txt) or [None, None])[1]
            res["addr"] = (re.search(r"소재지\s*(.{5,120}?)\s*대표자", txt) or [None, None])[1]
            # 엔지니어링업 신고번호·전문분야 / 컨설팅업
            m = re.search(r"엔지니어링업\s*신고번호\s*(\S+)\s*신고일자\s*(\S+)", txt)
            if m:
                res["eng_no"], res["eng_date"] = m.group(1), m.group(2)
            fields = re.findall(r"\[기술부문\]\s*전문분야\s*(.*?)(?=\s*엔지니어링컨설팅업|\s*\[기술부문\]|\s*닫기|$)", txt)
            res["fields_raw"] = " / ".join(f.strip() for f in fields if f.strip())
            # '[건설] 도로공항, 교통, 도시계획' → 부문=건설, 분야=[도로공항, 교통, 도시계획]
            spec, part = [], []
            for grp in re.findall(r"\[([^\]]*)\]\s*([^\[\]]*)", res["fields_raw"]):
                part.append(grp[0].strip())
                for tok in re.split(r"[,·/]", grp[1]):
                    tok = tok.strip()
                    if tok and tok not in spec:
                        spec.append(tok)
            res["parts"] = sorted(set(p for p in part if p))
            res["specialties"] = spec
            res["_text"] = txt[:1200]
        except Exception as e:                        # noqa: BLE001
            res = {"error": f"{type(e).__name__}: {e}"}
        fp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.3)
        return res

    def company(self, name, hint_addr=None):
        hits = [h for h in self.search(name).get("hits", []) if "company_id" in h]
        if not hits:
            return None
        target = norm(name)
        exact = [h for h in hits if norm(h["name"]) == target]
        cands = exact or hits
        dets = []
        for h in cands[:3]:
            det = self.detail(h["company_id"])
            det["company_id"] = h["company_id"]
            det["name"] = h["name"]
            dets.append(det)
        if hint_addr:
            hs, hg = sido_of(hint_addr), sigungu_of(hint_addr)
            same = [d for d in dets if d.get("addr") and sido_of(d["addr"]) == hs
                    and (not hg or sigungu_of(d["addr"]) == hg)]
            if same:
                return same[0]
        if len(dets) == 1:
            return dets[0]
        return {"ambiguous": [d.get("name") for d in dets], "candidates": dets}


# ---------------------------------------------------------------- 4) SWIT 스냅샷
def load_swit():
    import gzip
    fp = SOURCES / "swit_sw_business.json.gz"
    if not fp.exists():
        fp = SOURCES / "swit_sw_business.json"
        if not fp.exists():
            return None
    opener = gzip.open if fp.suffix == ".gz" else open
    with opener(fp, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def parse_swit_xls(path, out=None):
    """SWIT 공개검색 엑셀(HTML 표)을 정규화 JSON으로 바꾼다."""
    import html
    raw = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", raw, flags=re.S)
    recs = {}
    for r in rows[1:]:
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)]
        if len(cells) < 5:
            continue
        name, addr, repr_, size, status = cells[0], cells[1], cells[2], cells[3], cells[4]
        k = norm(name)
        if not k:
            continue
        recs[k] = {"name": name, "addr": addr, "repr": repr_, "size": size,
                   "status": status, "sp": cells[5] if len(cells) > 5 else None}
    data = {"source": "SWIT 소프트웨어사업자 공개검색 엑셀 다운로드",
            "downloaded_from": "https://www.swit.or.kr/IS/web/birPublic_SearhList.jsp (엑셀 전체목록)",
            "collected_at": datetime.now(KST).isoformat(timespec="seconds"),
            "count": len(recs), "companies": recs}
    import gzip
    out = pathlib.Path(out or (SOURCES / "swit_sw_business.json.gz"))
    if out.suffix == ".gz":
        with gzip.open(out, "wt", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    else:
        out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# ---------------------------------------------------------------- main
def main():
    refresh = "--refresh" in sys.argv
    pool = build_pool()
    POOL_OUT.write_text(json.dumps({"built_at": datetime.now(KST).isoformat(timespec="seconds"),
                                    "count": len(pool), "companies": pool},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pool] 업체 {len(pool)}곳 (낙찰 이력 기준)")

    kasm, etis = Kasm(), Etis()
    swit = load_swit() or {"companies": {}}
    swi = swit.get("companies", {})

    entries = []
    stat = {"kasm": 0, "etis": 0, "swit": 0, "none": 0}
    for i, p in enumerate(pool, 1):
        name = p["display"]
        e = {"key": p["key"], "display": name, "raw_names": p["raw_names"],
             "win_count": p["win_count"], "win_amount": p["win_amount"],
             "by_field": p["by_field"], "last_win": p["last_win"],
             "wins": p["wins"], "is_self": p["is_self"]}

        k = kasm.company(name)
        if k and "ambiguous" not in k:
            e["kasm"] = {"name": k["name"], "addr": k.get("addr"), "repr": k.get("repr"),
                         "tel": k.get("tel"), "ente_code": k.get("enteCode"),
                         "ceis_code": k.get("ceis"), "inds": k["inds"],
                         "ind_names": list(k["inds"].keys())}
            stat["kasm"] += 1
        elif k:
            e["kasm"] = {"ambiguous": k["ambiguous"]}

        hint = (e.get("kasm") or {}).get("addr")
        g = etis.company(name, hint_addr=hint)
        if g and "ambiguous" not in g:
            e["etis"] = {kk: g.get(kk) for kk in
                         ("name", "company_id", "bizno", "addr", "eng_no", "eng_date",
                          "parts", "specialties", "fields_raw")}
            stat["etis"] += 1
        elif g:
            e["etis"] = {"ambiguous": g["ambiguous"]}

        s = swi.get(p["key"])
        if s:
            e["sw"] = {"status": s["status"], "size": s["size"], "addr": s["addr"],
                       "sp": s.get("sp")}
            stat["swit"] += 1

        # 소재지: KASM > ETIS > SWIT
        e["addr"] = hint or (e.get("etis") or {}).get("addr") or (e.get("sw") or {}).get("addr")
        e["sido"] = sido_of(e["addr"])
        e["sigungu"] = sigungu_of(e["addr"])
        e["repr"] = (e.get("kasm") or {}).get("repr") or (e.get("sw") or {}).get("repr")

        # 동명이인 점검 — 원부 간 소재지 시·군이 어긋나면 다른 업체로 본다
        conflict = []
        base = loc_key(e["addr"])
        for src in ("etis", "sw"):
            a = (e.get(src) or {}).get("addr")
            lk = loc_key(a)
            if base and lk and base != lk:
                conflict.append(f"{src}:{lk}")
        if conflict:
            e["identity_conflict"] = conflict
            e["etis_used"] = not any(c.startswith("etis") for c in conflict)
            e["sw_used"] = not any(c.startswith("sw") for c in conflict)
        else:
            e["etis_used"] = bool(e.get("etis") and "ambiguous" not in e["etis"])
            e["sw_used"] = bool(e.get("sw"))

        inds = set((e.get("kasm") or {}).get("ind_names") or [])
        if e["etis_used"]:
            for sp in (e.get("etis") or {}).get("specialties") or []:
                inds.add(f"엔지니어링:{sp}")
        if e["sw_used"]:
            inds.add("SW사업자")
        e["inds"] = sorted(inds)
        if not e["inds"]:
            stat["none"] += 1
        entries.append(e)
        if i % 20 == 0:
            print(f"  ... {i}/{len(pool)}")

    entries.sort(key=lambda x: (not x["is_self"], -x["win_count"], -x["win_amount"], x["display"]))
    doc = {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "pool_source": {
            "도로대장 3년": str(ROAD_XLSX.relative_to(WORK)),
            "공간정보 5년": str(SPACE_XLSX.relative_to(WORK)),
            "개찰결과": "scan/enriched.json",
        },
        "sources": {
            "kasm": {"name": "한국공간정보산업협회 측량업체 검색", "url": Kasm.url_main,
                     "method": "POST /mbi/selectEnterpriseList.do (비로그인)", "scope": "측량업 11종·공간정보사업자·소재지·등록번호"},
            "etis": {"name": "엔지니어링종합정보시스템 엔지니어링사업자", "url": Etis.url_list,
                     "method": "POST QryChaeList.jsp → QryChaeView.jsp", "scope": "엔지니어링업 신고·전문분야"},
            "swit": {"name": "SW산업정보종합시스템 SW사업자 공개검색", "url": "https://www.swit.or.kr/IS/web/birPublic_SearhList.jsp",
                     "method": "전체목록 엑셀 스냅샷", "scope": "SW사업자 신고·기업규모·소재지",
                     "collected_at": swit.get("collected_at")},
            "smpp": {"name": "중소기업제품 공공구매종합정보망(직접생산확인)", "url": "https://www.smpp.go.kr/",
                     "status": "미연결 — 직접생산확인 조회는 기업회원 로그인 필요(비로그인 공개조회 없음)"},
            "g2b": {"name": "나라장터 입찰참가자격 등록업종", "url": "https://www.g2b.go.kr/",
                    "status": "공고별 industry_limit 필드로 대체"},
        },
        "stats": {"companies": len(entries), **stat},
        "companies": entries,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] {OUT} — 업체 {len(entries)}곳 / KASM {stat['kasm']} · ETIS {stat['etis']} · SWIT {stat['swit']} / 업종 없음 {stat['none']}")


# ---------------------------------------------------------------- 지역 파싱
SIDO_RE = [("서울", "서울특별시"), ("부산", "부산광역시"), ("대구", "대구광역시"), ("인천", "인천광역시"),
           ("광주", "광주광역시"), ("대전", "대전광역시"), ("울산", "울산광역시"), ("세종", "세종특별자치시"),
           ("경기", "경기도"), ("강원", "강원특별자치도"), ("충북", "충청북도"), ("충남", "충청남도"),
           ("전북", "전북특별자치도"), ("전남", "전라남도"), ("경북", "경상북도"), ("경남", "경상남도"),
           ("제주", "제주특별자치도")]


def loc_key(addr):
    """소재지 비교용 키(시·도 + 시·군·구)."""
    s, g = sido_of(addr), sigungu_of(addr)
    return f"{s or '?'}/{g or '?'}" if (s or g) else None


def sido_of(addr):
    if not addr:
        return None
    for short, full in SIDO_RE:
        if addr.startswith(full) or addr.startswith(short) or f" {short}" in addr:
            return full
    return None


SIGUNGU = {
    "경기도": "수원 성남 의정부 안양 부천 광명 평택 동두천 안산 고양 과천 구리 남양주 오산 시흥 군포 의왕 하남 용인 파주 이천 안성 김포 화성 양주 포천 여주 연천 가평 양평".split(),
    "강원특별자치도": "춘천 원주 강릉 동해 태백 속초 삼척 홍천 횡성 영월 평창 정선 철원 화천 양구 인제 고성 양양".split(),
    "충청북도": "청주 충주 제천 보은 옥천 영동 증평 진천 괴산 음성 단양".split(),
    "충청남도": "천안 공주 보령 아산 서산 논산 계룡 당진 금산 부여 서천 청양 홍성 예산 태안".split(),
    "전북특별자치도": "전주 군산 익산 정읍 남원 김제 완주 진안 무주 장수 임실 순창 고창 부안".split(),
    "전라남도": "목포 여수 순천 나주 광양 담양 곡성 구례 고흥 보성 화순 장흥 강진 해남 영암 무안 함평 영광 장성 완도 진도 신안".split(),
    "경상북도": "포항 경주 김천 안동 구미 영주 영천 상주 문경 경산 의성 청송 영양 영덕 청도 고령 성주 칠곡 예천 봉화 울진 울릉".split(),
    "경상남도": "창원 진주 통영 사천 김해 밀양 거제 양산 의령 함안 창녕 고성 남해 하동 산청 함양 거창 합천".split(),
}
METRO = {"서울특별시": "서울 서울특별시".split(), "부산광역시": "부산 부산광역시".split(),
         "대구광역시": "대구 대구광역시".split(), "인천광역시": "인천 인천광역시".split(),
         "광주광역시": "광주 광주광역시".split(), "대전광역시": "대전 대전광역시".split(),
         "울산광역시": "울산 울산광역시".split(), "세종특별자치시": ["세종"]}


def sigungu_of(addr):
    if not addr:
        return None
    sido = sido_of(addr)
    if not sido:
        return None
    if sido in METRO:
        rest = addr
        for tok in METRO[sido]:
            rest = rest.replace(tok, " ", 1)
        m = re.match(r"\s*(\S+?[구군])", rest)
        return m.group(1) if m else None
    for s in SIGUNGU.get(sido, []):
        if re.search(rf"(^|\s){s}(시|군|구)?(\s|$|,)", addr):
            return s
    return None


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "swit":
        d = parse_swit_xls(sys.argv[2] if len(sys.argv) > 2 else "/workspace/downloads/list__20261127.xls")
        print(f"SWIT 스냅샷 {d['count']}건 저장")
    else:
        main()
