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
from itertools import combinations

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

_SECTION = '<h2 style="font-size:14px;color:#0f172a;font-weight:700;border-left:3px solid #3b82f6;padding-left:10px;margin:18px 0 10px;letter-spacing:0.2px">{}</h2>'


def _ball(num, color):
    # 前区用红色，后区用蓝色（视觉区分）
    bg = "#ef4444" if color == "front" else "#3b82f6"
    return f'<span style="display:inline-block;width:24px;height:24px;line-height:24px;text-align:center;border-radius:50%;background:{bg};color:#fff;font-size:11px;font-weight:700;margin:0 1.5px">{num}</span>'


def _build_latest_draw_html(latest, nd):
    """最新开奖 + 下期预告 HTML（大乐透 5+2）"""
    if not latest:
        return '<p style="color:#94a3b8;font-size:11px">(暂无数据)</p>'
    fronts = "".join(_ball(b, "front") for b in latest.get("front_balls", []))
    backs = "".join(_ball(b, "back") for b in latest.get("back_balls", []))
    html = f'''
    <table style="width:100%;border-collapse:collapse;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <tr><td style="padding:10px 14px">
        <div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:6px">
          第{latest.get("period","")}期 · {latest.get("date","")}
        </div>
        <div style="margin-bottom:4px">{fronts}</div>
        <div style="margin-top:2px">{backs}</div>
      </td></tr>
    </table>'''
    if nd:
        html += f'''
    <table style="width:100%;border-collapse:collapse;background:#f0f9ff;border:1px solid #e0f2fe;border-radius:10px;overflow:hidden;margin-top:6px">
      <tr><td style="padding:8px 14px">
        <span style="font-size:11px;color:#64748b">下期预告</span>
        <span style="font-size:13px;font-weight:700;color:#0f172a;margin-left:6px">{nd.get("next_period","")}</span>
        <span style="font-size:11px;color:#475569;margin-left:6px">{nd.get("next_date_display","")} {nd.get("weekday","")} {nd.get("draw_time","21:25")}</span>
      </td></tr>
    </table>'''
    return html


def _build_predictions_html(pred, latest_period="", next_period=""):
    """AI 全部预测 HTML（含过期检测）"""
    if not pred or not pred.get("models"):
        return '<p style="color:#94a3b8;font-size:11px">(暂无预测数据)</p>'

    target = pred.get("target_period", "")
    # 检测预测是否已过期（目标期号 ≤ 最新开奖期号；isdigit 防越权路径 int() 崩溃）
    stale = (bool(target) and bool(latest_period)
             and str(target).isdigit() and str(latest_period).isdigit()
             and int(str(target)) <= int(str(latest_period)))
    if stale:
        warn = f'''
        <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:9px 12px;margin-bottom:10px;font-size:11px;color:#92400e;line-height:1.5">
          ⚠️ 当前 AI 预测目标为<b>第{target}期</b>，该期已开奖（最新开奖为第{latest_period}期），预测已过期。<br>
          下一期未开奖：<b>第{next_period}期</b>，待 AI 预测更新后将自动显示。
        </div>'''
    else:
        warn = ""

    cell = "padding:4px 8px;font-size:11px;line-height:1.5;"
    tables = ""
    for m in pred["models"]:
        rows = ""
        for i, g in enumerate(m.get("predictions", []), 1):
            fronts = "".join(_ball(b, "front") for b in g.get("front_balls", []))
            backs = "".join(_ball(b, "back") for b in g.get("back_balls", []))
            bg = "#f8fafc" if i % 2 == 1 else "#ffffff"
            rows += f'''
            <tr style="background:{bg}">
              <td style="{cell}width:34px;text-align:center;color:#3b82f6;font-weight:700;font-size:10px">G{g.get("group_id", i)}</td>
              <td style="{cell}font-weight:600;color:#0f172a;white-space:nowrap">{g.get("strategy", "—")}</td>
              <td style="{cell}white-space:nowrap">{fronts}<span style="color:#94a3b8;margin:0 3px">|</span>{backs}</td>
            </tr>'''
        tables += f'''
        <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:8px">
          <thead><tr style="background:#eff6ff">
            <th colspan="3" style="padding:7px 10px;text-align:left;font-size:12px;color:#1e40af;font-weight:700">{m["model_name"]}</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>'''
    return f'''
    {warn}
    <div style="font-size:11px;color:#64748b;margin-bottom:8px">
      目标期号: {pred.get("target_period","")} · 预测日期: {pred.get("prediction_date","")} · 模型数: {len(pred["models"])}
    </div>
    {tables}'''


def _medal(index):
    return {0: "🥇", 1: "🥈", 2: "🥉"}.get(index, f"{index + 1}")


def _row_bg(index):
    return "#fffbeb" if index == 0 else "#f8fafc" if index % 2 == 0 else "#ffffff"


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


def _build_ball_hit_html(records):
    """单球命中 — 最新一期 7 个开奖号码分别被哪些模型命中"""
    if not records:
        return ""
    latest = records[0]
    actual = latest.get("actual_result") or {}
    fronts = actual.get("front_balls", [])
    backs = actual.get("back_balls", [])
    if not fronts and not backs:
        return ""

    entries = [("front", b) for b in fronts] + [("back", b) for b in backs]
    hits = {(zone, ball): [] for zone, ball in entries}
    for m in latest.get("models", []):
        name = m.get("model_name", "—")
        for pred in m.get("predictions", []):
            hr = pred.get("hit_result") or {}
            for ball in hr.get("front_hits", []):
                key = ("front", ball)
                if key in hits and name not in hits[key]:
                    hits[key].append(name)
            for ball in hr.get("back_hits", []):
                key = ("back", ball)
                if key in hits and name not in hits[key]:
                    hits[key].append(name)

    cell = "padding:4px 6px;font-size:11px;line-height:1.5;"
    rows = ""
    for i, (zone, ball) in enumerate(entries):
        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        models = "、".join(hits[(zone, ball)])
        rows += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center">{_ball(ball, zone)}</td>
          <td style="{cell}text-align:center;color:#64748b">{'前区' if zone == 'front' else '后区'}</td>
          <td style="{cell}color:#0f172a;font-weight:600">{models}</td>
        </tr>'''

    return f'''
    <div style="font-size:12px;font-weight:700;color:#0f172a;margin:10px 0 6px">🎯 单球命中（第 {actual.get("period", "—")} 期）</div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:12px">
      <thead><tr style="background:#f8fafc">
        <th style="padding:4px 6px;text-align:center;color:#64748b;font-size:10px;font-weight:600">号码</th>
        <th style="padding:4px 6px;text-align:center;color:#64748b;font-size:10px;font-weight:600">区域</th>
        <th style="padding:4px 6px;text-align:left;color:#64748b;font-size:10px;font-weight:600">命中模型（空白表示 0 命中）</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>'''


def _build_best_combo_html(hist, pred=None, limit=10, threshold=5):
    """最佳组合 — 两两合并两个「模型+策略」的号码并去重,
    单期命中 >= threshold 球计 1 次,按次数取 Top N。
    每个模型+策略下方用小字显示其最新未开奖预测。
    """
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:11px;padding:10px">(暂无命中记录)</p>'

    current = {}
    if pred:
        for model in pred.get("models", []):
            for group in model.get("predictions", []):
                current[(model.get("model_id"), group.get("strategy"))] = group

    stats = {}
    for rec in records:
        actual = rec.get("actual_result") or {}
        actual_front = set(actual.get("front_balls", []))
        actual_back = set(actual.get("back_balls", []))

        entries = []
        for model in rec.get("models", []):
            model_id = model.get("model_id", "")
            model_name = model.get("model_name", "—")
            for group in model.get("predictions", []):
                if not group.get("hit_result"):
                    continue
                strategy = group.get("strategy", "—")
                entries.append((
                    model_id, strategy, f"{model_name}·{strategy}",
                    set(group.get("front_balls", [])),
                    set(group.get("back_balls", [])),
                ))

        for i in range(len(entries)):
            mid_a, strat_a, label_a, front_a, back_a = entries[i]
            for j in range(i + 1, len(entries)):
                mid_b, strat_b, label_b, front_b, back_b = entries[j]
                if mid_a == mid_b and strat_a == strat_b:
                    continue
                key_a = (mid_a, strat_a)
                key_b = (mid_b, strat_b)
                key = tuple(sorted([key_a, key_b]))
                hits = (len((front_a | front_b) & actual_front)
                        + len((back_a | back_b) & actual_back))
                s = stats.get(key)
                if s is None:
                    s = stats[key] = {
                        "keys": key,
                        "labels": {key_a: label_a, key_b: label_b},
                        "count": 0, "best": 0, "total": 0, "games": 0,
                    }
                s["games"] += 1
                s["total"] += hits
                s["best"] = max(s["best"], hits)
                if hits >= threshold:
                    s["count"] += 1

    rows = sorted(
        stats.values(),
        key=lambda s: (
            -s["count"], -s["best"],
            -(s["total"] / max(s["games"], 1)),
            s["labels"].get(s["keys"][0], ""),
            s["labels"].get(s["keys"][1], ""),
        ),
    )
    top = [r for r in rows if r["count"] > 0][:limit]
    if not top:
        return (f'<p style="color:#94a3b8;font-size:11px;padding:10px">'
                f'(暂无组合单期达到 {threshold} 球)</p>')

    def _mini(group):
        if not group:
            return '<span style="color:#94a3b8">暂无最新预测</span>'
        fronts = " ".join(group.get("front_balls", []))
        backs = " ".join(group.get("back_balls", []))
        return (f'<span style="color:#ef4444">前 {fronts}</span>'
                f'<span style="color:#cbd5e1"> | </span>'
                f'<span style="color:#3b82f6">后 {backs}</span>')

    target_period = (pred or {}).get("target_period", "")
    target_text = f"第 {target_period} 期" if target_period else "最新一期"

    cell = "padding:5px 6px;font-size:10px;line-height:1.5;"
    head = "padding:5px 6px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"
    body = ""
    for i, r in enumerate(top):
        bg = _row_bg(i)
        avg = r["total"] / r["games"] if r["games"] else 0
        key_a, key_b = r["keys"]
        label_a = r["labels"].get(key_a, "—")
        label_b = r["labels"].get(key_b, "—")
        mini_a = _mini(current.get(key_a))
        mini_b = _mini(current.get(key_b))
        body += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}">
            <div style="font-weight:600;color:#0f172a">{label_a}</div>
            <div style="margin-top:1px">{mini_a}</div>
            <div style="font-weight:600;color:#0f172a;margin-top:4px">+ {label_b}</div>
            <div style="margin-top:1px">{mini_b}</div>
          </td>
          <td style="{cell}text-align:center;font-weight:700;color:#ef4444">{r["count"]}次</td>
          <td style="{cell}text-align:center;color:#475569">{r["best"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{avg:.2f}球</td>
        </tr>'''

    return f'''
    <div style="font-size:10px;color:#94a3b8;margin-bottom:6px">
      两两合并号码并去重，单期命中 ≥{threshold} 球计 1 次 · 按次数取 Top {limit} · 小字为{target_text}未开奖预测
    </div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#f8fafc">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">组合与最新预测</th>
        <th style="{head}text-align:center">≥{threshold}球次数</th>
        <th style="{head}text-align:center">单期最高</th>
        <th style="{head}text-align:center">平均命中</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>'''


def _build_best_triple_html(hist, pred=None, limit=10, threshold=5):
    """最三组合 — 三组不同「模型+策略」前区号码合并去重，
    单期覆盖全部 threshold 个前区红球计 1 次，按次数取 Top N。
    每个模型+策略下方用小字显示其最新未开奖预测。
    """
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:11px;padding:10px">(暂无命中记录)</p>'

    current = {}
    if pred:
        for model in pred.get("models", []):
            for group in model.get("predictions", []):
                current[(model.get("model_id"), group.get("strategy"))] = group

    stats = {}
    for rec in records:
        actual = rec.get("actual_result") or {}
        actual_front = set(actual.get("front_balls", []))

        entries = []
        for model in rec.get("models", []):
            model_id = model.get("model_id", "")
            model_name = model.get("model_name", "—")
            for group in model.get("predictions", []):
                if not group.get("hit_result"):
                    continue
                strategy = group.get("strategy", "—")
                entries.append((
                    model_id, strategy, f"{model_name}·{strategy}",
                    set(group.get("front_balls", [])),
                    set(group.get("back_balls", [])),
                ))

        for combo in combinations(entries, 3):
            keys = tuple(sorted((entry[0], entry[1]) for entry in combo))
            if len(set(keys)) < 3:
                continue
            labels = {}
            front_union = set()
            for mid, strat, label, front, _back in combo:
                labels[(mid, strat)] = label
                front_union |= front
            hits = len(front_union & actual_front)

            s = stats.get(keys)
            if s is None:
                s = stats[keys] = {
                    "keys": keys, "labels": labels,
                    "count": 0, "best": 0, "total": 0, "games": 0,
                }
            s["games"] += 1
            s["total"] += hits
            s["best"] = max(s["best"], hits)
            if hits >= threshold:
                s["count"] += 1

    rows = sorted(
        stats.values(),
        key=lambda s: (
            -s["count"], -s["best"],
            -(s["total"] / max(s["games"], 1)),
            tuple(s["labels"].get(k, "") for k in s["keys"]),
        ),
    )
    top = [r for r in rows if r["count"] > 0][:limit]
    if not top:
        return (f'<p style="color:#94a3b8;font-size:11px;padding:10px">'
                f'(暂无组合单期覆盖 {threshold} 个红球)</p>')

    def _mini(group):
        if not group:
            return '<span style="color:#94a3b8">暂无最新预测</span>'
        fronts = " ".join(group.get("front_balls", []))
        backs = " ".join(group.get("back_balls", []))
        return (f'<span style="color:#ef4444">前 {fronts}</span>'
                f'<span style="color:#cbd5e1"> | </span>'
                f'<span style="color:#3b82f6">后 {backs}</span>')

    target_period = (pred or {}).get("target_period", "")
    target_text = f"第 {target_period} 期" if target_period else "最新一期"

    cell = "padding:5px 6px;font-size:10px;line-height:1.5;"
    head = "padding:5px 6px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"
    body = ""
    for i, r in enumerate(top):
        bg = _row_bg(i)
        avg = r["total"] / r["games"] if r["games"] else 0
        blocks = ""
        for idx, key in enumerate(r["keys"]):
            label = r["labels"].get(key, "—")
            mini = _mini(current.get(key))
            margin = "margin-top:4px;" if idx else ""
            blocks += f'''
            <div style="font-weight:600;color:#0f172a;{margin}">{label}</div>
            <div style="margin-top:1px">{mini}</div>'''
        body += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}">{blocks}</td>
          <td style="{cell}text-align:center;font-weight:700;color:#ef4444">{r["count"]}次</td>
          <td style="{cell}text-align:center;color:#475569">{r["best"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{avg:.2f}球</td>
        </tr>'''

    return f'''
    <div style="font-size:10px;color:#94a3b8;margin-bottom:6px">
      三组不同模型+策略前区合并去重，单期覆盖 {threshold} 个红球计 1 次 · 按次数取 Top {limit} · 小字为{target_text}未开奖预测
    </div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#f8fafc">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">组合与最新预测</th>
        <th style="{head}text-align:center">{threshold}红球次数</th>
        <th style="{head}text-align:center">单期最高红球</th>
        <th style="{head}text-align:center">平均红球</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>'''


def _build_ranking_html(hist, limit=8):
    """命中排行 HTML — 最新一期 + 历史累计（各 Top N）"""
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:11px;padding:10px">(暂无命中记录)</p>'

    stats = _collect_ranking_stats(records)
    cell = "padding:4px 6px;font-size:11px;line-height:1.5;"
    head = "padding:4px 6px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"
    dense_cell = "padding:4px 4px;font-size:10px;line-height:1.5;"
    dense_head = "padding:4px 4px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"

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
          <td style="{cell}font-weight:600;color:#0f172a">{r["model"]}</td>
          <td style="{cell}color:#475569">{r["strategy"]}</td>
          <td style="{cell}text-align:center;font-weight:700;color:#ef4444">{r["current"]}球</td>
          <td style="{cell}color:#2563eb;font-family:monospace">{r["frontHits"]}</td>
          <td style="{cell}text-align:center;font-weight:700;color:#3b82f6">{back_mark}</td>
        </tr>'''
    table1 = f'''
    <div style="font-size:12px;font-weight:700;color:#0f172a;margin:10px 0 6px">🏆 最新一期 Top {limit}</div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:12px">
      <thead><tr style="background:#f8fafc">
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
          <td style="{dense_cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{dense_cell}font-weight:600;color:#0f172a">{r["model"]}</td>
          <td style="{dense_cell}color:#475569">{r["strategy"]}</td>
          <td style="{dense_cell}text-align:center;color:#475569">{r["best"]}球</td>
          <td style="{dense_cell}text-align:center;color:#475569">{r["totalFront"]}球</td>
          <td style="{dense_cell}text-align:center;color:#3b82f6;font-weight:600">{r["totalBack"]}球</td>
          <td style="{dense_cell}text-align:center;color:#475569">{r["currentFront"]}球</td>
          <td style="{dense_cell}text-align:center;color:#ef4444;font-weight:600">{r["maxFront"]}球</td>
          <td style="{dense_cell}text-align:center;color:#475569">{r["games"]}期</td>
        </tr>'''
    table2 = f'''
    <div style="font-size:12px;font-weight:700;color:#0f172a;margin:10px 0 6px">📈 历史累计排行 Top {limit}</div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#f8fafc">
        <th style="{dense_head}text-align:center">#</th>
        <th style="{dense_head}text-align:left">模型</th>
        <th style="{dense_head}text-align:left">策略</th>
        <th style="{dense_head}text-align:center">历史最多</th>
        <th style="{dense_head}text-align:center">累计前区</th>
        <th style="{dense_head}text-align:center">累计后区</th>
        <th style="{dense_head}text-align:center">本期前区</th>
        <th style="{dense_head}text-align:center">单期最多前区</th>
        <th style="{dense_head}text-align:center">期数</th>
      </tr></thead>
      <tbody>{rows2}</tbody>
    </table>'''

    return table1 + _build_ball_hit_html(records) + table2


def _build_model_group_html(hist, limit=8):
    """模型分组统计 — 每个模型的 3 种策略合并后按累计命中排序 Top N"""
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:11px;padding:10px">(暂无命中记录)</p>'

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
    cell = "padding:4px 6px;font-size:11px;line-height:1.5;"
    head = "padding:4px 6px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"

    rows = ""
    for i, r in enumerate(arr):
        bg = _row_bg(i)
        rows += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}font-weight:600;color:#0f172a">{r["model"]}</td>
          <td style="{cell}text-align:center;color:#475569;font-weight:600">{r["total"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{r["totalFront"]}球</td>
          <td style="{cell}text-align:center;color:#3b82f6">{r["totalBack"]}球</td>
          <td style="{cell}text-align:center;color:#ef4444;font-weight:600">{r["maxFront"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{r["current"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{len(r["periods"])}期</td>
        </tr>'''

    return f'''
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#f8fafc">
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


def _build_recommendations_html(pred, hist, latest_period="", next_period="", limit=10):
    """本期推荐 — 按历史累计命中挑选 Top N 个「模型+策略」组合"""
    if not pred or not pred.get("models"):
        return '<p style="color:#94a3b8;font-size:11px">(暂无预测数据)</p>'

    records = hist.get("predictions_history", []) if hist else []
    current = {}
    for m in pred["models"]:
        for g in m.get("predictions", []):
            current[(m.get("model_id"), g.get("strategy"))] = (m, g)

    picks = []
    used_keys = set()
    seen_numbers = set()

    def add_pick(model, group, entry=None):
        key = (model.get("model_id"), group.get("strategy"))
        signature = (
            tuple(group.get("front_balls", [])),
            tuple(group.get("back_balls", [])),
        )
        # 同一模型+策略不重复；号码完全相同的组合自动顺延到下一名
        if key in used_keys or signature in seen_numbers:
            return False
        used_keys.add(key)
        seen_numbers.add(signature)
        picks.append((model, group, entry))
        return True

    # 优先使用历史累计命中最高的模型+策略
    for entry in rank_strategies(records):
        item = current.get((entry["model_id"], entry["strategy"]))
        if not item:
            continue
        add_pick(item[0], item[1], entry)
        if len(picks) >= limit:
            break

    # 历史数据不足时用当前预测补齐
    if len(picks) < limit:
        for m in pred["models"]:
            for g in m.get("predictions", []):
                add_pick(m, g)
                if len(picks) >= limit:
                    break
            if len(picks) >= limit:
                break

    if not picks:
        return '<p style="color:#94a3b8;font-size:11px">(暂无可推荐预测)</p>'

    cell = "padding:4px 6px;font-size:11px;line-height:1.5;"
    head = "padding:4px 6px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"
    rows = ""
    for i, (model, group, entry) in enumerate(picks, 1):
        fronts = "".join(_ball(b, "front") for b in group.get("front_balls", []))
        backs = "".join(_ball(b, "back") for b in group.get("back_balls", []))
        if entry:
            basis = f'{entry["total_hits"]}球 / {entry["games"]}期'
        else:
            basis = "—"
        bg = _row_bg(i - 1)
        rows += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i - 1)}</td>
          <td style="{cell}font-weight:600;color:#0f172a">{model.get("model_name", "—")}</td>
          <td style="{cell}color:#475569">{group.get("strategy", "—")}</td>
          <td style="{cell}white-space:nowrap">{fronts}<span style="color:#94a3b8;margin:0 3px">|</span>{backs}</td>
          <td style="{cell}text-align:center;color:#3b82f6;font-weight:600;white-space:nowrap">{basis}</td>
        </tr>'''
    table = f'''
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#f8fafc">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">模型</th>
        <th style="{head}text-align:left">策略</th>
        <th style="{head}text-align:left">推荐号码</th>
        <th style="{head}text-align:center;white-space:nowrap">历史累计</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>'''

    period_line = ""
    if latest_period or next_period:
        period_line = (
            f'<div style="font-size:11px;color:#64748b;margin-bottom:8px">'
            f'基于第 {latest_period or "—"} 期开奖 · 目标第 {next_period or "—"} 期 · '
            f'按历史累计命中排序 · Top {limit}（同号去重）</div>'
        )

    return period_line + table


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
        items = "".join(f'<li style="font-size:11px;color:#d97706;padding:1px 0">{w}</li>' for w in warnings)
        warn_html = f'<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:9px 12px;margin-bottom:12px"><ul style="margin:0;padding-left:18px">{items}</ul></div>'

    # 提交信息（仅 push 通知）
    commit_html = ""
    if is_push:
        author = commit_info.get("author", "unknown")
        msg = commit_info.get("message", "")
        files = commit_info.get("files", [])
        files_html = ""
        if files:
            items = "".join(f'<li style="font-size:10px;color:#475569;padding:1px 0">{f}</li>' for f in files)
            files_html = f'<ul style="margin:6px 0 0;padding-left:18px">{items}</ul>'
        commit_html = f'''
        {_SECTION.format("📦 提交信息")}
        <table style="width:100%;border-collapse:collapse;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
          <tr><td style="padding:10px 12px">
            <div style="font-size:11px;color:#475569;margin-bottom:3px"><span style="color:#94a3b8">作者</span> {author}</div>
            <div style="font-size:12px;font-weight:600;color:#0f172a">{msg}</div>
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
    <div style="max-width:600px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#ffffff;padding:0;color:#0f172a">
      <div style="background:linear-gradient(135deg,#eff6ff,#e0f2fe);padding:20px 18px;text-align:center;border-bottom:1px solid #dbeafe;border-radius:12px 12px 0 0">
        <div style="font-size:22px;margin-bottom:2px">🎯</div>
        <h1 style="color:#0f172a;font-size:18px;font-weight:700;margin:0;letter-spacing:-0.3px">大乐透 AI 预测</h1>
        <p style="color:#475569;font-size:11px;margin:4px 0 0">{subtitle} · {generated_at}</p>
      </div>
      <div style="padding:16px 18px">
        {warn_html}
        {commit_html}
        {_SECTION.format("🏆 最新开奖")}
        {_build_latest_draw_html(latest, nd)}
        {_SECTION.format("🔮 本期推荐 Top 10")}
        {_build_recommendations_html(pred, hist, latest_period, next_period, limit=10)}
        {_SECTION.format("📊 命中排行 Top 8")}
        {_build_ranking_html(hist, limit=8)}
        {_SECTION.format("🏅 最佳组合")}
        {_build_best_combo_html(hist, pred, limit=10)}
        {_SECTION.format("🏅 最佳三组合")}
        {_build_best_triple_html(hist, pred, limit=10)}
        {_SECTION.format("📈 模型分组统计 Top 8")}
        {_build_model_group_html(hist, limit=8)}
        {_SECTION.format("🤖 AI 全部预测")}
        {_build_predictions_html(pred, latest_period, next_period)}
      </div>
      <div style="background:#f8fafc;padding:12px 18px;text-align:center;border-top:1px solid #e2e8f0;border-radius:0 0 12px 12px">
        <p style="font-size:10px;color:#94a3b8;margin:0;line-height:1.6">
          {footer_text}<br>
          <a href="https://github.com/zigzag264/happy7" style="color:#3b82f6;text-decoration:none">happy7</a>
        </p>
      </div>
    </div>'''
    return html