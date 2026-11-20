#!/usr/bin/env python3
"""마감일이 비어 있는 건은 공공일감 일정(schedule)에서 보완한다."""
import json, re, pathlib, urllib.request, time

HERE = pathlib.Path(__file__).parent
DATA = HERE.parent / "data.json"
UA = {"User-Agent": "Mozilla/5.0 (dashboard refresh)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


d = json.loads(DATA.read_text(encoding="utf-8"))
targets = [i for i in d["items"] if not i["deadline"] and i["kind"] == "bid" and i["status"] == "입찰중"]
print("targets", len(targets))
patched = {}
for it in targets:
    try:
        h = fetch(f"https://work.00data.kr/projects/{it['no']}")
    except Exception as e:
        print("ERR", it["no"], e)
        continue
    m = re.search(r'"schedule":\[(.*?)\],"attachments"', h, flags=re.S)
    steps = []
    if m:
        for blk in re.findall(r"\{[^{}]*\}", m.group(1)):
            st = re.search(r'"step":"([^"]+)"', blk)
            at = re.search(r'"at":"([^"]+)"', blk)
            if st and at:
                steps.append((st.group(1), at.group(1)))
    pick = None
    for want in ("입찰서 제출 마감", "제안서 제출 마감", "마감"):
        for s, a in steps:
            if want in s:
                pick = (s, a)
                break
        if pick:
            break
    if not pick:
        for s, a in steps:
            if "개찰" in s:
                pick = (s, a)
    if pick:
        patched[it["no"]] = pick
        print(it["no"], pick)
    time.sleep(0.4)

for it in d["items"]:
    p = patched.get(it["no"])
    if not p:
        continue
    s, a = p
    stamp = a if len(a) > 16 else a + ":00"
    it["deadline"] = stamp[:16] + "+09:00"
    it["deadline_label"] = stamp[:10] + f"({s}) " + stamp[11:16]
    it["deadline_short"] = stamp[5:7] + "." + stamp[8:10] + " " + stamp[11:16]
    it["deadline_source"] = s

DATA.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("patched", len(patched))
