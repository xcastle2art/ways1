#!/usr/bin/env python3
"""아침 스캔용: presignal 키워드별 11-19~11-21 목록만 가볍게 훑기."""
import json, re, html, time, urllib.parse, urllib.request

KEYWORDS = ["토지적성평가", "재해취약성", "연속도면", "용도지역지구", "자율주행", "정밀지도",
            "공원관리", "공원녹지", "도보뷰", "도보네트워크", "도로대장", "GIS DB", "공간정보", "라이다"]
DATE_FROM, DATE_TO = "2026-11-19", "2026-11-22"
UA = {"User-Agent": "Mozilla/5.0 (dashboard refresh)"}


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
        out.append({"title": txt(title[0]), "spans": [s for s in spans if s and s != "·"],
                    "cells": cells, "href": href[0] if href else ""})
    return out


results = []
for kw in KEYWORDS:
    q = urllib.parse.quote(kw)
    for kind, path in (("bid", "bid"), ("prespec", "pre-spec")):
        url = (f"https://presignal.co.kr/notices/{path}?keyword={q}"
               f"&dateFrom={DATE_FROM}&dateTo={DATE_TO}&page=0&keywordChanged=1&sort=latest")
        try:
            h = fetch(url)
        except Exception as e:
            print("ERR", kw, kind, e)
            continue
        for r in parse_rows(h):
            results.append({"kw": kw, "kind": kind, "title": r["title"],
                            "spans": r["spans"], "cells": r["cells"], "href": r["href"]})
        time.sleep(0.3)

print(json.dumps(results, ensure_ascii=False, indent=1))
