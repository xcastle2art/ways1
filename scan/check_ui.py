#!/usr/bin/env python3
"""대시보드 화면 검증 — standalone HTML 을 데스크톱/모바일로 열어 캡처하고
   콘솔 오류·핵심 요소 존재를 확인한다."""
import pathlib, sys, json
from playwright.sync_api import sync_playwright

BASE = pathlib.Path(__file__).parent
FILE = BASE / "g2b-dashboard-standalone.html"
OUT = BASE / "preview"
OUT.mkdir(exist_ok=True)

errors, problems = [], []


def run():
    with sync_playwright() as p:
        b = p.chromium.launch()
        for label, vp in (("desktop", {"width": 1366, "height": 950}),
                          ("mobile", {"width": 390, "height": 844})):
            pg = b.new_page(viewport=vp, device_scale_factor=1)
            pg.on("console", lambda m: errors.append((label, m.type, m.text)) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errors.append((label, "pageerror", str(e))))
            pg.goto(FILE.as_uri())
            pg.wait_for_selector(".row", timeout=8000)
            pg.wait_for_timeout(400)
            pg.screenshot(path=str(OUT / f"elig-{label}-list.png"), full_page=False)

            # 판정 칩이 목록에 있는지
            n_chip = pg.locator(".echip").count()
            if not n_chip:
                problems.append(f"{label}: 목록에 판정 칩 없음")

            # 첫 행 드로어
            pg.locator(".row").first.click()
            pg.wait_for_timeout(350)
            h3 = [h.inner_text() for h in pg.locator(".dw-sec h3").all()]
            if not any("입찰참가자격" in h for h in h3):
                problems.append(f"{label}: 드로어에 입찰참가자격 섹션 없음")
            pg.screenshot(path=str(OUT / f"elig-{label}-drawer.png"))
            if pg.locator(".eligbox").count() == 0:
                problems.append(f"{label}: 판정 박스 없음")
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(200)

            # 업등록 DB 모달
            pg.click("#regBtn")
            pg.wait_for_timeout(350)
            if pg.locator("#regWrap").is_hidden():
                problems.append(f"{label}: 업등록 DB 모달이 열리지 않음")
            nrow = pg.locator(".regrow").count()
            if nrow < 5:
                problems.append(f"{label}: 업등록 DB 행 부족({nrow})")
            pg.screenshot(path=str(OUT / f"elig-{label}-registry.png"))
            # 검색 동작
            pg.fill("#regQ", "지오")
            pg.wait_for_timeout(250)
            filtered = pg.locator(".regrow").count()
            if filtered == 0:
                problems.append(f"{label}: 업등록 DB 검색 결과 없음")
            pg.screenshot(path=str(OUT / f"elig-{label}-registry-search.png"))
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(150)
            pg.close()
        b.close()


run()
print("console errors:", len(errors))
for e in errors[:10]:
    print("  ", e)
print("problems:", problems or "none")
sys.exit(1 if (errors or problems) else 0)
