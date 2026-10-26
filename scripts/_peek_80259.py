# -*- coding: utf-8 -*-
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
bank = json.loads((ROOT / "data/quiz_categorized.json").read_text(encoding="utf-8"))
for ch, qs in bank["questions_by_chapter"].items():
    for q in qs:
        seq = str(q["seq"]).zfill(4)
        if f"{ch}-{seq}" == "8-0259":
            print(json.dumps(q, ensure_ascii=False, indent=1))
        # 同考点排查：题干含 getenv / DASHSCOPE_API_KEY / api_key
        elif not q.get("deleted") and ("getenv" in q.get("stem", "") or "DASHSCOPE_API_KEY" in json.dumps(q.get("options", []), ensure_ascii=False)):
            print("RELATED:", f"{ch}-{seq}", "| answer:", q.get("answer"), "| stem:", q["stem"][:80])
