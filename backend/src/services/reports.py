import time, os, csv, io, hashlib, json
from src.config.settings import ARTIFACT_DIR


def create(db, data):
    from fastapi import HTTPException
    from src.models import Job, Report
    j = db.get(Job, data.job_id)
    if not j or j.status != 'completed' or not j.approved:
        raise HTTPException(409, '请先选择已完成且获批准的分析结果')
    r = Report(name=data.name, job_id=j.id, destination=data.destination,
               interval_seconds=data.interval_seconds,
               next_run=time.time() + data.delay_seconds, enabled=True)
    db.add(r)
    db.flush()
    return r


def deliver(db, report):
    """生成不可变附件快照。

    每次投递都使用唯一文件名，历史 CSV/JSON 从不被覆盖；附件内嵌任务运行时的
    日期段、统一权重、帧登记日与缺测说明，晚到记录触发的重算只产生新任务新文件。
    """
    from src.models import Job, Delivery
    j = db.get(Job, report.job_id)
    if not j or not j.approved:
        return
    result = j.result or {}
    trace = result.get('traceability', {})
    out = io.StringIO()
    out.write('﻿')
    writer = csv.writer(out)

    def safe(v):
        if v is None:
            return '无法计算（缺测）'
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
        text = str(v)
        return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r')) else text

    # 快照口径抬头：原日期、原权重、原缺测说明随附件一并留档。
    writer.writerow(['研究简报固定快照'])
    writer.writerow(['分析任务', j.name])
    periods = trace.get('periods', {})
    for label, key in (('早期', 'early'), ('后期', 'late')):
        window = periods.get(key, {})
        writer.writerow([f'{label}日期段', f"{window.get('start', '')} 至 {window.get('end', '')}"])
    writer.writerow(['权重规则', trace.get('frame_rule', '')])
    for frame in trace.get('frame_as_of', []):
        writer.writerow([f"统一权重·{frame.get('zone', '')}",
                         f"框规模 {frame.get('frame_size', '')}（登记日 {frame.get('registered_day', '')}），权重 {frame.get('weight_pct', '')}%"])
    for item in trace.get('missingness', []):
        writer.writerow([f"缺测说明·{item.get('period', '')}{item.get('team', '')}",
                         f"缺测层：{'、'.join(item.get('missing_zones') or [])}；{item.get('reason') or '不当零、不改分母，无法计算'}"])
    writer.writerow([])

    table = result.get('table', {})
    cols = table.get('columns', [])
    writer.writerow([safe(c['label']) for c in cols])
    for row in table.get('rows', []):
        writer.writerow([safe(row.get(c['key'], '')) for c in cols])
    data = out.getvalue().encode('utf-8')

    delivery = Delivery(report_id=report.id, created_at=time.time(),
                        checksum=hashlib.sha256(data).hexdigest(), filename='',
                        destination=report.destination)
    db.add(delivery)
    db.flush()
    # 唯一文件名保证历史附件不被新投递或重算覆盖。
    delivery.filename = f'report-{report.id}-delivery-{delivery.id}.csv'
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    with open(os.path.join(ARTIFACT_DIR, delivery.filename), 'wb') as f:
        f.write(data)
    with open(os.path.join(ARTIFACT_DIR, delivery.filename + '.json'), 'w') as f:
        json.dump({'job': j.name, 'params': j.params, 'result': j.result,
                   'checksum': delivery.checksum, 'traceability': trace},
                  f, ensure_ascii=False, allow_nan=False)
    report.next_run = time.time() + report.interval_seconds
    return delivery
