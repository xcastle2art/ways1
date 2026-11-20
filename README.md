# 나라장터 입찰·사전규격 모니터링 대시보드 (전국)

나라장터(www.g2b.go.kr) 입찰공고·사전규격·개찰결과를 **전국 지자체·기관** 기준으로 모아 보는 정적 웹앱입니다.
공고일 기준 **최근 30일** 자료를 14개 키워드(토지적성평가·재해취약성·연속도면·용도지역지구·자율주행·정밀지도·공원관리·공원녹지·도보뷰·도보네트워크·도로대장·GIS DB·공간정보·라이다)로 수집합니다.

- 라이브: **https://xcastle2art.github.io/ways1/**
- 저장소: https://github.com/xcastle2art/ways1 (public, Pages: `main` / root)
- 빌드 단계 없음: `index.html` + `style.css` + `app.js` + `data.json`

## 1. 화면 구성

| 탭 | 내용 |
|---|---|
| 전체 | 30일 내 입찰공고+사전규격 통합 목록 |
| 입찰공고 | 입찰공고만 |
| 사전규격 | 사전규격(의견등록 마감 기준)만 |
| 개찰결과 | 개찰 완료·유찰·개찰대기 건 (참가업체 수, 낙찰·계약업체, 금액, 낙찰률) |
| 담당권역 | 담당자 4명별 카드(진행 중 입찰·사전규격·마감 임박 D-3·예산 합계) → 카드 클릭 시 해당 권역만 필터 |

- **담당자 매핑**: 박정수(경남) · 조준래(경북·전남·전북) · 오창민(경기·강원) · 김충열(경기·충남·충북). **경기도는 오창민·김충열 두 사람 모두에게 잡힙니다.**
- 목록 행을 누르면 상세 드로어가 열리고 **첨부파일 목록 + 바로 열기**, **사전규격 질의(질문·답변 요약, 상태 구분)**, **개찰결과 요약**, **나라장터 직링크·공고번호 복사**가 표시됩니다.
- 30일 창과 D-day는 **접속 시각 기준으로 매번 재계산**됩니다(오래된 공고는 자동으로 빠짐). 하단 데이터 기준·수집 현황도 `data.json` 값으로 렌더링됩니다.

## 2. 나라장터 직링크 방식 (검증 완료)

| 대상 | 형식 | 검증 |
|---|---|---|
| 입찰공고 상세 | `https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={공고번호}&bidPbancOrd={차수}` | 동해시 `R26BK01842043` 실제 접속 → 공고상세 표시 |
| 첨부파일 다운로드 | `https://www.g2b.go.kr/pn/pnp/pnpe/UntyAtchFile/downloadFile.do?bidPbancNo=…&bidPbancOrd=…&fileType=&fileSeq=N&prcmBsneSeCd=03(용역)/05(공사)` | 실제 HWPX 파일 수신(200) |
| 사전규격(R26BD…) | 딥링크 없음 → 나라장터 메인 + **공고번호 원클릭 복사** 버튼 + 수집원 상세 | `PNPE027_01` 형식은 "공고정보가 존재하지 않습니다"로 실패 |

> 나라장터는 WebSquare SPA라 주소창 URL이 바뀌지 않습니다. 위 `link/...` 형식이 공고번호로 바로 열리는 유일한 공개 경로입니다.

## 3. data.json 스키마

```jsonc
{
  "updated_at": "2026-11-20T16:40+09:00",
  "updated_label": "2026-11-20(금) 16:40 KST",
  "window": { "from": "2026-10-21", "to": "2026-11-20", "days": 30 },
  "scan_basis": { "latest_scan": "...", "sources": "...", "note": "..." },
  "managers": [ { "id": "oh", "name": "오창민", "regions": ["경기","강원"], "color": "#059669" } ],
  "watchlist": [ { "id","label","status","tone","meta","note","g2b" } ],
  "keyword_stats": [ { "keyword": "도로대장", "bids": 6, "prespec": 1 } ],
  "items": [ {
    "id":"b-R26BK01842043", "kind":"bid|prespec", "title":"", "no":"", "order":"000",
    "org":"", "region":"경기", "region_detail":"경기도 남양주시", "managers":["오창민"],
    "posted":"", "deadline":"", "deadline_label":"", "deadline_kind":"입찰 마감|의견등록 마감",
    "open_at":"", "status":"입찰중|개찰대기|개찰완료|유찰|의견등록중|의견마감",
    "budget":0, "budget_text":"", "price_est":0, "base_amount":0, "lowest_rate":0,
    "contract":"", "conditions":"", "region_limit":"", "industry_limit":"",
    "attachments":[{"name":"","url":""}],
    "qna":{"state":"confirmed|noted|none|unknown","summary":"","items":[{"q":"","a":""}]},
    "result":{"state":"opened|failed|pending|before|none","participants":0,"winner":"","amount":0,"rate":0,"opened_at":"","note":""},
    "links":{"g2b":"","presignal":"","data00":""},
    "keywords":["도로대장"], "note":"체크포인트"
  } ],
  "counts": { "total":0, "bids":0, "prespec":0, "opened":0, "failed":0, "attachments":0 }
}
```

## 4. 갱신 절차

```bash
cd work/g2b-dashboard/scan
python3 collect.py        # presignal 14개 키워드 × 입찰·사전규격 목록
python3 enrich.py         # 공공일감: 첨부파일·개찰결과·금액
python3 ps_detail.py      # presignal 상세: 마감·개찰 확정 일시
python3 build_data.py     # ../data.json 생성 (지역 정규화·담당자 매핑)
cd .. && python3 build-standalone.py
git add -A && git commit -m "스캔 갱신 YYYY-MM-DD" && git push origin main
```

- 마감일이 비어 있는 직찰·협상 건은 `build_data.py`의 `MANUAL_DEADLINE`에 근거와 함께 추가합니다.
- 수집 사이트에 없는 값(자격·배점 등)은 지어내지 않고 "공고문 확인"으로 둡니다.

## 5. 출처·주의

- 원문: 나라장터(www.g2b.go.kr) · 수집: presignal.co.kr(키워드 검색) · 공공일감(work.00data.kr, 첨부·개찰결과)
- 사전규격 질의(의견등록 Q&A)는 나라장터 로그인 후 상세에서만 확인 가능 → 공개 수집원에 없으면 화면에 **미확인**으로 표시(등록된 질의 없음과 구분).
- 금액·마감은 수집 시점 정리값입니다. 응찰 전 공고문·제안요청서 원문으로 재확인하십시오.
