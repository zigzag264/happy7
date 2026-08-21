# -*- coding: utf-8 -*-
"""
Push 触发邮件通知脚本
在 GitHub Actions 中由 push 事件触发，发送更新摘要到邮箱。
与 email_content_builder.py 共用相同的 HTML 格式。
"""

import sys
import subprocess
from datetime import datetime, timezone, timedelta

from email_content_builder import build_html_digest, load_data, validate_data
from email_smtp_utils import load_config, validate_config, send_email

# ==================== 数据获取 ====================

def get_git_info():
    author, msg, files, stat = "unknown", "no commit info", [], ""
    try:
        author = subprocess.run(["git", "log", "-1", "--format=%an"], capture_output=True, text=True, check=True).stdout.strip()
        msg = subprocess.run(["git", "log", "-1", "--format=%s"], capture_output=True, text=True, check=True).stdout.strip()
        files = subprocess.run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], capture_output=True, text=True, check=True).stdout.strip().split("\n")
        stat = subprocess.run(["git", "diff", "--stat", "HEAD~1", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        pass
    return author, msg, [f for f in files if f], stat


# ==================== HTML 构建 ====================

def build_html():
    author, commit_msg, files, stat = get_git_info()
    BJ_TIME = datetime.now(timezone(timedelta(hours=8)))
    now = BJ_TIME.strftime("%Y-%m-%d %H:%M")

    # 使用统一的数据加载（与每日定时推送一致）
    data = load_data()
    errors, warnings = validate_data(data)

    # 硬校验失败（含"预测非下一期未开奖"）→ 阻断发送，与每日汇总保持一致
    if errors:
        print("\n❌ 数据校验失败，跳过 push 通知发送：")
        for e in errors:
            print(f"  ❌ {e}")
        sys.exit(1)

    commit_info = {
        "author": author,
        "message": commit_msg,
        "files": [f for f in files if f],
    }

    return build_html_digest(data, warnings, generated_at=now, commit_info=commit_info)


# ==================== 发送 ====================

def send():
    cfg = load_config()
    validate_config(cfg, allow_dry_run=True)

    if cfg["dry_run"]:
        print("ℹ️  Dry-run 模式：邮件将打印到控制台，不会实际发送\n")

    html = build_html()
    BJ_TIME = datetime.now(timezone(timedelta(hours=8)))
    subject = f"[大乐透] 项目更新 · {BJ_TIME.strftime('%m-%d %H:%M')}"

    try:
        send_email(subject, html, cfg, success_msg="✅ 推送通知邮件发送成功")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    send()