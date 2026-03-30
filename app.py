
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import sys
import webbrowser
import urllib.request
import urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "local_config.json"
LAST_REPORT_PATH = ROOT / "last_report.json"
SAMPLE_REPORT_PATH = ROOT / "sample_report.json"
PORT = 8765

DIMENSION_WEIGHTS = {
    "sector_prosperity": 12,
    "profit_pool": 12,
    "high_end_attribute": 10,
    "customer_validation": 12,
    "commercialization_progress": 10,
    "investability": 12,
    "exit_feasibility": 10,
    "competitive_position": 12,
    "information_sufficiency": 10,
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

EXCLUSION_PENALTY = {
    "配套功能件型": 5,
    "工程项目型": 5,
    "宽口径拼装型": 5,
    "标准耗材型": 5,
    "独立客户入口弱": 5,
    "利润池过薄": 5,
    "退出锚缺失": 5,
    "上市公司仅作参照": 20,
}

TRACKING_ORDER = {"立项": 0, "深跟": 1, "约访": 2, "补证": 3, "观察": 4, "放弃": 5}

def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return key[:3] + "***"
    return key[:7] + "…" + key[-4:]

def now_iso():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def build_schema():
    company_required = [
        "name","sector","value_node","listed_status","stage","location","core_product",
        "company_positioning","investment_thesis","main_recommendation_reason",
        "why_selected_over_peers","why_not_others","exclusion_logic","tracking_stage",
        "next_action","core_risks","info_gaps","switch_variables","exclusion_tags",
        "evidence","score_levels"
    ]
    evidence_required = ["event_type","date","title","summary","source_domain","source_url"]
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
                "required": ["run_date","search_scope","headline","system_positioning","method_summary"]
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
                    "required": ["sector","investment_mainline","signal_type","why_now"]
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
                                "required": evidence_required
                            }
                        },
                        "score_levels": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "sector_prosperity": {"type": "integer", "minimum": 0, "maximum": 5},
                                "profit_pool": {"type": "integer", "minimum": 0, "maximum": 5},
                                "high_end_attribute": {"type": "integer", "minimum": 0, "maximum": 5},
                                "customer_validation": {"type": "integer", "minimum": 0, "maximum": 5},
                                "commercialization_progress": {"type": "integer", "minimum": 0, "maximum": 5},
                                "investability": {"type": "integer", "minimum": 0, "maximum": 5},
                                "exit_feasibility": {"type": "integer", "minimum": 0, "maximum": 5},
                                "competitive_position": {"type": "integer", "minimum": 0, "maximum": 5},
                                "information_sufficiency": {"type": "integer", "minimum": 0, "maximum": 5}
                            },
                            "required": score_required
                        }
                    },
                    "required": company_required
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
                "required": ["recommended_company","backup_companies","excluded_companies","recommendation_logic","summary_for_ppt"]
            }
        },
        "required": ["search_context","top_sectors","candidate_companies","final_recommendation"]
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

输出应服务于买方投研工作台，语言为简体中文，措辞专业、密度高、避免口语化。
""".strip()

def build_user_prompt(params):
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    brief = (params.get("brief") or "").strip()
    exclude_directions = (params.get("exclude_directions") or "").strip()
    exclude_companies = (params.get("exclude_companies") or "").strip()
    scope = (params.get("scope") or "通用设备 / 工业自动化 / 高端制造相邻领域").strip()
    stage_pref = (params.get("stage_pref") or "优先B轮前后").strip()
    geography = (params.get("geography") or "中国").strip()
    max_companies = int(params.get("max_companies") or 10)
    return f"""
今天日期：{today}
研究地域：{geography}
研究范围：{scope}
融资阶段偏好：{stage_pref}
希望输出候选公司数量：{max_companies} 家左右

用户目标：
{brief or "请用今天的公开信息，在通用设备/工业自动化/高端制造相邻交叉领域中，筛选新的一级股权投资方向与未上市公司机会。"}

请特别注意：
1. 尽量避开我当前已覆盖的方向与公司。
2. 已覆盖方向（若有）：{exclude_directions or "无"}
3. 已覆盖公司（若有）：{exclude_companies or "无"}
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
                if isinstance(content, dict) and content.get("type") in ("output_text","text"):
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
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
        except Exception:
            domain = ""
        uniq.append({
            "url": url,
            "title": item.get("title") or url,
            "domain": domain
        })
    return uniq

def score_bucket(score: float):
    if score >= 80:
        return "重点推进"
    if score >= 70:
        return "深跟候选"
    if score >= 60:
        return "重点观察"
    if score >= 45:
        return "补证池"
    return "排除/低优先级"

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
            level = levels.get(key, 0)
            try:
                level = int(level)
            except Exception:
                level = 0
            level = max(0, min(5, level))
            weighted = round(weight * level / 5.0, 1)
            dimension_scores[key] = weighted
            total += weighted
        exclusion_tags = comp.get("exclusion_tags") or []
        penalty = 0
        for tag in exclusion_tags:
            penalty += EXCLUSION_PENALTY.get(tag, 5)
        penalty = min(20, penalty)
        total = round(max(0.0, total - penalty), 1)
        static_score = round(dimension_scores["sector_prosperity"] + dimension_scores["profit_pool"] + dimension_scores["high_end_attribute"] + dimension_scores["competitive_position"], 1)
        dynamic_score = round(dimension_scores["customer_validation"] + dimension_scores["commercialization_progress"] + dimension_scores["information_sufficiency"], 1)
        deal_score = round(dimension_scores["investability"] + dimension_scores["exit_feasibility"], 1)
        comp["_computed"] = {
            "dimension_scores": dimension_scores,
            "penalty": penalty,
            "total_score": total,
            "score_bucket": score_bucket(total),
            "static_score": static_score,
            "dynamic_score": dynamic_score,
            "deal_score": deal_score
        }
        normalized_companies.append(comp)
        sector = comp.get("sector") or "未分类"
        sector_map.setdefault(sector, []).append(total)
    normalized_companies.sort(key=lambda x: (-x["_computed"]["total_score"], TRACKING_ORDER.get(x.get("tracking_stage"), 99), x.get("name","")))
    sector_rank = []
    for sector, scores in sector_map.items():
        sector_rank.append({
            "sector": sector,
            "avg_score": round(sum(scores)/len(scores), 1),
            "company_count": len(scores)
        })
    sector_rank.sort(key=lambda x: (-x["avg_score"], -x["company_count"], x["sector"]))
    search_context = report.get("search_context") or {}
    final_rec = report.get("final_recommendation") or {}
    top_company = normalized_companies[0]["name"] if normalized_companies else ""
    sources = extract_sources(raw_response or {})
    if not final_rec.get("recommended_company") and top_company:
        final_rec["recommended_company"] = top_company
    if not final_rec.get("summary_for_ppt"):
        final_rec["summary_for_ppt"] = (
            f"本次系统围绕公开信息采集、赛道映射、未上市候选池构建、横向比较与解释型评分引擎，对一级PE候选公司进行结构化筛选。"
            f"当前优先跟踪赛道为：{('、'.join([x.get('sector') for x in (report.get('top_sectors') or [])[:3]]) or '待生成')}；"
            f"首选推荐公司为：{final_rec.get('recommended_company') or '待生成'}。"
        )
    normalized = {
        "meta": {
            "generated_at": now_iso(),
            "search_scope": search_context.get("search_scope") or (params or {}).get("scope") or "",
            "headline": search_context.get("headline") or "",
            "system_positioning": search_context.get("system_positioning") or "",
            "method_summary": search_context.get("method_summary") or "",
            "key_source_count": len(sources),
            "run_source": "live" if raw_response else "sample_or_cache"
        },
        "top_sectors": report.get("top_sectors") or [],
        "sector_rank": sector_rank,
        "candidate_companies": normalized_companies,
        "final_recommendation": final_rec,
        "sources": sources[:80],
        "dimension_weights": DIMENSION_WEIGHTS,
        "dimension_labels": DIMENSION_LABELS
    }
    return normalized

def build_request_body(config: dict, params: dict):
    model = (params.get("model") or config.get("model") or "gpt-5.4-mini").strip()
    allowed_domains_raw = (params.get("allowed_domains") or "").strip()
    tools = [{"type": "web_search", "external_web_access": True}]
    if allowed_domains_raw:
        domains = [x.strip() for x in re.split(r"[,，\n]+", allowed_domains_raw) if x.strip()]
        if domains:
            tools[0]["filters"] = {"allowed_domains": domains[:100]}
    schema = build_schema()
    body = {
        "model": model,
        "store": False,
        "reasoning": {"effort": "high"},
        "tool_choice": "auto",
        "tools": tools,
        "include": ["web_search_call.action.sources"],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "pe_agent_report",
                "strict": True,
                "schema": schema
            }
        },
        "instructions": build_system_prompt(),
        "input": build_user_prompt(params),
    }
    return body

def call_openai(config: dict, params: dict):
    api_key = (config.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("尚未保存 API Key。")
    body = build_request_body(config, params)
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    )
    if config.get("organization"):
        req.add_header("OpenAI-Organization", config["organization"])
    if config.get("project"):
        req.add_header("OpenAI-Project", config["project"])
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API 返回错误：HTTP {e.code}，{payload}")
    except Exception as e:
        raise RuntimeError(f"请求 OpenAI API 失败：{e}")
    output_text = clean_json_text(extract_output_text(raw))
    if not output_text:
        raise RuntimeError("模型未返回可解析的结构化内容。")
    try:
        parsed = json.loads(output_text)
    except Exception as e:
        raise RuntimeError(f"模型返回内容无法解析为 JSON：{e}\n原始输出前500字：{output_text[:500]}")
    normalized = normalize_report(parsed, raw, params)
    save_json(LAST_REPORT_PATH, {"raw": parsed, "normalized": normalized, "saved_at": now_iso()})
    return normalized

def load_last_or_sample():
    last = load_json(LAST_REPORT_PATH, {})
    if isinstance(last, dict) and last.get("normalized"):
        return {"source": "last", "report": last["normalized"]}
    sample = load_json(SAMPLE_REPORT_PATH, {})
    if sample:
        if sample.get("candidate_companies"):
            return {"source": "sample", "report": normalize_report(sample, None, None)}
        if sample.get("report"):
            return {"source": "sample", "report": sample["report"]}
    return {"source": "empty", "report": normalize_report({
        "search_context": {
            "run_date": now_iso(),
            "search_scope": "通用设备 / 工业自动化 / 高端制造相邻领域",
            "headline": "等待首次搜索",
            "system_positioning": "一级PE标的发现与筛选框架",
            "method_summary": "保存 API Key 后点击“今日全量搜索”，系统将按五大模块生成候选池、横向比较、解释型评分和最终推荐。 "
        },
        "top_sectors": [],
        "candidate_companies": [],
        "final_recommendation": {
            "recommended_company": "",
            "backup_companies": [],
            "excluded_companies": [],
            "recommendation_logic": "",
            "summary_for_ppt": "当前尚未运行实时搜索。保存 API Key 后点击“今日全量搜索”，系统会使用当天公开信息自动生成一级PE候选池与推荐结论。"
        }
    }, None, None)}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, data, code=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            cfg = load_json(CONFIG_PATH, {})
            self._send_json({
                "has_key": bool(cfg.get("api_key")),
                "api_key_masked": mask_key(cfg.get("api_key","")),
                "model": cfg.get("model", "gpt-5.4-mini"),
                "organization": cfg.get("organization",""),
                "project": cfg.get("project",""),
                "saved_at": cfg.get("saved_at",""),
            })
            return
        if parsed.path == "/api/last-or-sample":
            self._send_json(load_last_or_sample())
            return
        if parsed.path == "/api/sample":
            sample = load_json(SAMPLE_REPORT_PATH, {})
            report = normalize_report(sample, None, None) if sample else {}
            self._send_json({"source": "sample", "report": report})
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            body = {}
        if parsed.path == "/api/save-config":
            cfg = load_json(CONFIG_PATH, {})
            api_key = (body.get("api_key") or "").strip()
            if api_key:
                cfg["api_key"] = api_key
            if "organization" in body:
                cfg["organization"] = (body.get("organization") or "").strip()
            if "project" in body:
                cfg["project"] = (body.get("project") or "").strip()
            if "model" in body:
                cfg["model"] = (body.get("model") or "gpt-5.4-mini").strip()
            cfg["saved_at"] = now_iso()
            save_json(CONFIG_PATH, cfg)
            self._send_json({
                "ok": True,
                "has_key": bool(cfg.get("api_key")),
                "api_key_masked": mask_key(cfg.get("api_key","")),
                "model": cfg.get("model","gpt-5.4-mini"),
            })
            return
        if parsed.path == "/api/clear-config":
            if CONFIG_PATH.exists():
                CONFIG_PATH.unlink()
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/run":
            cfg = load_json(CONFIG_PATH, {})
            if not cfg.get("api_key"):
                self._send_json({"ok": False, "error": "请先保存 API Key。"}, code=400)
                return
            try:
                report = call_openai(cfg, body or {})
                self._send_json({"ok": True, "report": report})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, code=500)
            return
        self._send_json({"ok": False, "error": "Unknown endpoint"}, code=404)

def ensure_sample_exists():
    if SAMPLE_REPORT_PATH.exists():
        return
    sample = {
        "search_context": {
            "run_date": "2026-03-29",
            "search_scope": "通用设备 / 工业自动化 / 高端制造相邻领域",
            "headline": "演示样例：围绕工业3D视觉、厂内物流自动化与柔性协作的一级PE候选池",
            "system_positioning": "以研究先验为约束、以动态证据流为输入的一级PE标的发现与筛选框架",
            "method_summary": "通过公开信息采集、赛道映射、未上市候选池构建、横向比较与解释型评分，形成可复用的一级PE项目雷达。"
        },
        "top_sectors": [
            {"sector": "工业3D视觉与高端传感", "investment_mainline": "高端感知底座", "signal_type": "技术突破 + 客户验证", "why_now": "下游自动化渗透提升，感知层国产替代与系统集成价值同时释放。"},
            {"sector": "厂内物流自动化", "investment_mainline": "机器人控制底座 + 柔性物流", "signal_type": "需求催化 + 资本事件", "why_now": "制造与仓储场景对柔性搬运、调度与数字化控制底座需求持续提升。"},
            {"sector": "柔性协作机器人", "investment_mainline": "轻量化自动化", "signal_type": "商业化验证", "why_now": "中小客户导入门槛下降，场景复制性改善，存在继续融资与产业整合空间。"}
        ],
        "candidate_companies": [
            {
                "name": "梅卡曼德机器人",
                "sector": "工业3D视觉与高端传感",
                "value_node": "工业3D视觉算法与感知系统",
                "listed_status": "未上市",
                "stage": "后期成长阶段",
                "location": "北京",
                "core_product": "工业3D相机、视觉软件与机器人引导解决方案",
                "company_positioning": "面向高端制造场景的3D视觉底座型公司",
                "investment_thesis": "如果感知层持续成为自动化升级瓶颈，则兼具软硬一体能力的3D视觉公司有望向平台型能力延展。",
                "main_recommendation_reason": "感知层技术壁垒较高、对下游柔性自动化渗透具备放大效应，且具有跨行业复制潜力。",
                "why_selected_over_peers": "相较单一项目集成商，更接近底层感知能力供给方，产品与场景可复制性更强。",
                "why_not_others": "部分同类公司仍停留在单场景验证或方案交付阶段，平台化与证据完整性相对偏弱。",
                "exclusion_logic": "若后续发现客户验证主要集中于低端场景且缺乏高价值行业渗透，则优先级需下调。",
                "tracking_stage": "深跟",
                "next_action": "补充高端制造标杆客户导入深度与量产复制节奏。",
                "core_risks": ["客户集中度待核实", "海外竞争对手技术迭代快"],
                "info_gaps": ["近期新增大客户结构", "订单转化节奏"],
                "switch_variables": ["标杆客户扩张", "系统级产品延展", "新融资或产业合作进展"],
                "exclusion_tags": [],
                "evidence": [
                    {"event_type": "技术发布", "date": "待核实", "title": "发布面向工业场景的3D视觉产品与方案", "summary": "公司持续强调面向工业机器人引导和高端制造柔性场景的3D视觉能力。", "source_domain": "mech-mind.com", "source_url": "https://www.mech-mind.com/"},
                    {"event_type": "客户验证", "date": "待核实", "title": "多场景案例展示", "summary": "官网与公开案例持续展示在汽车、物流与制造等场景的落地。", "source_domain": "mech-mind.com", "source_url": "https://www.mech-mind.com/solutions/"}
                ],
                "score_levels": {"sector_prosperity": 4, "profit_pool": 4, "high_end_attribute": 5, "customer_validation": 4, "commercialization_progress": 4, "investability": 3, "exit_feasibility": 3, "competitive_position": 4, "information_sufficiency": 4}
            },
            {
                "name": "仙工智能",
                "sector": "厂内物流自动化",
                "value_node": "机器人控制系统与调度底座",
                "listed_status": "未上市",
                "stage": "成长阶段",
                "location": "上海",
                "core_product": "机器人控制器、操作系统、调度系统与生态平台",
                "company_positioning": "厂内物流自动化的控制底座型公司",
                "investment_thesis": "若AMR/移动机器人行业最终形成平台型生态，控制与调度底座相对整机更具平台价值。",
                "main_recommendation_reason": "更接近基础软件和控制底座，具备生态位与平台化延展空间。",
                "why_selected_over_peers": "相较单纯整机厂商，控制底座更有机会跨场景和多整机形态复用。",
                "why_not_others": "部分候选更偏项目交付或单机产品，长期平台价值与退出映射相对弱。",
                "exclusion_logic": "若未来商业化主要依赖定制项目而非标准化平台授权，需下调估值与优先级。",
                "tracking_stage": "深跟",
                "next_action": "补充生态合作伙伴结构与授权商业模式验证。",
                "core_risks": ["平台型变现节奏待验证", "生态粘性强度待核实"],
                "info_gaps": ["标准化收入占比", "头部客户续约率"],
                "switch_variables": ["生态扩展", "授权客户数量", "产业资本合作"],
                "exclusion_tags": [],
                "evidence": [
                    {"event_type": "产品发布", "date": "待核实", "title": "围绕机器人控制与调度底座持续迭代", "summary": "公开材料持续强调控制系统、调度与机器人开发平台能力。", "source_domain": "seer-robotics.ai", "source_url": "https://seer-robotics.ai/"},
                    {"event_type": "生态合作", "date": "待核实", "title": "生态伙伴与方案展示", "summary": "公司对外展示其底座型生态与多场景应用拓展。", "source_domain": "seer-robotics.ai", "source_url": "https://seer-robotics.ai/zh/medias/company"}
                ],
                "score_levels": {"sector_prosperity": 4, "profit_pool": 4, "high_end_attribute": 4, "customer_validation": 4, "commercialization_progress": 4, "investability": 4, "exit_feasibility": 3, "competitive_position": 5, "information_sufficiency": 4}
            },
            {
                "name": "优艾智合",
                "sector": "厂内物流自动化",
                "value_node": "移动机器人与柔性物流方案",
                "listed_status": "未上市",
                "stage": "成长阶段",
                "location": "深圳",
                "core_product": "移动机器人、场内物流与柔性自动化方案",
                "company_positioning": "场景切入较深的移动机器人公司",
                "investment_thesis": "若特定高价值行业对无人化物流需求提升，具备场景理解和交付能力的公司有望形成订单密度。",
                "main_recommendation_reason": "在高价值场景中的客户验证较为关键，具备从单点场景向平台方案扩展的可能。",
                "why_selected_over_peers": "相较单纯仓储搬运公司，制造场景与高端行业切入的含金量更高。",
                "why_not_others": "若竞争对手更多聚焦通用场景但缺乏深度行业验证，则优先级相对靠后。",
                "exclusion_logic": "若业务结构仍高度依赖项目型交付而标准化产品收入不足，则需要打折。",
                "tracking_stage": "补证",
                "next_action": "核实高价值客户导入深度与标准化收入比重。",
                "core_risks": ["项目属性偏重", "复制性仍需验证"],
                "info_gaps": ["收入结构", "重点行业客户复购"],
                "switch_variables": ["新增标杆客户", "标准化产品占比提升", "新一轮融资"],
                "exclusion_tags": ["工程项目型"],
                "evidence": [
                    {"event_type": "客户验证", "date": "待核实", "title": "公开展示在工业场景中的应用案例", "summary": "公司持续对外披露移动机器人在工业及高价值场景的应用。", "source_domain": "uagv.com", "source_url": "https://www.uagv.com/"},
                    {"event_type": "公司动态", "date": "待核实", "title": "公司新闻与行业活动披露", "summary": "公开新闻页可见行业活动、合作与案例类信息。", "source_domain": "uagv.com", "source_url": "https://www.uagv.com/news"}
                ],
                "score_levels": {"sector_prosperity": 4, "profit_pool": 3, "high_end_attribute": 3, "customer_validation": 4, "commercialization_progress": 4, "investability": 4, "exit_feasibility": 3, "competitive_position": 3, "information_sufficiency": 3}
            },
            {
                "name": "海柔创新",
                "sector": "厂内物流自动化",
                "value_node": "仓储机器人系统",
                "listed_status": "未上市",
                "stage": "后期成长阶段",
                "location": "深圳",
                "core_product": "箱式仓储机器人与仓储自动化系统",
                "company_positioning": "仓储自动化机器人公司",
                "investment_thesis": "仓储机器人场景商业化较成熟，但更需要判断利润池厚度与退出路径。",
                "main_recommendation_reason": "商业化成熟度较高，可作为仓储机器人方向的成熟参照。",
                "why_selected_over_peers": "相较早期候选，商业化与公开证据更充分。",
                "why_not_others": "部分同类公司在产品成熟度和品牌认知上仍偏弱。",
                "exclusion_logic": "若系统集成属性过强、标准产品占比下降，则一级投资逻辑会弱化。",
                "tracking_stage": "观察",
                "next_action": "补充利润池位置与系统集成属性判断。",
                "core_risks": ["系统集成属性可能偏强", "赛道竞争拥挤"],
                "info_gaps": ["高毛利部件占比", "后市场与服务收入结构"],
                "switch_variables": ["毛利改善", "海外扩张", "潜在退出参照增强"],
                "exclusion_tags": ["宽口径拼装型"],
                "evidence": [
                    {"event_type": "公司新闻", "date": "待核实", "title": "仓储自动化解决方案公开案例", "summary": "公司官网公开展示面向仓储场景的产品与案例。", "source_domain": "hairobotics.com", "source_url": "https://www.hairobotics.com/"},
                    {"event_type": "行业活动", "date": "待核实", "title": "持续参加展会与行业交流", "summary": "对外活动有助于观察行业地位与市场拓展。", "source_domain": "hairobotics.com", "source_url": "https://www.hairobotics.com/news"}
                ],
                "score_levels": {"sector_prosperity": 4, "profit_pool": 3, "high_end_attribute": 3, "customer_validation": 4, "commercialization_progress": 5, "investability": 3, "exit_feasibility": 4, "competitive_position": 4, "information_sufficiency": 4}
            },
            {
                "name": "节卡机器人",
                "sector": "柔性协作机器人",
                "value_node": "轻量化协作机器人",
                "listed_status": "未上市",
                "stage": "成长阶段",
                "location": "上海",
                "core_product": "协作机器人本体与应用方案",
                "company_positioning": "柔性自动化场景中的协作机器人公司",
                "investment_thesis": "协作机器人若继续向轻量化和场景化渗透，具备柔性自动化入口价值。",
                "main_recommendation_reason": "产品成熟度与场景渗透可作为柔性自动化方向的重要观察样本。",
                "why_selected_over_peers": "品牌与产品化程度较高，便于横向比较与退出映射。",
                "why_not_others": "部分同类公司公开证据或场景复制性不足。",
                "exclusion_logic": "若行业价格竞争恶化、利润池持续向下游集成迁移，则需要谨慎。",
                "tracking_stage": "观察",
                "next_action": "补充高价值行业客户验证和盈利能力判断。",
                "core_risks": ["价格竞争", "同质化风险"],
                "info_gaps": ["高端场景渗透率", "单客户贡献结构"],
                "switch_variables": ["高端行业突破", "差异化产品发布", "潜在退出窗口"],
                "exclusion_tags": [],
                "evidence": [
                    {"event_type": "产品发布", "date": "待核实", "title": "协作机器人产品线与应用展示", "summary": "官网展示其协作机器人产品与场景拓展。", "source_domain": "jaka.com", "source_url": "https://www.jaka.com/"},
                    {"event_type": "行业案例", "date": "待核实", "title": "公开案例与场景应用", "summary": "对外案例有助于判断场景复制性与行业深度。", "source_domain": "jaka.com", "source_url": "https://www.jaka.com/news"}
                ],
                "score_levels": {"sector_prosperity": 3, "profit_pool": 3, "high_end_attribute": 3, "customer_validation": 3, "commercialization_progress": 4, "investability": 4, "exit_feasibility": 3, "competitive_position": 4, "information_sufficiency": 4}
            },
            {
                "name": "蓝芯科技",
                "sector": "厂内物流自动化",
                "value_node": "视觉AMR与感知型物流机器人",
                "listed_status": "未上市",
                "stage": "成长阶段",
                "location": "杭州",
                "core_product": "移动机器人与视觉导航方案",
                "company_positioning": "以视觉感知差异化切入的移动机器人公司",
                "investment_thesis": "若移动机器人竞争从整机走向算法与感知差异化，视觉导航能力可能形成细分卡位。",
                "main_recommendation_reason": "相较标准搬运型产品，感知差异化有助于提升高端属性与进入壁垒。",
                "why_selected_over_peers": "具备感知层差异化叙事，不完全等同于通用搬运项目公司。",
                "why_not_others": "其他候选若更多是设备集成与定制交付，则高端属性和平台价值不足。",
                "exclusion_logic": "若客户验证主要停留在低门槛场景，且复用性不足，则需降级。",
                "tracking_stage": "补证",
                "next_action": "补充头部客户验证和量产复制性。",
                "core_risks": ["感知差异化是否可持续", "客户验证深度待核实"],
                "info_gaps": ["高端行业落地深度", "规模化复制速度"],
                "switch_variables": ["头部客户突破", "产品平台化", "战略合作"],
                "exclusion_tags": [],
                "evidence": [
                    {"event_type": "产品发布", "date": "待核实", "title": "视觉导航与移动机器人方案展示", "summary": "公开材料强调视觉导航与智能物流方案。", "source_domain": "lanxincorp.com", "source_url": "https://www.lanxincorp.com/"},
                    {"event_type": "公司动态", "date": "待核实", "title": "新闻与活动披露", "summary": "公开新闻有助于跟踪合作与应用落地。", "source_domain": "lanxincorp.com", "source_url": "https://www.lanxincorp.com/news"}
                ],
                "score_levels": {"sector_prosperity": 4, "profit_pool": 3, "high_end_attribute": 4, "customer_validation": 3, "commercialization_progress": 3, "investability": 4, "exit_feasibility": 3, "competitive_position": 3, "information_sufficiency": 3}
            },
            {
                "name": "迦智科技",
                "sector": "厂内物流自动化",
                "value_node": "移动机器人与场景化物流系统",
                "listed_status": "未上市",
                "stage": "成长阶段",
                "location": "杭州",
                "core_product": "AMR产品与厂内物流解决方案",
                "company_positioning": "场景落地能力较强的移动机器人公司",
                "investment_thesis": "在柔性制造场景中，交付能力较强的公司可能率先建立行业客户心智，但需穿透项目属性。",
                "main_recommendation_reason": "可作为场景型移动机器人候选，具备比较价值。",
                "why_selected_over_peers": "具备真实场景落地与产品化基础，适合作为横向比较对象。",
                "why_not_others": "若其他候选公开证据不足，则难以进行有效横向比较。",
                "exclusion_logic": "若项目属性过强、标准化复制不足，则优先级应下调。",
                "tracking_stage": "观察",
                "next_action": "核实产品标准化程度与高价值行业突破。",
                "core_risks": ["项目属性", "复制效率"],
                "info_gaps": ["软件收入占比", "可规模化交付能力"],
                "switch_variables": ["高价值客户突破", "标准化提升"],
                "exclusion_tags": ["工程项目型"],
                "evidence": [
                    {"event_type": "公司官网", "date": "待核实", "title": "AMR产品与方案展示", "summary": "官网与公开资料展示其移动机器人产品线和方案。", "source_domain": "visionnav.com", "source_url": "https://www.visionnav.com/"},
                    {"event_type": "新闻活动", "date": "待核实", "title": "公开案例与市场活动", "summary": "可用于观察公司市场拓展与行业活动参与度。", "source_domain": "visionnav.com", "source_url": "https://www.visionnav.com/news"}
                ],
                "score_levels": {"sector_prosperity": 4, "profit_pool": 3, "high_end_attribute": 3, "customer_validation": 3, "commercialization_progress": 4, "investability": 4, "exit_feasibility": 3, "competitive_position": 3, "information_sufficiency": 3}
            },
            {
                "name": "海伯森",
                "sector": "工业3D视觉与高端传感",
                "value_node": "工业传感与精密检测",
                "listed_status": "未上市",
                "stage": "成长阶段",
                "location": "深圳",
                "core_product": "工业传感器与视觉检测方案",
                "company_positioning": "高端制造中的感知与检测层候选",
                "investment_thesis": "检测与传感层如果持续上移到质量闭环关键节点，利润池和高端属性会优于通用自动化零部件。",
                "main_recommendation_reason": "更接近高精度传感与检测价值节点，具备高端属性与客户验证壁垒的可能。",
                "why_selected_over_peers": "相较普通视觉集成商，更接近底层传感与检测能力供给。",
                "why_not_others": "若其他公司主要依赖项目制集成，价值节点与利润池位置更弱。",
                "exclusion_logic": "若实际产品仍偏通用检测辅件，且缺乏高端行业卡位，则需降级。",
                "tracking_stage": "补证",
                "next_action": "补充高端制造客户验证、精度指标与复购情况。",
                "core_risks": ["信息透明度偏弱", "高端客户渗透待核实"],
                "info_gaps": ["标杆客户", "检测精度壁垒", "收入结构"],
                "switch_variables": ["核心客户披露", "量产应用案例"],
                "exclusion_tags": [],
                "evidence": [
                    {"event_type": "官网信息", "date": "待核实", "title": "工业传感与检测产品展示", "summary": "公开资料可见工业传感与检测相关产品表述。", "source_domain": "hypersen.com", "source_url": "https://www.hypersen.com/"},
                    {"event_type": "公司动态", "date": "待核实", "title": "新闻与活动更新", "summary": "可跟踪产品、合作与市场活动的公开信息。", "source_domain": "hypersen.com", "source_url": "https://www.hypersen.com/news"}
                ],
                "score_levels": {"sector_prosperity": 4, "profit_pool": 4, "high_end_attribute": 4, "customer_validation": 3, "commercialization_progress": 3, "investability": 4, "exit_feasibility": 3, "competitive_position": 3, "information_sufficiency": 3}
            }
        ],
        "final_recommendation": {
            "recommended_company": "仙工智能",
            "backup_companies": ["梅卡曼德机器人", "海伯森", "节卡机器人"],
            "excluded_companies": ["海柔创新"],
            "recommendation_logic": "优先选择更接近底座层、平台型、客户可复制且未明显滑向项目型交付的公司。",
            "summary_for_ppt": "系统将通用设备相邻领域的公开证据流映射为“赛道—价值节点—未上市公司”三层候选池，并通过横向比较、排除逻辑与九维解释型评分形成最终推荐。当前演示样例下，厂内物流自动化与工业3D视觉是优先关注方向；首选候选为仙工智能，核心原因在于其更接近机器人控制与调度底座，具备平台化延展空间与较清晰的一级PE比较逻辑。"
        }
    }
    save_json(SAMPLE_REPORT_PATH, sample)

def main():
    ensure_sample_exists()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"PE Agent Live Demo is running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nServer stopped.")

if __name__ == "__main__":
    main()
