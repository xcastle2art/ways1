# 나라장터 입찰·사전규격 모니터링 대시보드

공간정보사업실 담당 권역(강원·경기·충청·전북)의 나라장터 입찰공고·사전규격을 PC 웹과 모바일 브라우저 어디서나 조회·필터링하는 정적 웹앱입니다.
빌드 단계 없이 `index.html` + `style.css` + `app.js` + `data.json` 네 파일만으로 동작하며, GitHub Pages에 그대로 올릴 수 있습니다.

---

## 1. 파일 구성

| 파일 | 역할 |
|---|---|
| `index.html` | 화면 골격(상단바·KPI·필터·테이블·카드·키워드 현황·푸터) |
| `style.css` | 반응형 스타일. PC(≥901px)는 테이블, 모바일(≤900px)은 카드형 리스트로 전환 |
| `app.js` | `data.json` fetch → D-day 자동 계산 → 필터·검색·정렬·렌더링 |
| `data.json` | 표시할 모든 데이터(마지막 업데이트, 요약 지표, 입찰공고·사전규격·참고·특별 추적) |
| `build_data.py` | `data.json` 생성 스크립트(스캔 문서 기준 데이터를 코드로 관리, `python3 build_data.py`) |
| `build-standalone.py` | CSS·JS·데이터를 한 HTML로 인라인한 `g2b-dashboard-standalone.html` 생성 |
| `deploy.sh` | push → Pages 활성화 → HTTP 200 확인(대상 저장소 `xcastle2art/ways1`) |
| `README.md` | 이 문서 |

---

## 2. 화면 구성

1. **특별 추적 배너** — 강릉시 토지적성평가(미게시), LX 토적 표준프로그램 재공고(12-01), 경산시 사전규격(의견마감 후 본공고 대기), 부안군 도로대장(개찰결과 미게시). 마감일이 있는 카드는 D-day를 자동 표시합니다.
2. **요약 KPI 5장** — 진행 중 입찰 / D-2 이내 임박(입찰공고 기준) / 담당 권역 건수 / 사전규격(의견마감 전) / 마지막 업데이트.
3. **필터 & 검색**
   - 구분 탭: 전체 · 입찰공고 · 사전규격 · 참고(키워드외) — 탭 라벨에 현재 조건의 건수가 함께 표시됩니다.
   - 권역 칩: 전체 · 담당권역 · 전국·기타
   - 긴급도 칩: 전체 · D-2 이내 임박
   - 키워드 칩: 데이터에 등장하는 키워드를 건수와 함께 자동 생성
   - 검색창: 사업명·발주기관·공고번호·권역 통합 검색(공백 무시)
   - `마감 지난 건 표시` 체크박스로 마감 지난 항목까지 확인
4. **목록**
   - PC: 컬럼형 테이블(D-day / 사업명·공고번호 / 발주기관 / 금액 / 마감 / 접수·평가 / 체크포인트 / 원문). **행을 클릭하면** 참가자격·체크포인트 전문과 원문·시트·키워드 검색 버튼이 펼쳐집니다.
   - 모바일: 카드형 리스트. 금액·마감·접수·평가·자격·체크를 라벨과 함께 전부 노출하고, 하단에 `원문 보기`·`시트`·`키워드 검색` 버튼을 배치했습니다.
   - 방문접수·평가위원 추첨 등 놓치면 안 되는 접수 방식은 빨간색 `⚠` 로 강조됩니다.
5. **키워드별 현황** — 10개 키워드의 입찰/사전규격 건수와 비고. 카드를 누르면 해당 키워드로 필터됩니다.
6. **필터 상태가 URL 해시에 저장**됩니다(예: `#kind=bid&region=focus&urgency=urgent`). 즐겨찾기·홈 화면에 추가해 두면 같은 조건으로 바로 열립니다.

D-day는 저장된 값이 아니라 **접속한 날짜(KST) 기준으로 매번 계산**하므로, 며칠 뒤 열어도 마감 임박 여부가 자동으로 갱신됩니다. 다만 마감 전 항목이 모두 지나면 목록이 비고 `마감 지난 건 표시` 안내가 뜨므로, 그때는 `data.json`을 새 스캔 결과로 갱신해야 합니다.

---

## 3. data.json 스키마

```jsonc
{
  "updated_at": "2026-11-16T09:50:00+09:00",   // ISO 시각
  "updated_label": "2026-11-16(월) 09:50 KST",  // 화면 표시용
  "scan_basis": { "latest_scan": "...", "scans": [...], "new_items": 0, "changes": 0, "note": "..." },
  "sheet": { "id": "...", "url": "...", "tabs": { "bids": {"name":"...","gid":"..."}, ... } },
  "region_focus": ["강원", "경기", "충청", "전북"],
  "summary": { "bids": 11, "bids_open": 11, "urgent_d2_bids": 5, "focus_region": 9, "pre_specs": 6, "others": 4 },
  "watchlist": [ { "id","label","status","tone":"wait|urgent","deadline_iso","meta","note","links":[{label,url}] } ],
  "keyword_stats": [ { "keyword","bids","prespec","plan","note" } ],
  "bids":    [ 항목 ... ],   // 입찰공고
  "pre_specs":[ 항목 ... ],  // 사전규격 (deadline = 의견등록 마감)
  "others":  [ 항목 ... ]    // 참고(키워드외)
}
```

### 항목(item) 필드

| 필드 | 설명 |
|---|---|
| `id` | 고유 키(화면 렌더링·상세 펼치기용). 다른 항목과 겹치지 않게 |
| `region` / `region_group` | 표시용 권역 문자열 / `focus`(담당권역) · `nation`(전국) · `outside`(권역외) |
| `title` | 사업명 |
| `notice_no` | 공고번호 또는 사전규격번호 |
| `org` | 발주기관(+공고 차수) |
| `price_est` / `budget` / `amount_label` | 추정가격(원) / 기초·배정예산(원) / 금액을 문장으로 표기해야 할 때(예: `"1억 미만"`) |
| `deadline_label` / `deadline_iso` | 화면 표시용 마감 문구 / **D-day 계산 기준 시각**(`2026-11-17T17:00:00+09:00`) |
| `submit_method` / `submit_alert` | 접수 방식 / `true`면 빨간 ⚠ 강조 |
| `eval_label` | 개찰·제안서 평가 일시 |
| `method` | 계약·평가 방식(협상, 적격심사, 정량배점 등) |
| `qualification` | 참가자격 핵심 |
| `checkpoint` | 체크포인트(놓치면 안 되는 주의사항) |
| `link` | 원문 링크(presignal.co.kr `/p/{공고번호}`, 사전규격 `/p/s/{번호}`) |
| `keywords` | 키워드 필터에 쓰일 배열 |
| `in_sheet` | `false`면 화면에 `시트 미기재` 배지 표시(스캔 문서에만 있는 건) |
| `relevance` | `high` / `normal` / `low`. `low`면 `관련성 낮음` 배지 |
| `sheet_tab` | 이 항목이 실린 시트 탭 키(`bids` · `pre_specs` · `others`) — 항목별 '시트' 버튼이 그 탭으로 이동 |

---

## 4. 갱신 절차 (스캔 후 3분)

1. 새 스캔 문서에서 **신규·정정 건만** 확인합니다.
2. `data.json`에서:
   - `updated_at` / `updated_label` 을 현재 시각으로 바꿉니다.
   - `scan_basis`(최신 스캔 시각·신규 건수·정정 건수)를 갱신합니다.
   - 신규 건을 `bids` / `pre_specs` / `others`에 추가하거나 마감된 건을 삭제합니다.
   - `watchlist`의 강릉·LX·경산·부안 상태 문구를 갱신합니다.
   - `summary`의 숫자를 실제 건수로 맞춥니다(화면 KPI는 파일에서 자동 계산되지만, 값이 어긋나면 혼동을 줍니다).
3. 브라우저에서 새로고침하면 반영됩니다(상단 `새로고침` 버튼은 캐시를 무시하고 다시 받습니다).

> **원칙**: 금액·마감·자격은 스캔 시점 정리값입니다. 응찰 판단 전에는 반드시 공고문·제안요청서 원문으로 재확인하십시오. 특히 동해시 도로대장 직접방문 접수(11-30 09:30–16:00), 동해 질의 마감(11-23 16:00), 아산·광주과기원처럼 수집 사이트에 개찰시각만 표기된 건의 투찰 마감.
>
> 현재 `data.json`은 `build_data.py`로 생성됐습니다(스캔 문서 → 코드). 손으로 고치는 대신 이 스크립트를 수정해 다시 생성하는 쪽이 수치 오타를 줄입니다.

---

## 5. 로컬에서 확인하기

`fetch('data.json')` 을 쓰기 때문에 **`index.html` 을 파일로 직접 열면(file://) 데이터가 표시되지 않습니다.** 아래처럼 간단한 서버로 열어 주세요.

```bash
cd work/g2b-dashboard
python3 -m http.server 8000
# 브라우저에서 http://localhost:8000
```

실패하면 화면 상단에 원인과 함께 안내 문구가 표시됩니다.

## 6. 배포 (GitHub Pages)

| 항목 | 값 |
|---|---|
| 접속 URL | https://xcastle2art.github.io/ways1/ (**Pages 미활성 — 현재 404**) |
| 저장소 | https://github.com/xcastle2art/ways1 (**PRIVATE**) |
| Pages 설정 | Deploy from a branch · `main` · `/ (root)` |
| 로컬 소스 | `work/g2b-dashboard/` (이 폴더가 원본, 배포는 이 폴더를 push) |
| 배포 스크립트 | `bash deploy.sh` (push → Pages 활성화 → HTTP 200 확인) |

> 상태(2026-11-20 16:20 KST): 코드는 `xcastle2art/ways1` main에 푸시 완료. **GitHub Pages는 두 가지 이유로 열리지 않았습니다.**
> ① Pickle의 GitHub 연동 토큰에 Pages 권한이 없어 API 호출이 `403 Resource not accessible by integration`으로 거절됩니다(같은 토큰이 저장소에는 admin 권한 보유).
> ② 저장소가 PRIVATE이고 무료 플랜이므로, 권한이 있어도 GitHub Pages는 private 저장소에서 동작하지 않습니다(Pro 이상 필요).
> 무료로 웹 주소를 쓰려면 Settings → Danger Zone → Change visibility → **Public** 전환이 필요하지만, 이 저장소에는 공고 원문 외에 응찰 전략·정량배점 해석 메모가 들어 있어 공개 여부는 사용자가 결정해야 합니다.
> 서버 없이 지금 바로 보는 방법은 아래 단일 파일본입니다.
> 대신 서버 없이 바로 열 수 있는 단일 파일본도 함께 생성됩니다: `python3 build-standalone.py` → `g2b-dashboard-standalone.html`(CSS·JS·데이터 인라인, 폰으로 파일만 열면 동작).

**갱신 방법**은 이 폴더에서 파일을 고친 뒤 push만 하면 됩니다. Pages가 1분 안팎으로 자동 재빌드합니다.

```bash
cd work/g2b-dashboard
git add -A && git commit -m "스캔 갱신 2026-11-16" && git push origin main
```

> 저장소는 **private**입니다(위 상태 참고). 이 문서·데이터에는 공개 공고 원문 외에 응찰 전략 메모가 포함되므로, 외부에 알려지면 곤란한 내용은 `data.json`에 넣지 마십시오. 저장소를 private으로 돌리려면 GitHub Pro 이상 플랜이 필요합니다.

휴대폰 브라우저에서 위 URL을 연 뒤 **홈 화면에 추가**하면 앱처럼 쓸 수 있습니다.

---

## 7. 참고

- 원문 출처: presignal.co.kr(나라장터 OpenAPI 수집), g2b.go.kr(공고번호 검색)
- 정리본 시트: [나라장터 입찰·사전규격 모니터링 (2026-11-16)](https://docs.google.com/spreadsheets/d/1z7o28YuNfoprOY_Ob1OoBsA_6ztUo2auJdDDMJfggbM/edit)
- 데이터 기준: 2026-11-20(금) 16:20 KST / 최신 스캔 2026-11-20 16:00 KST
- 정리 시트는 2026-11-16 스냅샷이라 11-16 이후 신규·정정분이 반영되어 있지 않습니다(화면에 `시트 미기재` 배지로 표시)
