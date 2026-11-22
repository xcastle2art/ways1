# 나라장터 입찰·사전규격 모니터링 대시보드 (시·도별)

나라장터(www.g2b.go.kr) 입찰공고·사전규격·개찰결과를 **시·도별**로 한눈에 보는 정적 웹앱입니다.
공고일 기준 **최근 30일** 자료를 수집하며, 화면은 시·도 → 지금 챙길 것 → 목록 순으로 읽힙니다.

- 라이브: **https://xcastle2art.github.io/ways1/**
- 저장소: https://github.com/xcastle2art/ways1 (public, Pages: `main` / root)
- 빌드 단계 없음: `index.html` + `style.css` + `app.js` + `data.json`

## 1. 화면 구성 (2026-11-22 개편)

| 영역 | 내용 |
|---|---|
| 시·도 내비 (상단 고정) | `전체` + 17개 시·도 + `전국·중앙부처` 칩. 각 칩에 건수가 붙어 한눈에 분포를 보고, 한 번 눌러 그 시·도만 필터 |
| 지금 챙길 것 | 메뉴 바로 아래. **D-3 이내 마감**이면서 진행 중(입찰중·의견등록중)인 건만 최대 7건. 마감 경과·여유 있는 건은 넣지 않음. "N건 전체 보기"로 전부 확인 |
| 종류 | 전체 / 입찰공고 / 사전규격 / 개찰결과 (선택한 시·도의 건수 표시) |
| 키워드 | 대시보드에 남은 10개 키워드 칩(건수 표시) |
| 목록 | 행마다 `D-day·마감일시 / 공고명 / 발주기관·공고번호·첨부 / 상태·금액` 순. 마감 전 임박도에 따라 왼쪽 색 띠(빨강 D-1, 주황 D-3, 파랑 진행, 회색 종료) |
| 상세 드로어 | 마감·개찰·금액 요약 → 참가 조건 → 첨부파일 → 사전규격 질의 → 개찰결과 → 나라장터 직링크. 하단 고정 바에 `나라장터 열기`·`공고번호 복사` |
| 계속 지켜보는 건 | 목록 아래 접힘 영역(기본 닫힘) |

- **시·도는 발주기관 소재 기준**입니다. 중앙부처·전국 단위 공기업(LX·국토부·조달청·한국환경공단 등)은 `전국·중앙부처`로 묶습니다.
- 담당자 권역(4인) 매핑과 담당자 탭은 **제거**했습니다(2026-11-22 사용자 요청).
- 30일 창과 D-day는 **접속 시각 기준으로 매번 재계산**됩니다(오래된 공고는 자동으로 빠짐).

## 2. 대시보드 전용 키워드 제외 (수집은 그대로)

| 구분 | 키워드 |
|---|---|
| 수집(09:00·16:00 정기 스캔, `collect.py`) | 14개 — 토지적성평가·재해취약성·연속도면·용도지역지구·자율주행·정밀지도·공원관리·공원녹지·도보뷰·도보네트워크·도로대장·GIS DB·공간정보·라이다 |
| 웹 대시보드(`build_data.py` → `data.json`) | 위 14개 중 **공원녹지·라이다·도보네트워크·GIS DB를 제외한 10개** 표시 |

- 제외 규칙: 한 공고의 매칭 키워드가 **모두** 제외 대상 4개 안에 있을 때만 뺍니다. `도로대장`·`공간정보`·`토지적성평가` 등 다른 핵심 키워드에도 함께 걸린 건은 남습니다.
- 제외 결과는 `data.json`의 `dashboard_filter`(제외 건수·샘플·안내)에 기록되고 화면 푸터에도 표시됩니다.
- 정기 스캔·알림(09:00·16:00)은 14개 키워드 그대로라 이 필터의 영향을 받지 않습니다.
- 나라장터에 아직 게시되지 않은 **미게시(예정·추측) 항목은 data.json과 화면에서 제외**합니다(강릉시 토적 미게시 건 제거).

## 3. 나라장터 직링크 방식 (검증 완료)

| 대상 | 형식 | 검증 |
|---|---|---|
| 입찰공고 상세 | `https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={공고번호}&bidPbancOrd={차수}` | 동해시 `R26BK01842043` 실제 접속 → 공고상세 표시 |
| 첨부파일 다운로드 | `https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=…&bidPbancOrd=…&fileType=&fileSeq=N&prcmBsneSeCd=03(용역)/05(공사)` | 실제 HWPX 파일 수신(200) |
| 사전규격(R26BD…) 상세 | `https://www.g2b.go.kr/link/PRVA004_02/?bfSpecRegNo={사전규격등록번호}` | 2026-11-20 로그인 세션에서 실제 접속 → 사전규격상세조회 화면·첨부·규격서 의견 표시 |

> 나라장터는 WebSquare SPA라 내부 메뉴 이동만으로는 주소창 URL이 바뀌지 않습니다. 위 두 `link/...` 형식이 번호만으로 화면을 바로 여는 공개 경로입니다.

## 4. data.json 스키마 (주요 필드)

```jsonc
{
  "updated_at": "2026-11-22T15:00+09:00",
  "updated_label": "2026-11-22(일) 15:00 KST",
  "window": { "from": "2026-10-23", "to": "2026-11-22", "days": 30 },
  "scan_basis": { "latest_scan": "...", "sources": "...", "note": "..." },
  "collect_keywords": ["…14개…"],
  "dashboard_keywords": ["…10개…"],
  "dashboard_filter": { "excluded_keywords": ["공원녹지","라이다","도보네트워크","GIS DB"],
                        "excluded_items": 98, "kept_items": 133, "samples": [ … ], "note": "…" },
  "provinces": [ { "code": "경기", "name": "경기", "count": 27, "bids": 15, "prespec": 12, "urgent": 7 } ],
  "watchlist": [ { "id","label","status","tone","meta","note","g2b" } ],
  "keyword_stats": [ { "keyword": "도로대장", "bids": 6, "prespec": 0 } ],
  "items": [ {
    "id":"b-R26BK01842043", "kind":"bid|prespec", "title":"", "no":"", "order":"000",
    "org":"", "region":"강원", "sido":"강원", "region_detail":"",
    "posted":"", "deadline":"", "deadline_label":"", "deadline_short":"", "deadline_kind":"입찰 마감|의견등록 마감",
    "open_at":"", "status":"입찰중|개찰대기|개찰완료|유찰|재입찰|의견등록중|의견마감",
    "budget":0, "budget_text":"", "price_est":0,
    "contract":"", "conditions":"", "region_limit":"", "industry_limit":"",
    "attachments":[{"name":"","url":""}],
    "qna":{"state":"confirmed|noted|none|unknown","summary":"","items":[{"q":"","a":""}]},
    "result":{"state":"opened|failed|pending|before|none","participants":0,"winner":"","amount":0,"rate":0,"opened_at":"","note":""},
    "links":{"g2b":"","g2b_kind":"","presignal":"","data00":""},
    "keywords":["도로대장"], "note":"체크포인트"
  } ],
  "counts": { "total":0, "bids":0, "prespec":0, "opened":0, "failed":0, "attachments":0,
              "provinces":0, "urgent":0, "open_bids":0, "open_prespec":0 }
}
```

## 5. 갱신 절차

```bash
cd work/g2b-dashboard/scan
python3 collect.py        # presignal 14개 키워드 × 입찰·사전규격 목록
python3 enrich.py         # 공공일감: 첨부파일·개찰결과·금액
python3 ps_detail.py      # presignal 상세: 마감·개찰 확정 일시
python3 build_data.py     # ../data.json 생성 (시·도 정규화·대시보드 키워드 필터)
cd .. && python3 build-standalone.py
git add -A && git commit -m "스캔 갱신 YYYY-MM-DD" && git push origin main
```

- `build_data.py`의 `NOW`·`WIN_FROM`은 스캔 기준시각에 맞춰 갱신합니다(현재 2026-11-22 15:00 / 10-23).
- 마감일이 비어 있는 직찰·협상 건은 `MANUAL_DEADLINE`에 근거와 함께 추가합니다.
- 수집 사이트에 없는 값(자격·배점 등)은 지어내지 않고 "공고문 확인"으로 둡니다.
- 사전규격 첨부·질의·직링크 보강분은 `data.before_*.json` 백업에서 병합해 보존합니다(`BACKUPS` 목록).

## 6. 출처·주의

- 원문: 나라장터(www.g2b.go.kr) · 수집: presignal.co.kr(키워드 검색) · 공공일감(work.00data.kr, 첨부·개찰결과)
- 사전규격 질의(규격서 의견 Q&A)는 로그인 후 상세 화면에서만 보입니다. 확인된 건은 `등록된 질의 없음(0건)`과 `미확인`을 구분해 표시합니다.
- 금액·마감은 수집 시점 정리값입니다. 응찰 전 공고문·제안요청서 원문으로 재확인하십시오.
