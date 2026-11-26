import sys, json, re, subprocess

sid = "1z7o28YuNfoprOY_Ob1OoBsA_6ztUo2auJdDDMJfggbM"
rng = sys.argv[1]
out = subprocess.run(["gog", "--readonly", "sheets", "get", sid, rng], capture_output=True, text=True).stdout
d = None
for cand in re.findall(r'\{.*\}', out, re.S):
    try:
        d = json.loads(cand)
    except Exception:
        continue
if not d:
    print("PARSE_FAIL", out[:300])
    sys.exit(1)
vals = d.get("data", {}).get("values", [])
for i, r in enumerate(vals, 1):
    print(i, "||", "|".join((str(x).replace("\n", " / ") if x is not None else "") for x in r))
