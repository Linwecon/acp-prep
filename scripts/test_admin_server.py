# -*- coding: utf-8 -*-
"""管理服务 HTTP 端到端测试（副本模式）：起真实服务、走 HTTP API 验证操作与安全防护。

覆盖：
- 正常操作链（remove/restore/move/answer_fix/rollback，需会话令牌）；
- 静态文件 allowlist：/config/ 不可达（GET 与 HEAD）、路径折叠与编码绕行被拒；
- 写接口守卫：缺令牌 401、来源非法 403、请求体过大 413、非法 JSON 400；
- 显式 fixes 走 answer_fix 入口被校验器拒绝（400）；
- 正式题库 data/quiz_categorized.json 全程零字节变化。

运行: python scripts/test_admin_server.py -v
测试不输出任何令牌或密钥内容。
"""
import hashlib
import http.client as http_client
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 18765


def http(method: str, path: str, payload=None, port: int = PORT, token: str = "",
         origin: str = "", host: str = "", raw_body: bytes | None = None):
    url = f"http://127.0.0.1:{port}{path}"
    if raw_body is not None:
        data = raw_body
    else:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Session-Token"] = token
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    if host:  # 覆盖 Host 头
        req.host = host
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode("utf-8")
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, body
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def raw_request(method: str, path: str, headers: dict, port: int = PORT) -> tuple:
    """发送原始请求（用于精确控制 Host 头）。"""
    conn = http_client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, headers=headers)
    r = conn.getresponse()
    body = r.read().decode("utf-8")
    conn.close()
    return r.status, body


class AdminServerHTTPTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bank_dir = pathlib.Path(cls.tmp.name)
        shutil.copy(ROOT / "data" / "quiz_categorized.json",
                    cls.bank_dir / "quiz_categorized.json")
        cls.real_hash = hashlib.sha256(
            (ROOT / "data" / "quiz_categorized.json").read_bytes()).hexdigest()
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "admin_server.py"),
             "--bank", str(cls.bank_dir), "--port", str(PORT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            try:
                code, _ = http("GET", "/api/status")
                if code == 200:
                    break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError("admin_server 未能启动")
        # 获取会话令牌（不打印内容）
        code, s = http("GET", "/api/session")
        assert code == 200 and s.get("token"), "会话令牌获取失败"
        cls.token = s["token"]
        bank = json.loads((cls.bank_dir / "quiz_categorized.json").read_text(encoding="utf-8"))
        cls.initial_deleted = sum(bool(q.get("deleted")) for arr in bank["questions_by_chapter"].values() for q in arr)
        active = [q for q in bank["questions_by_chapter"]["11"] if not q.get("deleted")]
        cls.qid_ch11_1 = "11-" + str(active[0]["seq"]).zfill(4)
        cls.qid_ch11_2 = "11-" + str(active[1]["seq"]).zfill(4)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)
        cls.tmp.cleanup()

    # ---------- 基础 ----------

    def test_01_status_copy_mode(self):
        code, s = http("GET", "/api/status")
        self.assertEqual(code, 200)
        self.assertTrue(s["bank_copy_mode"])

    # ---------- 静态文件 allowlist ----------

    def test_02_config_blocked_get_and_head(self):
        code, _ = http("GET", "/config/verify_config.json")
        self.assertEqual(code, 403)
        code, _ = http("HEAD", "/config/verify_config.json")
        self.assertEqual(code, 403)

    def test_03_config_blocked_encoded_and_traversal(self):
        # 百分号编码路径
        code, _ = http("GET", "/%63onfig/verify_config.json")
        self.assertEqual(code, 403)
        # 路径折叠
        code, _ = http("GET", "/data/../config/verify_config.json")
        self.assertEqual(code, 403)
        code, _ = http("GET", "/data/%2e%2e/config/verify_config.json")
        self.assertEqual(code, 403)
        # HEAD 同样受限
        code, _ = http("HEAD", "/data/../config/verify_config.json")
        self.assertEqual(code, 403)

    def test_04_allowlist_allows_report_json(self):
        code, _ = http("GET", "/data/curate/gap_plan.json")
        self.assertEqual(code, 200)
        code, _ = http("GET", "/admin.html")
        self.assertEqual(code, 200)
        # 不在 allowlist 里的敏感/任意文件 → 403
        code, _ = http("GET", "/scripts/admin_server.py")
        self.assertEqual(code, 403)
        code, _ = http("GET", "/config/supabase.js")
        self.assertEqual(code, 403)

    # ---------- 写接口守卫 ----------

    def test_05_write_requires_token(self):
        code, _ = http("POST", "/api/ops/remove",
                       {"qids": [self.qid_ch11_1], "reason": "x", "apply": False})
        self.assertEqual(code, 401)  # 缺少令牌

    def test_06_write_requires_valid_origin(self):
        code, _ = http("POST", "/api/ops/remove",
                       {"qids": [self.qid_ch11_1], "reason": "x", "apply": False},
                       token=self.token, origin="http://evil.example.com")
        self.assertEqual(code, 403)

    def test_07_write_requires_valid_host(self):
        code, body = raw_request(
            "POST", "/api/ops/remove",
            {"Host": "evil.example.com", "Content-Type": "application/json",
             "X-Session-Token": self.token, "Content-Length": "2"},
            port=PORT)
        self.assertEqual(code, 403)
        self.assertIn("来源", str(body))

    def test_08_oversized_body_rejected(self):
        big = b'{"qids": "' + b"a" * (2_000_000) + b'"}'
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/ops/remove", data=big, method="POST",
            headers={"Content-Type": "application/json", "X-Session-Token": self.token})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        self.assertEqual(code, 413)

    def test_09_invalid_json_and_fields(self):
        code, _ = http("POST", "/api/ops/remove", raw_body=b"not-json{", token=self.token)
        self.assertEqual(code, 400)
        code, _ = http("POST", "/api/ops/remove",
                       {"qids": "11-0001", "reason": "x", "apply": False}, token=self.token)
        self.assertEqual(code, 400)  # qids 必须是列表
        code, _ = http("POST", "/api/ops/move",
                       {"items": [{"qid": self.qid_ch11_2, "to": 99}], "apply": False},
                       token=self.token)
        self.assertEqual(code, 400)  # 目标章非法

    def test_10_explicit_fixes_rejected_on_answer_fix(self):
        """显式 fixes 走 answer_fix 入口 → 校验器 400（人工纠正必须走 manual_fix）。"""
        code, body = http("POST", "/api/ops/answer_fix",
                          {"fixes": [{"qid": self.qid_ch11_1, "final": ["A"]}], "apply": False},
                          token=self.token)
        self.assertEqual(code, 400)

    # ---------- 正常操作链（令牌齐备） ----------

    def test_11_remove_dryrun_and_apply(self):
        code, r = http("POST", "/api/ops/remove",
                       {"qids": [self.qid_ch11_1], "reason": "e2e", "apply": False},
                       token=self.token)
        self.assertEqual(r["applied"], 1)
        code, r = http("POST", "/api/ops/remove",
                       {"qids": [self.qid_ch11_1], "reason": "e2e", "apply": True},
                       token=self.token)
        self.assertEqual(r["applied"], 1)
        code, s = http("GET", "/api/status")
        self.assertEqual(s["deleted"], self.initial_deleted + 1)

    def test_12_restore(self):
        code, r = http("POST", "/api/ops/restore",
                       {"qids": [self.qid_ch11_1], "apply": True}, token=self.token)
        self.assertEqual(r["applied"], 1)
        code, s = http("GET", "/api/status")
        self.assertEqual(s["deleted"], self.initial_deleted)

    def test_13_move_and_answer_fix_chain(self):
        code, r = http("POST", "/api/ops/move",
                       {"items": [{"qid": self.qid_ch11_2, "to": 1, "reason": "e2e"}],
                        "apply": True}, token=self.token)
        self.assertEqual(r["applied"], 1)
        # answer_fix：该题无验证方案 → 守卫拒绝（不抛异常）
        code, r = http("POST", "/api/ops/answer_fix",
                       {"qids": [self.qid_ch11_2], "apply": True}, token=self.token)
        self.assertEqual(code, 200)
        self.assertEqual(r["applied"], 0)

    def test_14_manual_fix_requires_reason(self):
        code, _ = http("POST", "/api/ops/manual_fix",
                       {"fixes": [{"qid": self.qid_ch11_1, "final": ["A", "B"]}],
                        "reason": "x", "apply": False}, token=self.token)
        self.assertEqual(code, 400)  # 理由不明确

    # ---------- 正式题库零改动 ----------

    def test_20_real_bank_untouched(self):
        h = hashlib.sha256(
            (ROOT / "data" / "quiz_categorized.json").read_bytes()).hexdigest()
        self.assertEqual(h, self.real_hash)


if __name__ == "__main__":
    unittest.main(verbosity=2)
