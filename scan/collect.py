#!/usr/bin/env python3
"""presignal.co.kr 14개 키워드 입찰공고·사전규격 목록 수집 (2026-10-21~2026-11-20)."""
import json, re, html, time, urllib.parse, pathlib, urllib.request

KEYWORDS = ["토지적성평가", "재해취약성", "연속도면", "용도지역지구", "자율주행", "정밀지도",
            "공원관리", "공원녹지", "도보뷰", "도보네트워크", "도로대장", "GIS DB", "공간정보", "라이다"]
DATE_FROM, DATE_TO = "2026-10-21", "2026-11-20"
UA = {"User-Agent": "Mozilla/5.0 (dashboard refresh)"}
OUT = pathlib.Path(__file__).with_name("raw_items.json")


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def txt(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", s)).split())


def parse_rows(page_html):
    m = re.search(r"<tbody>(.*?)</tbody>", page_html, flags=re.S)
    if not m:
        return []
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), flags=re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)
        if not tds:
            continue
        title = re.findall(r'class="ui-table__title-link"[^>]*>(.*?)</a>', tds[0], flags=re.S)
        if not title:
            continue
        spans = [txt(s) for s in re.findall(r"<span[^>]*>(.*?)</span>", tds[0], flags=re.S)]
        cells = [txt(t) for t in tds]
        href = re.findall(r'href="(/p/[^"]+)"', tds[0])
        out.append({"title": txt(title[0]), "spans": [s for s in spans if s and s != "·"], "cells": cells,
                    "href": href[0] if href else ""})
    return out


def parse_bid(r, kw):
    c = r["cells"]
    spans = r["spans"]
    no, order = None, "000"
    for s in spans:
        m = re.search(r"\[(R\d{2}[A-Z]{2}\d+)(?:-(\d+))?\]", s)
        if m:
            no, order = m.group(1), m.group(2) or "000"
    org = spans[0] if spans and not spans[0].startswith("[") else ""
    phone = ""
    for s in spans:
        m = re.search(r"·\s*([\d][\d\-]{7,})", s)
        if m:
            phone = m.group(1)
    cats = [s for s in spans if s and s not in (org,) and not s.startswith("[") and "·" not in s
            and not re.match(r"^[\d\-]+$", s)]
    return {
        "kind": "bid", "no": no or "", "order": order, "title": r["title"], "org": org, "phone": phone,
        "conditions": c[1] if len(c) > 1 else "",
        "budget_text": c[2] if len(c) > 2 else "",
        "contract": c[3] if len(c) > 3 else "",
        "posted": c[4] if len(c) > 4 else "",
        "deadline_text": c[5] if len(c) > 5 else "",
        "open_text": c[6] if len(c) > 6 else "",
        "status": c[7] if len(c) > 7 else "",
        "cats": cats, "keyword": kw, "presignal": "",
    }


def parse_prespec(r, kw):
    c = r["cells"]
    spans = r["spans"]
    org = spans[0] if spans else ""
    owner = ""
    for s in spans[1:]:
        m = re.search(r"·\s*(.+)$", s)
        if m:
            owner = m.group(1).strip()
    return {
        "kind": "prespec", "no": r["href"].rsplit("/", 1)[-1], "order": "000", "title": r["title"], "org": org, "owner": owner,
        "biz_type": c[1] if len(c) > 1 else "",
        "budget_text": c[2] if len(c) > 2 else "",
        "posted": c[4] if len(c) > 4 else "",
        "deadline_text": c[5] if len(c) > 5 else "",
        "status": "사전규격",
        "cats": [c[1] if len(c) > 1 else ""], "keyword": kw, "presignal": "",
    }


def main():
    items = []
    for kw in KEYWORDS:
        q = urllib.parse.quote(kw)
        for kind, path, parser in (("bid", "bid", parse_bid), ("prespec", "pre-spec", parse_prespec)):
            for page in range(0, 5):
                url = (f"https://presignal.co.kr/notices/{path}?keyword={q}"
                       f"&dateFrom={DATE_FROM}&dateTo={DATE_TO}&page={page}&keywordChanged=1&sort=latest")
                try:
                    h = fetch(url)
                except Exception as e:
                    print("ERR", kw, kind, page, e)
                    break
                rs = parse_rows(h)
                print(kw, kind, page, len(rs))
                if not rs:
                    break
                for r in rs:
                    it = parser(r, kw)
                    it["presignal"] = "https://presignal.co.kr/p/" + ("s/" if kind == "prespec" else "") + it["no"]
                    items.append(it)
                if len(rs) < 10:
                    break
                time.sleep(0.4)
            time.sleep(0.4)
    # 사전규격 번호는 href에서 확보
    merged = {}
    for it in items:
        if not it["no"]:
            continue
        it["keywords"] = [it.get("keyword")] if it.get("keyword") else []
        k = (it["kind"], it["no"], it["order"])
        if k in merged:
            m = merged[k]
            for kw in it["keywords"]:
                if kw not in m["keywords"]:
                    m["keywords"].append(kw)
            for f, v in it.items():
                if f in ("keywords", "kind", "no", "order"):
                    continue
                if not m.get(f) and v:
                    m[f] = v
        else:
            merged[k] = it
    out = []
    for it in merged.values():
        it.pop("keyword", None)
        out.append(it)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("total unique:", len(out), "bids:", sum(1 for i in out if i["kind"] == "bid"),
          "prespec:", sum(1 for i in out if i["kind"] == "prespec"))


if __name__ == "__main__":
    main()
