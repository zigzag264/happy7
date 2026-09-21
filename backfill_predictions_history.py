# -*- coding: utf-8 -*-
"""
一次性回补脚本：从 git 提交历史提取各期 ai_predictions.json，
与开奖结果比对后回补到 data/predictions_history.json。

背景：8 月 17 日项目从 LLM 预测切换到本地统计/ML 模型时，
归档逻辑（旧 generate_ai_prediction.py 的 archive_old_prediction）未被迁移，
导致 26095 期之后的命中历史中断。但每天的预测都保留在 bot 提交历史里。

每个目标期选取「开奖时刻之前最后一次提交的预测」版本；
若该期只有开奖后的版本（数据更新延迟），退回最早版本并在输出中标注。

用法：
    python backfill_predictions_history.py          # 预览，不写文件
    python backfill_predictions_history.py --write  # 实际写入
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from strategies.archive import build_history_record, PREDICTIONS_HISTORY_FILE, HISTORY_FILE

AI_PREDICTIONS_PATH = "data/ai_predictions.json"
# 大乐透开奖 21:25 北京时间 = 13:25 UTC
DRAW_CUTOFF_UTC_HOUR = 13
DRAW_CUTOFF_UTC_MINUTE = 25


def git(*args):
    return subprocess.run(["git", *args], cwd=SCRIPT_DIR,
                          capture_output=True, text=True, check=True).stdout


def list_prediction_commits():
    """所有触及 ai_predictions.json 的提交：(sha, commit_time_utc)，新→旧"""
    out = git("log", "--format=%H %cI", "--", AI_PREDICTIONS_PATH)
    commits = []
    for line in out.strip().splitlines():
        sha, ts = line.split(" ", 1)
        dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
        commits.append((sha, dt.astimezone(timezone.utc)))
    return commits


def load_predictions_at(sha):
    try:
        return json.loads(git("show", f"{sha}:{AI_PREDICTIONS_PATH}"))
    except Exception:
        return None


def main():
    write = "--write" in sys.argv

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        draws = json.load(f)["data"]
    draw_by_period = {str(d["period"]): d for d in draws}

    with open(PREDICTIONS_HISTORY_FILE, "r", encoding="utf-8") as f:
        history_data = json.load(f)
    records = history_data.setdefault("predictions_history", [])
    existing = {str(r.get("target_period")) for r in records}
    print(f"已有记录: {sorted(existing)} 期")

    # 每个目标期收集所有预测版本：(commit_time, predictions)
    versions = {}
    for sha, ctime in list_prediction_commits():
        pred = load_predictions_at(sha)
        if not pred or not pred.get("models"):
            continue
        target = str(pred.get("target_period", "") or "")
        if target:
            versions.setdefault(target, []).append((ctime, pred))

    new_records = []
    for period in sorted(versions):
        if period in existing:
            continue
        draw = draw_by_period.get(period)
        if not draw:
            continue  # 未开奖（当前预测），不归档

        cutoff = datetime.strptime(draw["date"], "%Y-%m-%d").replace(
            hour=DRAW_CUTOFF_UTC_HOUR, minute=DRAW_CUTOFF_UTC_MINUTE,
            tzinfo=timezone.utc)
        cands = sorted(versions[period], key=lambda x: x[0])
        pre = [c for c in cands if c[0] < cutoff]
        if pre:
            ctime, chosen = pre[-1]  # 开奖前最后一版
            note = ""
        else:
            ctime, chosen = cands[0]  # 退回最早版本（模型仅用开奖前数据，仍有效）
            note = " ⚠️ 无开奖前版本，用最早版本（提交于开奖后）"

        actual = {"period": draw["period"], "front_balls": draw["front_balls"],
                  "back_balls": draw["back_balls"], "date": draw["date"]}
        rec = build_history_record(chosen, actual)
        best_overall = max((m["best_hit_count"] for m in rec["models"]), default=0)
        print(f"  + 第 {period} 期（{draw['date']} 开奖）← {ctime:%Y-%m-%d %H:%M}UTC 版本"
              f" | {len(rec['models'])} 模型 | 最佳单组 {best_overall} 球{note}")
        new_records.append(rec)

    if not new_records:
        print("没有可回补的记录")
        return

    records.extend(new_records)
    records.sort(key=lambda r: int(str(r.get("target_period")) or 0), reverse=True)

    print(f"\n合计 {len(records)} 期记录（新增 {len(new_records)} 期）")
    if write:
        with open(PREDICTIONS_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, separators=(",", ":"))
        print(f"✅ 已写入 {PREDICTIONS_HISTORY_FILE}")
    else:
        print("（预览模式，加 --write 实际写入）")


if __name__ == "__main__":
    main()
