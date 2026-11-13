"""Stratified weighted field-observation pivot with Simpson reversal checks."""
from datetime import date, timedelta
import math
import random


def metadata():
    return {
        "name": "实地调研加权透视", "short": "survey-pivot", "tagline": "把样本结构与真实覆盖结构分开，让透视结论经得起复核",
        "client": "模拟客户：南岭公共服务研究所，12名观察员分为A/B两队，复核服务点无障碍通达情况。",
        "workflow": "两支采样队按各自路线提交日汇总，研究助理直接汇总合格率后比较队伍发现的问题比例。",
        "pains": ["两队中心区与外围区样本占比不同", "先平均每日百分比扭曲总体比率", "总计方向和分层方向相反却未被提示"],
        "upstream": "实地观察日汇总和区域服务点抽样框规模", "downstream": "研究员的分层复核清单、加权结果和方法附件。",
        "entities": ["分层观察样本", "加权透视运行", "研究简报计划"], "dataset_name": "南岭_服务点通达_分层观察日表.csv",
        "columns": [{"key": "day", "label": "观察日", "type": "string"}, {"key": "team", "label": "采样队", "type": "string"}, {"key": "zone", "label": "区域层", "type": "string"}, {"key": "observed", "label": "观察点数", "type": "number"}, {"key": "passed", "label": "通达合格数", "type": "number"}, {"key": "frame_size", "label": "该层抽样框点数", "type": "number"}],
        "parameters": [{"key": "weight_mode", "label": "目标层权重", "type": "select", "default": "population", "options": [{"value": "population", "label": "按抽样框规模"}, {"value": "equal", "label": "各区域等权"}]}, {"key": "minimum_cell", "label": "分层最低观察量", "type": "number", "default": 50, "min": 10, "max": 500}],
        "workbench_title": "样本结构与加权透视", "action_label": "计算加权率与反转检查", "unit": "%", "accent": "oklch(53% 0.09 215)", "style": "field-notebook",
        "seed_story": ["08:30 上传南岭_服务点通达_分层观察日表.csv，共30天120行。", "08:45 复核中心区抽样框6200个点、外围区3800个点。", "09:00 按抽样框规模加权，最低分层观察量50。", "09:10 查看两队各区域的合格数、观察数与层内比率。", "09:20 对照未加权合计，检查辛普森方向反转。", "10:00 切换等权目标作敏感性比较，不能覆盖原始运行记录。", "15:00 将权重、分母和限制写入研究附件，创建本地简报分发计划。"],
        "method": "层内p_h=Σ合格数/Σ观察数；标准化率p=ΣW_h p_h，W_h取统一抽样框占比或等权。近似方差ΣW_h²p_h(1−p_h)/n_h；方向反转比较A−B的原始合计与每层方向。",
        "limitations": ["假设层内观察可近似独立；置信区间未处理路线聚类和有限总体修正。", "队伍比较用于说明样本构成影响，不是人员绩效排名或随机实验因果结论。"],
    }


def seed_records():
    rng = random.Random(1019)
    start = date(2026, 10, 1)
    result = []
    for index in range(30):
        for team, zone, size, probability, frame in (("A队", "中心区", 9, 0.95, 6200), ("A队", "外围区", 43, 0.73, 3800), ("B队", "中心区", 43, 0.89, 6200), ("B队", "外围区", 9, 0.64, 3800)):
            observed = size + rng.randint(-2, 3)
            passed = sum(rng.random() < probability for _ in range(observed))
            result.append({"day": str(start + timedelta(days=index)), "team": team, "zone": zone, "observed": observed, "passed": passed, "frame_size": frame})
    return result


def _integer(value, name, minimum):
    try:
        answer = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name}必须是整数") from None
    if not math.isfinite(answer) or not answer.is_integer() or not minimum <= answer <= 1_000_000_000:
        raise ValueError(f"{name}必须是{minimum}至10亿之间的整数")
    return int(answer)


def analyze(records, params):
    if not isinstance(records, list) or not records:
        raise ValueError("请先提供区域分层观察日表")
    mode = params.get("weight_mode", "population")
    if mode not in ("population", "equal"):
        raise ValueError("未知权重模式")
    minimum = _integer(params.get("minimum_cell", 50), "最低分层观察量", 10)
    if minimum > 500:
        raise ValueError("最低分层观察量不能超过500")
    cells, frame, natural_keys = {}, {}, set()
    for record in records:
        try:
            day = date.fromisoformat(str(record["day"]))
            team, zone = str(record["team"]), str(record["zone"])
            n = _integer(record["observed"], "观察点数", 1)
            passed = _integer(record["passed"], "合格数", 0)
            size = _integer(record["frame_size"], "抽样框规模", 1)
        except (KeyError, TypeError):
            raise ValueError("记录缺少日期、队伍、区域或计数字段") from None
        except ValueError as error:
            raise ValueError(str(error)) from None
        if team not in ("A队", "B队") or not zone or passed > n:
            raise ValueError("队伍须为A队/B队，区域非空且合格数不能超过观察数")
        if (day, team, zone) in natural_keys:
            raise ValueError("同日同队同区域存在重复记录，请先去重")
        natural_keys.add((day, team, zone))
        if zone in frame and frame[zone] != size:
            raise ValueError("同一区域的抽样框规模冲突，不能确定统一权重")
        frame[zone] = size
        total = cells.setdefault((team, zone), {"n": 0, "passed": 0})
        total["n"] += n
        total["passed"] += passed
    zones = sorted(frame)
    if len(zones) < 2 or any((team, zone) not in cells for team in ("A队", "B队") for zone in zones):
        raise ValueError("至少需要2个区域层，每个区域须同时有A队和B队样本")
    frame_total = sum(frame.values())
    weights = {zone: frame[zone] / frame_total if mode == "population" else 1 / len(zones) for zone in zones}
    output, estimates, raw_rates = [], {}, {}
    warnings = []
    for team in ("A队", "B队"):
        weighted = variance = denominator = numerator = inverse_eff = 0.0
        for zone in zones:
            cell = cells[(team, zone)]
            n, passed = cell["n"], cell["passed"]
            rate = passed / n
            weight = weights[zone]
            weighted += weight * rate
            variance += weight ** 2 * rate * (1 - rate) / n
            inverse_eff += weight ** 2 / n
            numerator += passed
            denominator += n
            output.append({"team": team, "zone": zone, "passed": passed, "observed": n, "rate": round(rate*100, 3), "weight": round(weight*100, 2), "contribution": round(weight*rate*100, 3)})
            if n < minimum:
                warnings.append(f"{team}/{zone}仅{n}个观察点，低于最低量{minimum}。")
        se = math.sqrt(variance)
        estimates[team] = {"rate": weighted, "low": max(0, weighted-1.96*se), "high": min(1, weighted+1.96*se), "effective_n": 1/inverse_eff}
        raw_rates[team] = numerator / denominator
    raw_delta = raw_rates["A队"] - raw_rates["B队"]
    layer_deltas = [cells[("A队", zone)]["passed"]/cells[("A队", zone)]["n"] - cells[("B队", zone)]["passed"]/cells[("B队", zone)]["n"] for zone in zones]
    reversal = (raw_delta < 0 and all(delta > 0 for delta in layer_deltas)) or (raw_delta > 0 and all(delta < 0 for delta in layer_deltas))
    weighted_delta = estimates["A队"]["rate"] - estimates["B队"]["rate"]
    if reversal:
        warnings.append("检测到辛普森方向反转：原始合计的A−B方向与所有区域层内方向相反。")
    return {
        "summary": f"{len(records)}行观察按{'抽样框' if mode=='population' else '区域等权'}标准化；A队加权合格率{estimates['A队']['rate']:.2%}，B队{estimates['B队']['rate']:.2%}；{'发现' if reversal else '未发现严格的'}辛普森反转。",
        "metrics": [{"label": "A队加权合格率", "value": round(estimates["A队"]["rate"]*100, 3), "unit": "%"}, {"label": "B队加权合格率", "value": round(estimates["B队"]["rate"]*100, 3), "unit": "%"}, {"label": "加权A−B", "value": round(weighted_delta*100, 3), "unit": "百分点"}, {"label": "原始A−B", "value": round(raw_delta*100, 3), "unit": "百分点"}],
        "table": {"columns": [{"key": "team", "label": "采样队"}, {"key": "zone", "label": "区域层"}, {"key": "passed", "label": "合格分子"}, {"key": "observed", "label": "观察分母"}, {"key": "rate", "label": "层内合格率%"}, {"key": "weight", "label": "统一目标权重%"}, {"key": "contribution", "label": "加权贡献百分点"}], "rows": output},
        "chart": {"type": "bar", "labels": zones + ["原始总计", "加权总计"], "series": [{"name": team, "values": [round(cells[(team, zone)]["passed"]/cells[(team, zone)]["n"]*100, 3) for zone in zones] + [round(raw_rates[team]*100, 3), round(estimates[team]["rate"]*100, 3)]} for team in ("A队", "B队")]},
        "findings": [f"{team}：近似95%区间{estimates[team]['low']:.2%}至{estimates[team]['high']:.2%}，权重有效样本量{estimates[team]['effective_n']:.1f}。" for team in ("A队", "B队")] + ["合计先累加合格数与观察数再求比；不平均每日比率。", "目标权重在两队间保持一致；样本构成不同不能直接当成队伍绩效差异。"],
        "method": metadata()["method"], "warnings": warnings,
    }
