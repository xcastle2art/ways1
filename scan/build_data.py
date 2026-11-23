#!/usr/bin/env python3
"""data.json 생성 — 전국 30일(2026-10-24~11-23) 입찰공고·사전규격.

수집(collect.py)은 14개 키워드 그대로 — 이 스크립트에서만 웹 대시보드 표시용으로
'공원녹지·라이다·도보네트워크·GIS DB'만 걸린 건을 걸러낸다(09:00·16:00 정기 알림은 영향 없음).
시·도는 담당자 권역 대신 발주기관 소재 기준으로 정규화한다.
"""
import json, re, pathlib
from datetime import datetime, timedelta, timezone

HERE = pathlib.Path(__file__).parent
OUT = HERE.parent / "data.json"
KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 24, 9, 0, tzinfo=KST)
WIN_FROM = datetime(2026, 10, 24, tzinfo=KST)
# 사전규격 수작업 보강분(첨부·질의응답·나라장터 직링크) 보존 — 오래된 백업부터 읽어 최신이 덮어쓴다
BACKUPS = [
    HERE / "data.before_20261120_prespec.json",
    HERE / "data.before_20261121.json",
    HERE / "data.before_20261121_1600.json",
    HERE.parent / "data.before_20261122.json",
]
_prev = {}
for _bp in BACKUPS:
    if not _bp.exists():
        continue
    for _it in json.loads(_bp.read_text(encoding="utf-8"))["items"]:
        if _it.get("kind") == "prespec" and (_it.get("attachments") or _it.get("qna", {}).get("items")):
            _prev[_it["id"]] = _it

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
    "R26BK01843660": ("2026-11-30 14:00", "개찰 시각 기준(공고문 확인)"),
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
    "R26BD00304066": "영동군(충북) 토적 사전규격. 배정 4억 368만 5천원(부가세 포함)·조달청 대행(참조 재무과-30836)·납품기한 착수 후 300일·SW사업 대상. 첨부 제안요청서 1건(261112 작성), 규격서 의견 0건. 의견등록 11-25 23:59.",
    "R26BK01844693": "LX 2027년 지하공간통합지도 수정갱신 — 추정 15억 182만·배정 16억 6,414만. 사전규격 R26BD00295336 본공고. 업종: SW사업자(DB제작·검색서비스)·측량업(지하시설물·수치지도·공공·측지) 중 1. 공동수급 허용·지역제한 없음. 12-31 10:00 마감(개찰 11:00). 첨부: 제안요청서(hwpx)·입찰공고서(pdf).",
    "R26BK01844583": "LX 2027년 지하정보통합체계 운영·관리 — 추정 9억 1,818만·배정 10억 1,875만. 사전규격 R26BD00295335 본공고. 업종: SW사업자(컴퓨터관련서비스사업). 공동수급 허용·지역제한 없음. 12-31 10:00 마감. 첨부: 제안요청서(hwpx)·입찰공고서(pdf).",
    "R26BK01843782": "이천시 배수관로 GIS DB 현행화 1권역 재공고(소액수의). 추정 9,087만·배정 9,996만. **지역제한 경기도 이천시** — 이천 관내 업체만 참가 가능. 11-26 10:00 마감·11:00 개찰. 첨부 3종(과업지시서·재공고문 hwpx/pdf).",
    "R26BK01843805": "이천시 배수관로 GIS DB 현행화 2권역 재공고(소액수의). 1권역과 동일 조건(추정 9,087만·배정 9,996만·지역제한 이천시) — 두 권역 분리 발주. 11-26 10:00 마감.",
    "R26BK01843041": "죽천금평지구 농어촌생활용수 GIS DB(전북 무주). 추정 3억 5,548만·배정 3억 9,102만. 지역제한 전북, SW·측량업. 사전규격 R26BD00299492 본공고. 11-26 10:00 마감.",
    "R26BK01845405": "2027년 부산자율주행버스 위탁운영 — 추정 8억 782만·배정 8억 8,860만. 일반경쟁 협상, 업종 제한 없음. 사전규격 R26BD00295791 본공고. 12-11 10:00 마감. 첨부 6종(공고문·제안요청서·과업지시서·상생결제 안내).",
    "R26BK01845322": "자율주행 실증도시 홍보 강화 방안 연구 재공고(국토부). 원공고 R26BK01818370 11-20 10:00 유찰(참가 0) → 금액 동일(추정 2,455만·배정 2,700만) 재공고. 학술·연구용역, 12-01 10:00 마감.",
    "R26BK01843040": "국토부 2027년 공간정보오픈플랫폼 민간위탁(운영) — 11-20 12:00 개찰완료·참가 1(1인 수의시담·지정업체). 낙찰자·낙찰금액은 공개 수집원(공공일감)에 미등록.",
    "R26BK01843061": "국토부 2027년 공간정보오픈플랫폼 민간위탁(유지보수) — 11-20 12:00 개찰완료·참가 1(1인 수의시담). 낙찰자 미등록. 추정 23억 6,545만·배정 26억 200만.",
    "R26BK01818370": "국토부 자율주행 실증도시 홍보 강화 방안 연구 — 11-20 10:00 유찰(참가 0) → R26BK01845322로 재공고.",
    "R26BK01833099": "천안시 공원녹지기본계획 전략환경영향평가(소액수의견적) — 11-20 10:00 마감·11:00 개찰, 참가 8업체 모두 낙찰자 미선정으로 재입찰. 추정 7,017만·배정 7,718.7만, 지역제한 천안시·제1종 환경영향평가업.",
    "R26BK01825240": "인천경제자유구역청 2027년 IFEZ 3차원 공간정보서비스 유지보수 — 11-20 10:00 마감·17:00 개찰, 참가 0으로 유찰(재입찰). 추정 6,272만·배정 6,900만, 소액수의견적·SW사업자.",
    "R26BK01843237": "화성시 공원녹지사업소 소나무재선충병 방제 감리용역(수의시담) — 11-20 11:30 개찰완료·참가 1, 낙찰 주식회사 다산산림기술사사무소 2,655만(투찰률 94.634%). 키워드 관련성 낮음.",
    "R26BK01845358": "LX 2027년 노후계획도시정비플랫폼 운영·유지관리 재공고(키워드 외). 원공고 R26BK01818412(11-20 10:00) 참가 0 유찰 → 금액·자격 동일하게 12-01 14:00 마감(개찰 15:00). 추정 1억 6,364만·배정 1억 8,000만, 협상·SW사업자(컴퓨터관련서비스), 하도급 불허·공동수급 허용. 사전규격 R26BD00290320.",
    "R26BD00299726_dummy": "",
}

# 수집(09:00·16:00 정기 스캔)이 쓰는 14개 키워드 — collect.py와 동일하게 유지
KEYWORDS = ["토지적성평가", "재해취약성", "연속도면", "용도지역지구", "자율주행", "정밀지도",
            "공원관리", "공원녹지", "도보뷰", "도보네트워크", "도로대장", "GIS DB", "공간정보", "라이다"]

# 웹 대시보드에서만 제외하는 키워드(2026-11-22 사용자 지시) — 수집·정기 알림은 그대로
EXCLUDE_KEYWORDS = ["공원녹지", "라이다", "도보네트워크", "GIS DB"]

# 시·도 표시 순서·이름 (발주기관 소재 기준, 건수 0인 시·도는 화면에서 숨김)
SIDO_ORDER = ["전국", "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
              "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
SIDO_NAME = {"전국": "전국·중앙부처"}
WEEKDAY = "월화수목금토일"


def region_of(org):
    """발주기관 문자열 → 시·도. 중앙부처·전국 단위 공기업은 '전국'."""
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
    # 시·도 산하 공사·공단 (예: 화성도시공사, 김포도시관리공사)
    m = re.match(r"^(\S+?)(?:도시공사|도시관리공사|시설공단|시설관리공단|도시개발공사|문화재단|환경사업소|공원관리사업소)", s)
    if m:
        stem = m.group(1)
        for prov, names in CITY.items():
            for n in names:
                if stem == n or stem == n + "시":
                    return prov, s
    # 같은 이름의 시·군이 둘 이상인 경우(고성: 강원/경남) 도 이름이 함께 있을 때만 단정
    for prov, names in CITY.items():
        for n in names:
            m2 = re.search(r"(?<![\w])" + re.escape(n) + r"(시|군)?(?![\w])", s)
            if m2 or f"{n}시" in s or f"{n}군" in s:
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
    kind = raw["kind"]
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
    elif progress == "재입찰":
        status = "재입찰"
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
    elif status == "재입찰":
        result = {"state": "failed", "participants": int(participants) if participants is not None else None,
                  "note": "재입찰 (참가 %s·낙찰자 미선정)" % (int(participants) if participants is not None else "?")}
    elif status == "개찰완료":
        result = {"state": "opened", "participants": int(participants) if participants else None, "winner": winner, "amount": amount,
                  "rate": d.get("winner_rate"),
                  "opened_at": iso(open_at or parse_dt(d.get("opened_at", ""))),
                  "note": None}
        if not any([participants, winner, amount]):
            result["note"] = "개찰은 완료됐으나 참가·낙찰 정보가 수집원에 없음"
    elif status == "개찰대기":
        result = {"state": "pending", "participants": None, "note": "마감 후 개찰결과 미등록"}
    else:
        result = {"state": "before", "note": "마감 전"}

    qna = {"state": "unknown",
           "summary": "나라장터 사전규격 의견등록(질의·답변)은 로그인 후 상세에서 확인할 수 있어 수집 사이트에 공개되지 않았습니다.",
           "items": []}
    if kind == "prespec" and no == "R26BD00304066":
        attachments = [{"name": "제안요청서_영동군 토지적성평가 및 재해취약성분석_261112.hwpx",
                        "size": "185.2KB", "url": ""}]
        qna = {"state": "confirmed",
               "summary": "11-21 08:55 나라장터 사전규격 상세(PRVA004_02) 직접 확인 — 첨부 1건(제안요청서 hwpx, 김범준 등록 11-20 15:49), 규격서 의견 0건. 의견등록 11-25 23:59까지.",
               "items": [{"q": "규격서 의견 등록", "a": "0건 (2026-11-21 08:55 기준)"}]}
    if kind == "bid" and no == "R26BK01842043":
        qna = {"state": "noted",
               "summary": "질의 접수 11-23 16:00까지(서식 문서 1회). 공고문 기준 별도 사전 질의·답변 공개분은 확인되지 않았습니다.",
               "items": [{"q": "질의 마감", "a": "2026-11-23 16:00 (동해시 건설과 033-530-2591)"}]}
    elif kind == "prespec" and deadline and deadline < NOW:
        qna = {"state": "unknown",
               "summary": "의견등록이 마감된 사전규격입니다. 등록된 질의·답변 요약은 나라장터 사전규격 상세(로그인)에서 확인해야 하며, 공개 수집원에는 없습니다.",
               "items": []}

    items.append({
        "id": ("ps-" if kind == "prespec" else "b-") + no,
        "kind": kind,
        "title": raw["title"],
        "no": no,
        "order": raw.get("order", "000"),
        "org": org or "기관 미상",
        "region": region,
        "sido": SIDO_NAME.get(region, region),
        "region_detail": detail,
        "posted": iso(posted),
        "posted_label": posted.strftime("%m-%d") if posted else "",
        "deadline": iso(deadline),
        "deadline_label": (deadline.strftime("%Y-%m-%d") + "(" + WEEKDAY[deadline.weekday()] + ") " + deadline.strftime("%H:%M") if deadline else "일정 확인"),
        "deadline_short": (deadline.strftime("%m.%d") + "(" + WEEKDAY[deadline.weekday()] + ") " + deadline.strftime("%H:%M") if deadline else "—"),
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
                    if kind == "bid" else f"https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo={no}"),
            "g2b_kind": "입찰공고 상세" if kind == "bid" else "나라장터 사전규격 상세",
            "presignal": raw.get("presignal") or "",
            "data00": f"https://work.00data.kr/projects/{no}" if kind == "bid" else "",
        },
        "keywords": raw.get("keywords", []),
        "note": NOTES.get(no, ""),
        "owner": raw.get("owner", ""),
    })

# 사전규격 보강분(첨부·질의·직링크) 복원 — build_data가 덮어쓰지 않도록 기존 값 우선
for it in items:
    if it["kind"] != "prespec":
        continue
    prev = _prev.get(it["id"])
    if not prev:
        continue
    if not it["attachments"] and prev.get("attachments"):
        it["attachments"] = prev["attachments"]
    if prev.get("qna", {}).get("items") and not it["qna"].get("items"):
        it["qna"] = prev["qna"]
    if prev.get("links", {}).get("g2b", "").startswith("https://www.g2b.go.kr/link/PRVA004_02"):
        it["links"]["g2b"] = prev["links"]["g2b"]
        it["links"]["g2b_kind"] = prev["links"].get("g2b_kind", "나라장터 사전규격 상세")

# 30일 창 필터(공고일 기준) — 수집 기본 조건과 동일하지만 안전하게 재확인
items = [i for i in items if not i["posted"] or datetime.fromisoformat(i["posted"]) >= WIN_FROM]
window_count = len(items)

# ── 웹 대시보드 전용 제외 필터 ─────────────────────────────────────────────
# 사용자 지시(2026-11-22): 키워드 '공원녹지·라이다·도보네트워크·GIS DB'에서 걸린 건은
# 대시보드에서만 뺀다. 수집(collect.py 14개 키워드)과 09:00·16:00 정기 알림은 그대로 둔다.
# 규칙: 한 공고의 매칭 키워드가 모두 제외 대상 4개 안에 있을 때만 제외한다.
#       다른 핵심 키워드(토지적성평가·공간정보·도로대장 등)에도 함께 걸린 건은 남긴다.
def only_excluded(it):
    kws = it.get("keywords") or []
    return bool(kws) and all(k in EXCLUDE_KEYWORDS for k in kws)

dropped = [i for i in items if only_excluded(i)]
items = [i for i in items if not only_excluded(i)]

# ── 시·도 집계 ────────────────────────────────────────────────────────────
def is_urgent(it):
    if not it["deadline"] or it["status"] not in ("입찰중", "의견등록중"):
        return False
    left = datetime.fromisoformat(it["deadline"]) - NOW
    return 0 <= left.total_seconds() / 86400 <= 3

provinces = []
for code in SIDO_ORDER:
    sub = [i for i in items if i["region"] == code]
    if not sub:
        continue
    provinces.append({
        "code": code,
        "name": SIDO_NAME.get(code, code),
        "count": len(sub),
        "bids": sum(1 for i in sub if i["kind"] == "bid"),
        "prespec": sum(1 for i in sub if i["kind"] == "prespec"),
        "urgent": sum(1 for i in sub if is_urgent(i)),
    })

# 키워드 통계 — 대시보드에 남은 10개 키워드만
DASH_KEYWORDS = [k for k in KEYWORDS if k not in EXCLUDE_KEYWORDS]
kstats = []
for kw in DASH_KEYWORDS:
    b = sum(1 for i in items if i["kind"] == "bid" and kw in i["keywords"])
    p = sum(1 for i in items if i["kind"] == "prespec" and kw in i["keywords"])
    kstats.append({"keyword": kw, "bids": b, "prespec": p})

# 추적 목록 — 나라장터에 아직 게시되지 않은 '미게시' 항목은 넣지 않는다(강릉 토적 제외).
WATCH = [
    {"id": "wl-lx", "label": "LX 2027 토지적성평가 표준프로그램", "status": "재공고", "tone": "urgent",
     "meta": "원공고 유찰(참가 0) → 재공고 R26BK01843852 / 12-01 10:00 마감",
     "note": "금액·자격 동일, 일정만 재설정. 업체는 11-30 18:00까지 참가등록·공동수급협정",
     "g2b": "https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26BK01843852&bidPbancOrd=000"},
    {"id": "wl-gyeongsan", "label": "경산시 토지적성평가 사전규격", "status": "본공고 전환 대기", "tone": "wait",
     "meta": "R26BD00299726 의견등록 11-18 23:59 마감 · 본공고 미전환(11-24 09:00 재확인, 규격서 의견 4건·답변 없음)",
     "note": "사전규격은 게시 상태. 본공고 전환 시 즉시 반영", "g2b": "https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo=R26BD00299726"},
    {"id": "wl-buan", "label": "부안군 도로대장", "status": "개찰결과 미등록", "tone": "wait",
     "meta": "R26BK01812769 11-18 16:00 개찰(직찰) · 11-24 09:00 재확인에도 개찰결과·협상순위 미등록(6일째)",
     "note": "11-20 14:00 부안군청 제안서 평가 진행 — 협상 결과 등록 여부 계속 추적",
     "g2b": "https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26BK01812769&bidPbancOrd=000"},
    {"id": "wl-lx-underground", "label": "LX 2027 지하공간통합지도·지하정보통합체계", "status": "입찰중", "tone": "watch",
     "meta": "R26BK01844693(배정 16.64억)·R26BK01844583(배정 10.19억) 모두 12-31 10:00 마감",
     "note": "LX 전국 발주·공동수급 허용·지역제한 없음. 지하공간통합지도는 SW+측량업 동시 보유 필요",
     "g2b": "https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26BK01844693&bidPbancOrd=000"},
]

data = {
    "updated_at": NOW.isoformat(timespec="minutes"),
    "updated_label": "2026-11-24(화) 09:00 KST",
    "window": {"from": "2026-10-25", "to": "2026-11-24", "days": 30},
    "scan_basis": {
        "latest_scan": "2026-11-24 09:00 KST (화요일 오전 스캔 — 신규 입찰공고 11건·사전규격 12건(11-23 게시), 개찰결과 7건 갱신 · 웹 반영 6건)",
        "sources": "presignal.co.kr 14개 키워드 검색(입찰공고·사전규격) + work.00data.kr(공공일감) 상세(첨부·개찰결과) + 나라장터 원문 링크",
        "note": "공고일 기준 최근 30일(2026-10-25~11-24). 11-24 09:00 스캔에서 11-23 게시 신규 입찰 11건·사전규격 12건 확인 — 웹에는 6건 반영(라이다·GIS DB·공원녹지 제외 키워드 및 중복 제외). 개찰결과는 유찰 4건(라이다 2·자율주행 2)·개찰완료 3건 갱신.",
    },
    "collect_keywords": KEYWORDS,
    "dashboard_keywords": DASH_KEYWORDS,
    "dashboard_filter": {
        "excluded_keywords": EXCLUDE_KEYWORDS,
        "excluded_items": len(dropped),
        "kept_items": len(items),
        "window_items": window_count,
        "samples": [{"no": i["no"], "title": i["title"], "keywords": i["keywords"]} for i in dropped[:6]],
        "note": "웹 대시보드 표시에서만 제외. 09:00·16:00 정기 스캔과 알림은 14개 키워드 그대로 유지.",
    },
    "watchlist": WATCH,
    "provinces": provinces,
    "keyword_stats": kstats,
    "items": items,
    "counts": {
        "total": len(items),
        "bids": sum(1 for i in items if i["kind"] == "bid"),
        "prespec": sum(1 for i in items if i["kind"] == "prespec"),
        "opened": sum(1 for i in items if i["result"]["state"] == "opened"),
        "failed": sum(1 for i in items if i["result"]["state"] == "failed"),
        "attachments": sum(1 for i in items if i["attachments"]),
        "provinces": len({i["region"] for i in items}),
        "urgent": sum(1 for i in items if is_urgent(i)),
        "open_bids": sum(1 for i in items if i["kind"] == "bid" and i["status"] == "입찰중"),
        "open_prespec": sum(1 for i in items if i["kind"] == "prespec" and i["status"] == "의견등록중"),
    },
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print("items", len(items), "excluded", len(dropped), data["counts"])
from collections import Counter
print(Counter(i["region"] for i in items).most_common())
print("prespec with attachments", sum(1 for i in items if i["kind"] == "prespec" and i["attachments"]))
print("urgent", data["counts"]["urgent"])
