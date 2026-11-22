#!/usr/bin/env python3
# 단일 파일(standalone) 빌드: index.html + style.css + app.js + data.json 을 한 HTML 로 인라인.
# 서버 없이 파일로 바로 열 수 있어 폰·PC 어디서나 볼 수 있는 임시 배포본 용도.
import json, pathlib, re

base = pathlib.Path(__file__).parent
html = (base / "index.html").read_text(encoding="utf-8")
css = (base / "style.css").read_text(encoding="utf-8")
js = (base / "app.js").read_text(encoding="utf-8")
data = json.loads((base / "data.json").read_text(encoding="utf-8"))

shim = (
    "<script>\n"
    "window.__G2B_INLINE__ = " + json.dumps(data, ensure_ascii=False) + ";\n"
    "(function(){var _f=window.fetch;window.fetch=function(u,o){var s=(typeof u==='string')?u:((u&&u.url)||'');"
    "if(s.indexOf('data.json')===0){return Promise.resolve({ok:true,status:200,"
    "json:function(){return Promise.resolve(window.__G2B_INLINE__);}});}"
    "return _f.apply(this,arguments);};})();\n"
    "</script>\n"
)

out = re.sub(r'<link rel="stylesheet" href="style\.css[^"]*" />', lambda m: "<style>\n" + css + "\n</style>", html)
out = re.sub(r'<script src="app\.js[^"]*"></script>', lambda m: shim + "<script>\n" + js + "\n</script>", out)
if "href=\"style.css\"" in out or "src=\"app.js\"" in out:
    raise SystemExit("인라인 치환 실패 — index.html 구조를 확인하세요")

target = base / "g2b-dashboard-standalone.html"
target.write_text(out, encoding="utf-8")
print(target, len(out), "bytes")
