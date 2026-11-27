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
import base64
import struct
import zlib
from itertools import combinations

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from freshness import check_freshness

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

    # ---- 硬校验：数据必须相对北京时间是新鲜的 ----
    # 定时任务可能延迟数小时；数据未跟上开奖节奏时，即使文件内部自洽也不能推送。
    fresh_errors, fresh_warnings = check_freshness(lh)
    errors.extend(fresh_errors)
    warnings.extend(fresh_warnings)
    return errors, warnings


# ==================== 共用 HTML 构建 ====================

_SECTION = '<h2 style="font-size:14px;color:#0f172a;font-weight:700;border-left:3px solid #3b82f6;padding-left:10px;margin:18px 0 10px;letter-spacing:0.2px">{}</h2>'


def _ball(num, color, size=24, font_size=11):
    # 前区用红色，后区用蓝色（视觉区分）
    bg = "#ef4444" if color == "front" else "#3b82f6"
    return f'<span style="display:inline-block;width:{size}px;height:{size}px;line-height:{size}px;text-align:center;border-radius:50%;background:{bg};color:#fff;font-size:{font_size}px;font-weight:700;margin:0 1.5px">{num}</span>'


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


def _build_predictions_html(pred, latest_period="", next_period="", hist=None):
    """AI 全部预测 HTML（含过期检测，按模型累计命中总球数降序）"""
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

    # 模型累计命中统计（与「模型分组统计」口径一致），用于排序展示
    def _mid(m):
        return m.get("model_id") or m.get("model_name", "—")

    model_totals = {}
    for rec in (hist or {}).get("predictions_history", []) or []:
        for m in rec.get("models", []):
            s = model_totals.setdefault(_mid(m), {"total": 0, "back": 0})
            for group in m.get("predictions", []):
                hr = group.get("hit_result")
                if not hr:
                    continue
                s["total"] += hr.get("total_hits", 0)
                s["back"] += hr.get("back_hit_count", 0)

    original_order = {_mid(m): i for i, m in enumerate(pred["models"])}
    models = sorted(
        pred["models"],
        key=lambda m: (
            -model_totals.get(_mid(m), {}).get("total", 0),
            -model_totals.get(_mid(m), {}).get("back", 0),
            original_order.get(_mid(m), 0),
        ),
    )

    cell = "padding:4px 8px;font-size:11px;line-height:1.5;"
    head = "padding:6px 8px;font-size:10px;color:#1e40af;font-weight:700;"
    body = ""
    for mi, m in enumerate(models):
        preds = m.get("predictions", [])
        span = max(len(preds), 1)
        model_bg = "#eff6ff" if mi % 2 == 0 else "#f8fafc"
        sep = ";border-top:1px solid #e2e8f0" if mi > 0 else ""
        if not preds:
            body += f'''
            <tr style="background:#ffffff">
              <td style="{cell}font-weight:700;color:#1e40af;white-space:nowrap;vertical-align:top;background:{model_bg}{sep}">{m["model_name"]}</td>
              <td style="{cell}text-align:center;color:#94a3b8{sep}">—</td>
              <td style="{cell}color:#94a3b8{sep}">暂无预测</td>
              <td style="{cell}color:#94a3b8{sep}">—</td>
            </tr>'''
            continue
        for i, g in enumerate(preds, 1):
            fronts = "".join(_ball(b, "front") for b in g.get("front_balls", []))
            backs = "".join(_ball(b, "back") for b in g.get("back_balls", []))
            bg = "#ffffff" if i % 2 == 1 else "#f8fafc"
            first = (i == 1)
            row_sep = sep if first else ""
            model_cell = ""
            if first:
                model_cell = (f'<td rowspan="{span}" style="{cell}font-weight:700;color:#1e40af;'
                              f'white-space:nowrap;vertical-align:top;background:{model_bg}{sep}">{m["model_name"]}</td>')
            body += f'''
            <tr style="background:{bg}">
              {model_cell}
              <td style="{cell}width:34px;text-align:center;color:#3b82f6;font-weight:700;font-size:10px{row_sep}">G{g.get("group_id", i)}</td>
              <td style="{cell}font-weight:600;color:#0f172a;white-space:nowrap{row_sep}">{g.get("strategy", "—")}</td>
              <td style="{cell}white-space:nowrap{row_sep}">{fronts}<span style="color:#94a3b8;margin:0 3px">|</span>{backs}</td>
            </tr>'''
    return f'''
    {warn}
    <div style="font-size:11px;color:#64748b;margin-bottom:8px">
      目标期号: {pred.get("target_period","")} · 预测日期: {pred.get("prediction_date","")} · 模型数: {len(pred["models"])}
    </div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#eff6ff">
        <th style="{head}text-align:left">模型</th>
        <th style="{head}text-align:center;width:34px">组</th>
        <th style="{head}text-align:left">策略</th>
        <th style="{head}text-align:left">号码（前区 | 后区）</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>'''


def _medal(index):
    return {0: "🥇", 1: "🥈", 2: "🥉"}.get(index, f"{index + 1}")


def _row_bg(index):
    return "#fffbeb" if index == 0 else "#f8fafc" if index % 2 == 0 else "#ffffff"


# 组合板块中使用的模型简称（完整名称见「策略索引」）
MODEL_SHORT_NAMES = {
    "markov-chain": "马尔可夫",
    "bayesian-inference": "贝叶斯",
    "arima-time-series": "ARIMA",
    "monte-carlo": "蒙特卡洛",
    "ensemble-ml": "随机森林",
    "lstm-neural-network": "LSTM",
    "apriori-rules": "Apriori",
    "genetic-algorithm": "遗传",
    "hidden-markov-model": "HMM",
    "constraint-satisfaction": "CSP",
}


def _short_model_name(model_id, model_name):
    return MODEL_SHORT_NAMES.get(model_id, model_name)


def _build_group_map(pred):
    """model_id -> {strategy: G编号}，以当前预测的 group_id 为准。

    历史记录里的 group_id 会随入选策略变化而重排（同一策略在不同期可能是
    G1 或 G2），因此显示时统一以当前预测为稳定基准，避免图例与号码错位。
    """
    mapping = {}
    for m in (pred or {}).get("models", []):
        mid = m.get("model_id", "")
        groups = {}
        for g in m.get("predictions", []):
            gid = g.get("group_id")
            if gid is not None:
                groups[g.get("strategy", "—")] = f"G{gid}"
        if groups:
            mapping[mid] = groups
    return mapping


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
                        "model_id": m.get("model_id", ""),
                        "model": model_name,
                        "strategy": pred.get("strategy", "—"),
                        "total": 0, "best": 0, "games": 0,
                        "current": 0, "currentFront": 0, "backHit": 0,
                        "frontHits": "", "backHits": "", "totalFront": 0, "totalBack": 0,
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
                    back_hits = hr.get("back_hits", [])
                    s["backHits"] = " ".join(back_hits) if back_hits else "—"
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
    <div style="font-size:10px;color:#94a3b8;margin-bottom:6px">第 {actual.get("period", "—")} 期 · 空白表示 0 命中</div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:12px">
      <thead><tr style="background:#f8fafc">
        <th style="padding:4px 6px;text-align:center;color:#64748b;font-size:10px;font-weight:600">号码</th>
        <th style="padding:4px 6px;text-align:center;color:#64748b;font-size:10px;font-weight:600">区域</th>
        <th style="padding:4px 6px;text-align:left;color:#64748b;font-size:10px;font-weight:600">命中模型（空白表示 0 命中）</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>'''


def _build_best_combo_html(hist, pred=None, limit=10, front_threshold=4):
    """最佳组合 — 两两合并两个「模型+策略」的号码并去重,
    单期前区命中 >= front_threshold 球计 1 次,按次数取 Top N。
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
    group_map = _build_group_map(pred)

    stats = {}
    group_stats = {}  # (model_id, strategy) -> 该组自身历史前区命中 / 期数
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
                gid = group_map.get(model_id, {}).get(strategy)
                short = _short_model_name(model_id, model_name)
                label = f"{short}·{gid}" if gid else f"{short}·{strategy}"
                gs = group_stats.setdefault((model_id, strategy), {"total": 0, "games": 0})
                gs["total"] += group["hit_result"].get("front_hit_count", 0)
                gs["games"] += 1
                entries.append((
                    model_id, strategy, label,
                    set(group.get("front_balls", [])),
                ))

        for i in range(len(entries)):
            mid_a, strat_a, label_a, front_a = entries[i]
            for j in range(i + 1, len(entries)):
                mid_b, strat_b, label_b, front_b = entries[j]
                if mid_a == mid_b and strat_a == strat_b:
                    continue
                key_a = (mid_a, strat_a)
                key_b = (mid_b, strat_b)
                key = tuple(sorted([key_a, key_b]))
                side_a_hits = len(front_a & actual_front)
                side_b_hits = len(front_b & actual_front)
                front_hits = len((front_a | front_b) & actual_front)
                s = stats.get(key)
                if s is None:
                    s = stats[key] = {
                        "keys": key,
                        "labels": {key_a: label_a, key_b: label_b},
                        "front_count": 0, "max_front": 0, "max_single": 0,
                        "front_total": 0, "games": 0,
                    }
                s["games"] += 1
                s["front_total"] += front_hits
                s["max_front"] = max(s["max_front"], front_hits)
                s["max_single"] = max(s["max_single"], side_a_hits, side_b_hits)
                if front_hits >= front_threshold:
                    s["front_count"] += 1

    rows = sorted(
        stats.values(),
        key=lambda s: (
            -s["front_count"], -s["max_front"], -s["max_single"],
            -(s["front_total"] / max(s["games"], 1)),
            s["labels"].get(s["keys"][0], ""),
            s["labels"].get(s["keys"][1], ""),
        ),
    )
    # 每个「模型+策略」在 Top 列表中最多出现 2 次，避免同一强组霸榜
    top, appearances = [], {}
    for r in rows:
        if len(top) >= limit:
            break
        if r["front_count"] <= 0:
            break
        if any(appearances.get(k, 0) >= 2 for k in r["keys"]):
            continue
        for k in r["keys"]:
            appearances[k] = appearances.get(k, 0) + 1
        top.append(r)
    if not top:
        return (f'<p style="color:#94a3b8;font-size:11px;padding:10px">'
                f'(暂无组合单期前区命中达到 {front_threshold} 球)</p>')

    def _mini(group, key):
        if not group:
            return '<span style="color:#94a3b8">暂无最新预测</span>'
        fronts = " ".join(group.get("front_balls", []))
        gs = group_stats.get(key)
        stat = f'<span style="color:#94a3b8">（{gs["total"]}球/{gs["games"]}期）</span>' if gs else ""
        return f'<span style="color:#ef4444">前 {fronts}</span>{stat}'

    target_period = (pred or {}).get("target_period", "")
    target_text = f"第 {target_period} 期" if target_period else "最新一期"

    cell = "padding:5px 6px;font-size:10px;line-height:1.5;"
    head = "padding:5px 6px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"
    body = ""
    for i, r in enumerate(top):
        bg = _row_bg(i)
        # 组内按各自命中总球数降序，球数高的排上方
        ordered = sorted(
            r["keys"],
            key=lambda k: (-group_stats.get(k, {}).get("total", 0), r["labels"].get(k, "")),
        )
        blocks = ""
        for idx, key in enumerate(ordered):
            label = r["labels"].get(key, "—")
            mini = _mini(current.get(key), key)
            prefix = "+ " if idx else ""
            margin = "margin-top:2px;" if idx else ""
            blocks += f'''
            <div style="font-weight:600;color:#0f172a;white-space:nowrap;{margin}">{prefix}{label}<span style="margin-left:5px;font-weight:400">{mini}</span></div>'''
        body += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}">{blocks}</td>
          <td style="{cell}text-align:center;color:#475569">{r["front_count"]}次</td>
          <td style="{cell}text-align:center;color:#475569">{r["max_front"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{r["max_single"]}球</td>
        </tr>'''

    return f'''
    <div style="font-size:10px;color:#94a3b8;margin-bottom:6px">
      两两合并号码并去重，单期前区总球数 ≥{front_threshold} 计 1 次 · 按次数/去重最高/单个模型最高排序取 Top {limit} · 每个模型+策略最多出现 2 次 · 每行一组，号码仅显示{target_text}前区未开奖预测，括号内为该组自身历史前区命中/期数
    </div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#f8fafc">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">组合与前区预测</th>
        <th style="{head}text-align:center">前区总球数≥{front_threshold}</th>
        <th style="{head}text-align:center">前区去重最高</th>
        <th style="{head}text-align:center">单个模型最高</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>'''


def _build_best_blue_combo_html(hist, pred=None, limit=10, threshold=2):
    """最蓝组合 — 两组不同「模型+策略」后区蓝球合并去重，
    单期覆盖全部 threshold 个蓝球计 1 次，按次数取 Top N。
    """
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:11px;padding:10px">(暂无命中记录)</p>'

    current = {}
    if pred:
        for model in pred.get("models", []):
            for group in model.get("predictions", []):
                current[(model.get("model_id"), group.get("strategy"))] = group
    group_map = _build_group_map(pred)

    stats = {}
    group_stats = {}  # (model_id, strategy) -> 该组自身历史蓝球命中 / 期数
    for rec in records:
        actual = rec.get("actual_result") or {}
        actual_back = set(actual.get("back_balls", []))

        entries = []
        for model in rec.get("models", []):
            model_id = model.get("model_id", "")
            model_name = model.get("model_name", "—")
            for group in model.get("predictions", []):
                if not group.get("hit_result"):
                    continue
                strategy = group.get("strategy", "—")
                gid = group_map.get(model_id, {}).get(strategy)
                short = _short_model_name(model_id, model_name)
                label = f"{short}·{gid}" if gid else f"{short}·{strategy}"
                gs = group_stats.setdefault((model_id, strategy), {"total": 0, "games": 0, "full": 0})
                back_count = group["hit_result"].get("back_hit_count", 0)
                gs["total"] += back_count
                gs["games"] += 1
                if back_count >= threshold:
                    gs["full"] += 1
                entries.append((
                    model_id, strategy, label,
                    set(group.get("front_balls", [])),
                    set(group.get("back_balls", [])),
                ))

        for combo in combinations(entries, 2):
            keys = tuple(sorted((entry[0], entry[1]) for entry in combo))
            if len(set(keys)) < 2:
                continue
            labels = {}
            back_union = set()
            for mid, strat, label, _front, back in combo:
                labels[(mid, strat)] = label
                back_union |= back
            hits = len(back_union & actual_back)

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
                f'(暂无组合单期覆盖 {threshold} 个蓝球)</p>')

    def _mini(group, key):
        if not group:
            return '<span style="color:#94a3b8">暂无最新预测</span>'
        backs = " ".join(group.get("back_balls", []))
        gs = group_stats.get(key)
        stat = (f'<span style="color:#94a3b8">（{gs["total"]}球/{gs["games"]}期 · 全中{gs["full"]}次）</span>'
                if gs else "")
        return f'<span style="color:#3b82f6">后 {backs}</span>{stat}'

    target_period = (pred or {}).get("target_period", "")
    target_text = f"第 {target_period} 期" if target_period else "最新一期"

    cell = "padding:5px 6px;font-size:10px;line-height:1.5;"
    head = "padding:5px 6px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"
    body = ""
    for i, r in enumerate(top):
        bg = _row_bg(i)
        blocks = ""
        # 组内按各自命中总球数降序，球数高的排上方
        ordered = sorted(
            r["keys"],
            key=lambda k: (-group_stats.get(k, {}).get("total", 0), r["labels"].get(k, "")),
        )
        for idx, key in enumerate(ordered):
            label = r["labels"].get(key, "—")
            mini = _mini(current.get(key), key)
            prefix = "+ " if idx else ""
            margin = "margin-top:2px;" if idx else ""
            blocks += f'''
            <div style="font-weight:600;color:#0f172a;white-space:nowrap;{margin}">{prefix}{label}<span style="margin-left:5px;font-weight:400">{mini}</span></div>'''
        body += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}">{blocks}</td>
          <td style="{cell}text-align:center;font-weight:700;color:#3b82f6">{r["count"]}次</td>
          <td style="{cell}text-align:center;color:#475569">{r["total"]}球 / {r["games"]}期</td>
        </tr>'''

    return f'''
    <div style="font-size:10px;color:#94a3b8;margin-bottom:6px">
      两组不同模型+策略后区蓝球合并去重，单期覆盖 {threshold} 个蓝球计 1 次 · 按次数取 Top {limit} · 每行一组，号码仅显示{target_text}后区未开奖预测，括号内为该组自身历史蓝球命中/期数及 {threshold} 蓝球全中次数
    </div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#f8fafc">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">组合与后区预测</th>
        <th style="{head}text-align:center">{threshold}蓝球次数</th>
        <th style="{head}text-align:center">累计蓝球 / 期数</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>'''


def _build_extreme3_combo_html(hist, pred=None, limit=10, threshold=3):
    """极3组合 — 沿用「最佳组合」的两两合并逻辑:
    合并两个不同「模型+策略」的前区、后区号码并各自去重,
    单期「前区+后区」总命中 >= threshold 球计 1 次,按次数取 Top N。
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
    group_map = _build_group_map(pred)

    stats = {}
    group_stats = {}  # (model_id, strategy) -> 该组自身历史总命中 / 期数 / >=threshold 次数
    for rec in records:
        actual = rec.get("actual_result") or {}
        actual_front = set(actual.get("front_balls", []))
        actual_back = set(actual.get("back_balls", []))

        entries = []
        for model in rec.get("models", []):
            model_id = model.get("model_id", "")
            model_name = model.get("model_name", "—")
            for group in model.get("predictions", []):
                hr = group.get("hit_result")
                if not hr:
                    continue
                strategy = group.get("strategy", "—")
                gid = group_map.get(model_id, {}).get(strategy)
                short = _short_model_name(model_id, model_name)
                label = f"{short}·{gid}" if gid else f"{short}·{strategy}"
                gs = group_stats.setdefault(
                    (model_id, strategy), {"total": 0, "games": 0, "full": 0})
                total = hr.get("total_hits", 0)
                gs["total"] += total
                gs["games"] += 1
                if total >= threshold:
                    gs["full"] += 1
                entries.append((
                    model_id, strategy, label,
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
                side_a_hits = len(front_a & actual_front) + len(back_a & actual_back)
                side_b_hits = len(front_b & actual_front) + len(back_b & actual_back)
                front_hits = len((front_a | front_b) & actual_front)
                back_hits = len((back_a | back_b) & actual_back)
                total_hits = front_hits + back_hits
                s = stats.get(key)
                if s is None:
                    s = stats[key] = {
                        "keys": key,
                        "labels": {key_a: label_a, key_b: label_b},
                        "count": 0, "max_total": 0, "max_single": 0,
                        "total_hits": 0, "games": 0,
                    }
                s["games"] += 1
                s["total_hits"] += total_hits
                s["max_total"] = max(s["max_total"], total_hits)
                s["max_single"] = max(s["max_single"], side_a_hits, side_b_hits)
                if total_hits >= threshold:
                    s["count"] += 1

    rows = sorted(
        stats.values(),
        key=lambda s: (
            -s["count"], -s["max_total"], -s["max_single"],
            -(s["total_hits"] / max(s["games"], 1)),
            s["labels"].get(s["keys"][0], ""),
            s["labels"].get(s["keys"][1], ""),
        ),
    )
    # 每个「模型+策略」在 Top 列表中最多出现 2 次，避免同一强组霸榜
    top, appearances = [], {}
    for r in rows:
        if len(top) >= limit:
            break
        if r["count"] <= 0:
            break
        if any(appearances.get(k, 0) >= 2 for k in r["keys"]):
            continue
        for k in r["keys"]:
            appearances[k] = appearances.get(k, 0) + 1
        top.append(r)
    if not top:
        return (f'<p style="color:#94a3b8;font-size:11px;padding:10px">'
                f'(暂无组合单期总命中达到 {threshold} 球)</p>')

    def _mini(group, key):
        if not group:
            return '<span style="color:#94a3b8">暂无最新预测</span>'
        fronts = " ".join(group.get("front_balls", []))
        backs = " ".join(group.get("back_balls", []))
        gs = group_stats.get(key)
        stat = (f'<span style="color:#94a3b8">（{gs["total"]}球/{gs["games"]}期 · '
                f'≥{threshold}球{gs["full"]}次）</span>' if gs else "")
        return (f'<span style="color:#ef4444">前 {fronts}</span> '
                f'<span style="color:#3b82f6">后 {backs}</span>{stat}')

    target_period = (pred or {}).get("target_period", "")
    target_text = f"第 {target_period} 期" if target_period else "最新一期"

    cell = "padding:5px 6px;font-size:10px;line-height:1.5;"
    head = "padding:5px 6px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"
    body = ""
    for i, r in enumerate(top):
        bg = _row_bg(i)
        # 组内按各自命中总球数降序，球数高的排上方
        ordered = sorted(
            r["keys"],
            key=lambda k: (-group_stats.get(k, {}).get("total", 0), r["labels"].get(k, "")),
        )
        blocks = ""
        for idx, key in enumerate(ordered):
            label = r["labels"].get(key, "—")
            mini = _mini(current.get(key), key)
            prefix = "+ " if idx else ""
            margin = "margin-top:2px;" if idx else ""
            blocks += f'''
            <div style="font-weight:600;color:#0f172a;white-space:nowrap;{margin}">{prefix}{label}<span style="margin-left:5px;font-weight:400">{mini}</span></div>'''
        body += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}">{blocks}</td>
          <td style="{cell}text-align:center;color:#475569">{r["count"]}次</td>
          <td style="{cell}text-align:center;color:#475569">{r["max_total"]}球</td>
          <td style="{cell}text-align:center;color:#475569">{r["max_single"]}球</td>
        </tr>'''

    return f'''
    <div style="font-size:10px;color:#94a3b8;margin-bottom:6px">
      沿用最佳组合两两合并逻辑：两个不同「模型+策略」前区、后区号码各自去重，单期「前区+后区」总球数 ≥{threshold} 计 1 次 · 按次数/去重最高/单个模型最高排序取 Top {limit} · 每个模型+策略最多出现 2 次 · 每行一组，号码显示{target_text}前区+后区未开奖预测，括号内为该组自身历史总命中/期数及 ≥{threshold} 球次数
    </div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
      <thead><tr style="background:#f8fafc">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">组合与前区+后区预测</th>
        <th style="{head}text-align:center">总球数≥{threshold}</th>
        <th style="{head}text-align:center">去重最高</th>
        <th style="{head}text-align:center">单个模型最高</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>'''


def _build_latest_ranking_html(hist, limit=10):
    """最新一期命中排行 Top N（仅表格）"""
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:11px;padding:10px">(暂无命中记录)</p>'

    stats = _collect_ranking_stats(records)
    cell = "padding:4px 6px;font-size:11px;line-height:1.5;"
    head = "padding:4px 6px;color:#64748b;font-size:10px;font-weight:600;background:#f8fafc;"

    # 按 总命中球数 → 后区命中数 → 前区命中数 排序
    latest_arr = [s for s in stats.values() if s["current"] > 0]
    latest_arr.sort(
        key=lambda x: (x["current"], x["backHit"], x["currentFront"]),
        reverse=True,
    )
    latest_top = latest_arr[:limit]

    rows = ""
    for i, r in enumerate(latest_top):
        bg = _row_bg(i)
        rows += f'''
        <tr style="background:{bg}">
          <td style="{cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{cell}font-weight:600;color:#0f172a">{r["model"]}</td>
          <td style="{cell}color:#475569">{r["strategy"]}</td>
          <td style="{cell}color:#2563eb;font-family:monospace">{r["frontHits"]}</td>
          <td style="{cell}color:#3b82f6;font-family:monospace">{r["backHits"]}</td>
        </tr>'''

    return f'''
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:12px">
      <thead><tr style="background:#f8fafc">
        <th style="{head}text-align:center">#</th>
        <th style="{head}text-align:left">模型</th>
        <th style="{head}text-align:left">策略</th>
        <th style="{head}text-align:left">命中前区</th>
        <th style="{head}text-align:left">命中后区</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>'''


def _build_history_ranking_html(hist, pred=None, limit=10):
    """历史累计命中排行 Top N（含本期推荐号码）"""
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:11px;padding:10px">(暂无命中记录)</p>'

    stats = _collect_ranking_stats(records)
    dense_cell = "padding:3px 4px;font-size:10px;line-height:1.3;white-space:nowrap;"
    dense_head = "padding:3px 4px;color:#64748b;font-size:9px;font-weight:600;background:#f8fafc;white-space:nowrap;"

    # 当前预测：按 模型+策略 查最新推荐号码；G编号用于策略简写
    current = {}
    for m in (pred or {}).get("models", []):
        for g in m.get("predictions", []):
            current[(m.get("model_id"), g.get("strategy"))] = g
    group_map = _build_group_map(pred)

    # 按 总球数 → 累计后区 排序
    hist_arr = sorted(stats.values(), key=lambda x: (x["total"], x["totalBack"]), reverse=True)
    hist_top = hist_arr[:limit]

    rows = ""
    for i, r in enumerate(hist_top):
        bg = _row_bg(i)
        mid = r.get("model_id")
        gid = group_map.get(mid, {}).get(r["strategy"])
        label = (f'{_short_model_name(mid, r["model"])}·{gid}' if gid
                 else f'{_short_model_name(mid, r["model"])}·{r["strategy"][:4]}')
        group = current.get((mid, r["strategy"]))
        if group:
            fronts = "".join(_ball(b, "front", size=16, font_size=8) for b in group.get("front_balls", []))
            backs = "".join(_ball(b, "back", size=16, font_size=8) for b in group.get("back_balls", []))
            numbers = f'{fronts}<span style="color:#94a3b8;margin:0 1px">|</span>{backs}'
        else:
            numbers = '<span style="color:#94a3b8">—</span>'
        rows += f'''
        <tr style="background:{bg}">
          <td style="{dense_cell}text-align:center;font-weight:700">{_medal(i)}</td>
          <td style="{dense_cell}font-weight:600;color:#0f172a">{label}</td>
          <td style="{dense_cell}">{numbers}</td>
          <td style="{dense_cell}text-align:center;color:#475569">{r["best"]}</td>
          <td style="{dense_cell}text-align:center;color:#475569">{r["totalFront"]}</td>
          <td style="{dense_cell}text-align:center;color:#3b82f6;font-weight:600">{r["totalBack"]}</td>
          <td style="{dense_cell}text-align:center;color:#475569">{r["games"]}</td>
        </tr>'''

    return f'''
    <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:12px">
      <thead><tr style="background:#f8fafc">
        <th style="{dense_head}text-align:center">#</th>
        <th style="{dense_head}text-align:left">模型·策略</th>
        <th style="{dense_head}text-align:left">推荐号码</th>
        <th style="{dense_head}text-align:center">最高</th>
        <th style="{dense_head}text-align:center">累计前</th>
        <th style="{dense_head}text-align:center">累计后</th>
        <th style="{dense_head}text-align:center">期数</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>'''


def _build_model_group_html(hist, limit=8):
    """模型分组统计 — 每个模型的 3 种策略合并后按累计命中排序 Top N"""
    records = hist.get("predictions_history", []) if hist else []
    if not records:
        return '<p style="color:#94a3b8;font-size:11px;padding:10px">(暂无命中记录)</p>'

    stats = {}
    for rec in records:
        for m in rec.get("models", []):
            name = m.get("model_name", "—")
            s = stats.get(name)
            if s is None:
                s = stats[name] = {
                    "model": name, "total": 0, "totalFront": 0,
                    "totalBack": 0, "maxFront": 0,
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
        <th style="{head}text-align:center">期数</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>'''


# ==================== 模型去重命中趋势（折线图） ====================

# 折线配色（按近 10 期去重总和排名 1-5）
_TREND_COLORS = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6"]

# 5x7 点阵数字（仅用于图内坐标轴文字，不依赖系统字体/第三方库）
_DIGIT_FONT = {
    "0": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
}


def _hex_rgb(color):
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


class _Canvas:
    """极简 RGB 画布 + 纯标准库 PNG 编码。

    邮件客户端对 SVG / CSS transform 支持不一致，内嵌 PNG（CID）兼容性最好。
    """

    def __init__(self, w, h, bg=(255, 255, 255)):
        self.w = w
        self.h = h
        self.buf = bytearray(bytes(bg) * (w * h))

    def px(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = color[0]
            self.buf[i + 1] = color[1]
            self.buf[i + 2] = color[2]

    def rect(self, x, y, w, h, color):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy, color)

    def disc(self, cx, cy, r, color):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    self.px(cx + dx, cy + dy, color)

    def hline(self, x0, x1, y, color):
        for x in range(x0, x1 + 1):
            self.px(x, y, color)

    def line(self, x0, y0, x1, y1, color, thickness=5):
        steps = max(abs(x1 - x0), abs(y1 - y0))
        r = max(1, thickness // 2)
        if steps == 0:
            self.disc(x0, y0, r, color)
            return
        for s in range(steps + 1):
            t = s / steps
            self.disc(round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t), r, color)

    def text(self, x, y, text, color, scale=2):
        cx = x
        for ch in str(text):
            pattern = _DIGIT_FONT.get(ch)
            if pattern:
                for ry, row in enumerate(pattern):
                    for rx, bit in enumerate(row):
                        if bit == "1":
                            self.rect(cx + rx * scale, y + ry * scale, scale, scale, color)
            cx += 6 * scale

    def png(self):
        stride = self.w * 3
        raw = bytearray()
        for y in range(self.h):
            raw.append(0)  # filter type: none
            raw += self.buf[y * stride:(y + 1) * stride]

        def chunk(tag, data):
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def _collect_strategy_trend(hist, periods=10, top_n=3):
    """每期每个「模型+策略」：该组号码对当期开奖的命中球数（前区+后区）。

    返回 (期号列表[旧→新], 系列列表)。系列按近 N 期命中总和降序取前 top_n，
    某期该策略无记录时值为 None（折线在该处断开）。
    """
    records = list((hist or {}).get("predictions_history") or [])[:periods]
    if len(records) < 2:
        return [], []

    chronological = list(reversed(records))  # 旧 → 新，便于作图
    period_labels = [str(r.get("target_period", "")) for r in chronological]
    names, values = {}, {}

    for rec in chronological:
        p = str(rec.get("target_period", ""))
        actual = rec.get("actual_result") or {}
        actual_front = set(actual.get("front_balls") or [])
        actual_back = set(actual.get("back_balls") or [])
        for m in rec.get("models") or []:
            mid = m.get("model_id") or m.get("model_name") or "?"
            mname = m.get("model_name") or mid
            for g in m.get("predictions") or []:
                strategy = g.get("strategy") or "—"
                key = (mid, strategy)
                names.setdefault(key, f"{_short_model_name(mid, mname)}·{strategy}")
                hr = g.get("hit_result") or {}
                total = hr.get("total_hits")
                if total is None:  # 兜底：直接按号码计算
                    total = (len(set(g.get("front_balls") or []) & actual_front)
                             + len(set(g.get("back_balls") or []) & actual_back))
                values.setdefault(key, {})[p] = total

    ranked = sorted(
        values,
        key=lambda key: (-sum(values[key].values()), names.get(key, "")),
    )[:top_n]

    series = []
    for i, key in enumerate(ranked):
        vals = [values[key].get(p) for p in period_labels]
        series.append({
            "model_id": key[0],
            "strategy": key[1],
            "name": names.get(key, "—"),
            "values": vals,
            "total": sum(v for v in vals if v is not None),
            "color": _TREND_COLORS[i % len(_TREND_COLORS)],
        })
    return period_labels, series


def _render_trend_png(period_labels, series, scale=2):
    """绘制折线图 PNG。逻辑尺寸 540×190，按 scale 超采样保证清晰度。"""
    w, h = 540, 190
    cv = _Canvas(w * scale, h * scale)
    left, right, top, bottom = 28, w - 20, 10, h - 30
    n = len(period_labels)
    y_max = max(4, max((v for s in series for v in s["values"] if v is not None), default=0))
    grid_vals = sorted({0, y_max // 2, y_max})

    def x_at(i):
        return left + (right - left) * i / (n - 1)

    def y_at(v):
        return bottom - (v / y_max) * (bottom - top)

    grid_color, axis_color, label_color = _hex_rgb("#e2e8f0"), _hex_rgb("#cbd5e1"), _hex_rgb("#94a3b8")

    # 横向网格线 + 纵轴刻度
    for gv in grid_vals:
        gy = round(y_at(gv) * scale)
        cv.hline(left * scale, right * scale, gy, axis_color if gv == 0 else grid_color)
        txt = str(gv)
        tw = (len(txt) * 6 - 1) * scale
        cv.text((left - 5) * scale - tw, gy - 7 * scale // 2 - scale, txt, label_color, scale)

    # 折线（缺失期断开）
    for s in series:
        color = _hex_rgb(s["color"])
        pts = [(round(x_at(i) * scale), None if v is None else round(y_at(v) * scale))
               for i, v in enumerate(s["values"])]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if y0 is None or y1 is None:
                continue
            cv.line(x0, y0, x1, y1, color, thickness=2 * scale)
        for x, y in pts:
            if y is None:
                continue
            cv.disc(x, y, 4 * scale, (255, 255, 255))  # 白色描边，避免线条交汇处糊成一片
            cv.disc(x, y, 3 * scale, color)

    # 横轴期号（后三位，节省空间）
    for i, label in enumerate(period_labels):
        txt = str(label)[-3:]
        tw = (len(txt) * 6 - 1) * scale
        cv.text(round(x_at(i) * scale) - tw // 2, (bottom + 10) * scale, txt, label_color, scale)

    return cv.png()


def _build_trend_chart_html(hist, periods=10, top_n=3, inline_images=None,
                            cid="model-trend-chart"):
    """模型+策略命中趋势折线图（Top 3 模型+策略 × 近 10 期）。

    inline_images 为 None 时使用 data URI（便于预览/测试）；否则写入
    inline_images 列表并使用 CID 引用，由邮件发送层内嵌。
    """
    labels, series = _collect_strategy_trend(hist, periods, top_n)
    if len(labels) < 2 or not series:
        return '<p style="color:#94a3b8;font-size:11px;padding:10px">(暂无足够的命中记录)</p>'

    png = _render_trend_png(labels, series)
    if inline_images is None:
        src = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    else:
        src = f"cid:{cid}"
        inline_images.append({
            "cid": cid, "data": png,
            "filename": "model-trend.png", "mime": "image/png",
        })

    legend = ""
    for s in series:
        legend += (
            f'<span style="display:inline-block;margin:0 10px 4px 0;font-size:10px;'
            f'color:#475569;white-space:nowrap">'
            f'<span style="display:inline-block;width:8px;height:8px;border-radius:2px;'
            f'background:{s["color"]};margin-right:4px;vertical-align:middle"></span>'
            f'{s["name"]} <b style="color:#0f172a">{s["total"]}</b>球</span>'
        )

    return f'''
    <div style="font-size:10px;color:#94a3b8;margin-bottom:6px;line-height:1.5">
      每个「模型+策略」单期命中球数（前区+后区）· 近 {len(labels)} 期
      （横轴为各期期号后三位）· 按命中总和取 Top {len(series)}
    </div>
    <div style="text-align:center;margin-bottom:6px">
      <img src="{src}" width="540" height="190" alt="模型+策略命中趋势折线图"
           style="display:inline-block;width:540px;max-width:100%;height:auto;border:1px solid #e2e8f0;border-radius:8px">
    </div>
    <div style="margin-bottom:10px">{legend}</div>'''


def build_html_digest(data, warnings, generated_at, commit_info=None, inline_images=None):
    """
    构建 HTML 邮件正文。

    参数:
        data: load_data() 返回的 3 个数据源
        warnings: validate_data() 返回的警告列表
        generated_at: 生成时间字符串
        commit_info: 可选，push 通知的提交信息 dict，含 author / message / files / stat
        inline_images: 可选列表。传入时折线图以 CID 内嵌（需发送层支持），
                       不传则退回 data URI（便于预览）
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
        {_SECTION.format("🎯 单球命中")}
        {_build_ball_hit_html(hist.get("predictions_history", []))}
        {_SECTION.format("🏆 最新一期 Top 10")}
        {_build_latest_ranking_html(hist, limit=10)}
        {_SECTION.format("📈 历史累计排行 Top 10")}
        {_build_history_ranking_html(hist, pred, limit=10)}
        {_SECTION.format("📈 模型分组统计 Top 10")}
        {_build_model_group_html(hist, limit=10)}
        {_SECTION.format("📉 模型+策略命中趋势（近 10 期）")}
        {_build_trend_chart_html(hist, periods=10, top_n=3, inline_images=inline_images)}
        {_SECTION.format("🏅 最佳组合")}
        {_build_best_combo_html(hist, pred, limit=10)}
        {_SECTION.format("🏅 最蓝组合")}
        {_build_best_blue_combo_html(hist, pred, limit=10)}
        {_SECTION.format("⚡ 极3组合")}
        {_build_extreme3_combo_html(hist, pred, limit=10)}
        {_SECTION.format("🤖 AI 全部预测")}
        {_build_predictions_html(pred, latest_period, next_period, hist)}
      </div>
      <div style="background:#f8fafc;padding:12px 18px;text-align:center;border-top:1px solid #e2e8f0;border-radius:0 0 12px 12px">
        <p style="font-size:10px;color:#94a3b8;margin:0;line-height:1.6">
          {footer_text}<br>
          <a href="https://github.com/zigzag264/happy7" style="color:#3b82f6;text-decoration:none">happy7</a>
        </p>
      </div>
    </div>'''
    return html