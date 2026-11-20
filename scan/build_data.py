#!/usr/bin/env python3
"""data.json 생성 — 전국 30일(2026-10-21~11-20) 14개 키워드 입찰공고·사전규격."""
import json, re, pathlib
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent / "data.json"
KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 20, 16, 40, tzinfo=KST)

RAW = json.loads((HERE / "raw_items.json").read_text(encoding="utf-8"))
DET = json.loads((HERE / "enriched.json").read_text(encoding="utf-8"))["detail"]
PS = json.loads((HERE / "ps_detail.json").read_text(encoding="utf-8"))

PROVINCES = {
    "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
    "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
    "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
    "제주": "제주특별자치도",
}

CITY = {
    "경기": "수원 성남 의정부 안양 부천 광명 평택 동두천 안산 고양 과천 구리 남양주 오산 시흥 군포 의왕 하남 용인 파주 이천 안성 김포 화성 광주시 양주 포천 여주 연천 가평 양평".split(),
    "강원": "춘천 원주 강릉 동해 태백 속초 삼척 홍천 횡성 영월 평창 정선 철원 화천 양구 인제 고성 양양".split(),
    "충북": "청주 충주 제천 보은 옥천 영동 증평 진천 괴산 음성 단양".split(),
    "충남": "천안 공주 보령 아산 서산 논산 계룡 당진 금산 부여 서천 청양 홍성 예산 태안".split(),
    "전북": "전주 군산 익산 정읍 남원 김제 완주 진안 무주 장수 임실 순창 고창 부안".split(),
    "전남": "목포 여수 순천 나주 광양 담양 곡성 구례 고흥 보성 화순 장흥 강진 해남 영암 무안 함평 영광 장성 완도 진도 신안".split(),
    "경북": "포항 경주 김천 안동 구미 영주 영천 상주 문경 경산 의성 청송 영양 영덕 청도 고령 성주 칠곡 예천 봉화 울진 울릉".split(),
    "경남": "창원 진주 통영 사천 김해 밀양 거제 양산 의령 함안 창녕 고성 남해 하동 산청 함양 거창 합천".split(),
    "제주": "제주 서귀포".split(),
}

METRO_PREFIX = [("서울", "서울"), ("부산", "부산"), ("대구", "대구"), ("인천", "인천"),
                ("광주광역시", "광주"), ("대전", "대전"), ("울산", "울산"), ("세종", "세종")]

CENTRAL = ["조달청", "한국국토정보공사", "LX", "국토교통부", "한국환경공단", "한국도로공사",
           "한국전력공사", "한전KDN", "한국지능형교통체계협회", "한국전파진흥협회", "국방부",
           "산림청", "경찰청", "소상공인시장진흥공단", "한국교통안전공단", "한국철도공사",
           "한국수자원공사", "한국농어촌공사", "한국가스공사"]

MANUAL_DEADLINE = {
    "R26BK01842043": ("2026-11-30 16:00", "제안서 접수 마감(직접 방문 09:30~16:00)"),
    "R26BK01812769": ("2026-11-18 16:00", "개찰(접수 13:00~16:00)"),
    "R26BK01813931": ("2026-11-20 16:00", "개찰"),
    "R26BK01824629": ("2026-11-23 18:00", "개찰 시각 기준(공고문 확인)"),
}

NOTES = {
    "R26BK01842043": "직접 방문접수(11-30 09:30~16:00)·질의 11-23 16:00·공동수급협정 11-30 16:00. 정량 상생협력 3.0(강원 관내 공동수급 지분 49%↑). 첨부 5종(공고문·제안요청서·과업지시서·내역서·PDF).",
    "R26BK01843852": "원공고 R26BK01810145(11-19 10:00) 참가 0으로 유찰 → 금액·자격 동일, 일정만 재설정. 기술 90:가격 10, 기술 85% 이상 협상적격.",
    "R26BK01812769": "개찰(11-18 16:00) 후 개찰결과 미게시. 11-20 14:00 부안군청 제안서 평가 진행 — 결과 등록 여부 다음 회차 확인.",
    "R26BD00299726": "의견등록 11-18 23:59 종료 후 11-20 16:00 기준 본공고 미전환.",
    "R26BK01814013": "안동시 서부권 군도 도로대장 — 공동수급 허용, 12-01 10:00 마감.",
    "R26BK01813931": "김천시 도로대장 — 11-20 16:00 개찰. 개찰결과 미게시.",
    "R26BK01837321": "전북 남원시 도시관리계획(용도지역 변경) — 11-23 12:00 마감·13:00 개찰.",
    "R26BK01819376": "11-11 게시 누락 보완분. SW사업 가격 80% 미만 투찰 시 가격점수 30% 페널티. 12-08 10:00 마감.",
    "R26BK01824629": "11-12 게시 누락 보완분. 수집 사이트에 마감이 개찰시각(11-23 18:00)으로만 표기 — 공고문 확인 필요.",
    "R26BD00303729": "여주시 하수관로 GIS DB — 배정 4.481억, 의견등록 11-25 23:59.",
    "R26BD00299726_dummy": "",
}

KEYWORDS = ["토지적성평가", "재해취약성", "연속도면", "용도지역지구", "자율주행", "정밀지도",
            "공원관리", "공원녹지", "도보뷰", "도보네트워크", "도로대장", "GIS DB", "공간정보", "라이다"]

MANAGERS = [
    {"id": "park", "name": "박정수", "regions": ["경남"], "color": "#2563eb"},
    {"id": "jo", "name": "조준래", "regions": ["경북", "전남", "전북"], "color": "#7c3aed"},
    {"id": "oh", "name": "오창민", "regions": ["경기", "강원"], "color": "#059669"},
    {"id": "kim", "name": "김충열", "regions": ["경기", "충남", "충북"], "color": "#d97706"},
]


def region_of(org):
    s = org or ""
    if "전남광주통합" in s:
        if re.search(r"(동구|서구|남구|북구|광산구)", s):
            return "광주", s
        return "전남", s
    for key, full in PROVINCES.items():
        if full in s or (key + "도") in s or (key == "강원" and "강원도" in s) or (key == "전북" and "전라북도" in s):
            return key, s
    for token, key in [("서울", "서울"), ("부산", "부산"), ("대구", "대구"), ("인천", "인천"),
                       ("광주", "광주"), ("대전", "대전"), ("울산", "울산"), ("세종", "세종")]:
        if token in s:
            return key, s
    m = re.match(r"^(\S+?)(?:도시공사|도시관리공사|시설공단|시설관리공단|도시개발공사|문화재단)", s)
    if m:
        stem = m.group(1)
        for prov, names in CITY.items():
            for n in names:
                if stem == n or stem == n + "시":
                    return prov, s
    for prov, names in CITY.items():
        for n in names:
            if re.search(re.escape(n) + r"(시|군)?(\s|$|\b|·|,)", s) or f"{n}시" in s or f"{n}군" in s:
                return prov, s
    return "전국", s


def iso(dt):
    return dt.astimezone(KST).isoformat(timespec="minutes") if dt else None


def parse_dt(text):
    if not text:
        return None
    t = text.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}))?", t)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh = int(m.group(4) or 23)
    mm = int(m.group(5) or 59)
    try:
        return datetime(y, mo, d, hh, mm, tzinfo=KST)
    except ValueError:
        return None


def parse_posted(text):
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2})", text or "")
    if not m:
        return None
    return datetime(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=KST)


def parse_deadline_from_list(text):
    m = re.search(r"(\d{2})\.(\d{2})\s+(\d{2}):(\d{2})", text or "")
    if not m:
        return None
    return datetime(2026, int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), tzinfo=KST)


def dday_label(dt):
    if not dt:
        return "일정 확인"
    days = (dt.date() - NOW.date()).days
    return f"D-{days}" if days > 0 else ("D-DAY" if days == 0 else f"{abs(days)}일 경과")


def norm_budget(text):
    if not text:
        return None
    t = text.replace(",", "").replace(" ", "")
    m = re.match(r"([\d.]+)억(?:(\d+)만)?", t)
    if m:
        v = float(m.group(1)) * 1e8 + (int(m.group(2)) * 1e4 if m.group(2) else 0)
        return int(round(v))
    m = re.match(r"([\d]+)만", t)
    return int(m.group(1)) * 1e4 if m else None


items = []
for raw in RAW:
    no = raw["no"]
    d = DET.get(no, {})
    ps = PS.get(no, {})
    org = (ps.get("org") or raw.get("org") or "").strip()
    region, detail = region_of(org)
    posted = parse_posted(raw.get("posted", "")) or parse_dt(ps.get("posted"))
    deadline = parse_dt(ps.get("deadline")) or parse_deadline_from_list(raw.get("deadline_text"))
    open_at = parse_dt(ps.get("open"))
    manual = MANUAL_DEADLINE.get(no)
    deadline_note = (manual[1] if manual else None)
    if manual:
        deadline = parse_dt(manual[0])
    if not deadline and open_at and kind == "bid":
        deadline = open_at
        deadline_note = "개찰 시각 기준(투찰 마감은 공고문 확인)"
    budget_text = raw.get("budget_text", "")
    budget = norm_budget(budget_text) or d.get("budget") or d.get("estimated_price")
    kind = raw["kind"]

    attachments = d.get("attachments") or []
    progress = d.get("progress")
    participants = d.get("participants")
    winner = d.get("signed_corp") or d.get("contract_corp") or d.get("winner_name")
    amount = d.get("signed_amount") or d.get("contract_amount") or d.get("winner_amount")

    status_raw = raw.get("status", "")
    if kind == "prespec":
        status = "의견등록중" if (deadline and deadline >= NOW) else "의견마감"
    elif progress == "유찰" or "유찰" in status_raw:
        status = "유찰"
    elif progress in ("개찰완료", "낙찰") or status_raw.startswith("개찰완료"):
        status = "개찰완료"
    elif deadline and deadline < NOW:
        status = "개찰대기"
    else:
        status = "입찰중"

    if kind == "prespec":
        result = {"state": "none"}
    elif status == "유찰":
        result = {"state": "failed", "participants": int(participants) if participants is not None else None, "note": "유찰 (참가 0)" if participants == 0 else "유찰"}
    elif status == "개찰완료":
        result = {"state": "opened", "participants": int(participants) if participants else None, "winner": winner, "amount": amount,
                  "rate": d.get("winner_rate"),
                  "opened_at": iso(open_at or parse_dt(d.get("opened_at", ""))),
                  "note": None}
        if not any([participants, winner, amount]):
            result["note"] = "개찰은 완료됐으나 참가·낙찰 정보가 수집원에 없음"
    elif status == "개찰대기":
        result = {"state": "pending", "participants": None, "note": "마감 후 개찰결과 미게시"}
    else:
        result = {"state": "before", "note": "마감 전"}

    qna = {"state": "unknown",
           "summary": "나라장터 사전규격 의견등록(질의·답변)은 로그인 후 상세에서 확인할 수 있어 수집 사이트에 공개되지 않았습니다.",
           "items": []}
    if kind == "bid" and no == "R26BK01842043":
        qna = {"state": "noted",
               "summary": "질의 접수 11-23 16:00까지(서식 문서 1회). 공고문 기준 별도 사전 질의·답변 공개분은 확인되지 않았습니다.",
               "items": [{"q": "질의 마감", "a": "2026-11-23 16:00 (동해시 건설과 033-530-2591)"}]}
    elif kind == "prespec" and deadline and deadline < NOW:
        qna = {"state": "unknown",
               "summary": "의견등록이 마감된 사전규격입니다. 등록된 질의·답변 요약은 나라장터 사전규격 상세(로그인)에서 확인해야 하며, 공개 수집원에는 없습니다.",
               "items": []}

    managers = [m["name"] for m in MANAGERS if region in m["regions"]]

    items.append({
        "id": ("ps-" if kind == "prespec" else "b-") + no,
        "kind": kind,
        "title": raw["title"],
        "no": no,
        "order": raw.get("order", "000"),
        "org": org or "기관 미상",
        "region": region,
        "region_detail": detail,
        "managers": managers,
        "posted": iso(posted),
        "posted_label": posted.strftime("%m-%d") if posted else "",
        "deadline": iso(deadline),
        "deadline_label": (deadline.strftime("%Y-%m-%d(%a) %H:%M") if deadline else "일정 확인"),
        "deadline_short": (deadline.strftime("%m.%d %H:%M") if deadline else "—"),
        "deadline_kind": "의견등록 마감" if kind == "prespec" else "입찰 마감",
        "deadline_note": deadline_note,
        "open_at": iso(open_at),
        "open_label": open_at.strftime("%m.%d %H:%M") if open_at else "",
        "status": status,
        "progress": progress,
        "budget": int(budget) if budget else None,
        "budget_text": budget_text or ps.get("budget") or "",
        "price_est": d.get("estimated_price"),
        "base_amount": d.get("base_amount"),
        "lowest_rate": d.get("lowest_bid_rate"),
        "contract": raw.get("contract") or ps.get("method") or "",
        "biz": ps.get("biz") or "",
        "conditions": raw.get("conditions", ""),
        "region_limit": d.get("region_limit"),
        "industry_limit": d.get("industry_limit"),
        "attachments": attachments,
        "qna": qna,
        "result": result,
        "links": {
            "g2b": (f"https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={no}&bidPbancOrd={raw.get('order','000')}"
                    if kind == "bid" else "https://www.g2b.go.kr/"),
            "g2b_kind": "입찰공고 상세" if kind == "bid" else "나라장터(사전규격은 번호 복사 후 검색)",
            "presignal": raw.get("presignal") or "",
            "data00": f"https://work.00data.kr/projects/{no}" if kind == "bid" else "",
        },
        "keywords": raw.get("keywords", []),
        "note": NOTES.get(no, ""),
        "owner": raw.get("owner", ""),
    })

# 30일 창 필터(공고일 기준) — 수집 기본 조건과 동일하지만 안전하게 재확인
win_from = datetime(2026, 10, 21, tzinfo=KST)
items = [i for i in items if not i["posted"] or datetime.fromisoformat(i["posted"]) >= win_from]

# 키워드 통계
kstats = []
for kw in KEYWORDS:
    b = sum(1 for i in items if i["kind"] == "bid" and kw in i["keywords"])
    p = sum(1 for i in items if i["kind"] == "prespec" and kw in i["keywords"])
    kstats.append({"keyword": kw, "bids": b, "prespec": p})

WATCH = [
    {"id": "wl-gangneung", "label": "강릉시 토지적성평가 용역", "status": "미게시", "tone": "wait",
     "meta": "11-13 이후 11-20 16:00까지 입찰공고·사전규격 모두 0건",
     "note": "2027년 본예산 확정 후 발주 예상 — 게시 즉시 확인 대상",
     "g2b": "https://www.g2b.go.kr/"},
    {"id": "wl-lx", "label": "LX 2027 토지적성평가 표준프로그램", "status": "재공고", "tone": "urgent",
     "meta": "원공고 유찰(참가 0) → 재공고 R26BK01843852 / 12-01 10:00 마감",
     "note": "금액·자격 동일, 일정만 재설정. 업체는 11-30 18:00까지 참가등록·공동수급협정",
     "g2b": "https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26BK01843852&bidPbancOrd=000"},
    {"id": "wl-gyeongsan", "label": "경산시 토지적성평가 사전규격", "status": "본공고 대기", "tone": "wait",
     "meta": "R26BD00299726 의견등록 11-18 23:59 마감 · 본공고 미전환(11-20 16:00)",
     "note": "본공고 전환 시 추적", "g2b": "https://www.g2b.go.kr/"},
    {"id": "wl-buan", "label": "부안군 도로대장", "status": "개찰결과 미게시", "tone": "wait",
     "meta": "R26BK01812769 11-18 16:00 개찰 · 11-20 14:00 제안서 평가",
     "note": "개찰결과 등록 여부 다음 회차 확인",
     "g2b": "https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26BK01812769&bidPbancOrd=000"},
]

now_iso = NOW.isoformat(timespec="minutes")
data = {
    "updated_at": now_iso,
    "updated_label": "2026-11-20(금) 16:40 KST",
    "window": {"from": "2026-10-21", "to": "2026-11-20", "days": 30},
    "scan_basis": {
        "latest_scan": "2026-11-20 16:00 KST (오전 09:00 + 오후 16:00)",
        "sources": "presignal.co.kr 14개 키워드 검색(입찰공고·사전규격) + work.00data.kr(공공일감) 상세(첨부·개찰결과) + 나라장터 원문 링크",
        "note": "공고일 기준 최근 30일(2026-10-21~11-20) 수집. 키워드별 검색 결과 전수(페이지 전체) 기준.",
    },
    "managers": MANAGERS,
    "watchlist": WATCH,
    "keyword_stats": kstats,
    "items": items,
    "counts": {
        "total": len(items),
        "bids": sum(1 for i in items if i["kind"] == "bid"),
        "prespec": sum(1 for i in items if i["kind"] == "prespec"),
        "opened": sum(1 for i in items if i["result"]["state"] == "opened"),
        "failed": sum(1 for i in items if i["result"]["state"] == "failed"),
        "attachments": sum(1 for i in items if i["attachments"]),
        "regions": len({i["region"] for i in items}),
    },
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("items", len(items), data["counts"])
from collections import Counter
print(Counter(i["region"] for i in items).most_common())
print(Counter(len(i["managers"]) for i in items))
print("with attachments", data["counts"]["attachments"])
