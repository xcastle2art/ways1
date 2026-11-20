#!/usr/bin/env python3
"""ps_detail.json 보완: 429 회피를 위해 순차 요청 + 재시도."""
import json, time, pathlib, urllib.request, importlib.util

HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("p", HERE / "ps_detail.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

items = json.loads((HERE / "raw_items.json").read_text(encoding="utf-8"))
out = HERE / "ps_detail.json"
res = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
todo = [i for i in items if not res.get(i["no"], {}).get("deadline")]
print("todo", len(todo))
for n, it in enumerate(todo):
    for attempt in range(3):
        try:
            d = p.one({"no": it["no"], "kind": it["kind"]})[1]
            res[it["no"]] = d
            break
        except Exception:
            pass
        time.sleep(2 + attempt * 3)
    time.sleep(0.4)
    if n % 25 == 0:
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print("...", n, flush=True)
out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
ok = sum(1 for v in res.values() if v.get("deadline"))
print("done. with deadline:", ok, "/", len(res))
