# -*- coding: utf-8 -*-
"""批次G：8-0259 选项措辞修正（用户报告）。

答案 A 方向正确（B/C/D 为 temperature/低采样/max_tokens 的作用，与 api_key 无关），
但选项 A "设置API密钥"不准确：os.getenv() 是从环境变量读取值，不是设置。
解析同样自相矛盾。题意考点不变（api_key 参数作用），保留 ID，text_fix + revised_at。
台账：rebuild20261027_G_fix
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import curate_core as cc
from datetime import datetime

NOW = datetime.now().isoformat(timespec="seconds")
BANK = cc.load_bank()
BY = BANK["questions_by_chapter"]

q = None
for x in BY.get("8", []):
    if str(x["seq"]).zfill(4) == "0259" and not x.get("deleted"):
        q = x; break
assert q, "8-0259 not found"
assert q["answer"] == "A" and q["options"][0]["option_text"] == "设置API密钥"

q["options"][0]["option_text"] = "从环境变量读取 API 密钥，供调用大模型服务时做身份认证"
q["analysis"] = (
    "os.getenv(\"DASHSCOPE_API_KEY\") 从环境变量中读取 API 密钥的值，赋给 api_key 参数，"
    "用于调用百炼/DashScope 服务时的身份认证——这是官方推荐的密钥管理方式，避免把密钥硬编码在代码里。"
    "B 是 temperature 参数（较高取值）的作用；C 是 temperature/top_p 调低后的效果；"
    "D 是 max_tokens 参数的作用。三者均与 api_key 无关。"
)
q["revised_at"] = NOW

if not cc.batch_exists("rebuild20261027_G_fix"):
    cc.append_batch("text_fix", "rebuild_batch_G.py",
                    [{"qid": "8-0259", "reason":
                      "选项A措辞'设置API密钥'不准确（os.getenv为读取环境变量），解析自相矛盾；"
                      "修正措辞与解析，答案A与考点不变，保留ID"}],
                    reason="批次G：8-0259 选项措辞/解析修正（用户报告）",
                    batch_id="rebuild20261027_G_fix")
cc.write_bank(BANK)
print("批次G 完成: 8-0259 已修正")
