#!/usr/bin/env python3
"""공공일감(work.00data.kr)에서 첨부파일·개찰결과·금액 정보 보강."""
import json, re, pathlib, time, urllib.request, concurrent.futures as cf

HERE = pathlib.Path(__file__).parent
RAW = HERE / "raw_items.json"
OUT = HERE / "enriched.json"
UA = {"User-Agent": "Mozilla/5.0 (dashboard refresh)"}


def fetch(url):
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(3 + attempt * 4)
    raise last


def arr_after(h, anchor):
    i = h.find(anchor)
    if i < 0:
        return None
    seg = h[i + len(anchor):]
    depth, instr, esc = 1, False, False
    for k, ch in enumerate(seg):
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                instr = False
            continue
        if ch == '"':
            instr = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads("[" + seg[:k + 1])
                except Exception:
                    return None
    return None


def num(pm):
    return None if not pm or pm in ("null", "") else float(pm)


def extract(h):
    d = {}
    m = re.search(r'"result":\{([^}]*)\}', h)
    if m:
        blk = m.group(1)
        g = lambda p: (re.search(p, blk).group(1) if re.search(p, blk) else None)
        d["progress"] = g(r'"progressDiv":"([^"]*)"')
        d["participants"] = num(g(r'"participants":(\d+|null)'))
        d["opened_at"] = g(r'"openedAt":"?([^",]*)')
        d["winner_name"] = g(r'"winnerName":"([^"]*)"')
        d["winner_amount"] = num(g(r'"winnerAmount":(\d+|null)'))
        d["winner_rate"] = num(g(r'"winnerRate":([\d.]+|null)'))
    m = re.search(r'"signed":\{"parties":\d+,"corp":(null|"[^"]*"),"partners":\d+,"amount":(null|\d+)', h)
    if m:
        d["signed_corp"] = None if m.group(1) == "null" else m.group(1).strip('"')
        d["signed_amount"] = num(m.group(2))
    for key, pat in (("estimated_price", r'"estimatedPrice":(null|\d+)'),
                     ("budget", r'"budget":(null|\d+)'),
                     ("base_amount", r'"baseAmount":(null|\d+)'),
                     ("lowest_bid_rate", r'"lowestBidRate":(null|[\d.]+)'),
                     ("pre_spec_no", r'"preSpecNo":(null|"[^"]*")'),
                     ("region", r'"region":"([^"]*)"'),
                     ("region_limit", r'"regionLimit":(null|"[^"]*")'),
                     ("industry_limit", r'"industryLimit":(null|"[^"]*")'),
                     ("contract_method", r'"contractMethod":"([^"]*)"'),
                     ("bid_method", r'"bidMethod":"([^"]*)"'),
                     ("deadline", r'"deadline":"([^"]*)"')):
        m = re.search(pat, h)
        v = m.group(1) if m else None
        if isinstance(v, str) and v.startswith('"'):
            v = v.strip('"')
        d[key] = v if v != "null" else None
    atts = arr_after(h, '"attachments":[')
    d["attachments"] = [{"name": a.get("name", "").strip(), "url": a.get("url", "")}
                        for a in (atts or []) if a.get("url")]
    # 계약(낙찰) 정보
    m = re.search(r'"contracts":\[\{"contractNo":"[^"]*","noticeNo":"[^"]*","name":"[^"]*","amount":(\d+|null),'
                  r'"totalAmount":(\d+|null),"period":("[^"]*"|null),"contractedOn":("[^"]*"|null)', h)
    if m:
        d["contract_amount"] = num(m.group(1))
        d["contracted_on"] = None if m.group(4) == "null" else m.group(4).strip('"')
    m = re.search(r'"contracts":\[.*?"corps":\[\{"role":"[^"]*","name":"([^"]*)"', h)
    if m:
        d["contract_corp"] = m.group(1)
    return d


def one(item):
    url = f"https://work.00data.kr/projects/{item['no']}"
    try:
        h = fetch(url)
    except Exception as e:
        return item["no"], {"error": str(e)[:80]}
    if "입찰공고상세" not in h:
        return item["no"], {"error": "not_found"}
    return item["no"], extract(h)


def main():
    items = json.loads(RAW.read_text(encoding="utf-8"))
    bids = [i for i in items if i["kind"] == "bid"]
    nos = sorted({i["no"] for i in bids})
    print("unique bid notices:", len(nos))
    res = {}
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        for n, d in ex.map(one, [{"no": n} for n in nos]):
            res[n] = d
    ok = sum(1 for v in res.values() if "error" not in v)
    withatt = sum(1 for v in res.values() if v.get("attachments"))
    withres = sum(1 for v in res.values() if v.get("progress") in ("개찰완료", "낙찰", "유찰"))
    print("ok:", ok, "attachments:", withatt, "개찰결과:", withres)
    OUT.write_text(json.dumps({"items": items, "detail": res}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
