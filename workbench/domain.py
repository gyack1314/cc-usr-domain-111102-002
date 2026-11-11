from datetime import datetime,timezone

EVENT_KINDS=('arrival','cancel')

def timestamp(value):
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None or dt.microsecond:raise ValueError('时刻需含偏移且精确到秒')
    return int((dt.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)).total_seconds())

def classify(row):
    """单行领域校验与规范化，不做跨航次去重。

    合法行返回两类结构之一：
      入队：{'status':'included','subject':{id,route,entry,exit,kind}}
      旁路：{'status':'excluded','reason':'before_entry', ...终点信息}
    非法关系直接抛 ValueError；时刻均换算为相对启航的整数秒。
    终点等于 entry 或 cutoff 均可计事件；终点晚于 cutoff 按截止处右删失处理。
    """
    start=timestamp(row['departure']);entry=timestamp(row['entry']);cutoff=timestamp(row['cutoff'])
    if not start<=entry<=cutoff:raise ValueError('观察区间无效')
    ends=[(k,timestamp(row[k])) for k in EVENT_KINDS if row.get(k) is not None]
    if len(ends)>1:raise ValueError('终点互斥')
    if ends and ends[0][1]<start:raise ValueError('终点早于启航')
    if ends and ends[0][1]<entry:
        kind,end=ends[0]
        return {'id':row['id'],'route':row['route'],'status':'excluded','reason':'before_entry',
                'event_kind':kind,'event_time':end-start}
    if ends and ends[0][1]<=cutoff:
        kind,end=ends[0]
    else:
        kind,end=('censor',cutoff)
    return {'id':row['id'],'route':row['route'],'status':'included',
            'subject':{'id':row['id'],'route':row['route'],'entry':entry-start,
                       'exit':end-start,'kind':kind}}

def observation(row):
    result=classify(row)
    if result['status']=='excluded':
        return {'id':result['id'],'included':False,'reason':result['reason']}
    subject=result['subject']
    return {'id':subject['id'],'route':subject['route'],'included':True,
            'entry':subject['entry'],'exit':subject['exit'],'kind':subject['kind']}
