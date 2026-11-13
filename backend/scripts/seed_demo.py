import time, json
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit
from src.services.business import metadata, seed_records, analyze, validate_params
from src.services.reports import deliver
from src.utils.security import hash_password
from src.utils.serialization import checksum

# 基线两期窗口与晚到记录到达后的重算窗口（互不影响，重算只生成新任务与新附件）。
BASELINE_PARAMS = {"weight_mode": "population", "minimum_cell": 50,
                   "early_start": "2026-10-01", "early_end": "2026-10-15",
                   "late_start": "2026-10-16", "late_end": "2026-10-30"}
# 晚到批次重算窗口：两段不重叠且不相邻，早期取10月上旬完整段，后期取11月扩展段，
# 两队缺测区域不同（早期B队可计算，后期A队外围缺测无法计算）。
EXTENDED_PARAMS = {"weight_mode": "population", "minimum_cell": 50,
                   "early_start": "2026-10-01", "early_end": "2026-10-15",
                   "late_start": "2026-11-01", "late_end": "2026-11-14"}


def _dataset(db, name, source, rows):
    d = db.scalar(select(Dataset).where(Dataset.name == name))
    if not d:
        d = Dataset(name=name, source=source, records=rows,
                    checksum=checksum(rows), created_at=time.time())
        db.add(d)
        db.flush()
    return d


def _job(db, name, dataset, params, user, approved=False):
    j = db.scalar(select(Job).where(Job.name == name))
    if j:
        return j
    result = analyze(dataset.records, validate_params(params))
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    j = Job(name=name, dataset_id=dataset.id, params=validate_params(params),
            status='completed', result=result, created_by=user.id,
            created_at=time.time() - 3600, finished_at=time.time() - 3595, approved=approved)
    db.add(j)
    db.flush()
    return j


def seed():
    migrate()
    with Session() as db:
        for role, name in [('admin', '林知 · 业务负责人'), ('analyst', '陈舟 · 分析员'), ('viewer', '周禾 · 观察员')]:
            email = role + '@demo.local'
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, name=name, role=role, password=hash_password('Demo123!')))
        db.flush()
        admin = db.scalar(select(User).where(User.role == 'admin'))
        m = metadata()

        # 基线批次（45 天）：后期 B队中心区整层缺测，框规模 10/16 调整。
        baseline_rows = seed_records(extra_days=0)
        baseline = _dataset(db, m['dataset_name'], m['short'] + '-202611.csv', baseline_rows)

        # 晚到记录扩展批次（60 天）：扩展期 A队外围区整层缺测，框规模 11/01 再调整。
        late_rows = seed_records(extra_days=15)
        extended = _dataset(db, m['dataset_name'].replace('.csv', '_晚到扩展.csv'),
                            m['short'] + '-202611-late.csv', late_rows)

        # 基线运行：批准并投递，附件固化原日期、原权重与原缺测说明。
        baseline_job = _job(db, '基线两期复核 · ' + m['name'], baseline, BASELINE_PARAMS, admin, approved=True)
        if not db.scalar(select(Report).where(Report.job_id == baseline_job.id)):
            r = Report(name='每日业务复核简报', job_id=baseline_job.id,
                       destination='业务复核组 · 本地收件箱', interval_seconds=86400,
                       next_run=time.time() + 86400, enabled=True)
            db.add(r)
            db.flush()
            deliver(db, r)

        # 晚到记录到达后的重算运行：新批次新窗口新权重，不覆盖基线任务与既有附件。
        _job(db, '晚到记录重算 · ' + m['name'], extended, EXTENDED_PARAMS, admin, approved=False)
        db.add(Audit(actor='seed', action='demo.baseline',
                     detail={'dataset': baseline.id, 'extended_dataset': extended.id}))
        db.commit()
        counts = {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                  for model in [User, Dataset, Job, Report, Delivery, Audit]}
        print(json.dumps(counts, ensure_ascii=False))
        return counts


if __name__ == '__main__':
    seed()
