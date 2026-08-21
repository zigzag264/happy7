#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大乐透 AI 预测 · 本地服务器
- 静态文件服务（等价 python -m http.server）
- POST /api/update  手动更新入口：
    1) 运行 fetch_history/fetch_lottery_history.py  抓取最新开奖数据
    2) 运行 strategies.runner                       重新生成下一期模型预测

用法: python server.py [port]   （默认 8000）
"""

import json
import os
import subprocess
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FETCH_SCRIPT = os.path.join(BASE_DIR, "fetch_history", "fetch_lottery_history.py")
UPDATE_LOCK = threading.Lock()


def run_step(args, timeout):
    """运行子进程，返回 (ok, output)。强制 utf-8 规避 Windows 管道编码问题。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=BASE_DIR,
            env=env,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "执行超时（{}s）".format(timeout)
    except Exception as e:
        return False, str(e)


def refresh_data():
    """抓取开奖数据 + 重新生成预测，返回结果摘要。"""
    steps = []
    ok1, out1 = run_step([sys.executable, FETCH_SCRIPT], timeout=180)
    steps.append({"name": "更新开奖数据", "ok": ok1, "output": out1})

    ok2, out2 = run_step([sys.executable, "-m", "strategies.runner"], timeout=600)
    steps.append({"name": "生成模型预测", "ok": ok2, "output": out2})

    summary = {}
    try:
        hist = json.load(open(os.path.join(BASE_DIR, "data", "lottery_history.json"), encoding="utf-8"))
        data = hist.get("data") or []
        summary["history_count"] = len(data)
        summary["latest_period"] = data[0]["period"] if data else None
        summary["latest_date"] = data[0]["date"] if data else None
        nd = hist.get("next_draw") or {}
        summary["next_period"] = nd.get("next_period")
        summary["next_date"] = nd.get("next_date")
    except Exception as e:
        summary["history_error"] = str(e)

    try:
        pred = json.load(open(os.path.join(BASE_DIR, "data", "ai_predictions.json"), encoding="utf-8"))
        summary["prediction_date"] = pred.get("prediction_date")
        summary["target_period"] = pred.get("target_period")
        summary["model_count"] = len(pred.get("models") or [])
    except Exception as e:
        summary["prediction_error"] = str(e)

    return {
        "ok": ok1 and ok2,
        "steps": steps,
        "summary": summary,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


class Handler(SimpleHTTPRequestHandler):
    """静态文件 + /api/update 接口"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_POST(self):
        if self.path.rstrip("/") == "/api/update":
            if not UPDATE_LOCK.acquire(blocking=False):
                self._send_json({"ok": False, "error": "已有更新任务进行中，请稍候再试"}, 429)
                return
            try:
                self._send_json(refresh_data(), 200)
            finally:
                UPDATE_LOCK.release()
        else:
            self.send_error(404, "Not Found")

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("", port), Handler)
    print("=" * 50)
    print("大乐透 AI 预测 · 本地服务器")
    print("=" * 50)
    print("📡 服务器地址: http://localhost:{}".format(port))
    print("🔄 手动更新接口: POST /api/update")
    print("💡 提示: 按 Ctrl+C 停止服务器")
    print("=" * 50)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()