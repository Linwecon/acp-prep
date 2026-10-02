# -*- coding: utf-8 -*-
"""题库治理本机管理服务（admin server）

为 admin.html 提供可实际执行的治理操作 API（软删除/恢复/移章/答案修正/回滚），
所有变更走 curate_core 共享核心：写库前自动备份、原子替换写文件、写台账、
保留旧版本、可回滚；读库→校验→写库→记账→重建全程互斥。

启动:
    python scripts/admin_server.py                 # 正式题库，http://127.0.0.1:8765/admin.html
    python scripts/admin_server.py --port 9000
    python scripts/admin_server.py --bank <副本目录>  # 在题库副本上操作（副本需含 quiz_categorized.json）
    python scripts/admin_server.py --read-only     # 禁用全部写 API

安全（仅监听 127.0.0.1 之外的强制约束）:
    - 静态文件 allowlist：只允许 admin.html、题库 JSON/JS 与 data/curate、scripts/_drafts
      下的 .json；路径先 unquote 再 realpath 规范化，路径折叠 / 编码绕行一律 403/404；
      /config/（含 verify_config.json 的 API Key）永不可达，GET 与 HEAD 同样受限；
    - 写接口需要会话令牌（GET /api/session 仅对本机回环请求发放），
      并校验 Host / Origin；请求体 ≤ 1MB；JSON 字段与类型严格校验；
    - 答案修正统一走 curate_core.check_fix_entry 守卫；显式修正不经过守卫的入口不存在，
      人工纠正必须走 /api/ops/manual_fix 并提供明确理由，台账记录为「人工覆盖」。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import secrets
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import curate_core as cc  # noqa: E402
import quiz_curate as qc  # noqa: E402

BANK_COPY_MODE = False  # --bank 副本模式：跳过 min.js 重压缩（compress 固定读正式路径）
READ_ONLY = False
SESSION_TOKEN = ""
MAX_BODY = 1_000_000
ACTIONS_PATH = ROOT / "data" / "curate" / "answer_actions.json"  # 测试可指向副本

QID_RE = re.compile(r"^\d{1,2}-\d{4,6}b?$")

# 静态文件 allowlist（相对 ROOT 的目录 + 单文件）
ALLOW_DIRS = (
    ROOT / "data" / "curate",
    ROOT / "scripts" / "_drafts",
)
ALLOW_FILES = {
    ROOT / "admin.html",
    ROOT / "data" / "quiz_categorized.json",
    ROOT / "data" / "quiz_categorized.js",
}


# ---------------- 输入校验 ----------------

def v_qids(payload: dict, key="qids") -> list:
    qids = payload.get(key)
    if not isinstance(qids, list) or not qids or len(qids) > 500:
        raise ValueError(f"{key} 必须是非空字符串列表（≤500）")
    if not all(isinstance(q, str) and QID_RE.match(q) for q in qids):
        raise ValueError(f"{key} 含非法题号格式")
    return qids


def v_reason(payload: dict, key="reason", min_len=0, max_len=300) -> str:
    r = payload.get(key, "")
    if not isinstance(r, str) or len(r) > max_len or len(r.strip()) < min_len:
        raise ValueError(f"{key} 必须为字符串（长度 {min_len}~{max_len}）")
    return r.strip()


def v_apply(payload: dict) -> bool:
    a = payload.get("apply", False)
    if not isinstance(a, bool):
        raise ValueError("apply 必须为布尔值")
    return a


def v_batch(payload: dict) -> str:
    b = payload.get("batch", "")
    if not isinstance(b, str) or not re.match(r"^[\w\-]{6,80}$", b):
        raise ValueError("batch 格式非法")
    return b


def v_move_items(payload: dict) -> list:
    items = payload.get("items")
    if not isinstance(items, list) or not items or len(items) > 500:
        raise ValueError("items 必须是非空列表（≤500）")
    out = []
    for it in items:
        if not isinstance(it, dict):
            raise ValueError("items 元素必须为对象")
        qid = it.get("qid")
        to = it.get("to")
        if not isinstance(qid, str) or not QID_RE.match(qid):
            raise ValueError(f"非法 qid: {qid}")
        if not isinstance(to, int) or to not in range(1, 13):
            raise ValueError(f"非法目标章: {to}")
        out.append({"qid": qid, "to": to, "reason": v_reason(it, "reason", max_len=300)})
    return out


def v_manual_fixes(payload: dict) -> list:
    """人工覆盖入口的显式修正条目（每条都必须有明确理由）。"""
    fixes = payload.get("fixes")
    if not isinstance(fixes, list) or not fixes or len(fixes) > 200:
        raise ValueError("fixes 必须是非空列表（≤200）")
    out = []
    for f in fixes:
        if not isinstance(f, dict):
            raise ValueError("fixes 元素必须为对象")
        qid = f.get("qid")
        if not isinstance(qid, str) or not QID_RE.match(qid):
            raise ValueError(f"非法 qid: {qid}")
        final = f.get("final")
        if not isinstance(final, list) or not all(isinstance(a, str) for a in final) or not final:
            raise ValueError(f"{qid}: final 必须为字母数组")
        analysis = f.get("analysis")
        if analysis is not None and not isinstance(analysis, str):
            raise ValueError(f"{qid}: analysis 必须为字符串")
        out.append({"qid": qid, "final": final, "analysis": analysis})
    return out


# ---------------- 操作实现（全部经 OPS_LOCK 互斥） ----------------

def _with_lock(fn):
    def wrapper(payload: dict) -> dict:
        with cc.OPS_LOCK:
            return fn(payload)
    return wrapper


def finish(bank, kind, result, apply: bool, batch_id, source: str) -> dict:
    out = {"applied": result["applied"], "skipped": result["skipped"]}
    if apply and result["applied"]:
        cc.write_bank(bank)
        try:
            out["batch_id"] = cc.append_batch(kind, source, result["ledger_items"],
                                              batch_id=batch_id)
        except Exception as e:
            # 写库成功但台账失败：备份已生成（write_bank 内），明确报告而不是静默
            out["ledger_error"] = (f"台账写入失败（{e}），题库变更已生效并已自动备份到 "
                                   f"{cc.BACKUP_DIR}；请手工补记批次 {batch_id}")
        rebuild()
    return out


@_with_lock
def op_remove(payload: dict) -> dict:
    bank = cc.load_bank()
    bid = cc.new_batch_id("soft_delete") if payload["apply"] else None
    entries = [{"qid": q, "reason": payload["reason"]} for q in payload["qids"]]
    result = cc.soft_delete(bank, entries, source="admin_server remove", batch_id=bid)
    return finish(bank, "soft_delete", result, payload["apply"], bid, "admin_server remove")


@_with_lock
def op_restore(payload: dict) -> dict:
    bank = cc.load_bank()
    bid = cc.new_batch_id("restore") if payload["apply"] else None
    result = cc.restore(bank, payload["qids"], source="admin_server restore", batch_id=bid)
    return finish(bank, "restore", result, payload["apply"], bid, "admin_server restore")


@_with_lock
def op_move(payload: dict) -> dict:
    bank = cc.load_bank()
    bid = cc.new_batch_id("move") if payload["apply"] else None
    result = cc.move_questions(bank, payload["items"], qc.CHAPTERS)
    out = {"applied": len(result["ledger_items"]), "skipped": result["skipped"],
           "plan": result["plan"]}
    if payload["apply"] and out["applied"]:
        cc.write_bank(bank)
        try:
            out["batch_id"] = cc.append_batch("move", "admin_server move",
                                              result["ledger_items"], batch_id=bid)
        except Exception as e:
            out["ledger_error"] = f"台账写入失败（{e}），请手工补记批次 {bid}"
        rebuild()
    return out


def _build_actions_fixes(bank, qids: list) -> tuple[list, list]:
    """从 answer_actions.json 取修正方案，逐条过统一守卫。返回 (通过, 拒绝)。"""
    index = cc.build_index(bank)
    actions_path = ACTIONS_PATH
    fixes_all = {}
    if actions_path.exists():
        for it in json.loads(actions_path.read_text(encoding="utf-8")).get("fix", []):
            fixes_all[it["qid"]] = it
    ok_list, rejected = [], []
    for qid in qids:
        if qid not in index:
            rejected.append({"qid": qid, "why": "题号不存在"})
            continue
        _, q = index[qid]
        src = fixes_all.get(qid)
        if not src:
            rejected.append({"qid": qid, "why": "answer_actions.json 中无该题修正方案"})
            continue
        entry = {"qid": qid, "final": src.get("final"), "analysis": src.get("analysis"),
                 "fingerprint": src.get("fingerprint"),
                 "external_evidence": (src.get("evidence") or {}).get("external_evidence")}
        ok, why, info = cc.check_fix_entry(entry, q, allow_manual=False)
        if not ok:
            rejected.append({"qid": qid, "why": why})
            continue
        entry["reason"] = why
        entry["evidence"] = {"tally": (src.get("evidence") or {}).get("vote_tally"),
                             "external_evidence": entry["external_evidence"]}
        ok_list.append(entry)
    return ok_list, rejected


@_with_lock
def op_answer_fix(payload: dict) -> dict:
    """答案修正（验证链入口）：只接受 answer_actions.json 中通过统一守卫的方案。"""
    bank = cc.load_bank()
    bid = cc.new_batch_id("answer_fix") if payload["apply"] else None
    fixes, rejected = _build_actions_fixes(bank, payload["qids"])
    result = cc.apply_answer_fix(bank, fixes, source="admin_server answer_fix", batch_id=bid)
    out = finish(bank, "answer_fix", result, payload["apply"], bid, "admin_server answer_fix")
    out["skipped"] = rejected + out["skipped"]
    return out


@_with_lock
def op_manual_fix(payload: dict) -> dict:
    """人工覆盖入口（单独定义）：显式修正必须提供明确理由，台账记录为「人工覆盖」，
    answer_history 中不伪装成验证通过。"""
    bank = cc.load_bank()
    index = cc.build_index(bank)
    bid = cc.new_batch_id("manual_fix") if payload["apply"] else None
    reason = payload["reason"]
    fixes, rejected = [], []
    for f in payload["fixes"]:
        qid = f["qid"]
        if qid not in index:
            rejected.append({"qid": qid, "why": "题号不存在"})
            continue
        _, q = index[qid]
        entry = {"qid": qid, "final": f["final"], "analysis": f.get("analysis"),
                 "manual_reason": reason}
        ok, why, info = cc.check_fix_entry(entry, q, allow_manual=True)
        if not ok:
            rejected.append({"qid": qid, "why": why})
            continue
        entry["reason"] = f"人工覆盖: {reason}"
        entry["evidence"] = {"manual": True, "manual_reason": reason}
        fixes.append(entry)
    result = cc.apply_answer_fix(bank, fixes, source="admin_server manual_fix（人工覆盖）",
                                 batch_id=bid)
    out = finish(bank, "answer_fix", result, payload["apply"], bid,
                 f"admin_server manual_fix（人工覆盖: {reason[:80]}）")
    out["skipped"] = rejected + out["skipped"]
    out["manual_count"] = result["applied"]
    return out


@_with_lock
def op_rollback(payload: dict) -> dict:
    batch = payload["batch"]
    done, notes = cc.rollback_batch(batch, dry_run=not payload["apply"])
    out = {"applied": done, "notes": notes, "conflicts": sum(1 for n in notes if "冲突" in n)}
    if payload["apply"] and done:
        rebuild()
    return out


OPS = {
    "remove": (op_remove, lambda p: {"qids": v_qids(p), "reason": v_reason(p, min_len=0),
                                     "apply": v_apply(p)}),
    "restore": (op_restore, lambda p: {"qids": v_qids(p), "apply": v_apply(p)}),
    "move": (op_move, lambda p: {"items": v_move_items(p), "apply": v_apply(p)}),
    "answer_fix": (op_answer_fix, lambda p: {"qids": v_qids(p), "apply": v_apply(p)}),
    "manual_fix": (op_manual_fix,
                   lambda p: {"fixes": v_manual_fixes(p), "reason": v_reason(p, "reason", min_len=5),
                              "apply": v_apply(p)}),
    "rollback": (op_rollback, lambda p: {"batch": v_batch(p), "apply": v_apply(p)}),
}


def rebuild():
    if BANK_COPY_MODE:
        return  # 副本模式不重建正式 min.js
    qc.rebuild_min_js()


def status_payload() -> dict:
    bank = cc.load_bank()
    all_q = [q for arr in bank["questions_by_chapter"].values() for q in arr]
    ledger = cc.load_ledger()
    return {
        "total": len(all_q),
        "active": sum(1 for q in all_q if not q.get("deleted")),
        "deleted": sum(1 for q in all_q if q.get("deleted")),
        "answer_history": sum(1 for q in all_q if q.get("answer_history")),
        "batches": ledger["batches"][-50:][::-1],
        "bank_copy_mode": BANK_COPY_MODE,
    }


# ---------------- HTTP ----------------

def _host_ok(self) -> bool:
    host = (self.headers.get("Host") or "").lower()
    return host in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")


def _origin_ok(self) -> bool:
    origin = self.headers.get("Origin")
    if not origin:  # 同源表单/无 Origin 的客户端
        return True
    return origin.lower().rstrip("/") in (
        f"http://127.0.0.1:{self.server.server_port}",
        f"http://localhost:{self.server.server_port}")


def _static_allowed(self) -> bool:
    """静态文件 allowlist：unquote + realpath 规范化后必须落在允许集合内。"""
    from urllib.parse import unquote
    path = unquote(urlparse(self.path).path)
    full = os.path.realpath(os.path.join(str(ROOT), path.lstrip("/")))
    fullp = pathlib.Path(full)
    if fullp in ALLOW_FILES:
        return fullp.exists()
    if any(fullp.parent == d or str(fullp).startswith(str(d) + os.sep)
           for d in ALLOW_DIRS):
        return fullp.suffix == ".json" and fullp.exists()
    return False


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):  # 安静模式
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_static(self):
        if not _static_allowed(self):
            return self._json({"error": "not found or forbidden（静态文件走 allowlist）"}, 403)
        return super().do_GET()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            return self._json(status_payload())
        if path == "/api/session":
            # 会话令牌只发给本机回环且 Host 正确的请求
            if not self.client_address[0] == "127.0.0.1" or not _host_ok(self):
                return self._json({"error": "forbidden"}, 403)
            return self._json({"token": SESSION_TOKEN})
        return self._serve_static()

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self._json({}, 200 if path == "/api/status" else 404)
        if not _static_allowed(self):
            return self._json({"error": "forbidden"}, 403)
        return super().do_HEAD()

    def do_POST(self):
        path = urlparse(self.path).path
        if READ_ONLY:
            return self._json({"error": "服务以 --read-only 启动，写操作已禁用"}, 403)
        if not path.startswith("/api/ops/"):
            return self._json({"error": "unknown endpoint"}, 404)
        op = path.rsplit("/", 1)[-1]
        if op not in OPS:
            return self._json({"error": f"unknown op: {op}"}, 404)
        # 会话令牌 + Host + Origin
        if not _host_ok(self) or not _origin_ok(self):
            return self._json({"error": "来源校验失败（Host/Origin）"}, 403)
        if self.headers.get("X-Session-Token") != SESSION_TOKEN:
            return self._json({"error": "缺少或错误的会话令牌"}, 401)
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return self._json({"error": "Content-Length 非法"}, 400)
        if length > MAX_BODY:
            return self._json({"error": "请求体过大"}, 413)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except Exception:
            return self._json({"error": "JSON 解析失败"}, 400)
        if not isinstance(payload, dict):
            return self._json({"error": "请求体必须是 JSON 对象"}, 400)
        try:
            validated = OPS[op][1](payload)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        try:
            return self._json(OPS[op][0](validated))
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 500)


def main() -> int:
    global BANK_COPY_MODE, READ_ONLY, SESSION_TOKEN
    ap = argparse.ArgumentParser(description="题库治理本机管理服务")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--bank", default="", help="题库副本目录（含 quiz_categorized.json），在该副本上操作")
    ap.add_argument("--read-only", action="store_true", help="只读模式（禁用写 API）")
    args = ap.parse_args()
    READ_ONLY = args.read_only
    SESSION_TOKEN = secrets.token_urlsafe(24)  # 不打印、不落盘，页面经 /api/session 获取

    if args.bank:
        src = pathlib.Path(args.bank)
        if not src.is_absolute():
            src = ROOT / src
        if not (src / "quiz_categorized.json").exists():
            print(f"[错误] 副本目录缺少 quiz_categorized.json: {src}")
            return 1
        cc.JSON_PATH = src / "quiz_categorized.json"
        cc.JS_PATH = src / "quiz_categorized.js"
        cc.LEDGER_PATH = src / "curate" / "ledger.json"
        cc.BACKUP_DIR = src / "backup"
        BANK_COPY_MODE = True
        print(f"[副本模式] 所有读写指向 {src}，正式题库不受影响")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"题库治理台已启动: http://127.0.0.1:{args.port}/admin.html （Ctrl+C 停止）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
