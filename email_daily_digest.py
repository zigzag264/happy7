# -*- coding: utf-8 -*-
"""
大乐透每日邮件汇总 — 主入口

流程：读取环境变量配置 → 加载数据 → 校验 → 组装内容 → 发送邮件

凭证通过环境变量注入，绝不硬编码。支持 dry-run 模式。
"""

import sys
from datetime import datetime, timezone, timedelta

from email_content_builder import build_html_digest, load_data, validate_data
from email_smtp_utils import load_config, validate_config, send_email

# ==================== 主流程 ====================

def main():
    print("=" * 50)
    print("📧 大乐透每日邮件汇总")
    print("=" * 50)

    # 1. 加载 SMTP 配置
    cfg = load_config()
    validate_config(cfg)

    if cfg["dry_run"]:
        print("ℹ️  Dry-run 模式：邮件将打印到控制台，不会实际发送\n")

    # 2. 加载数据
    print("\n📊 加载数据...")
    data = load_data()

    # 3. 校验
    print("\n🔍 校验数据完整性...")
    errors, warnings = validate_data(data)
    for e in errors:
        print(f"  ❌ {e}")
    for w in warnings:
        print(f"  ⚠️ {w}")

    if errors:
        print("\n❌ 关键字段缺失，跳过本次发送")
        sys.exit(1)

    # 4. 组装内容
    print("\n📝 组装邮件内容...")
    BJ_TIME = datetime.now(timezone(timedelta(hours=8)))
    now = BJ_TIME.strftime("%Y-%m-%d %H:%M")
    body = build_html_digest(data, warnings, generated_at=now)
    today = BJ_TIME.strftime("%Y-%m-%d")
    subject = f"[大乐透] 每日汇总 · {today}"
    print("  ✓ 内容组装完成")

    # 5. 发送
    print("\n📤 发送邮件...")
    send_email(subject, body, cfg)

    print("\n" + "=" * 50)
    print("🎉 邮件汇总完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()