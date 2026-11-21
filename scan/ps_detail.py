#!/usr/bin/env python3
"""presignal 상세 페이지에서 마감·개찰 일시, 예산 규모 등 확정 정보 수집."""
import json, re, html, pathlib, urllib.request, concurrent.futures as cf, time

HERE = pathlib.Path(__file__).parent
RAW = HERE / "raw_items.json"
OUT = HERE / "ps_detail.json"
UA = {"User-Agent": "Mozilla/5.0 (dashboard refresh)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def flatten(h):
    t = re.sub(r"<(script|style).*?</\1>", "", h, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "|", t))
    t = re.sub(r"\|+", "|", t)
    return re.sub(r"[ \t]+", " ", t)


def field(t, label):
    m = re.search(r"\|" + re.escape(label) + r"\|(?:\s*\|)*\s*([^|\s][^|]*?)\s*\|", t)
    return m.group(1).strip() if m else None


def one(item):
    url = "https://presignal.co.kr" + ("/p/s/" if item["kind"] == "prespec" else "/p/") + item["no"]
    try:
        t = flatten(fetch(url))
    except Exception as e:
        return item["no"], {"error": str(e)[:70]}
    d = {
        "org": field(t, "발주기관"),
        "biz": field(t, "업무구분"),
        "posted": field(t, "공고일"),
        "deadline": field(t, "입찰 마감") or field(t, "의견 마감"),
        "open": field(t, "개찰일시"),
        "budget": field(t, "예산 규모"),
        "method": field(t, "계약 방법"),
    }
    return item["no"], d


def main():
    items = json.loads(RAW.read_text(encoding="utf-8"))
    nos = [{"no": i["no"], "kind": i["kind"]} for i in items]
    res = {}
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        for n, d in ex.map(one, nos):
            res[n] = d
    # 실패분 재시도(연속 요청으로 일시 차단되는 경우가 있어 간격을 두고 2회까지)
    for attempt in range(2):
        retry = [i for i in nos if "error" in res.get(i["no"], {})]
        if not retry:
            break
        print("retry", attempt + 1, "items:", len(retry))
        time.sleep(4)
        with cf.ThreadPoolExecutor(max_workers=2) as ex:
            for n, d in ex.map(one, retry):
                res[n] = d
    ok = sum(1 for v in res.values() if v.get("deadline"))
    err = sum(1 for v in res.values() if "error" in v)
    print("items:", len(nos), "with deadline:", ok, "errors:", err)
    # 기존 파일의 정상 값을 잃지 않도록 병합(새로 실패한 키는 이전 값 유지)
    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    for k, v in res.items():
        if (not v.get("deadline") or "error" in v) and k in prev and "error" not in prev[k]:
            res[k] = prev[k]
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
