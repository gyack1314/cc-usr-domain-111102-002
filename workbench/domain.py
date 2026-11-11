from datetime import datetime,timezone
def timestamp(value):
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None or dt.microsecond:raise ValueError('时刻需含偏移且精确到秒')
    return int((dt.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)).total_seconds())

def observation(row):
    start=timestamp(row['departure']);entry=timestamp(row['entry']);cutoff=timestamp(row['cutoff'])
    if not start<=entry<=cutoff:raise ValueError('观察区间无效')
    ends=[(k,timestamp(row[k])) for k in ['arrival','cancel'] if row.get(k) is not None]
    if len(ends)>1:raise ValueError('终点互斥')
    if ends and ends[0][1]<start:raise ValueError('终点早于启航')
    if ends and ends[0][1]<entry:return {'id':row['id'],'included':False,'reason':'before_entry'}
    kind,end=ends[0] if ends and ends[0][1]<=cutoff else ('censor',cutoff)
    return {'id':row['id'],'route':row['route'],'included':True,'entry':entry-start,'exit':end-start,'kind':kind}
