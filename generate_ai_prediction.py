# -*- coding: utf-8 -*-
"""
大乐透 AI 预测自动生成脚本
自动调用 AI 模型生成下期大乐透预测数据
"""

import argparse
import json
import os
import sys
import time as time_module
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI
from openai import (
    APITimeoutError,
    RateLimitError,
    APIConnectionError,
    InternalServerError,
    AuthenticationError,
    NotFoundError,
    BadRequestError,
)
from typing import Dict, Any, Optional

# ==================== 加载 .env 文件 ====================
load_dotenv()

# ==================== 配置区 ====================
# 默认 API 配置（通过环境变量设置，用于多数模型）
BASE_URL = os.environ.get("AI_BASE_URL")
API_KEY = os.environ.get("AI_API_KEY")

# 模型配置列表（每个模型可单独配置 api_key / base_url，留空则用默认凭证）
# 每模型可单独配置：streaming 支持、超时、温度、重试次数、输出长度上限
MODELS = [
    {
        "id": "glm-5.2",
        "name": "GLM 5.2",
        "model_id": "glm-5.2",
        "supports_streaming": False,  # 流式下 response_format 被忽略，强制非流式
        "timeout": 120,
        "temperature": 0.7,
        "max_retries": 2,
        "max_completion_tokens": 4000,
        "json_mode": True,
    },
    {
        "id": "deepseek-v4-flash",
        "name": "DeepSeek V4 Flash",
        "model_id": "deepseek-v4-flash",
        "supports_streaming": True,
        "timeout": 120,
        "temperature": 0.7,
        "max_retries": 2,
        "max_completion_tokens": 8000,
        "reasoning_effort": "low",
        "json_mode": True,
    },
    ]

# 全局硬性时间预算（秒）：整个预测流程最多运行这么久，防止无限等待
GLOBAL_TIME_BUDGET = 900

# 命令行参数（由 main() 设置）
FORCE_ARCHIVE = False

# 文件路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOTTERY_HISTORY_FILE = os.path.join(SCRIPT_DIR, "data", "lottery_history.json")
AI_PREDICTIONS_FILE = os.path.join(SCRIPT_DIR, "data", "ai_predictions.json")
PREDICTIONS_HISTORY_FILE = os.path.join(SCRIPT_DIR, "data", "predictions_history.json")
TOKEN_USAGE_FILE = os.path.join(SCRIPT_DIR, "data", "token_usage.json")
PROMPT_FILE = os.path.join(SCRIPT_DIR, "doc", "prompt2.0.md")

# ==================== 工具函数 ====================

def load_prompt_template() -> str:
    """加载 Prompt 模板文件"""
    try:
        with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"❌ 加载 Prompt 文件失败: {str(e)}")
        raise

def load_lottery_history() -> Dict[str, Any]:
    """加载历史开奖数据"""
    try:
        with open(LOTTERY_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 加载历史数据失败: {str(e)}")
        raise

def get_next_draw_date() -> str:
    """
    根据大乐透开奖规则（每周一、三、六 21:25）计算下期开奖日期
    返回 YYYY-MM-DD 格式
    """
    today = datetime.now()
    weekday = today.weekday()  # 0=周一, 1=周二, 2=周三, 3=周四, 4=周五, 5=周六, 6=周日

    # 开奖日: 周二(1), 周四(3), 周日(6)
    draw_weekdays = [0, 2, 5]

    # 如果今天是开奖日且未到开奖时间(21:15)，则预测今天
    if weekday in draw_weekdays:
        draw_time = today.replace(hour=21, minute=25, second=0, microsecond=0)
        if today < draw_time:
            return today.strftime("%Y-%m-%d")

    # 否则找下一个开奖日
    for days_ahead in range(1, 8):
        future_date = today + timedelta(days=days_ahead)
        if future_date.weekday() in draw_weekdays:
            return future_date.strftime("%Y-%m-%d")

    # 理论上不会到这里
    return today.strftime("%Y-%m-%d")

def get_openai_client(api_key: str = None, base_url: str = None, default_timeout: int = 120) -> OpenAI:
    """获取 OpenAI 客户端（支持自定义凭证）"""
    return OpenAI(
        api_key=api_key or API_KEY,
        base_url=base_url or BASE_URL,
        timeout=default_timeout,
        max_retries=0
    )

def extract_json_from_response(response_text: str) -> str:
    """
    从 AI 响应中提取 JSON 内容（鲁棒版）
    处理推理模型在最终 JSON 前输出大量分析文字的情况
    """
    text = response_text.strip()

    # 1. 整体就是合法 JSON，直接返回
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    candidates = []

    # 2. 收集所有 ```json / ``` 代码块内容
    idx = 0
    while True:
        fence = text.find("```", idx)
        if fence < 0:
            break
        lang_end = text.find("\n", fence)
        if lang_end < 0:
            break
        lang = text[fence + 3:lang_end].strip()
        content_start = lang_end + 1
        close = text.find("```", content_start)
        if close < 0:
            break
        if lang == "json" or lang == "" or "json" in lang:
            candidates.append(text[content_start:close].strip())
        idx = close + 3

    # 3. 平衡括号扫描：从每个 { 出发，收集能完整闭合的 JSON 对象
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[i:j + 1])
                    break

    # 4. 从后往前尝试解析，优先选择包含 predictions 键的完整预测 JSON
    score_best = None
    fallback_best = None
    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        if isinstance(obj, dict) and "predictions" in obj:
            return cand  # 完整预测结构，直接返回
        if isinstance(obj, dict) and len(obj) > 1 and score_best is None:
            score_best = cand  # 保留较大的 JSON 对象作为备选
        if fallback_best is None:
            fallback_best = cand
    if score_best:
        return score_best
    if fallback_best:
        return fallback_best

    # 5. 兜底：返回最后一个候选（可能解析失败，由调用方处理）
    return candidates[-1] if candidates else text

# ==================== 模型调用核心 ====================

def _build_messages(prompt: str) -> list:
    """构建统一的 messages 列表"""
    return [
        {
            "role": "system",
            "content": "你是一个专业的彩票数据分析师，擅长基于历史数据进行模式分析和预测。请严格按照要求返回 JSON 格式数据，不要有任何额外的解释或说明。禁止输出任何推理、思考、分析过程（reasoning/thinking/CoT）。禁止使用 reasoning、thinking 等标签包裹内容。直接输出最终 JSON 结果。"
        },
        {
            "role": "user",
            "content": prompt
        }
    ]


def _call_with_streaming(client: OpenAI, model_config: dict, prompt: str):
    """流式模式调用，返回 (完整响应文本, token用量dict)"""
    timeout = model_config.get("timeout", 60)
    response_text = ""
    usage = {}

    stream_kwargs = dict(
        model=model_config["id"],
        messages=_build_messages(prompt),
        temperature=model_config.get("temperature", 0.7),
        stream=True,
        stream_options={"include_usage": True},
        timeout=timeout + 30,  # 流式较慢，额外加 30s
    )
    # 推理模型默认会输出大量推理链，
    # 用 reasoning_effort=low 抑制推理深度，大幅减少 token 消耗和耗时
    # 推理模型用 max_completion_tokens 而非 max_tokens 来控制总输出
    if "max_tokens" in model_config:
        stream_kwargs["max_tokens"] = model_config["max_tokens"]
    if "max_completion_tokens" in model_config:
        stream_kwargs["max_completion_tokens"] = model_config["max_completion_tokens"]
    if "reasoning_effort" in model_config:
        stream_kwargs["reasoning_effort"] = model_config["reasoning_effort"]
    if model_config.get("json_mode"):
        stream_kwargs["response_format"] = {"type": "json_object"}

    stream = client.chat.completions.create(**stream_kwargs)

    for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }
            continue
        if chunk.choices:
            delta = chunk.choices[0].delta
            # 部分推理模型把内容输出在
            # reasoning / reasoning_content 字段而非 content 字段
            if delta.content:
                response_text += delta.content
            else:
                rc = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
                if rc:
                    response_text += rc

    return response_text.strip(), usage


def _call_without_streaming(client: OpenAI, model_config: dict, prompt: str):
    """非流式模式调用，返回 (完整响应文本, token用量dict)"""
    timeout = model_config.get("timeout", 60)

    create_kwargs = dict(
        model=model_config["id"],
        messages=_build_messages(prompt),
        temperature=model_config.get("temperature", 0.7),
        stream=False,
        timeout=timeout,
    )
    if "max_tokens" in model_config:
        create_kwargs["max_tokens"] = model_config["max_tokens"]
    if "max_completion_tokens" in model_config:
        create_kwargs["max_completion_tokens"] = model_config["max_completion_tokens"]
    if "reasoning_effort" in model_config:
        create_kwargs["reasoning_effort"] = model_config["reasoning_effort"]
    if model_config.get("json_mode"):
        create_kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**create_kwargs)

    usage = {}
    if getattr(response, "usage", None):
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    msg = response.choices[0].message
    response_text = msg.content or ""
    # 非流式下推理模型可能把内容放在 reasoning / reasoning_content 字段
    if not response_text:
        response_text = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None) or ""

    return response_text.strip(), usage


def _is_retryable_error(e: Exception) -> bool:
    """判断错误是否可重试"""
    return isinstance(e, (APITimeoutError, RateLimitError, APIConnectionError, InternalServerError))


def _is_skip_error(e: Exception) -> bool:
    """判断错误是否应跳过（不重试）"""
    return isinstance(e, (AuthenticationError, NotFoundError, BadRequestError))


def _format_usage(usage: dict) -> str:
    """格式化 token 用量显示"""
    if not usage:
        return "token: N/A"
    p = usage.get("prompt_tokens", 0)
    c = usage.get("completion_tokens", 0)
    t = usage.get("total_tokens", 0)
    return f"token: ↑{p:,} ↓{c:,} ∑{t:,}"


def _parse_prediction(response_text: str, model_name: str) -> Dict[str, Any]:
    """从响应文本中提取并解析 JSON 预测数据，验证包含 predictions 键"""
    json_text = extract_json_from_response(response_text)
    try:
        obj = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"    ❌ {model_name} JSON 解析失败: {e}")
        print(f"    原始响应前500字符:\n{response_text[:500]}")
        raise
    if not isinstance(obj, dict) or "predictions" not in obj:
        print(f"    ❌ {model_name} JSON 缺少 predictions 键")
        print(f"    原始响应前200字符:\n{json_text[:200]}")
        raise json.JSONDecodeError("Missing predictions key", json_text, 0)
    return obj


def call_ai_model(client: OpenAI, model_config: dict, prompt: str) -> Optional[Dict[str, Any]]:
    """
    调用 AI 模型获取预测（带自动流式回退 + 重试）

    流程：
      1. 若模型支持 streaming → 尝试流式调用
      2. 流式失败 → 自动回退到非流式
      3. 对可重试错误（超时/限流/断连/500）进行重试
      4. 对不可重试错误（认证/模型不存在/参数错误）直接跳过
    """
    model_name = model_config["name"]
    max_retries = model_config.get("max_retries", 2)
    usage = {}

    # ---- 尝试流式调用 ----
    if model_config.get("supports_streaming", True):
        for attempt in range(max_retries + 1):
            try:
                t0 = time_module.time()
                response_text, usage = _call_with_streaming(client, model_config, prompt)
                elapsed = time_module.time() - t0
                prediction = _parse_prediction(response_text, model_name)
                print(f"    ✅ 流式成功 | 耗时: {elapsed:.1f}s | 响应: {len(response_text)} 字符 | {_format_usage(usage)}")
                return prediction, usage

            except json.JSONDecodeError:
                # JSON 解析失败 → 回退到非流式模式（非流式可能支持 json_mode）
                print(f"    ⚠️ 流式返回非JSON内容，进入非流式回退")
                break
            except Exception as e:
                if _is_skip_error(e):
                    print(f"    ❌ 流式调用失败 (不可恢复): {type(e).__name__}")
                    print(f"       {e}")
                    break  # 不再尝试流式，进入非流式回退
                if attempt < max_retries:
                    wait = 5 * (2 ** attempt) if isinstance(e, RateLimitError) else 2 ** attempt
                    print(f"    ⚠️ 流式调用失败 (第{attempt+1}次): {type(e).__name__}")
                    print(f"       {e}")
                    print(f"    ℹ️  等待 {wait}s 后重试...")
                    time_module.sleep(wait)
                else:
                    print(f"    ❌ 流式调用失败 ({max_retries+1}次均失败): {type(e).__name__}")
                    print(f"       {e}")

        # 流式全部失败 → 回退到非流式
        print(f"    ℹ️  回退到非流式模式...")

    # ---- 非流式调用 ----
    for attempt in range(max_retries + 1):
        try:
            t0 = time_module.time()
            response_text, usage = _call_without_streaming(client, model_config, prompt)
            elapsed = time_module.time() - t0
            prediction = _parse_prediction(response_text, model_name)
            print(f"    ✅ 非流式成功 | 耗时: {elapsed:.1f}s | 响应: {len(response_text)} 字符 | {_format_usage(usage)}")
            return prediction, usage

        except json.JSONDecodeError:
            # 推理模型行为不稳定，返回非JSON时重试（可能下次成功）
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"    ⚠️ 非流式返回非JSON内容 (第{attempt+1}次)")
                print(f"    ℹ️  等待 {wait}s 后重试...")
                time_module.sleep(wait)
            else:
                print(f"    ❌ 非流式返回非JSON内容 ({max_retries+1}次均失败)，放弃")
                return None, usage
        except Exception as e:
            if _is_skip_error(e):
                print(f"    ❌ 非流式调用失败 (不可恢复): {type(e).__name__}")
                print(f"       {e}")
                return None, usage
            if attempt < max_retries:
                wait = 5 * (2 ** attempt) if isinstance(e, RateLimitError) else 2 ** attempt
                print(f"    ⚠️ 非流式调用失败 (第{attempt+1}次): {type(e).__name__}")
                print(f"       {e}")
                print(f"    ℹ️  等待 {wait}s 后重试...")
                time_module.sleep(wait)
            else:
                print(f"    ❌ 非流式调用失败 ({max_retries+1}次均失败): {type(e).__name__}")
                print(f"       {e}")
                return None, usage

def validate_prediction(prediction: Dict[str, Any]) -> bool:
    """验证预测数据格式（大乐透 5+2）"""
    try:
        # 检查必需字段（模型层不再需要 prediction_date/target_period，顶层已有）
        required_fields = ["model_id", "model_name", "predictions"]
        for field in required_fields:
            if field not in prediction:
                print(f"    ⚠️  缺少字段: {field}")
                return False

        # 检查预测组数量（应4组）
        if len(prediction["predictions"]) != 4:
            print(f"    ⚠️  预测组数量不正确: {len(prediction['predictions'])}（应为4组）")
            return False

        # 检查策略名是否互不相同
        strategies = [g["strategy"] for g in prediction["predictions"]]
        if len(set(strategies)) != 4:
            print(f"    ⚠️  策略名存在重复: {strategies}")
            return False

        # 检查每组预测
        seen_groups = set()
        for group in prediction["predictions"]:
            # 检查前区
            if len(group["front_balls"]) != 5:
                print(f"    ⚠️  前区数量不正确: {len(group['front_balls'])}")
                return False

            # 检查前区是否排序
            sorted_fronts = sorted(group["front_balls"])
            if group["front_balls"] != sorted_fronts:
                print(f"    ⚠️  前区未排序: {group['front_balls']}")
                return False

            # 检查前区范围（01-35）
            for b in group["front_balls"]:
                if not (b.isdigit() and 1 <= int(b) <= 35):
                    print(f"    ⚠️  前区超出范围: {b}")
                    return False

            # 检查后区
            if len(group["back_balls"]) != 2:
                print(f"    ⚠️  后区数量不正确: {len(group['back_balls'])}")
                return False

            # 检查后区范围（01-12）
            for b in group["back_balls"]:
                if not b.isdigit() or not (1 <= int(b) <= 12):
                    print(f"    ⚠️  后区超出范围: {b}")
                    return False

            # 检查后区是否排序
            sorted_backs = sorted(group["back_balls"])
            if group["back_balls"] != sorted_backs:
                print(f"    ⚠️  后区未排序: {group['back_balls']}")
                return False

            # 检查重复组（前区+后区完全相同）
            group_key = (tuple(group["front_balls"]), tuple(group["back_balls"]))
            if group_key in seen_groups:
                print(f"    ⚠️  存在完全重复的预测组: {group['front_balls']} + {group['back_balls']}")
                return False
            seen_groups.add(group_key)

            # 检查前区数组内是否有重复号码
            if len(set(group["front_balls"])) != 5:
                print(f"    ⚠️  前区存在重复号码: {group['front_balls']}")
                return False

            # 检查后区数组内是否有重复号码
            if len(set(group["back_balls"])) != 2:
                print(f"    ⚠️  后区存在重复号码: {group['back_balls']}")
                return False

        return True

    except Exception as e:
        print(f"    ⚠️  验证出错: {str(e)}")
        return False

def _migrate_legacy_token_records(old_records: list) -> list:
    """将旧格式 token_usage 记录（每条一个模型）迁移为按期聚合的新格式"""
    period_map = {}
    for r in old_records:
        key = r.get("target_period", "?")
        if key not in period_map:
            period_map[key] = {
                "period": key,
                "date": r.get("date", ""),
                "models": {},
            }
        mid = r.get("model_id", "")
        if mid not in period_map[key]["models"]:
            period_map[key]["models"][mid] = {
                "name": r.get("model_name", mid),
                "prompt": 0,
                "completion": 0,
                "total": 0,
                "elapsed": 0,
                "retries": 0,
                "ok": False,
            }
        m = period_map[key]["models"][mid]
        m["prompt"] += r.get("prompt_tokens", 0)
        m["completion"] += r.get("completion_tokens", 0)
        m["total"] += r.get("total_tokens", 0)
        m["elapsed"] = max(m["elapsed"], r.get("elapsed_seconds", 0))
        m["retries"] += 1
        if r.get("success"):
            m["ok"] = True
    return list(period_map.values())


def save_token_usage(diagnostics: list, target_period: str, prediction_date: str):
    """将本次各模型的 token 用量按期聚合存入 data/token_usage.json"""
    try:
        # 按模型聚合诊断结果（同一模型可能有多次重试）
        model_map = {}
        for d in diagnostics:
            mid = d.get("model_id", "")
            if mid not in model_map:
                model_map[mid] = []
            model_map[mid].append(d)

        # 构建聚合后的模型数据
        models = {}
        for mid, entries in model_map.items():
            # 取最后一次成功的结果，若全部失败则取最后一次尝试
            last = entries[-1]
            usage = last.get("usage") or {}
            last_ok = last.get("status") == "✅ 成功"

            # 若有成功结果，优先取成功的那次
            success_entries = [e for e in entries if e.get("status") == "✅ 成功"]
            if success_entries:
                chosen = success_entries[-1]
                usage = chosen.get("usage") or {}
            else:
                chosen = last

            models[mid] = {
                "name": chosen.get("name", mid),
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
                "elapsed": round(chosen.get("elapsed", 0), 1),
                "retries": len(entries),
                "ok": last_ok,
            }

        # 读取现有记录，合并或追加
        records = []
        if os.path.exists(TOKEN_USAGE_FILE):
            try:
                with open(TOKEN_USAGE_FILE, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                records = existing.get("records", [])
                # 迁移旧格式：旧记录含 model_id 且无 period 字段，转换为新结构
                if records and "period" not in records[0] and "model_id" in records[0]:
                    records = _migrate_legacy_token_records(records)
            except Exception:
                records = []

        # 检查该期是否已有记录
        existing_idx = None
        for i, r in enumerate(records):
            if r.get("period") == target_period:
                existing_idx = i
                break

        new_record = {
            "period": target_period,
            "date": prediction_date,
            "models": models,
        }

        if existing_idx is not None:
            # 合并：更新已有期的模型数据（新增或覆盖）
            records[existing_idx]["models"].update(models)
            records[existing_idx]["date"] = prediction_date
        else:
            records.insert(0, new_record)

        # 只保留最近 50 期记录
        records = records[:50]

        with open(TOKEN_USAGE_FILE, 'w', encoding='utf-8') as f:
            f.write(_compact_json({"records": records}))
        print(f"  📊 已按期聚合 {len(diagnostics)} 条诊断记录 → token_usage.json（{len(models)} 个模型）")
    except Exception as e:
        print(f"  ⚠️  保存 token 用量失败: {str(e)}")


def format_compact_history(history_data: list) -> str:
    """
    将历史数据压缩为紧凑格式，大幅减少 token 占用。
    原格式：30期完整 JSON（含日期字段）约 7KB
    压缩后：约 1.2KB
    """
    lines = ["期号|前区|后区"]
    for draw in history_data:
        period = draw.get("period", "?")
        fronts = " ".join(draw.get("front_balls", []))
        backs = " ".join(draw.get("back_balls", []))
        lines.append(f"{period}|{fronts}|{backs}")
    return "\n".join(lines)


def generate_predictions() -> Dict[str, Any]:
    """生成所有模型的预测"""
    print("\n" + "="*50)
    print("🤖 大乐透 AI 预测自动生成")
    print("="*50 + "\n")

    # 加载 Prompt 模板
    print("📄 加载 Prompt 模板...")
    try:
        prompt_template = load_prompt_template()
        print(f"  ✓ Prompt 模板加载成功 ({len(prompt_template)} 字符)\n")
    except Exception as e:
        print(f"  ✗ Prompt 模板加载失败: {str(e)}\n")
        return None

    # 加载历史数据
    print("📊 加载历史开奖数据...")
    lottery_data = load_lottery_history()

    # 归档旧预测（如果已开奖）
    archived = archive_old_prediction(lottery_data, force=FORCE_ARCHIVE)

    # 获取下期信息
    next_draw = lottery_data.get("next_draw", {})
    target_period = next_draw.get("next_period", "")
    target_date = next_draw.get("next_date_display", "")

    if not target_period:
        print("❌ 无法获取下期期号信息")
        return None

    print(f"🎯 目标期号: {target_period}")
    print(f"📅 开奖日期: {target_date}")
    print(f"📝 历史数据: 最近 {len(lottery_data.get('data', []))} 期\n")

    # 准备历史数据（最近30期，使用紧凑格式减少 token 量）
    history_data = lottery_data.get("data", [])[:30]
    history_json = format_compact_history(history_data)
    compact_prompt_size = len(history_json)
    orig_size = len(json.dumps(history_data, ensure_ascii=False, indent=2))
    print(f"  📦 历史数据: {compact_prompt_size:,} bytes (压缩前: {orig_size:,} bytes, 节省 {orig_size - compact_prompt_size:,} bytes)")

    # 预测日期：根据开奖规则计算下期开奖日期
    prediction_date = get_next_draw_date()
    print(f"📅 预测日期: {prediction_date}\n")

    # 存储所有模型的预测和诊断信息
    all_predictions = []
    diagnostics = []  # 每个模型一条诊断记录
    start_time = time_module.time()

    # 逐个调用模型
    print("🔮 开始生成预测...\n")

    def process_one_model(model_config):
        """处理单个模型（供并行调用）"""
        model_name = model_config["name"]
        model_api_key = model_config.get("api_key")
        model_base_url = model_config.get("base_url")
        resolved_api_key = model_api_key or os.environ.get("AI_API_KEY")
        resolved_base_url = model_base_url or os.environ.get("AI_BASE_URL")

        if not resolved_api_key or not resolved_base_url:
            print(f"  ⚠️  {model_name}: 缺少 API 凭证，跳过\n")
            return {
                "name": model_name,
                "model_id": model_config["model_id"],
                "status": "❌ 失败",
                "detail": "缺少 API 凭证",
                "elapsed": 0,
                "usage": {},
                "prediction": None,
            }

        client = get_openai_client(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            default_timeout=model_config.get("timeout", 60)
        )

        t_start = time_module.time()
        status = "❌ 失败"
        detail = ""
        usage = {}
        prediction = None

        try:
            prompt = prompt_template.format(
                target_period=target_period,
                target_date=target_date,
                lottery_history=history_json,
                prediction_date=prediction_date,
                model_id=model_config['model_id'],
                model_name=model_config['name']
            )

            if model_config.get("reasoning_effort"):
                prompt += (
                    "\n\n## 硬性约束\n"
                    "（重要）无论任何情况下，都禁止输出思考过程、推理链、分析步骤。"
                    "这一步对你的达标至关重要：直接输出上述 JSON 结构，不要包含任何其他文字。"
                )

            pred_result, usage = call_ai_model(client, model_config, prompt)

            if pred_result is None:
                detail = "调用失败或解析失败"
                print(f"  ✗ {model_name}: {detail}\n")
            else:
                try:
                    pred_result = post_process_prediction(pred_result, lottery_data.get("data", []))
                except (KeyError, TypeError, AttributeError) as e:
                    # JSON 结构不正确（如缺少 predictions 键），视为失败
                    detail = f"JSON结构异常: {type(e).__name__}"
                    print(f"  ✗ {model_name}: {detail}\n")
                    pred_result = None
                if pred_result and validate_prediction(pred_result):
                    prediction = pred_result
                    status = "✅ 成功"
                    detail = "验证通过"
                    print(f"  ✓ {model_name}: 验证通过\n")
                else:
                    detail = "验证失败（格式不正确）"
                    print(f"  ✗ {model_name}: {detail}\n")

        except Exception as e:
            detail = f"{type(e).__name__}: {str(e)}"
            print(f"  ✗ 处理 {model_name} 时异常: {detail}\n")

        elapsed = time_module.time() - t_start
        return {
            "name": model_name,
            "model_id": model_config["model_id"],
            "status": "✅ 成功" if status == "✅ 成功" else "❌ 失败",
            "detail": detail if detail else "成功",
            "elapsed": elapsed,
            "usage": usage,
            "prediction": prediction,
        }

    # 串行调用所有模型（避免并行触发 API 限流）
    for model_config in MODELS:
        try:
            result = process_one_model(model_config)
            diagnostics.append(result)
            if result["prediction"]:
                all_predictions.append(result["prediction"])
        except Exception as e:
            model_name = model_config.get("name", "?")
            print(f"  ✗ {model_name} 执行异常: {e}\n")
            diagnostics.append({
                "name": model_name,
                "model_id": model_config.get("model_id", ""),
                "status": "❌ 失败",
                "detail": f"异常: {e}",
                "elapsed": 0,
                "usage": {},
            })

    # 打印诊断汇总表
    print("\n" + "=" * 60)
    print("📊 模型调用诊断汇总")
    print("=" * 60)
    for d in diagnostics:
        elapsed_str = f"{d['elapsed']:.1f}s" if d['elapsed'] < 60 else f"{d['elapsed']/60:.1f}min"
        token_str = _format_usage(d.get("usage", {}))
        print(f"  {d['status']} | {d['name']:<8s} | {elapsed_str:>7s} | {token_str} | {d['detail']}")
    print("=" * 60)
    print(f"  总计: {sum(1 for d in diagnostics if d['status'] == '✅ 成功')}/{len(diagnostics)} 个模型成功\n")

    # 记录 token 用量（无论是否全部成功）
    save_token_usage(diagnostics, target_period, prediction_date)

    # 构建最终输出
    if not all_predictions:
        print("❌ 没有成功生成任何预测")
        if archived:
            # 旧预测已归档但新预测失败，清空文件避免脏数据进入邮件推送
            print("  ℹ️  旧预测已被归档，正在清空 ai_predictions.json...")
            _clear_predictions_file()
        return None

    result = {
        "prediction_date": prediction_date,
        "target_period": target_period,
        "models": all_predictions
    }

    print(f"✅ 成功生成 {len(all_predictions)}/{len(MODELS)} 个模型的预测\n")
    return result

def calculate_hit_result(prediction_group: Dict[str, Any], actual_result: Dict[str, Any]) -> Dict[str, Any]:
    """计算单组预测的命中结果（大乐透 5+2）"""
    front_hits = [b for b in prediction_group["front_balls"] if b in actual_result["front_balls"]]
    back_hits = [b for b in prediction_group["back_balls"] if b in actual_result["back_balls"]]

    return {
        "front_hits": front_hits,
        "front_hit_count": len(front_hits),
        "back_hits": back_hits,
        "back_hit_count": len(back_hits),
        "total_hits": len(front_hits) + len(back_hits)
    }

def _front_hits_between(group_fronts: list, draw_fronts: list) -> int:
    """计算两组前区号码的重合数"""
    return len(set(group_fronts) & set(draw_fronts))


def _repair_group(group: Dict[str, Any], recent_draws: list) -> Dict[str, Any]:
    """
    修复与近期开奖过于相似的预测组（大乐透 5+2）。
    将重合过多的前区号码替换为同区间内近期出现较少的号码。
    """
    # 找出最近3期开奖
    last3 = [d for d in recent_draws[:3] if isinstance(d, dict) and "front_balls" in d]
    if not last3:
        return group

    new_fronts = list(group["front_balls"])
    new_backs = list(group["back_balls"])

    # 检查前区：与任何一期重合 ≥4 则修复（5个中4个已高度重合）
    for draw in last3:
        hits = _front_hits_between(new_fronts, draw["front_balls"])
        if hits >= 4:
            # 找出重合的号码
            overlap = [b for b in new_fronts if b in draw["front_balls"]]
            # 替换 1-2 个重合号码
            replacements_needed = min(hits - 3, 2)  # 降到 3 重合以下
            for _ in range(replacements_needed):
                if not overlap:
                    break
                to_replace = overlap.pop(0)
                # 确定该号码所在的区间
                n = int(to_replace)
                if n <= 12:
                    candidates = [f"{i:02d}" for i in range(1, 13)]
                elif n <= 24:
                    candidates = [f"{i:02d}" for i in range(13, 25)]
                else:
                    candidates = [f"{i:02d}" for i in range(25, 36)]

                # 排除当前组已有的号码
                candidates = [c for c in candidates if c not in new_fronts]
                # 排除近期开奖中该区间出现过的号码
                for d in last3:
                    candidates = [c for c in candidates if c not in d["front_balls"]]

                if candidates:
                    # 选区间内数值最接近的号码
                    candidates.sort(key=lambda c: abs(int(c) - n))
                    new_fronts.remove(to_replace)
                    new_fronts.append(candidates[0])

            new_fronts.sort()

    # 检查后区：与最近3期任何一期后区号码重合则替换
    if new_backs and any(b in new_backs for d in last3 for b in d.get("back_balls", [])):
        all_backs = [f"{i:02d}" for i in range(1, 13)]
        used = set()
        for d in last3:
            for b in d.get("back_balls", []):
                used.add(b)
        available = [b for b in all_backs if b not in used and b not in new_backs]
        if available:
            # 替换后区号码
            new_backs = sorted(available[:2])

    return {
        "group_id": group["group_id"],
        "strategy": group["strategy"],
        "front_balls": new_fronts,
        "back_balls": new_backs,
        "description": group.get("description", "")
    }


def post_process_prediction(prediction: Dict[str, Any], history_data: list) -> Dict[str, Any]:
    """
    对模型预测进行后处理（大乐透 5+2）：
    1. 去重：移除前区+后区完全相同的重复组
    2. 防复读：修复与近期开奖太相似的组
    3. 补齐：确保总是 4 组
    """
    recent_draws = [d for d in history_data if isinstance(d, dict) and "front_balls" in d and "back_balls" in d]

    # 1. 去重
    seen = set()
    unique_groups = []
    for g in prediction["predictions"]:
        key = (tuple(g["front_balls"]), tuple(g["back_balls"]))
        if key not in seen:
            seen.add(key)
            unique_groups.append(g)
        else:
            print(f"    ⚠️  发现重复组 (策略: {g['strategy']})，已移除")

    # 2. 策略名归一化：确保4组使用不同策略名（热号/平衡/周期/综合）
    canonical_strategies = ["热号追随者", "平衡策略师", "周期理论家", "综合决策者"]
    # 找出缺失的策略名和重复策略
    used = [g["strategy"] for g in unique_groups]
    missing = [s for s in canonical_strategies if s not in used]
    # 找出重复的策略并替换为缺失策略名
    for i, g in enumerate(unique_groups):
        if g["strategy"] not in canonical_strategies:
            if missing:
                old = g["strategy"]
                g["strategy"] = missing.pop(0)
                print(f"    ⚠️  策略「{old}」不规范，更名为「{g['strategy']}」")
        elif used.count(g["strategy"]) > 1:
            if missing:
                old = g["strategy"]
                g["strategy"] = missing.pop(0)
                print(f"    ⚠️  策略「{old}」重复，更名为「{g['strategy']}」")

    # 3. 防复读修复
    repaired = []
    for g in unique_groups:
        # 检查是否与最近3期过于相似
        needs_repair = False
        for draw in recent_draws[:3]:
            if _front_hits_between(g["front_balls"], draw["front_balls"]) >= 4:
                needs_repair = True
                print(f"    ⚠️  策略「{g['strategy']}」与 {draw.get('period', '?')} 期前区重合 ≥4，执行修复")
                break
        if needs_repair:
            repaired.append(_repair_group(g, recent_draws))
        else:
            repaired.append(g)

    # 4. 补齐到 4 组（如果去重或策略名修正后不足）
    while len(repaired) < 4:
        # 以最后一组为蓝本生成变体
        template = repaired[-1] if repaired else unique_groups[0]
        # 计算当前已使用的策略名，分配一个缺失的规范策略名
        used_strategies = [g["strategy"] for g in repaired]
        missing_strategies = [s for s in canonical_strategies if s not in used_strategies]
        fill_strategy = missing_strategies[0] if missing_strategies else template["strategy"]
        variant = {
            "group_id": len(repaired) + 1,
            "strategy": fill_strategy,
            "front_balls": list(template["front_balls"]),
            "back_balls": list(template["back_balls"]),
        }
        # 交换前区中的两个不同区间号码
        fronts = list(variant["front_balls"])
        # 找一个可替换的号码
        all_fronts = [f"{i:02d}" for i in range(1, 36)]
        available = [r for r in all_fronts if r not in fronts]
        if available:
            # 替换第 (len(repaired) % 5) 个位置
            idx = len(repaired) % 5
            old = fronts[idx]
            # 找同区间可用的
            n = int(old)
            if n <= 12:
                pool = [r for r in available if 1 <= int(r) <= 12]
            elif n <= 24:
                pool = [r for r in available if 13 <= int(r) <= 24]
            else:
                pool = [r for r in available if 25 <= int(r) <= 35]
            if pool:
                pool.sort(key=lambda r: abs(int(r) - n))
                fronts[idx] = pool[0]
                fronts.sort()
        variant["front_balls"] = fronts
        variant["back_balls"] = list(template["back_balls"])
        variant["description"] = template.get("description", "")
        repaired.append(variant)
        print(f"    ⚠️  补齐第 {len(repaired)} 组预测")

    # 重新编号 group_id
    for i, g in enumerate(repaired):
        g["group_id"] = i + 1

    prediction["predictions"] = repaired
    return prediction


def archive_old_prediction(lottery_data: Dict[str, Any], force: bool = False) -> bool:
    """
    将旧预测归档到历史记录（如果已开奖）。
    返回是否成功归档。

    force: 强制归档（即使预测期尚未开奖，也会用当前预测归档）
    """
    try:
        # 检查是否存在旧预测文件
        if not os.path.exists(AI_PREDICTIONS_FILE):
            print("  ℹ️  没有旧预测需要归档\n")
            return False

        # 读取旧预测
        with open(AI_PREDICTIONS_FILE, 'r', encoding='utf-8') as f:
            old_predictions = json.load(f)

        old_target_period = old_predictions.get("target_period")
        if not old_target_period:
            print("  ⚠️  旧预测文件格式异常，跳过归档\n")
            return False

        # 检查该期号是否已开奖
        latest_period = lottery_data.get("data", [{}])[0].get("period")
        if not latest_period:
            print("  ⚠️  历史数据中无期号信息，跳过归档\n")
            return False

        if int(old_target_period) > int(latest_period):
            # 兜底检测：若预测日期已过去较久仍未见开奖，多半是爬虫未更新数据
            try:
                pred_date = datetime.strptime(old_predictions.get("prediction_date", ""), "%Y-%m-%d")
                days_passed = (datetime.now() - pred_date).days
            except Exception:
                days_passed = 0

            if days_passed >= 3:
                print(f"  ⚠️  旧预测期号 {old_target_period} 的预测日期已过去 {days_passed} 天仍未见开奖数据！")
                print(f"  ⚠️  最新期号仅到 {latest_period}，请先运行爬虫更新开奖数据 (fetch_history/fetch_lottery_history.py)")
                print(f"  ⚠️  否则该期预测将无法自动归档")
                if force:
                    print(f"  → 已启用 --force-archive，跳过开奖检查，直接归档\n")
                else:
                    print(f"  → 可使用 --force-archive 参数强制归档\n")
                    return False
            elif force:
                print(f"  ℹ️  旧预测期号 {old_target_period} 尚未开奖，但 --force-archive 已启用，继续归档...")
            else:
                print(f"  ℹ️  旧预测期号 {old_target_period} 尚未开奖（最新期号 {latest_period}），无需归档")
                print(f"  → 开奖后再次运行本脚本会自动归档，或使用 --force-archive 参数强制归档\n")
                return False

        print(f"  📦 旧预测期号 {old_target_period} 已开奖，开始归档...")

        # 查找实际开奖结果
        actual_result = None
        for draw in lottery_data.get("data", []):
            if draw.get("period") == old_target_period:
                actual_result = draw
                break

        if not actual_result:
            print(f"  ⚠️  找不到期号 {old_target_period} 的开奖结果，跳过归档\n")
            return False

        # 读取历史记录文件
        history_data = {"predictions_history": []}
        if os.path.exists(PREDICTIONS_HISTORY_FILE):
            with open(PREDICTIONS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                history_data = json.load(f)

        # 检查该期号是否已存在
        existing_record = next((r for r in history_data["predictions_history"]
                               if r["target_period"] == old_target_period), None)

        if existing_record:
            print(f"  ℹ️  期号 {old_target_period} 已存在于历史记录中\n")
            return False

        # 为每个模型计算命中结果
        models_with_hits = []
        for model_data in old_predictions.get("models", []):
            # 为每组预测计算命中
            predictions_with_hits = []
            for pred_group in model_data.get("predictions", []):
                pred_with_hit = pred_group.copy()
                pred_with_hit["hit_result"] = calculate_hit_result(pred_group, actual_result)
                predictions_with_hits.append(pred_with_hit)

            # 找出最佳预测组
            best_pred = max(predictions_with_hits, key=lambda p: p["hit_result"]["total_hits"])

            models_with_hits.append({
                "model_id": model_data.get("model_id"),
                "model_name": model_data.get("model_name"),
                "predictions": predictions_with_hits,
                "best_group": best_pred["group_id"],
                "best_hit_count": best_pred["hit_result"]["total_hits"]
            })

        # 创建新的历史记录
        new_record = {
            "prediction_date": old_predictions.get("prediction_date"),
            "target_period": old_target_period,
            "actual_result": actual_result,
            "models": models_with_hits
        }

        # 插入到历史记录顶部
        history_data["predictions_history"].insert(0, new_record)

        # 保存历史记录（紧凑格式）
        with open(PREDICTIONS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            f.write(_compact_json(history_data))

        print(f"  ✅ 已将期号 {old_target_period} 的预测归档到历史记录")
        print(f"  📊 归档模型数: {len(models_with_hits)}\n")
        return True

    except Exception as e:
        print(f"  ⚠️  归档旧预测时出错: {str(e)}")
        print(f"  继续生成新预测...\n")
        return False

def _clear_predictions_file():
    """清空当前 AI 预测文件（写入空结构），避免邮件推送展示过期货。"""
    empty = {
        "prediction_date": "",
        "target_period": "",
        "models": []
    }
    try:
        with open(AI_PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
            f.write(_compact_json(empty))
        print(f"  ✓ 已清空 {os.path.basename(AI_PREDICTIONS_FILE)}")
    except Exception as e:
        print(f"  ⚠️  清空预测文件失败: {e}")

def _strip_model_redundant_fields(predictions: Dict[str, Any]) -> Dict[str, Any]:
    """移除模型层冗余的 prediction_date/target_period（已在顶层存储）"""
    for model in predictions.get("models", []):
        model.pop("prediction_date", None)
        model.pop("target_period", None)
    return predictions


def _compact_json(data) -> str:
    """紧凑 JSON 序列化（无空格换行，适合生产环境）"""
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


def save_predictions(predictions: Dict[str, Any]):
    """保存预测数据到文件（保留已有的统计模型）"""
    try:
        print("💾 保存预测数据...")

        # 创建备份（写入 archive 目录，保留漂亮格式方便人工查验）
        if os.path.exists(AI_PREDICTIONS_FILE):
            archive_dir = os.path.join(os.path.dirname(AI_PREDICTIONS_FILE), "archive")
            os.makedirs(archive_dir, exist_ok=True)
            backup_file = os.path.join(archive_dir, f"ai_predictions_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(AI_PREDICTIONS_FILE, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            print(f"  ✓ 已创建备份: {os.path.basename(backup_file)}")

            # 从现有文件中提取统计模型（非 LLM 模型），保留它们
            existing_models = backup_data.get("models", [])
            stat_models = [m for m in existing_models
                          if m.get("model_type") in ("statistical", "ml", "deep")]
            if stat_models:
                print(f"  📦 保留 {len(stat_models)} 个统计/ML模型")
                # 记录已存在的 model_id，避免重复
                existing_ids = {m.get("model_id") for m in stat_models if m.get("model_id")}
                new_llm = predictions.get("models", [])
                added = 0
                for m in new_llm:
                    mtype = m.get("model_type", "llm")
                    mid = m.get("model_id", "")
                    if mtype not in ("statistical", "ml", "deep") and mid not in existing_ids:
                        stat_models.append(m)
                        if mid:
                            existing_ids.add(mid)
                            added += 1
                if added:
                    print(f"  ➕ 新增 {added} 个 LLM 模型")
                predictions["models"] = stat_models

        # 剥离模型层冗余字段
        predictions = _strip_model_redundant_fields(predictions)

        # 保存新预测（紧凑格式，生产环境用）
        with open(AI_PREDICTIONS_FILE, 'w', encoding='utf-8') as f:
            f.write(_compact_json(predictions))

        print(f"  ✓ 已保存到: {AI_PREDICTIONS_FILE}（紧凑格式，{len(_compact_json(predictions))} bytes）\n")

    except Exception as e:
        print(f"❌ 保存失败: {str(e)}")
        raise

def main():
    """主函数"""
    global FORCE_ARCHIVE

    parser = argparse.ArgumentParser(description='大乐透 AI 预测自动生成')
    parser.add_argument('--force-archive', action='store_true',
                        help='强制归档当前预测（即使尚未开奖），用于手动备份')
    args = parser.parse_args()

    if args.force_archive:
        FORCE_ARCHIVE = True
        print("=" * 50)
        print("🔧 --force-archive 模式已启用")
        print("=" * 50 + "\n")

    try:
        # 生成预测
        predictions = generate_predictions()

        if predictions:
            # 保存预测
            save_predictions(predictions)

            print("="*50)
            print("🎉 预测生成完成！")
            print("="*50 + "\n")

            # 显示预测摘要
            print("📋 预测摘要:")
            print(f"  期号: {predictions['target_period']}")
            print(f"  日期: {predictions['prediction_date']}")
            print(f"  模型数量: {len(predictions['models'])}")
            for model in predictions['models']:
                print(f"    - {model['model_name']}")
            print()
        else:
            print("❌ 预测生成失败")

    except Exception as e:
        print(f"\n❌ 程序执行出错: {str(e)}")
        raise

if __name__ == "__main__":
    main()
