#!/usr/bin/env python3
"""LX(한국국토정보공사) 주요 공간정보 공고 수동 보강 — 14개 키워드에 걸리지 않는 LX 발주 건을 raw_items.json에 병합.

collect.py 실행 후 매번 돌린다(이미 있으면 건너뜀).
"""
import json, pathlib

HERE = pathlib.Path(__file__).parent
RAW = HERE / "raw_items.json"

EXTRA = [
    {
        "kind": "bid", "no": "R26BK01844693", "order": "000",
        "title": "2027년 지하공간통합지도 수정갱신 사업",
        "org": "한국국토정보공사", "phone": "070-4056-7377",
        "conditions": "공동수급 허용", "budget_text": "16억 6,414만",
        "contract": "제한경쟁 협상에의한계약", "posted": "26.11.20",
        "deadline_text": "D-40 12.31 10:00", "open_text": "12.31 11:00", "status": "입찰중",
        "cats": ["DB구축 및 자료입력", "IT·정보통신"],
        "presignal": "https://presignal.co.kr/p/R26BK01844693", "keywords": ["공간정보"],
    },
    {
        "kind": "bid", "no": "R26BK01844583", "order": "000",
        "title": "2027년 지하정보통합체계 운영 및 관리",
        "org": "한국국토정보공사", "phone": "070-4056-7377",
        "conditions": "공동수급 허용", "budget_text": "10억 1,875만",
        "contract": "제한경쟁 협상에의한계약", "posted": "26.11.20",
        "deadline_text": "D-40 12.31 10:00", "open_text": "12.31 11:00", "status": "입찰중",
        "cats": ["운영 및 유지관리", "IT·정보통신"],
        "presignal": "https://presignal.co.kr/p/R26BK01844583", "keywords": ["공간정보"],
    },
    {
        "kind": "bid", "no": "R26BK01845358", "order": "000",
        "title": "(재공고) 2027년 노후계획도시정비플랫폼 운영 및 유지관리",
        "org": "한국국토정보공사", "phone": "070-4056-7377",
        "conditions": "공동수급 허용 · 하도급 불허", "budget_text": "1억 8,000만",
        "contract": "제한경쟁 협상에의한계약", "posted": "26.11.20",
        "deadline_text": "D-10 12.01 14:00", "open_text": "12.01 15:00", "status": "입찰중",
        "cats": ["운영 및 유지관리", "IT·정보통신"],
        "presignal": "https://presignal.co.kr/p/R26BK01845358", "keywords": [],
    },
]

items = json.loads(RAW.read_text(encoding="utf-8"))
have = {(i["kind"], i["no"], i.get("order")) for i in items}
added = 0
for e in EXTRA:
    k = (e["kind"], e["no"], e["order"])
    if k in have:
        continue
    items.append(e)
    have.add(k)
    added += 1
RAW.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
print("lx_extra merged:", added, "total:", len(items))
