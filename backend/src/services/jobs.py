import time
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services.business import metadata, validate_params


def create(db, data, user):
    if not db.get(Dataset, data.dataset_id):
        raise HTTPException(404, '数据批次不存在')
    allowed = {p['key']: p for p in metadata().get('parameters', [])}
    if set(data.params) - set(allowed):
        raise HTTPException(422, '包含未知分析参数')
    params = {k: p['default'] for k, p in allowed.items()}
    params.update(data.params)
    for key, p in allowed.items():
        v = params[key]
        if p['type'] == 'number':
            try:
                v = float(v)
                if not (p.get('min', -1e9) <= v <= p.get('max', 1e9)):
                    raise ValueError()
                params[key] = v
            except (ValueError, TypeError):
                raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif p['type'] == 'date':
            try:
                params[key] = str(v)
                # 日期格式与跨字段窗口校验集中在业务模块，保证与 worker 同一口径。
                validate_params(params)
            except (ValueError, TypeError):
                raise HTTPException(422, f'{p["label"]} 必须是YYYY-MM-DD格式的日期')
        elif str(v) not in [str(o['value']) for o in p.get('options', [])]:
            raise HTTPException(422, f'{p["label"]} 不是有效选项')
    try:
        # 跨参数校验：窗口不重叠、最低量范围等，失败时整个任务拒绝入队。
        params = validate_params(params)
    except ValueError as error:
        raise HTTPException(422, str(error))
    j = Job(name=data.name, dataset_id=data.dataset_id, params=params, created_by=user.id,
            created_at=time.time(), status='queued')
    db.add(j)
    db.flush()
    return j


def enqueue(job_id):
    try:
        r = Redis.from_url(REDIS_URL)
        r.rpush('analysis:queue', job_id)
        r.close()
    except Exception:
        pass  # SQL queued status is the durable fallback
