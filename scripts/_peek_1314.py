# -*- coding: utf-8 -*-
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
raw = (ROOT / "data/quiz_categorized.js").read_text(encoding="utf-8")
m = re.search(r"const\s+QUIZ_DATA_BY_CHAPTER\s*=\s*(\{.*\});?\s*$", raw, re.S)
data = json.loads(m.group(1).rstrip().rstrip(";"))
q8 = [q for q in data["8"] if str(q["seq"]).zfill(4) == "0259"]
print("quiz_categorized.js 8-0259 answer:", q8[0]["answer"] if q8 else "NOT FOUND")

minraw = (ROOT / "data/quiz_categorized.min.js").read_text(encoding="utf-8")
m2 = re.search(r"const\s+QUIZ_DATA_BY_CHAPTER\s*=\s*(\{.*\});?\s*$", minraw, re.S)
d2 = json.loads(m2.group(1).rstrip().rstrip(";"))
q8m = [q for q in d2["8"] if str(q["s"]).zfill(4) == "0259"]
print("min.js 8-0259 answer:", q8m[0]["a"] if q8m else "NOT FOUND")

bank = json.loads((ROOT / "data/quiz_categorized.json").read_text(encoding="utf-8"))
for q in bank["questions_by_chapter"].get("10", []):
    if str(q["seq"]).zfill(4) == "1314" and not q.get("deleted"):
        print("=" * 60)
        print(json.dumps(q, ensure_ascii=False, indent=1))
