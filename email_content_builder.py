# -*- coding: utf-8 -*-
"""
邮件内容组装模块 — HTML 统一格式
供 email_daily_digest.py 和 email_push_notify.py 共用。

纯函数，无网络 IO：
  1. load_data()        — 读取 3 个 JSON 数据文件
  2. validate_data()    — 校验数据完整性，返回 (errors, warnings)
  3. build_html_digest() — 渲染 HTML 邮件正文（每日汇总）
"""

import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from strategies.selection import rank_strategies

HISTORY_FILE     = os.path.join(BASE_DIR, "data", "lottery_history.json")
PREDICTIONS_FILE = os.path.join(BASE_DIR, "data", "ai_predictions.json")
HIT_HISTORY_FILE = os.path.join(BASE_DIR, "data", "predictions_history.json")


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data():
    """加载全部 3 个数据源，各自独立异常隔离。"""
    result = {"lottery_history": None, "ai_predictions": None, "hit_history": None}
    try:
        result["lottery_history"] = _load(HISTORY_FILE)
        print(f"  ✓ 大乐透历史加载成功 ({len(result['lottery_history'].get('data', []))} 期)")
    except Exception as e:
        print(f"  ✗ 大乐透历史加载失败: {e}")
    try:
        result["ai_predictions"] = _load(PREDICTIONS_FILE)
        print(f"  ✓ 大乐透AI预测加载成功 ({len(result['ai_predictions'].get('models', []))} 个模型)")
    except Exception as e:
        print(f"  ✗ 大乐透AI预测加载失败: {e}")
    try:
        result["hit_history"] = _load(HIT_HISTORY_FILE)
        recs = result["hit_history"].get("predictions_history", []) if result["hit_history"] else []
        print(f"  ✓ 大乐透命中历史加载成功 ({len(recs)} 期记录)")
    except Exception as e:
        print(f"  ✗ 大乐透命中历史加载失败: {e}")
    return result


def validate_data(data):
    """校验数据完整性。返回 (errors, warnings)

    errors 阻断推送（由调用方决定退出），warnings 仅提示。
    其中"预测目标期必须是下一期未开奖"为硬校验：
      已开奖 / 期号异常 / 与系统计算的下一期不一致 → errors，拒绝推送。
    """
    errors, warnings = [], []
    lh = data.get("lottery_history")
    if lh is None:
        errors.append("开奖历史文件加载失败")
    elif not lh.get("data"):
        errors.append("开奖历史数据为空")
    pred = data.get("ai_predictions")
    if pred is None:
        warnings.append("AI 预测文件加载失败，预测栏将显示为空")
    elif not pred.get("models"):
        warnings.append("暂无可用 AI 预测数据")
    hist = data.get("hit_history")
    if hist is None:
        warnings.append("命中历史文件加载失败，命中栏将显示为空")
    elif not hist.get("predictions_history"):
        warnings.append("暂无命中历史记录")

    # ---- 硬校验：推送的预测必须是"下一期未开奖"的数据 ----
    if lh is not None and pred is not None:
        latest_list = lh.get("data") or []
        latest_period = str((latest_list[0].get("period", "") if latest_list else "") or "")
        next_period = str(((lh.get("next_draw") or {}).get("next_period", "")) or "")
        target = str(pred.get("target_period", "") or "")

        if not target:
            errors.append("AI 预测缺少目标期号（target_period），无法确认其为下一期未开奖，拒绝推送")
        elif not (target.isdigit() and latest_period.isdigit() and next_period.isdigit()):
            errors.append(
                f"期号格式异常，拒绝推送（预测目标期={target or '空'}, 最新开奖期={latest_period or '空'}, 系统下一期={next_period or '空'}）"
            )
        elif int(target) <= int(latest_period):
            errors.append(
                f"预测目标为第 {target} 期，该期已开奖（最新开奖第 {latest_period} 期），"
                f"推送的预测已过期，拒绝推送"
            )
        elif int(target) != int(next_period):
            # 未开奖但期号与系统计算的下一期不一致（数据不同步/竞态）
            errors.append(
                f"预测目标为第 {target} 期，与系统计算的下一期未开奖（第 {next_period} 期）不一致，拒绝推送"
            )
        # else: target == next_period，正是下一期未开奖 ✅
    return errors, warnings


# ==================== 共用 HTML 构建 ====================

_SECTION = '<h2 style="font-size:16px;color:#1e293b;border-left:4px solid #3b82f6;padding-left:12px;margin:24px 0 12px">{}</h2>'


def _ball(num, color):
    # 前区用红色，后区用蓝色（视觉区分）
    bg = "#ef4444" if color == "front" else "#3b82f6"
    return f'<span style="display:inline-block;width:28px;height:28px;line-height:28px;text-align:center;border-radius:50%;background:{bg};color:#fff;font-size:13px;font-weight:700;margin:0 2px">{num}</span>'


def _build_latest_draw_html(latest, nd):
    """最新开奖 + 下期预告 HTML（大乐透 5+2）"""
    if not latest:
        return '<p style="color:#94a3b8;font-size:13px">(暂无数据)</p>'
    fronts = "".join(_ball(b, "front") for b in latest.get("front_balls", []))
    backs = "".join(_ball(b, "back") for b in latest.get("back_balls", []))
    html = f'''
    <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:8px;overflow:hidden">
      <tr><td style="padding:12px 16px">
        <div style="font-size:14px;font-weight:700;color:#1e293b;margin-bottom:8px">
          第{latest.get("period","")}期 · {latest.get("date","")}
        </div>
        <div style="margin-bottom:6px">{fronts}</div>
        <div style="margin-top:4px">{backs}</div>
      </td></tr>
    </table>'''
    if nd:
        html += f'''
    <table style="width:100%;border-collapse:collapse;background:#eff6ff;border-radius:8px;overflow:hidden;margin-top:8px">
      <tr><td style="padding:10px 16px">
        <span style="font-size:13px;color:#64748b">下期预告</span>
        <span style="font-size:15px;font-weight:700;color:#1e293b;margin-left:8px">{nd.get("next_period","")}</span>
        <span style="font-size:13px;color:#475569;margin-left:8px">{nd.get("next_date_display","")} {nd.get("weekday","")} {nd.get("draw_time","21:25")}</span>
      </td></tr>
    </table>'''
    return html


def _build_predictions_html(pred, latest_period="", next_period=""):
    """AI 全部预测 HTML（含过期检测）"""
    if not pred or not pred.get("models"):
        return '<p style="color:#94a3b8;font-size:13px">(暂无预测数据)</p>'

    target = pred.get("target_period", "")
    # 检测预测是否已过期（目标期号 ≤ 最新开奖期号；isdigit 防越权路径 int() 崩溃）
    stale = (bool(target) and bool(latest_period)
             and str(target).isdigit() and str(latest_period).isdigit()
             and int(str(target)) <= int(str(latest_period)))
    if stale:
        warn = f'''
        <div style="background:#fef3c7;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:13px;color:#92400e">
          ⚠️ 当前 AI 预测目标为<b>第{target}期</b>，该期已开奖（最新开奖为第{latest_period}期），预测已过期。<br>
          下一期未开奖：<b>第{next_period}期</b>，待 AI 预测更新后将自动显示。
        </div>'''
    else:
        warn = ""

    cards = ""
    for m in pred["models"]:
        groups = ""
        for g in m.get("predictions", []):
            fronts = "".join(_ball(b, "front") for b in g.get("front_balls", []))
            backs = "".join(_ball(b, "back") for b in g.get("back_balls", []))
            desc = g.get("description", "")
            desc_html = f'<div style="font-size:11px;color:#94a3b8;margin-top:4px">{desc}</div>' if desc else ""
            groups += f'''
            <div style="padding:8px 12px;border-bottom:1px solid #f1f5f9">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <span style="font-size:11px;font-weight:700;color:#3b82f6;background:#eff6ff;padding:2px 8px;border-radius:4px">G{g["group_id"]}</span>
                <span style="font-size:13px;font-weight:600;color:#1e293b">{g["strategy"]}</span>
              </div>
              <div style="margin-top:6px;display:flex;align-items:center;flex-wrap:wrap;gap:2px">{fronts}<span style="color:#94a3b8;margin:0 4px">|</span>{backs}</div>
              {desc_html}
            </div>'''
        cards += f'''
        <div style="border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:12px">
          <div style="background:linear-gradient(135deg,#1e293b,#334155);padding:10px 14px">
            <span style="font-size:14px;font-weight:700;color:#fff">{m["model_name"]}</span>
          </div>
          {groups}
        </div>'''
    return f'''
    {warn}
    <div style="font-size:13px;color:#64748b;margin-bottom:12px">
      目标期号: {pred.get("target_period","")} · 预测日期: {pred.get("prediction_date","")} · 模型数: {len(pred["models"])}
    </div>
    {cards}'''


def _medal(index):
    return {0: "🥇", 1: "🥈", 2: "🥉"}.get(index, f"{index + 1}")


def _row_bg(index):
    return "#fefce8" if index == 0 else "#f8fafc" if index % 2 == 0 else "#ffffff"


def _collect_ranking_stats(records):
    """按 模型+策略 汇总命中，附带本期与单期最多前区数据"""
    latest_record = records[0]
    stats = {}
    for rec in records:
        is_latest = rec is latest_record
        for m in rec.get("models", []):
            model_name = m.get("model_name", "—")
            for pred in m.get("predictions", []):
                hr = pred.get("hit_result")
                if not hr:
                    continue
                key = f"{model_name}|{pred.get('strategy', '—')}"
                s = stats.get(key)
                if s is None:
                    s = stats[key] = {
                        "model": model_name,
                        "strategy": pred.get("strategy", "—"),
                        "total": 0, "best": 0, "games": 0,
                        "current": 0, "currentFront": 0, "backHit": 0,
                        "frontHits": "", "totalFront": 0, "totalBack": 0,
                        "maxFront": 0,
                    }
                total = hr.get("total_hits", 0)
                front = hr.get("front_hit_count", 0)
                back = hr.get("back_hit_count", 0)
                s["total"] += total
                s["games"] += 1
                s["totalFront"] += front
                s["totalBack"] += back
                s["maxFront"] = max(s["maxFront"], front)
                if total > s["best"]:
                    s["best"] = total
                if is_latest:
                    s["current"] = total
                    s["currentFront"] = front
                    s["backHit"] = back
                    front_hits = hr.get("front_hits", [])
                    s["frontHits"] = " ".join(front_hits) if front_hits else "—"
    return stats


def _build_ranking_html(hist, limit=8):
    """命中排行 HTML — 最新一期 + 历史累计（各 Top N）"""
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:13px;padding:12px">(暂无命中记录)</p>'

    stats = _collect_ranking_stats(records)
    cell = "padding:5px 6px;font-size:11px;"
    head = "padding:5px 6px;color:#64748b;font-size:10px;font-weight:600;"

    # === 最新一期：按 后区命中 → 本期命中数 排序 ===
    latest_arr = [s for s in stats.values() if s["current"] > 0]
    latest_arr.sort(key=lambda x: (x["backHit"], x["current"]), reverse=True)
    latest_top = latest_arr[:limit]

    rows1 = ""
    for i, r in enumerate(latest_top):
        bg = _row_bg(i)
        back_mark = f"{r['backHit']}后" if r["backHit"] > 0 else "—"
        rows1 += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}font-weight:600;color:#1e293b">{r["model"]}</td>
          <td style="{cell}color:#475569">{r["strategy"]}</td>
          <td style="{cell}text-align:center;font-weight:700;color:#ef4444">{r["current"]}球</td>
          <td style="{cell}color:#2563eb;font-family:monospace">{r["frontHits"]}</td>
          <td style="{cell}text-align:center;font-weight:700;color:#3b82f6">{back_mark}</td>
        </tr>'''
    table1 = f'''
    <div style="font-size:13px;font-weight:700;color:#1e293b;margin:12px 0 6px">🏆 最新一期 Top {limit}</div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:16px">
      <thead><tr style="background:#f1f5f9">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">模型</th>
        <th style="{head}text-align:left">策略</th>
        <th style="{head}text-align:center">本期命中</th>
        <th style="{head}text-align:left">命中前区</th>
        <th style="{head}text-align:center">后区</th>
      </tr></thead>
      <tbody>{rows1}</tbody>
    </table>'''

    # === 历史累计：按 总球数 → 累计后区 排序 ===
    hist_arr = sorted(stats.values(), key=lambda x: (x["total"], x["totalBack"]), reverse=True)
    hist_top = hist_arr[:limit]

    rows2 = ""
    for i, r in enumerate(hist_top):
        bg = _row_bg(i)
        rows2 += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}font-weight:600;color:#1e293b">{r["model"]}</td>
          <td style="{cell}color:#475569">{r["strategy"]}</td>
          <td style="{cell}text-align:center;color:#475569">{r["best"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{r["totalFront"]}球</td>
          <td style="{cell}text-align:center;color:#3b82f6;font-weight:600">{r["totalBack"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{r["currentFront"]}球</td>
          <td style="{cell}text-align:center;color:#ef4444;font-weight:600">{r["maxFront"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{r["games"]}期</td>
        </tr>'''
    table2 = f'''
    <div style="font-size:13px;font-weight:700;color:#1e293b;margin:12px 0 6px">📈 历史累计排行 Top {limit}</div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
      <thead><tr style="background:#f1f5f9">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">模型</th>
        <th style="{head}text-align:left">策略</th>
        <th style="{head}text-align:center">历史最多</th>
        <th style="{head}text-align:center">累计前区</th>
        <th style="{head}text-align:center">累计后区</th>
        <th style="{head}text-align:center">本期前区</th>
        <th style="{head}text-align:center">单期最多前区</th>
        <th style="{head}text-align:center">期数</th>
      </tr></thead>
      <tbody>{rows2}</tbody>
    </table>'''

    return table1 + table2


def _build_model_group_html(hist, limit=8):
    """模型分组统计 — 每个模型的 3 种策略合并后按累计命中排序 Top N"""
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:13px;padding:12px">(暂无命中记录)</p>'

    latest_record = records[0]
    stats = {}
    for rec in records:
        is_latest = rec is latest_record
        for m in rec.get("models", []):
            name = m.get("model_name", "—")
            s = stats.get(name)
            if s is None:
                s = stats[name] = {
                    "model": name, "total": 0, "totalFront": 0,
                    "totalBack": 0, "maxFront": 0, "current": 0,
                    "periods": set(),
                }
            s["periods"].add(str(rec.get("target_period", "")))
            for pred in m.get("predictions", []):
                hr = pred.get("hit_result")
                if not hr:
                    continue
                total = hr.get("total_hits", 0)
                front = hr.get("front_hit_count", 0)
                s["total"] += total
                s["totalFront"] += front
                s["totalBack"] += hr.get("back_hit_count", 0)
                s["maxFront"] = max(s["maxFront"], front)
                if is_latest:
                    s["current"] += total

    arr = sorted(stats.values(), key=lambda x: (x["total"], x["totalBack"]), reverse=True)[:limit]
    cell = "padding:5px 6px;font-size:11px;"
    head = "padding:5px 6px;color:#64748b;font-size:10px;font-weight:600;"

    rows = ""
    for i, r in enumerate(arr):
        bg = _row_bg(i)
        rows += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}font-weight:600;color:#1e293b">{r["model"]}</td>
          <td style="{cell}text-align:center;color:#475569;font-weight:600">{r["total"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{r["totalFront"]}球</td>
          <td style="{cell}text-align:center;color:#3b82f6">{r["totalBack"]}球</td>
          <td style="{cell}text-align:center;color:#ef4444;font-weight:600">{r["maxFront"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{r["current"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{len(r["periods"])}期</td>
        </tr>'''

    return f'''
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
      <thead><tr style="background:#f1f5f9">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">模型</th>
        <th style="{head}text-align:center">累计命中</th>
        <th style="{head}text-align:center">累计前区</th>
        <th style="{head}text-align:center">累计后区</th>
        <th style="{head}text-align:center">单期最多前区</th>
        <th style="{head}text-align:center">本期命中</th>
        <th style="{head}text-align:center">期数</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>'''


def _build_recommendations_html(pred, hist, latest_period="", next_period=""):
    """本期推荐 — 从当前预测中挑选历史累计命中最高的策略组合"""
    if not pred or not pred.get("models"):
        return '<p style="color:#94a3b8;font-size:13px">(暂无预测数据)</p>'

    records = hist.get("predictions_history", []) if hist else []
    current = {}
    for m in pred["models"]:
        for g in m.get("predictions", []):
            current[(m.get("model_id"), g.get("strategy"))] = (m, g)

    picks = []
    seen = set()

    def add_pick(model, group, entry=None):
        signature = (
            tuple(group.get("front_balls", [])),
            tuple(group.get("back_balls", [])),
        )
        if signature in seen:
            return False
        seen.add(signature)
        picks.append((model, group, entry))
        return True

    # 优先使用历史累计命中最高的策略
    for entry in rank_strategies(records):
        item = current.get((entry["model_id"], entry["strategy"]))
        if not item:
            continue
        if add_pick(item[0], item[1], entry) and len(picks) >= 3:
            break

    # 历史数据不足时用当前预测补齐
    if len(picks) < 3:
        for m in pred["models"]:
            for g in m.get("predictions", []):
                if add_pick(m, g) and len(picks) >= 3:
                    break
            if len(picks) >= 3:
                break

    if not picks:
        return '<p style="color:#94a3b8;font-size:13px">(暂无可推荐预测)</p>'

    cards = ""
    for i, (model, group, entry) in enumerate(picks, 1):
        fronts = "".join(_ball(b, "front") for b in group.get("front_balls", []))
        backs = "".join(_ball(b, "back") for b in group.get("back_balls", []))
        base = f'{model.get("model_name", "—")} · {group.get("strategy", "—")}'
        if entry:
            basis = f'历史累计 {entry["total_hits"]} 球 / {entry["games"]} 期'
        else:
            basis = "按当前预测顺序"
        cards += f'''
        <div style="border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;margin-bottom:8px;background:#f8fafc">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:6px">
            <span style="font-size:12px;font-weight:700;color:#3b82f6">推荐 {i}</span>
            <span style="font-size:11px;color:#64748b">{base}</span>
          </div>
          <div>{fronts}<span style="color:#94a3b8;margin:0 4px">|</span>{backs}</div>
          <div style="font-size:11px;color:#94a3b8;margin-top:4px">{basis}</div>
        </div>'''

    period_line = ""
    if latest_period or next_period:
        period_line = (
            f'<div style="font-size:12px;color:#64748b;margin-bottom:10px">'
            f'基于第 {latest_period or "—"} 期开奖 · 目标第 {next_period or "—"} 期 · '
            f'按历史累计命中排序</div>'
        )

    return period_line + cards


def build_html_digest(data, warnings, generated_at, commit_info=None):
    """
    构建 HTML 邮件正文。

    参数:
        data: load_data() 返回的 3 个数据源
        warnings: validate_data() 返回的警告列表
        generated_at: 生成时间字符串
        commit_info: 可选，push 通知的提交信息 dict，含 author / message / files / stat
    """
    lh = data.get("lottery_history") or {}
    pred = data.get("ai_predictions") or {}
    hist = data.get("hit_history") or {}
    latest = lh.get("data", [{}])[0] if lh.get("data") else {}
    nd = lh.get("next_draw", {})
    latest_period = latest.get("period", "")
    next_period = nd.get("next_period", "")

    # 邮件类型（决定 subtitle 和 footer）
    is_push = commit_info is not None
    subtitle = "项目更新通知" if is_push else "每日汇总"

    # 警告
    warn_html = ""
    if warnings:
        items = "".join(f'<li style="font-size:12px;color:#d97706;padding:2px 0">⚠️ {w}</li>' for w in warnings)
        warn_html = f'<div style="background:#fef3c7;border:1px solid #fde68a;border-radius:8px;padding:12px 16px;margin-bottom:16px"><ul style="margin:0;padding-left:20px">{items}</ul></div>'

    # 提交信息（仅 push 通知）
    commit_html = ""
    if is_push:
        author = commit_info.get("author", "unknown")
        msg = commit_info.get("message", "")
        files = commit_info.get("files", [])
        files_html = ""
        if files:
            items = "".join(f'<li style="font-size:13px;color:#475569;padding:2px 0">{f}</li>' for f in files)
            files_html = f'<ul style="margin:8px 0 0;padding-left:20px">{items}</ul>'
        commit_html = f'''
        {_SECTION.format("📦 提交信息")}
        <table style="width:100%;border-collapse:collapse;background:#f8fafc;border-radius:8px;overflow:hidden">
          <tr><td style="padding:12px 16px">
            <div style="font-size:13px;color:#475569;margin-bottom:4px"><span style="color:#94a3b8">作者</span> {author}</div>
            <div style="font-size:14px;font-weight:600;color:#1e293b">{msg}</div>
            {files_html}
          </td></tr>
        </table>'''

    # Footer
    footer_text = (
        '本邮件由 GitHub Actions 自动推送'
        if is_push else
        '本邮件由自动系统生成 · 彩票预测仅供娱乐参考，不构成投资建议'
    )

    html = f'''
    <div style="max-width:600px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#ffffff;padding:0;color:#1e293b">
      <div style="background:linear-gradient(135deg,#1e293b,#3b82f6);padding:28px 24px;text-align:center;border-radius:12px 12px 0 0">
        <div style="font-size:28px;margin-bottom:4px">🎯</div>
        <h1 style="color:#ffffff;font-size:20px;font-weight:800;margin:0;letter-spacing:-0.5px">大乐透 AI 预测</h1>
        <p style="color:#93c5fd;font-size:13px;margin:4px 0 0">{subtitle} · {generated_at}</p>
      </div>
      <div style="padding:20px 24px">
        {warn_html}
        {commit_html}
        {_SECTION.format("🏆 最新开奖")}
        {_build_latest_draw_html(latest, nd)}
        {_SECTION.format("🔮 本期推荐")}
        {_build_recommendations_html(pred, hist, latest_period, next_period)}
        {_SECTION.format("📊 命中排行 Top 8")}
        {_build_ranking_html(hist, limit=8)}
        {_SECTION.format("📈 模型分组统计 Top 8")}
        {_build_model_group_html(hist, limit=8)}
        {_SECTION.format("🤖 AI 全部预测")}
        {_build_predictions_html(pred, latest_period, next_period)}
      </div>
      <div style="background:#f8fafc;padding:16px 24px;text-align:center;border-top:1px solid #e2e8f0;border-radius:0 0 12px 12px">
        <p style="font-size:12px;color:#94a3b8;margin:0">
          {footer_text}<br>
          <a href="https://github.com/zhens/double-color-ball" style="color:#3b82f6;text-decoration:none">super-lotto</a>
        </p>
      </div>
    </div>'''
    return html