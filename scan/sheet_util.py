import sys, json, re, subprocess

sid = "1z7o28YuNfoprOY_Ob1OoBsA_6ztUo2auJdDDMJfggbM"
rng = sys.argv[1]
out = subprocess.run(["gog", "--readonly", "sheets", "get", sid, rng], capture_output=True, text=True).stdout
out = re.sub(r"<<<EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>", "", out)
out = re.sub(r"<<<END_EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>", "", out)
out = out.strip()
if out.startswith("Source: gog"):
    out = out[len("Source: gog"):].strip()
if out.startswith("---"):
    out = out[3:].strip()
try:
    d = json.loads(out)
except Exception:
    print("PARSE_FAIL:", out[:400])
    sys.exit(1)
if not d.get("ok"):
    print("NOT_OK:", d.get("code"), d.get("message"))
    sys.exit(1)
vals = d.get("data", {}).get("values", [])
start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
for i, r in enumerate(vals, start):
    print(i, "||", "|".join((str(x).replace("\n", " / ") if x is not None else "") for x in r))
