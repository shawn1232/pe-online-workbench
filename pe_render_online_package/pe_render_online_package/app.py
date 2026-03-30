
import base64
import copy
import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, jsonify, render_template, request, session

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", APP_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SEED_REPORT_PATH = APP_DIR / "data" / "seed_report.json"
REPORT_CACHE_PATH = DATA_DIR / "report_cache.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
HISTORY_PATH = DATA_DIR / "history.json"

DEFAULT_SETTINGS = {
    "brief": "请围绕中国一级PE可投的工业科技/通用设备相邻方向，优先识别过去180天内公开证据明显增强的细分赛道与未上市公司；重点关注信息采集与赛道映射、未上市候选池构建、横向比较与排除逻辑、解释型评分引擎、最终标的推荐与动态跟踪五个模块的完整闭环。",
    "scope": "工业机器视觉、协作机器人与柔性自动化、智能仓储与厂内物流、工业软件、在线检测与工业感知",
    "stage_pref": "优先B轮前后，也接受A+至C轮；上市公司只作参照，不进入一级推荐主体",
    "geography": "中国",
    "max_companies": 8,
    "model": os.getenv("OPENAI_MODEL", "gpt-4.1"),
    "allowed_domains": "",
    "exclude_directions": "不沿用已有研究中的通用设备私有方向；尽量输出新的可讲述赛道",
    "exclude_companies": "",
    "openai_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "saved_api_key": "",
    "admin_note": "公开页默认展示最近一次成功结果；管理员可在后台点击“立即更新”。"
}

DIMENSION_WEIGHTS = {
    "sector_prosperity": 15,
    "profit_pool": 15,
    "high_end_attribute": 12,
    "customer_validation": 14,
    "commercialization_progress": 10,
    "investability": 10,
    "exit_feasibility": 10,
    "competitive_position": 8,
    "information_sufficiency": 6,
}

DIMENSION_LABELS = {
    "sector_prosperity": "赛道景气",
    "profit_pool": "利润池",
    "high_end_attribute": "高端属性",
    "customer_validation": "客户验证",
    "commercialization_progress": "商业化进度",
    "investability": "可投性",
    "exit_feasibility": "退出可行性",
    "competitive_position": "竞争卡位",
    "information_sufficiency": "信息充分度",
}

DIMENSION_GUIDE = {
    "sector_prosperity": "政策催化、需求扩张、渗透率提升、产业景气度",
    "profit_pool": "价值节点位置、议价能力、毛利厚度、后市场厚度",
    "high_end_attribute": "精度、可靠性、认证壁垒、工艺 know-how、国产替代难度",
    "customer_validation": "标杆客户、验证周期、导入深度、复购或复制性",
    "commercialization_progress": "量产交付、订单转化、渠道/交付体系、规模化能力",
    "investability": "轮次、股权结构、融资节奏、接触可能性、估值可谈性",
    "exit_feasibility": "产业买家密度、IPO 可比、并购承接、退出路径清晰度",
    "competitive_position": "差异化、行业地位、客户心智、平台化延展",
    "information_sufficiency": "公开证据完整性、交叉验证程度、信息一致性",
}

WEIGHT_BAND = {
    "sector_prosperity": "高",
    "profit_pool": "高",
    "high_end_attribute": "高",
    "customer_validation": "高",
    "commercialization_progress": "中",
    "investability": "中",
    "exit_feasibility": "中",
    "competitive_position": "中",
    "information_sufficiency": "低",
}

EXCLUSION_PENALTY = {
    "配套功能件型": 4,
    "工程项目型": 4,
    "宽口径拼装型": 4,
    "标准耗材型": 4,
    "独立客户入口弱": 4,
    "利润池过薄": 4,
    "退出锚缺失": 4,
    "上市公司仅作参照": 20,
}

TRACKING_ORDER = {"立项": 0, "深跟": 1, "约访": 2, "补证": 3, "观察": 4, "放弃": 5}

MODULES = [
    {
        "title": "模块1：信息采集与赛道映射",
        "desc": "围绕政策、行业协会、展会发布、公司官网、融资事件、客户验证、招投标、年报/招股书等公开信息进行持续采集，并映射至既有赛道库，识别其属于哪个细分赛道、对应哪条投资主线，以及属于需求催化、技术突破、客户验证还是资本事件，为后续候选标的筛选提供结构化入口。",
    },
    {
        "title": "模块2：未上市候选公司池构建",
        "desc": "以未上市公司为核心筛选对象，优先纳入处于B轮前后、具备一定客户验证、产品卡位清晰、业务相对聚焦、未来具备继续融资或退出可能的公司；上市公司仅作为产业参照、估值锚和退出映射，不作为本轮一级候选筛选主体。通过该模块形成每个细分赛道的核心候选公司池，而非单点拍脑袋选公司。",
    },
    {
        "title": "模块3：横向比较与排除逻辑生成",
        "desc": "围绕公司定位、核心产品、高端属性、客户验证、商业化成熟度、融资阶段、行业地位、退出可行性等维度，对候选公司进行横向比较，并同步生成排除逻辑。系统不仅回答“为什么选这家公司”，也回答“为什么没有选其他公司”，从而提升标的选择过程的完整性与说服力。",
    },
    {
        "title": "模块4：解释型评分引擎",
        "desc": "针对赛道景气、利润池、高端属性、客户验证、商业化进度、可投性、退出可行性、竞争卡位和信息充分度等维度进行结构化赋分。评分不是简单给总分，而是要求每一项分数均可追溯至对应公开证据，实现“可打分、可解释、可复核”的研究闭环。",
    },
    {
        "title": "模块5：最终标的推荐与动态跟踪",
        "desc": "在候选池、横向比较和评分结果基础上，输出当前赛道重点跟踪公司、备选公司和最终推荐标的，并明确推荐理由、核心证据、仍待核实的信息缺口，以及哪些变量变化可能导致推荐切换。系统当前以半自动在线工作台形式验证逻辑闭环，未来可进一步升级为动态更新的一级标的发现系统。",
    },
]

JOBS = {}
JOBS_LOCK = threading.Lock()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
app.config["JSON_AS_ASCII"] = False


def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def atomic_save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path, default):
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return copy.deepcopy(default)


def app_secret():
    return os.getenv("APP_SECRET_KEY") or app.secret_key


def fernet_from_secret(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_text(plain: str) -> str:
    if not plain:
        return ""
    return fernet_from_secret(app_secret()).encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    try:
        return fernet_from_secret(app_secret()).decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def load_settings():
    data = load_json(SETTINGS_PATH, DEFAULT_SETTINGS)
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    merged.update(data or {})
    return merged


def save_settings(data):
    merged = load_settings()
    merged.update(data or {})
    atomic_save_json(SETTINGS_PATH, merged)
    return merged


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return key[:3] + "***"
    return key[:7] + "…" + key[-4:]


def get_effective_api_key(settings=None):
    env_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if env_key:
        return env_key, "env"
    settings = settings or load_settings()
    saved = decrypt_text(settings.get("saved_api_key", ""))
    if saved:
        return saved, "encrypted_store"
    return "", "missing"


def admin_password():
    return (os.getenv("ADMIN_PASSWORD") or "").strip()


def is_admin():
    return bool(session.get("is_admin"))


def score_bucket(score: float):
    if score >= 78:
        return "最终推荐"
    if score >= 66:
        return "重点跟踪"
    if score >= 54:
        return "备选观察"
    return "排除/低优先级"


def build_schema():
    score_required = list(DIMENSION_WEIGHTS.keys())
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "search_context": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "run_date": {"type": "string"},
                    "search_scope": {"type": "string"},
                    "headline": {"type": "string"},
                    "system_positioning": {"type": "string"},
                    "method_summary": {"type": "string"}
                },
                "required": ["run_date", "search_scope", "headline", "system_positioning", "method_summary"]
            },
            "top_sectors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "sector": {"type": "string"},
                        "investment_mainline": {"type": "string"},
                        "signal_type": {"type": "string"},
                        "why_now": {"type": "string"}
                    },
                    "required": ["sector", "investment_mainline", "signal_type", "why_now"]
                }
            },
            "candidate_companies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "sector": {"type": "string"},
                        "value_node": {"type": "string"},
                        "listed_status": {"type": "string"},
                        "stage": {"type": "string"},
                        "location": {"type": "string"},
                        "core_product": {"type": "string"},
                        "company_positioning": {"type": "string"},
                        "investment_thesis": {"type": "string"},
                        "main_recommendation_reason": {"type": "string"},
                        "why_selected_over_peers": {"type": "string"},
                        "why_not_others": {"type": "string"},
                        "exclusion_logic": {"type": "string"},
                        "tracking_stage": {"type": "string"},
                        "next_action": {"type": "string"},
                        "core_risks": {"type": "array", "items": {"type": "string"}},
                        "info_gaps": {"type": "array", "items": {"type": "string"}},
                        "switch_variables": {"type": "array", "items": {"type": "string"}},
                        "exclusion_tags": {"type": "array", "items": {"type": "string"}},
                        "evidence": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "event_type": {"type": "string"},
                                    "date": {"type": "string"},
                                    "title": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "source_domain": {"type": "string"},
                                    "source_url": {"type": "string"}
                                },
                                "required": ["event_type", "date", "title", "summary", "source_domain", "source_url"]
                            }
                        },
                        "score_levels": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {k: {"type": "integer", "minimum": 0, "maximum": 5} for k in score_required},
                            "required": score_required
                        }
                    },
                    "required": [
                        "name", "sector", "value_node", "listed_status", "stage", "location", "core_product",
                        "company_positioning", "investment_thesis", "main_recommendation_reason",
                        "why_selected_over_peers", "why_not_others", "exclusion_logic", "tracking_stage",
                        "next_action", "core_risks", "info_gaps", "switch_variables", "exclusion_tags",
                        "evidence", "score_levels"
                    ]
                }
            },
            "final_recommendation": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "recommended_company": {"type": "string"},
                    "backup_companies": {"type": "array", "items": {"type": "string"}},
                    "excluded_companies": {"type": "array", "items": {"type": "string"}},
                    "recommendation_logic": {"type": "string"},
                    "summary_for_ppt": {"type": "string"}
                },
                "required": ["recommended_company", "backup_companies", "excluded_companies", "recommendation_logic", "summary_for_ppt"]
            }
        },
        "required": ["search_context", "top_sectors", "candidate_companies", "final_recommendation"]
    }


def build_system_prompt():
    return """
你是“一级PE标的发现与筛选引擎”的研究代理。你的工作不是替代投资判断，而是将一级PE中最难被信服的环节——从赛道初筛、候选池构建、横向比较、排除逻辑到最终标的收敛——流程化、证据化、可解释化，形成一个可复用的一级标的发现与筛选框架。

你必须围绕以下五个模块工作：
模块1：信息采集与赛道映射。围绕政策、行业协会、展会发布、公司官网、融资事件、客户验证、招投标、年报/招股书等公开信息进行持续采集，并映射至既有赛道库，识别其属于哪个细分赛道、对应哪条投资主线，以及属于需求催化、技术突破、客户验证还是资本事件，为后续候选标的筛选提供结构化入口。
模块2：未上市候选公司池构建。以未上市公司为核心筛选对象，优先纳入处于B轮前后、具备一定客户验证、产品卡位清晰、业务相对聚焦、未来具备继续融资或退出可能的公司；上市公司仅作为产业参照、估值锚和退出映射，不作为本轮一级候选筛选主体。通过该模块形成每个细分赛道的核心候选公司池，而非单点拍脑袋选公司。
模块3：横向比较与排除逻辑生成。围绕公司定位、核心产品、高端属性、客户验证、商业化成熟度、融资阶段、行业地位、退出可行性等维度，对候选公司进行横向比较，并同步生成排除逻辑。系统不仅回答“为什么选这家公司”，也回答“为什么没有选其他公司”，从而提升标的选择过程的完整性与说服力。
模块4：解释型评分引擎。针对赛道景气、利润池、高端属性、客户验证、商业化进度、可投性、退出可行性、竞争卡位和信息充分度等维度进行结构化赋分。评分不是简单给总分，而是要求每一项分数均可追溯至对应公开证据，实现“可打分、可解释、可复核”的研究闭环。
模块5：最终标的推荐与动态跟踪。在候选池、横向比较和评分结果基础上，输出当前赛道重点跟踪公司、备选公司和最终推荐标的，并明确推荐理由、核心证据、仍待核实的信息缺口，以及哪些变量变化可能导致推荐切换。

必须遵守：
1. 候选主体以真实的未上市公司为主；上市公司只能作为参照和退出映射，不能作为本轮一级推荐主体。
2. 只使用公开可得信息；若结论不确定必须写“待核实”，禁止编造融资轮次、客户名单或订单金额。
3. 优先使用较新的公开证据；要体现“今天”的研究状态。
4. 输出必须同时解释“为什么选”与“为什么不选其他候选”。
5. 所有公司都必须给出 0-5 档的九维评分等级：赛道景气、利润池、高端属性、客户验证、商业化进度、可投性、退出可行性、竞争卡位、信息充分度。
6. 可使用的排除标签包括：配套功能件型、工程项目型、宽口径拼装型、标准耗材型、独立客户入口弱、利润池过薄、退出锚缺失、上市公司仅作参照。
7. 跟踪阶段只能从：观察、补证、约访、深跟、立项、放弃 中选择。
8. 每家公司的证据列表必须给出事件类型、日期、标题、摘要、来源域名、来源 URL；日期拿不到可写“待核实”。
9. 你不是在回答二级市场选股，而是在做一级PE未上市项目筛选。
10. 尽量输出 8-12 家候选公司，并保持彼此可比较。

评分参考口径：
- 赛道景气：政策催化、需求扩张、渗透率提升、产业景气度
- 利润池：价值节点位置、议价能力、毛利厚度、后市场厚度
- 高端属性：精度、可靠性、认证壁垒、工艺know-how、国产替代难度
- 客户验证：标杆客户、验证周期、导入深度、复购或复制性
- 商业化进度：量产交付、订单转化、渠道/交付体系、规模化能力
- 可投性：轮次、股权结构、融资节奏、接触可能性、估值可谈性
- 退出可行性：产业买家密度、IPO可比、并购承接、退出路径清晰度
- 竞争卡位：差异化、行业地位、客户心智、平台化延展
- 信息充分度：公开证据完整性、交叉验证程度、信息一致性

输出语言为简体中文，内容要适合一级PE项目工作台直接展示。返回严格 JSON，不要输出代码块。
""".strip()


def build_user_prompt(params):
    today = datetime.now().strftime("%Y-%m-%d")
    brief = (params.get("brief") or "").strip()
    exclude_directions = (params.get("exclude_directions") or "").strip()
    exclude_companies = (params.get("exclude_companies") or "").strip()
    scope = (params.get("scope") or DEFAULT_SETTINGS["scope"]).strip()
    stage_pref = (params.get("stage_pref") or DEFAULT_SETTINGS["stage_pref"]).strip()
    geography = (params.get("geography") or DEFAULT_SETTINGS["geography"]).strip()
    max_companies = int(params.get("max_companies") or DEFAULT_SETTINGS["max_companies"])
    return f"""
今天日期：{today}
研究地域：{geography}
研究范围：{scope}
融资阶段偏好：{stage_pref}
希望输出候选公司数量：{max_companies} 家左右

用户目标：
{brief or DEFAULT_SETTINGS['brief']}

请特别注意：
1. 尽量避开当前已覆盖方向与公司。
2. 已覆盖方向（若有）：{exclude_directions or '无'}
3. 已覆盖公司（若有）：{exclude_companies or '无'}
4. 上市公司只可作为产业参照或退出映射，不作为本轮一级候选推荐主体。
5. 输出必须适合直接进入“一级PE项目工作台”：可横向比较、可解释评分、可生成最终推荐与备选。
6. 若某家公司信息不足，请保留但明确标记信息缺口，不要硬凑确定性结论。
""".strip()


def clean_json_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_output_text(resp: dict) -> str:
    if isinstance(resp, dict) and isinstance(resp.get("output_text"), str) and resp.get("output_text").strip():
        return resp["output_text"]
    output = resp.get("output", [])
    chunks = []
    for item in output:
        if isinstance(item, dict) and item.get("type") == "message":
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") in ("output_text", "text"):
                    txt = content.get("text")
                    if isinstance(txt, str):
                        chunks.append(txt)
    return "\n".join(chunks).strip()


def recursive_collect_sources(obj, out):
    if isinstance(obj, dict):
        if "sources" in obj and isinstance(obj["sources"], list):
            for item in obj["sources"]:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("source_url") or ""
                    title = item.get("title") or item.get("name") or url
                    if url:
                        out.append({"url": url, "title": title})
        for value in obj.values():
            recursive_collect_sources(value, out)
    elif isinstance(obj, list):
        for item in obj:
            recursive_collect_sources(item, out)


def extract_sources(resp: dict):
    found = []
    recursive_collect_sources(resp, found)
    uniq = []
    seen = set()
    for item in found:
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        domain = ""
        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = ""
        uniq.append({"url": url, "title": item.get("title") or url, "domain": domain})
    return uniq


def normalize_report(report: dict, raw_response: dict | None = None, params: dict | None = None):
    report = report or {}
    candidates = report.get("candidate_companies") or []
    normalized_companies = []
    sector_map = {}
    for comp in candidates:
        levels = comp.get("score_levels") or {}
        dimension_scores = {}
        total = 0.0
        for key, weight in DIMENSION_WEIGHTS.items():
            try:
                level = int(levels.get(key, 0))
            except Exception:
                level = 0
            level = max(0, min(5, level))
            weighted = round(weight * level / 5.0, 1)
            dimension_scores[key] = weighted
            total += weighted
        penalty = 0
        for tag in comp.get("exclusion_tags") or []:
            penalty += EXCLUSION_PENALTY.get(tag, 4)
        penalty = min(20, penalty)
        total = round(max(0.0, total - penalty), 1)
        comp["_computed"] = {
            "dimension_scores": dimension_scores,
            "penalty": penalty,
            "total_score": total,
            "score_bucket": score_bucket(total),
            "static_score": round(dimension_scores["sector_prosperity"] + dimension_scores["profit_pool"] + dimension_scores["high_end_attribute"] + dimension_scores["competitive_position"], 1),
            "dynamic_score": round(dimension_scores["customer_validation"] + dimension_scores["commercialization_progress"] + dimension_scores["information_sufficiency"], 1),
            "deal_score": round(dimension_scores["investability"] + dimension_scores["exit_feasibility"], 1),
        }
        normalized_companies.append(comp)
        sector = comp.get("sector") or "未分类"
        sector_map.setdefault(sector, []).append(total)

    normalized_companies.sort(key=lambda x: (-x["_computed"]["total_score"], TRACKING_ORDER.get(x.get("tracking_stage"), 99), x.get("name", "")))
    sector_rank = [
        {"sector": sector, "avg_score": round(sum(scores) / len(scores), 1), "company_count": len(scores)}
        for sector, scores in sector_map.items()
    ]
    sector_rank.sort(key=lambda x: (-x["avg_score"], -x["company_count"], x["sector"]))

    search_context = report.get("search_context") or {}
    final_rec = report.get("final_recommendation") or {}
    sources = extract_sources(raw_response or {})

    if normalized_companies and not final_rec.get("recommended_company"):
        final_rec["recommended_company"] = normalized_companies[0]["name"]
    if not final_rec.get("summary_for_ppt"):
        top_sector_names = "、".join([x.get("sector", "") for x in (report.get("top_sectors") or [])[:3] if x.get("sector")])
        final_rec["summary_for_ppt"] = f"当前系统围绕公开证据完成赛道映射、候选池构建、横向比较与解释型评分，优先赛道为：{top_sector_names or '待生成'}；当前首选公司为：{final_rec.get('recommended_company') or '待生成'}。"

    return {
        "meta": {
            "generated_at": now_iso(),
            "run_date": search_context.get("run_date") or now_iso(),
            "search_scope": search_context.get("search_scope") or (params or {}).get("scope") or DEFAULT_SETTINGS["scope"],
            "headline": search_context.get("headline") or "一级PE在线项目工作台",
            "system_positioning": search_context.get("system_positioning") or "一级PE标的发现与筛选框架",
            "method_summary": search_context.get("method_summary") or "以研究先验为约束，以动态证据流为输入，串联赛道初筛、候选池构建、横向比较、排除逻辑与最终标的收敛。",
            "key_source_count": len(sources),
            "run_source": "live" if raw_response else "seed_or_cache",
        },
        "top_sectors": report.get("top_sectors") or [],
        "sector_rank": sector_rank,
        "candidate_companies": normalized_companies,
        "final_recommendation": final_rec,
        "sources": sources[:80],
        "dimension_weights": DIMENSION_WEIGHTS,
        "dimension_labels": DIMENSION_LABELS,
        "dimension_guide": DIMENSION_GUIDE,
        "weight_band": WEIGHT_BAND,
    }


def make_empty_report(message="当前尚未生成实时结果。"):
    return normalize_report({
        "search_context": {
            "run_date": now_iso(),
            "search_scope": DEFAULT_SETTINGS["scope"],
            "headline": "等待首次更新",
            "system_positioning": "一级PE标的发现与筛选框架",
            "method_summary": message,
        },
        "top_sectors": [],
        "candidate_companies": [],
        "final_recommendation": {
            "recommended_company": "",
            "backup_companies": [],
            "excluded_companies": [],
            "recommendation_logic": "",
            "summary_for_ppt": message,
        },
    })


def load_current_report():
    if REPORT_CACHE_PATH.exists():
        data = load_json(REPORT_CACHE_PATH, {})
        if data.get("report"):
            return data
    if SEED_REPORT_PATH.exists():
        seed = load_json(SEED_REPORT_PATH, {})
        return {"report": normalize_report(seed), "source": "seed", "saved_at": now_iso()}
    return {"report": make_empty_report(), "source": "empty", "saved_at": now_iso()}


def save_current_report(report, source="live", raw=None):
    payload = {"report": report, "source": source, "saved_at": now_iso()}
    if raw:
        payload["raw"] = raw
    atomic_save_json(REPORT_CACHE_PATH, payload)
    history = load_json(HISTORY_PATH, [])
    history.insert(0, {
        "saved_at": payload["saved_at"],
        "source": source,
        "headline": report.get("meta", {}).get("headline", ""),
        "recommended_company": report.get("final_recommendation", {}).get("recommended_company", ""),
    })
    history = history[:20]
    atomic_save_json(HISTORY_PATH, history)
    return payload


def build_request_payload(settings, tool_variant, use_schema=True):
    model = (settings.get("model") or DEFAULT_SETTINGS["model"]).strip()
    scope_domains = [x.strip() for x in re.split(r"[,，\n]+", settings.get("allowed_domains", "")) if x.strip()]
    tool = copy.deepcopy(tool_variant)
    if scope_domains:
        if tool["type"] == "web_search":
            tool.setdefault("filters", {})["allowed_domains"] = scope_domains[:100]
        else:
            tool["allowed_domains"] = scope_domains[:100]

    payload = {
        "model": model,
        "store": False,
        "temperature": 0.2,
        "instructions": build_system_prompt(),
        "input": build_user_prompt(settings),
        "tools": [tool],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "max_output_tokens": 9000,
    }
    if use_schema:
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": "pe_agent_report",
                "strict": True,
                "schema": build_schema(),
            }
        }
    return payload


def call_openai_live(settings, log_callback=None):
    api_key, source = get_effective_api_key(settings)
    if not api_key:
        raise RuntimeError("还没有可用的 OpenAI API Key。请在 Render 环境变量中设置 OPENAI_API_KEY，或在管理员设置页保存一次。")

    base_url = (settings.get("openai_base_url") or DEFAULT_SETTINGS["openai_base_url"]).rstrip("/")
    endpoint = base_url if base_url.endswith("/responses") else base_url + "/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if os.getenv("OPENAI_ORGANIZATION"):
        headers["OpenAI-Organization"] = os.getenv("OPENAI_ORGANIZATION")
    if os.getenv("OPENAI_PROJECT"):
        headers["OpenAI-Project"] = os.getenv("OPENAI_PROJECT")

    tool_variants = [
        {"type": "web_search", "external_web_access": True},
        {"type": "web_search_preview"},
        {"type": "web_search_preview_2025_03_11"},
    ]

    errors = []
    for idx, tool_variant in enumerate(tool_variants, start=1):
        for use_schema in (True, False):
            payload = build_request_payload(settings, tool_variant, use_schema=use_schema)
            if not use_schema:
                payload["input"] += "\n\n请只输出一个合法 JSON 对象，不要输出任何解释、代码块或多余文字。"
            if log_callback:
                log_callback(f"尝试 OpenAI 请求：工具变体 {idx} / {'结构化模式' if use_schema else '纯 JSON 模式'}")
            try:
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=300)
            except Exception as e:
                errors.append(f"请求失败：{e}")
                continue
            if resp.status_code >= 400:
                errors.append(f"HTTP {resp.status_code}: {resp.text[:500]}")
                continue
            raw = resp.json()
            output_text = clean_json_text(extract_output_text(raw))
            if not output_text:
                errors.append("模型未返回可解析文本")
                continue
            try:
                parsed = json.loads(output_text)
            except Exception as e:
                errors.append(f"JSON 解析失败：{e}; 输出前 300 字：{output_text[:300]}")
                continue
            normalized = normalize_report(parsed, raw, settings)
            return normalized, raw, source
    raise RuntimeError("；".join(errors[-6:]) or "调用 OpenAI 失败")


def start_job(name="manual_refresh"):
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "name": name,
            "status": "queued",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "logs": ["任务已创建"],
            "error": "",
            "result": None,
        }
    return job_id


def append_job_log(job_id, message):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        job["updated_at"] = now_iso()


def set_job_status(job_id, status, error="", result=None):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["status"] = status
        job["updated_at"] = now_iso()
        job["error"] = error
        if result is not None:
            job["result"] = result


def run_refresh_job(job_id):
    settings = load_settings()
    try:
        set_job_status(job_id, "running")
        append_job_log(job_id, "开始读取管理员设置")
        append_job_log(job_id, "开始调用模型与公开网页搜索")
        report, raw, key_source = call_openai_live(settings, lambda msg: append_job_log(job_id, msg))
        append_job_log(job_id, f"OpenAI 请求完成，Key 来源：{key_source}")
        save_current_report(report, source="live", raw=raw)
        append_job_log(job_id, "结果已写入服务器缓存并可公开查看")
        set_job_status(job_id, "completed", result=report)
    except Exception as e:
        append_job_log(job_id, f"任务失败：{e}")
        set_job_status(job_id, "failed", error=str(e))


def job_snapshot(job_id):
    with JOBS_LOCK:
        return copy.deepcopy(JOBS.get(job_id))


@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"ok": True, "time": now_iso()})


@app.route("/api/public/state")
def api_public_state():
    current = load_current_report()
    settings = load_settings()
    active_job = None
    with JOBS_LOCK:
        if JOBS:
            latest = sorted(JOBS.values(), key=lambda x: x["updated_at"], reverse=True)[0]
            if latest["status"] in {"queued", "running"}:
                active_job = copy.deepcopy(latest)
    return jsonify({
        "report": current["report"],
        "saved_at": current.get("saved_at"),
        "source": current.get("source", "cache"),
        "modules": MODULES,
        "scoring_guide": [
            {"key": key, "label": DIMENSION_LABELS[key], "guide": DIMENSION_GUIDE[key], "band": WEIGHT_BAND[key], "weight": DIMENSION_WEIGHTS[key]}
            for key in DIMENSION_WEIGHTS
        ],
        "system_positioning": "本系统不是替代投资判断，而是将一级PE中最难被信服的环节——从赛道初筛、候选池构建、横向比较、排除逻辑到最终标的收敛——流程化、证据化、可解释化，形成一个可复用的一级标的发现与筛选框架。",
        "public_note": settings.get("admin_note", DEFAULT_SETTINGS["admin_note"]),
        "active_job": active_job,
    })


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    password = (request.json or {}).get("password", "")
    expected = admin_password()
    if not expected:
        return jsonify({"ok": False, "error": "服务器未设置 ADMIN_PASSWORD，请先在 Render 环境变量中设置。"}), 400
    if password != expected:
        return jsonify({"ok": False, "error": "管理员密码不正确。"}), 401
    session["is_admin"] = True
    return jsonify({"ok": True})


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/admin/status")
def api_admin_status():
    if not is_admin():
        return jsonify({"ok": False, "error": "未登录"}), 401
    settings = load_settings()
    key, source = get_effective_api_key(settings)
    return jsonify({
        "ok": True,
        "settings": {**settings, "saved_api_key": ""},
        "api_key_source": source,
        "api_key_mask": mask_key(key),
        "history": load_json(HISTORY_PATH, []),
    })


@app.route("/api/admin/settings", methods=["POST"])
def api_admin_settings():
    if not is_admin():
        return jsonify({"ok": False, "error": "未登录"}), 401
    data = request.json or {}
    payload = {k: data.get(k, DEFAULT_SETTINGS.get(k)) for k in DEFAULT_SETTINGS if k != "saved_api_key"}
    raw_key = (data.get("api_key") or "").strip()
    if raw_key:
        payload["saved_api_key"] = encrypt_text(raw_key)
    elif data.get("clear_api_key"):
        payload["saved_api_key"] = ""
    merged = save_settings(payload)
    key, source = get_effective_api_key(merged)
    return jsonify({
        "ok": True,
        "settings": {**merged, "saved_api_key": ""},
        "api_key_source": source,
        "api_key_mask": mask_key(key),
    })


@app.route("/api/admin/refresh", methods=["POST"])
def api_admin_refresh():
    if not is_admin():
        return jsonify({"ok": False, "error": "未登录"}), 401
    job_id = start_job("manual_refresh")
    t = threading.Thread(target=run_refresh_job, args=(job_id,), daemon=True)
    t.start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/admin/job/<job_id>")
def api_admin_job(job_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "未登录"}), 401
    job = job_snapshot(job_id)
    if not job:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    return jsonify({"ok": True, "job": job})


@app.route("/api/admin/reset-to-seed", methods=["POST"])
def api_reset_seed():
    if not is_admin():
        return jsonify({"ok": False, "error": "未登录"}), 401
    seed = load_json(SEED_REPORT_PATH, {})
    normalized = normalize_report(seed)
    save_current_report(normalized, source="seed")
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
