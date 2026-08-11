# -*- coding: utf-8 -*-
"""
SMTP 邮件发送工具模块 — 供 email_daily_digest.py 和 email_push_notify.py 共用。

消除了两个邮件脚本重复的 SMTP 配置、凭证校验和发送逻辑。
凭证全部通过环境变量注入，绝不硬编码。
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def load_config():
    """读取 SMTP 配置（全部来自环境变量），返回配置字典"""
    return {
        "server": os.environ.get("SMTP_SERVER", "smtp.qq.com"),
        "port": int(os.environ.get("SMTP_PORT", "465")),
        "user": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "recipient": os.environ.get("EMAIL_RECIPIENT"),
        "dry_run": os.environ.get("EMAIL_DRY_RUN", "").lower() == "true",
    }


def validate_config(cfg, allow_dry_run=True):
    """校验凭证是否完整。缺凭证时 dry-run 可仅警告，否则退出。"""
    missing = [k for k in ("user", "password", "recipient") if not cfg[k]]
    if missing:
        if cfg["dry_run"] and allow_dry_run:
            print("ℹ️  Dry-run 模式：缺少邮件凭证，仅打印邮件内容\n")
            return False
        print("❌ 缺少邮件凭证，请设置以下环境变量：")
        for k in missing:
            label = {"user": "SMTP_USER（邮箱地址）",
                     "password": "SMTP_PASSWORD（邮箱授权码，非登录密码）",
                     "recipient": "EMAIL_RECIPIENT（收件人邮箱）"}[k]
            print(f"   {label}")
        sys.exit(1)
    return True


def build_message(subject, body, cfg):
    """构建 MIME HTML 邮件"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = cfg["recipient"]
    msg.attach(MIMEText(body, "html", "utf-8"))
    return msg


def send_email(subject, body, cfg, success_msg="✅ 邮件发送成功"):
    """发送或打印邮件。dry_run 时仅打印不发送。"""
    if cfg["dry_run"]:
        print("=" * 60)
        print(f"[DRY-RUN] 收件人: {cfg['recipient']}")
        print(f"[DRY-RUN] 主题: {subject}")
        print("=" * 60)
        print(body)
        print("=" * 60)
        print("ℹ️  Dry-run 模式，邮件未实际发送")
        return

    msg = build_message(subject, body, cfg)
    try:
        with smtplib.SMTP_SSL(cfg["server"], cfg["port"], timeout=15) as server:
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["user"], [cfg["recipient"]], msg.as_string())
        print(success_msg)
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP 认证失败: {e}")
        print("   请检查：")
        print("   1. QQ 邮箱是否已开启 SMTP 服务")
        print("   2. SMTP_PASSWORD 是否为授权码（而非登录密码）")
        raise
    except smtplib.SMTPException as e:
        print(f"❌ SMTP 错误: {e}")
        raise