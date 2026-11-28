#!/usr/bin/env python3
"""공고별 제안요청서·공고문·과업지시서 첨부를 내려받아 텍스트로 캐시한다.

정량평가 기준(배점표·실적 기준선·인력 구간·지역상생 조건)을 공고문 원문에서
파싱하기 위한 1단계. 이미 받은 파일은 건너뛰므로 매 회차 실행해도 새 공고분만 받는다.

  python3 fetch_rfp.py                # data.json 의 진행중 협상·적격심사 공고 전체
  python3 fetch_rfp.py --no R26BK...  # 특정 공고만
  python3 fetch_rfp.py --all          # 결과 나온 공고 포함 전체 입찰공고

출력
  scan/att/rfp/{공고번호}/{n}_{파일명}          내려받은 원본
  scan/registry/att_text/rfp_{공고번호}_{n}.txt  추출 텍스트
  scan/registry/att_text/_manifest.json          파일↔공고 매핑
"""
import json, pathlib, re, sys, time, urllib.request, zipfile
import concurrent.futures as cf

HERE = pathlib.Path(__file__).parent
WORK = HERE.parent
DATA = WORK / "data.json"
ATT = HERE / "att" / "rfp"
TXT = HERE / "registry" / "att_text"
MAN = TXT / "_manifest.json"
UA = {"User-Agent": "Mozilla/5.0 (dashboard refresh)"}
NAME_OK = re.compile(r"제안요청서|공고문|과업지시서|과업내용서|RFP|규격서|입찰공고", re.I)
EXT_OK = (".hwpx", ".pdf")
MAX_BYTES = 12 * 1024 * 1024
MAX_FILES = 4
KEEP_OPEN = ("입찰중", "개찰대기")


def fetch(url):
    last = None
    for a in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read(MAX_BYTES + 1)
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + a * 3)
    raise last


def pdf_text(b):
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open(stream=b, filetype="pdf")
        t = "\n".join(p.get_text() for p in doc)
        doc.close()
        return t
    except Exception:                                # noqa: BLE001
        return ""


def hwpx_text(b):
    import io
    try:
        out = []
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            for n in z.namelist():
                if n.startswith("Contents/") and n.endswith(".xml") and "section" in n:
                    x = z.read(n).decode("utf-8", "replace")
                    x = x.replace("</hp:p>", "\n").replace("</hp:tr>", "\n").replace("</hp:tc>", " | ")
                    x = re.sub(r"<[^>]+>", " ", x)
                    out.append(re.sub(r"[ \t]+", " ", x))
        return "\n".join(out)
    except Exception:                                # noqa: BLE001
        return ""


def safe(s, n=40):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_")
    return s[:n]


def one(item):
    no = item["no"]
    key = f"{no}-{item.get('order') or '000'}"
    got, man = [], {}
    atts = [a for a in (item.get("attachments") or [])
            if a.get("url") and a.get("name", "").lower().endswith(EXT_OK)
            and NAME_OK.search(a.get("name", ""))]
    # PDF 는 같은 문서의 중복일 때가 많아 뒤로
    atts.sort(key=lambda a: (a["name"].lower().endswith(".pdf"),))
    atts = atts[:MAX_FILES]
    for idx, a in enumerate(atts, 1):
        ext = pathlib.Path(a["name"]).suffix.lower()
        cache = TXT / f"rfp_{key}_{idx}.txt"
        if cache.exists() and cache.stat().st_size > 200:
            got.append({"file": a["name"], "text": str(cache), "cached": True})
            continue
        try:
            b = fetch(a["url"])
        except Exception as e:                        # noqa: BLE001
            man[a["name"]] = {"error": str(e)[:80]}
            continue
        if len(b) > MAX_BYTES:
            man[a["name"]] = {"error": "too_large"}
            continue
        d = ATT / key
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{idx}_{safe(a['name'])}").write_bytes(b)
        t = pdf_text(b) if ext == ".pdf" else hwpx_text(b)
        if len(t) < 200:
            continue
        cache.write_text(t, encoding="utf-8")
        got.append({"file": a["name"], "text": str(cache), "cached": False})
    return key, got


def main():
    args = sys.argv[1:]
    only = args[args.index("--no") + 1] if "--no" in args else None
    allk = "--all" in args
    data = json.loads(DATA.read_text(encoding="utf-8"))
    items, seen = [], set()
    for it in data["items"]:
        if it["kind"] != "bid":
            continue
        if only and it["no"] != only:
            continue
        if not only and not allk and it.get("status") not in KEEP_OPEN:
            continue
        k = f"{it['no']}-{it.get('order') or '000'}"
        if k in seen:
            continue
        seen.add(k)
        items.append(it)
    TXT.mkdir(parents=True, exist_ok=True)
    man = json.loads(MAN.read_text(encoding="utf-8")) if MAN.exists() else {}
    new_n = 0
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for key, got in ex.map(one, items):
            man[key] = got
            new_n += sum(1 for g in got if not g.get("cached"))
    MAN.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    have = sum(1 for v in man.values() if v)
    print(f"[fetch_rfp] 공고 {len(items)}건 조회 · 새로 받은 파일 {new_n}개 · 텍스트 보유 공고 {have}건")


if __name__ == "__main__":
    main()
