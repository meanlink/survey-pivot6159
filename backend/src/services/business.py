"""两期通达率加权透视：统一框规模权重、缺测标注与辛普森/跨期反转检查。

设计要点（对应业务要求）：
- 工作台选择两个不重叠的前后日期段（早期/后期），段内按日记录聚合。
- 统一目标权重取“后期结束日（含）之前，每个区域层最后一次登记的抽样框规模”，
  A/B 两队、两个期共用同一套权重；等权模式下仍按同一层集合计算。
- 缺测层（某队在某期完全没有该层观察）既不当零，也不重算分母：
  该队该期的加权合格率标记为无法计算并给出原因；原始合计仅在实际观察到的层上求比，
  同样附覆盖说明，不能与完整口径直接比较。
- 同日同层出现不同 frame_size 直接拒绝（不论队伍）。
- 结果携带 traceability 快照（日期段、帧登记日、权重、缺测说明、数据指纹），
  晚到记录触发的重算只会产生新任务/新附件，历史结果与已分发文件保持原样。
"""
from datetime import date, timedelta
import math
import random

TEAMS = ("A队", "B队")


def metadata():
    return {
        "name": "实地调研加权透视", "short": "survey-pivot", "tagline": "把样本结构与真实覆盖结构分开，让透视结论经得起复核",
        "client": "模拟客户：南岭公共服务研究所，12名观察员分为A/B两队，复核服务点无障碍通达情况。",
        "workflow": "两支采样队按各自路线提交日汇总，研究助理直接汇总合格率后比较队伍发现的问题比例。",
        "pains": ["两队中心区与外围区样本占比不同", "先平均每日百分比扭曲总体比率", "总计方向和分层方向相反却未被提示", "两期抽样框会变、两队缺测层不同，缺测不能当零也不能各改分母"],
        "upstream": "实地观察日汇总和区域服务点抽样框规模", "downstream": "研究员的分层复核清单、加权结果和方法附件。",
        "entities": ["分层观察样本", "加权透视运行", "研究简报计划"], "dataset_name": "南岭_服务点通达_分层观察日表.csv",
        "columns": [{"key": "day", "label": "观察日", "type": "string"}, {"key": "team", "label": "采样队", "type": "string"}, {"key": "zone", "label": "区域层", "type": "string"}, {"key": "observed", "label": "观察点数", "type": "number"}, {"key": "passed", "label": "通达合格数", "type": "number"}, {"key": "frame_size", "label": "该层抽样框点数", "type": "number"}],
        "parameters": [
            {"key": "weight_mode", "label": "目标层权重", "type": "select", "default": "population", "options": [{"value": "population", "label": "按抽样框规模"}, {"value": "equal", "label": "各区域等权"}]},
            {"key": "minimum_cell", "label": "分层最低观察量", "type": "number", "default": 50, "min": 10, "max": 500},
            {"key": "early_start", "label": "早期开始日期", "type": "date", "default": "2026-10-01"},
            {"key": "early_end", "label": "早期结束日期", "type": "date", "default": "2026-10-15"},
            {"key": "late_start", "label": "后期开始日期", "type": "date", "default": "2026-10-16"},
            {"key": "late_end", "label": "后期结束日期", "type": "date", "default": "2026-10-30"},
        ],
        "workbench_title": "样本结构与两期加权透视", "action_label": "计算两期加权率与反转检查", "unit": "%", "accent": "oklch(53% 0.09 215)", "style": "field-notebook",
        "seed_story": ["08:30 上传南岭_服务点通达_分层观察日表.csv，基线45天，后期另有晚到记录扩展批次。", "08:45 复核中心区/外围区各日登记的抽样框规模，框规模在10月16日与11月1日调整。", "09:00 选择不重叠的早期10/01–10/15与后期10/16–10/30，按后期结束前最后登记框规模加权。", "09:10 查看两队两期各区域的合格数、观察数、层内比率与缺测标注。", "09:20 对照未加权合计，检查每期辛普森方向反转与跨期方向反转。", "10:00 切换等权目标作敏感性比较，不能覆盖原始运行记录。", "15:00 将日期段、权重、分母、缺测说明写入研究附件，创建本地简报分发计划；晚到记录重算不改动既有附件。"],
        "method": "两期各自聚合：层内p_h=Σ合格/Σ观察；统一标准化率p=ΣW_h p_h，W_h取后期结束前最后登记框规模占比或等权，两队两期共用。近似方差ΣW_h²p_h(1−p_h)/n_h。缺测层不当零、不改分母，整期加权率标记无法计算。",
        "limitations": ["假设层内观察可近似独立；置信区间未处理路线聚类和有限总体修正。", "队伍比较用于说明样本构成影响，不是人员绩效排名或随机实验因果结论。", "缺测层不做插补：标注无法计算的比较不得与完整口径结果并列解读。", "结果为固定快照；晚到记录需建立新批次重算，历史运行与分发附件保留原日期、原权重与原缺测说明。"],
    }


def seed_records(extra_days=0):
    """固定种子生成两期演示数据。

    基线 45 天（2026-10-01 起）：框规模 10/16 调整；后期 B队中心区整层缺测。
    extra_days>0 时追加晚到记录：11/01 框规模再次调整，扩展期 A队外围区整层缺测，
    与基线缺测区域不同，用于演示“两队缺测区域不同”和重算不覆盖历史。
    """
    rng = random.Random(1019)
    start = date(2026, 10, 1)
    total_days = 45 + extra_days

    def frame(day_, zone):
        if day_ < date(2026, 10, 16):
            return 6200 if zone == "中心区" else 3800
        if day_ < date(2026, 11, 1):
            return 6500 if zone == "中心区" else 3500
        return 6000 if zone == "中心区" else 4000

    result = []
    for index in range(total_days):
        day = start + timedelta(days=index)
        for team, zone, size, probability in (("A队", "中心区", 9, 0.95), ("A队", "外围区", 43, 0.73), ("B队", "中心区", 43, 0.89), ("B队", "外围区", 9, 0.64)):
            # 后期（10/16 起）B队中心区整层缺测；扩展期（11/01 起）A队外围区整层缺测。
            if day >= date(2026, 10, 16) and team == "B队" and zone == "中心区":
                continue
            if day >= date(2026, 11, 1) and team == "A队" and zone == "外围区":
                continue
            observed = size + rng.randint(-2, 3)
            passed = sum(rng.random() < probability for _ in range(observed))
            result.append({"day": str(day), "team": team, "zone": zone, "observed": observed, "passed": passed, "frame_size": frame(day, zone)})
    return result


def _integer(value, name, minimum):
    try:
        answer = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name}必须是整数") from None
    if not math.isfinite(answer) or not answer.is_integer() or not minimum <= answer <= 1_000_000_000:
        raise ValueError(f"{name}必须是{minimum}至10亿之间的整数")
    return int(answer)


def _day(value, name):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValueError(f"{name}必须是YYYY-MM-DD格式的日期") from None


def validate_params(params):
    """供任务创建服务复用的参数校验，返回规范化后的参数字典。"""
    mode = params.get("weight_mode", "population")
    if mode not in ("population", "equal"):
        raise ValueError("未知权重模式")
    minimum = _integer(params.get("minimum_cell", 50), "最低分层观察量", 10)
    if minimum > 500:
        raise ValueError("最低分层观察量不能超过500")
    early_start = _day(params.get("early_start", "2026-10-01"), "早期开始日期")
    early_end = _day(params.get("early_end", "2026-10-15"), "早期结束日期")
    late_start = _day(params.get("late_start", "2026-10-16"), "后期开始日期")
    late_end = _day(params.get("late_end", "2026-10-30"), "后期结束日期")
    if early_start > early_end:
        raise ValueError("早期开始日期不能晚于早期结束日期")
    if late_start > late_end:
        raise ValueError("后期开始日期不能晚于后期结束日期")
    if early_end >= late_start:
        raise ValueError("前后两个日期段必须不重叠，且早期须完全早于后期")
    return {
        "weight_mode": mode, "minimum_cell": minimum,
        "early_start": str(early_start), "early_end": str(early_end),
        "late_start": str(late_start), "late_end": str(late_end),
    }


def _pct(value):
    return None if value is None else round(value * 100, 3)


def analyze(records, params):
    if not isinstance(records, list) or not records:
        raise ValueError("请先提供区域分层观察日表")
    p = validate_params(params)
    mode, minimum = p["weight_mode"], p["minimum_cell"]
    early = (_day(p["early_start"], "早期开始日期"), _day(p["early_end"], "早期结束日期"))
    late = (_day(p["late_start"], "后期开始日期"), _day(p["late_end"], "后期结束日期"))
    cutoff = late[1]
    periods = (("早期", early), ("后期", late))

    # 第一遍：校验、按(日,层)登记框规模并检测同日同层冲突，累计窗口内单元。
    frame_by_day = {}          # (day, zone) -> frame_size
    frame_history = {}         # zone -> [(day, size), ...]
    natural_keys = set()
    # cells[period_key][(team, zone)] = {"n":..,"passed":..,"days":..}
    cells = {"早期": {}, "后期": {}}
    in_window = 0
    for record in records:
        try:
            day = _day(record["day"], "观察日")
            team, zone = str(record["team"]), str(record["zone"])
            n = _integer(record["observed"], "观察点数", 1)
            passed = _integer(record["passed"], "合格数", 0)
            size = _integer(record["frame_size"], "抽样框规模", 1)
        except (KeyError, TypeError):
            raise ValueError("记录缺少日期、队伍、区域或计数字段") from None
        if team not in TEAMS or not zone or passed > n:
            raise ValueError("队伍须为A队/B队，区域非空且合格数不能超过观察数")
        if (day, team, zone) in natural_keys:
            raise ValueError("同日同队同区域存在重复记录，请先去重")
        natural_keys.add((day, team, zone))
        key = (day, zone)
        if key in frame_by_day and frame_by_day[key] != size:
            raise ValueError(f"{day} 的区域层「{zone}」存在冲突的抽样框规模（{frame_by_day[key]} 与 {size}），无法确定统一权重")
        frame_by_day[key] = size
        history = frame_history.setdefault(zone, [])
        if not history or history[-1][0] != day:
            history.append((day, size))
        for label, (start, end) in periods:
            if start <= day <= end:
                in_window += 1
                cell = cells[label].setdefault((team, zone), {"n": 0, "passed": 0, "days": 0})
                cell["n"] += n
                cell["passed"] += passed
                cell["days"] += 1
    if in_window == 0:
        raise ValueError("所选两个日期段内没有任何观察记录，请调整日期范围")

    # 统一权重：后期结束日（含）之前每个区域层最后一次登记的框规模。
    zones = sorted(frame_history)
    as_of_frame, frame_as_of_day = {}, {}
    for zone in zones:
        latest = None
        for day, size in frame_history[zone]:
            if day <= cutoff:
                latest = (day, size)
            else:
                break
        if latest is None:
            raise ValueError(f"区域层「{zone}」在后期结束日 {cutoff} 之前没有登记过抽样框规模，无法统一加权")
        frame_as_of_day[zone], as_of_frame[zone] = latest
    used_zones = sorted({zone for label in cells for (_, zone) in cells[label]})
    if len(used_zones) < 2:
        raise ValueError("至少需要2个区域层才能做加权比较")
    frame_total = sum(as_of_frame[z] for z in used_zones)
    weights = {z: (as_of_frame[z] / frame_total if mode == "population" else 1 / len(used_zones)) for z in used_zones}

    warnings, notes = [], []
    # estimates[label][team] = dict(rate/low/high/effective_n/raw_rate/raw_coverage/missing)
    estimates = {label: {} for label, _ in periods}

    for label, _ in periods:
        for team in TEAMS:
            missing = [z for z in used_zones if (team, z) not in cells[label]]
            present = [z for z in used_zones if (team, z) in cells[label]]
            numerator = denominator = 0
            for z in present:
                cell = cells[label][(team, z)]
                numerator += cell["passed"]
                denominator += cell["n"]
                if cell["n"] < minimum:
                    warnings.append(f"{label}{team}/{z}仅{cell['n']}个观察点，低于最低量{minimum}。")
            raw_rate = numerator / denominator if denominator else None
            entry = {"missing_zones": missing, "present_zones": present,
                     "raw_rate": raw_rate, "raw_observed": denominator, "raw_passed": numerator}
            if missing:
                entry["rate"] = None
                reason = f"{label}{team}缺测层：{'、'.join(missing)}；缺测不当零、不改分母，该期加权合格率无法计算"
                entry["reason"] = reason
                notes.append(reason + "。")
                if raw_rate is not None:
                    entry["raw_coverage"] = f"原始合计仅覆盖{'、'.join(present)}，不能与完整口径直接比较"
            else:
                weighted = variance = inverse_eff = 0.0
                for z in used_zones:
                    cell = cells[label][(team, z)]
                    rate = cell["passed"] / cell["n"]
                    w = weights[z]
                    weighted += w * rate
                    variance += w ** 2 * rate * (1 - rate) / cell["n"]
                    inverse_eff += w ** 2 / cell["n"]
                se = math.sqrt(variance)
                entry.update({"rate": weighted, "low": max(0.0, weighted - 1.96 * se),
                              "high": min(1.0, weighted + 1.96 * se), "effective_n": 1 / inverse_eff})
            estimates[label][team] = entry

    # 明细表按 期×队×层 展开，缺测层保留行并标注。
    table_rows = []
    for label, _ in periods:
        for team in TEAMS:
            for z in used_zones:
                cell = cells[label].get((team, z))
                if cell is None:
                    table_rows.append({"period": label, "team": team, "zone": z, "status": "缺测",
                                       "passed": None, "observed": None, "rate": None,
                                       "weight": round(weights[z] * 100, 2), "contribution": None,
                                       "note": "该队本期此层无观察记录；不当零、不改分母"})
                else:
                    rate = cell["passed"] / cell["n"]
                    table_rows.append({"period": label, "team": team, "zone": z, "status": "可计算",
                                       "passed": cell["passed"], "observed": cell["n"], "rate": _pct(rate),
                                       "weight": round(weights[z] * 100, 2),
                                       "contribution": _pct(weights[z] * rate), "note": f"覆盖{cell['days']}个观察日"})

    # 每期辛普森方向反转：需要两队该期都可计算加权率且每层两队都有样本。
    layer_reversals = []
    for label, _ in periods:
        layer_deltas, layer_ok = [], True
        for z in used_zones:
            ca, cb = cells[label].get(("A队", z)), cells[label].get(("B队", z))
            if not ca or not cb:
                layer_ok = False
                break
            layer_deltas.append(ca["passed"] / ca["n"] - cb["passed"] / cb["n"])
        ea, eb = estimates[label]["A队"], estimates[label]["B队"]
        if not layer_ok or ea["rate"] is None or eb["rate"] is None or ea["raw_rate"] is None or eb["raw_rate"] is None:
            reversal_info = {"period": label, "reversal": None,
                             "detail": "存在缺测层，原始合计与层内方向的严格反转比较无法计算"}
        else:
            raw_delta = ea["raw_rate"] - eb["raw_rate"]
            reversal = ((raw_delta < 0 and all(d > 0 for d in layer_deltas)) or
                        (raw_delta > 0 and all(d < 0 for d in layer_deltas)))
            reversal_info = {"period": label, "reversal": reversal,
                             "raw_delta": _pct(raw_delta),
                             "weighted_delta": _pct(ea["rate"] - eb["rate"]),
                             "layer_deltas": [_pct(d) for d in layer_deltas]}
            if reversal:
                warnings.append(f"{label}检测到辛普森方向反转：原始合计的A−B方向与所有区域层内方向相反。")
        layer_reversals.append(reversal_info)

    # 跨期变化与跨期方向反转（每队：后期率−早期率）。
    changes = []
    for team in TEAMS:
        early_rate, late_rate = estimates["早期"][team]["rate"], estimates["后期"][team]["rate"]
        item = {"team": team}
        if early_rate is None or late_rate is None:
            item.update({"early_rate": _pct(early_rate), "late_rate": _pct(late_rate), "delta": None,
                         "direction_reversal": None,
                         "reason": "早期或后期加权合格率无法计算（存在缺测层），跨期变化与方向反转无法计算"})
            notes.append(f"{team}跨期变化无法计算：{item['reason']}。")
        else:
            delta = late_rate - early_rate
            item.update({"early_rate": _pct(early_rate), "late_rate": _pct(late_rate), "delta": _pct(delta),
                         "direction": "上升" if delta > 0 else ("下降" if delta < 0 else "持平"),
                         "direction_reversal": False})
        changes.append(item)
    # 两队方向都可计算且相反时，标注跨期方向反转。
    computable = [c for c in changes if c["delta"] is not None]
    if len(computable) == 2 and computable[0]["delta"] * computable[1]["delta"] < 0:
        for c in changes:
            c["direction_reversal"] = True
        warnings.append("检测到跨期方向反转：A队与B队的合格率变化方向相反。")

    # 指标卡与图表（无法计算用 null，前端显示为缺测）。
    metrics = []
    for label, _ in periods:
        for team in TEAMS:
            e = estimates[label][team]
            metrics.append({"label": f"{team}{label}加权合格率", "value": _pct(e["rate"]),
                            "unit": "%" if e["rate"] is not None else "无法计算"})
    for team in TEAMS:
        c = next(c for c in changes if c["team"] == team)
        metrics.append({"label": f"{team}跨期变化（后−早）", "value": c["delta"],
                        "unit": "百分点" if c["delta"] is not None else "无法计算"})

    chart_labels = [f"{label}·{z}" for label, _ in periods for z in used_zones] + ["早期加权", "后期加权"]
    series = []
    for team in TEAMS:
        values = []
        for label, _ in periods:
            for z in used_zones:
                cell = cells[label].get((team, z))
                values.append(None if cell is None else _pct(cell["passed"] / cell["n"]))
        values += [_pct(estimates["早期"][team]["rate"]), _pct(estimates["后期"][team]["rate"])]
        series.append({"name": team, "values": values})

    findings = []
    for label, _ in periods:
        for team in TEAMS:
            e = estimates[label][team]
            if e["rate"] is None:
                findings.append(f"{label}{team}：加权合格率无法计算（{'、'.join(e['missing_zones'])}缺测）；原始合计{e['raw_rate']:.2%}仅基于实际观察层。" if e["raw_rate"] is not None
                                else f"{label}{team}：该期无任何观察记录，所有比较均无法计算。")
            else:
                findings.append(f"{label}{team}：加权合格率{e['rate']:.2%}，近似95%区间{e['low']:.2%}至{e['high']:.2%}，权重有效样本量{e['effective_n']:.1f}。")
    findings += ["合计先累加合格数与观察数再求比；不平均每日比率。", "目标权重在两队两期间保持一致；样本构成不同不能直接当成队伍绩效差异。", "缺测层不插补、不当零；标注无法计算的比较不参与加权与反转结论。"]

    summary = (f"窗口内{in_window}行观察；权重取{cutoff}前最后登记框规模"
               f"（{'按框规模占比' if mode == 'population' else '区域等权'}）。"
               + "；".join(f"{team}早期" + ("无法计算" if estimates['早期'][team]['rate'] is None else f"{estimates['早期'][team]['rate']:.2%}")
                           + "/后期" + ("无法计算" if estimates['后期'][team]['rate'] is None else f"{estimates['后期'][team]['rate']:.2%}")
                           for team in TEAMS)
               + "。" + "；".join((f"{r['period']}发现辛普森反转" if r["reversal"] else (f"{r['period']}未发现严格反转" if r["reversal"] is False else f"{r['period']}反转无法计算")) for r in layer_reversals))

    traceability = {
        "snapshot_note": "本结果为固定快照；晚到记录应建立新批次并创建新分析，历史结果与分发附件不被覆盖。",
        "periods": {"early": {"start": p["early_start"], "end": p["early_end"]},
                    "late": {"start": p["late_start"], "end": p["late_end"]}},
        "frame_rule": f"统一权重采用后期结束日 {p['late_end']}（含）之前各区域层最后登记的抽样框规模",
        "frame_as_of": [{"zone": z, "frame_size": as_of_frame[z], "registered_day": str(frame_as_of_day[z]),
                         "weight_pct": round(weights[z] * 100, 2)} for z in used_zones],
        "weight_mode": mode,
        "missingness": [{"period": label, "team": team, "missing_zones": estimates[label][team]["missing_zones"],
                         "reason": estimates[label][team].get("reason")}
                        for label, _ in periods for team in TEAMS if estimates[label][team]["missing_zones"]],
        "minimum_cell": minimum,
        "records_in_window": in_window,
    }

    return {
        "summary": summary,
        "metrics": metrics,
        "table": {"columns": [{"key": "period", "label": "期段"}, {"key": "team", "label": "采样队"}, {"key": "zone", "label": "区域层"}, {"key": "status", "label": "状态"}, {"key": "passed", "label": "合格分子"}, {"key": "observed", "label": "观察分母"}, {"key": "rate", "label": "层内合格率%"}, {"key": "weight", "label": "统一目标权重%"}, {"key": "contribution", "label": "加权贡献百分点"}, {"key": "note", "label": "缺测/覆盖说明"}],
                  "rows": table_rows},
        "chart": {"type": "bar", "labels": chart_labels, "series": series},
        "periods": [
            {"period": label, "start": p["early_start" if label == "早期" else "late_start"],
             "end": p["early_end" if label == "早期" else "late_end"],
             "teams": [{"team": team, **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in estimates[label][team].items()}} for team in TEAMS]}
            for label, _ in periods
        ],
        "changes": changes,
        "layer_reversals": layer_reversals,
        "findings": findings,
        "method": metadata()["method"],
        "warnings": warnings,
        "notes": notes,
        "traceability": traceability,
    }
