"""延迟入组竞争风险统计（Aalen-Johansen，整数秒时间轴）。

时间轴以各航次自身启航时刻为零，时长为整数秒。风险集 Y(t) 为满足
entry<=t<=exit 的航次数；同刻处理顺序固定为：先入组并确定共同风险集，
再用同一个 Y 同时处理该刻 arrival 与 cancel 两类终点，更新总生存 S 与
两类累计发生 F，最后移除该刻终点与右删失。cancel 是竞争终点，不会被
转成普通删失；只有缺失终点的航次在 cutoff 处右删失。

入组延迟按独立截断（delayed entry）假设解释，算法本身不消除选择偏倚。
风险集一旦排空、其后又出现新入组，空档两侧不延续同一条无条件曲线，
该层在覆盖断裂后暂停估计（计数与逐时点核对仍继续输出）。
"""
from fractions import Fraction

from .domain import classify
from .io import canonical

OVERALL='overall'
ASSUMPTIONS=(
    '入组延迟按独立截断假设解释，算法不消除选择偏倚，仅在该假设下解释条件风险集递推',
    'arrival 与 cancel 互斥且为竞争终点；cancel 计为终点事件，不转换为普通删失',
    '观察截止后才发生的终点按截止当时未知处理，仅在 cutoff 处右删失',
)

def load_rows(root):
    """读取资料包全部来源文件，附加 source/ordinal 来源行信息。"""
    from .io import read_bundle
    _manifest,tables=read_bundle(root)
    rows=[]
    for source,items in tables.items():
        for ordinal,row in enumerate(items):
            record=dict(row);record['_source']=source;record['_ordinal']=ordinal
            rows.append(record)
    return rows

def load_rows_catalog(catalog,import_id):
    """从本地存档读取某个 import_id 的全部来源行。"""
    rows=[]
    for source in catalog.summary_sources(import_id):
        for ordinal,row in enumerate(catalog.rows(import_id,source)):
            record=dict(row);record['_source']=source;record['_ordinal']=ordinal
            rows.append(record)
    return rows

def build_cohort(rows):
    """校验、去重并旁路冲突记录，返回可入队航次与逐行诊断。

    同一航次 id 内容完全一致只保留一份（重复来源行登记在 duplicates）；
    同一 id 内容冲突则整组旁路到 conflicts，不参与统计。
    领域校验失败与观察入组前完结分别进入 invalid 与 excluded。
    """
    invalid=[];excluded=[];classified=[]
    for row in rows:
        source=row.get('_source');ordinal=row.get('_ordinal')
        provenance=None if source is None else {'source':source,'ordinal':ordinal}
        try:
            result=classify(row)
        except (ValueError,KeyError,TypeError) as exc:
            invalid.append({'id':row.get('id'),'route':row.get('route'),
                            'provenance':provenance,'error':str(exc)})
            continue
        result['provenance']=provenance
        if result['route']==OVERALL:
            invalid.append({'id':result['id'],'route':result['route'],
                            'provenance':provenance,'error':f'route 名 {OVERALL!r} 为保留键'})
            continue
        if result['status']=='excluded':
            excluded.append(result)
        classified.append(result)

    by_id={}
    for result in classified:
        by_id.setdefault(result['id'],[]).append(result)

    subjects=[];duplicates=[];conflicts=[]
    conflict_ids=set()
    for voyage_id,group in by_id.items():
        payloads={canonical(_without_provenance(item)) for item in group}
        provenance=[item['provenance'] for item in group if item['provenance'] is not None]
        if len(payloads)>1:
            conflicts.append({'id':voyage_id,'reason':'content_conflict','provenance':provenance})
            conflict_ids.add(voyage_id)
            continue
        if len(group)>1:
            duplicates.append({'id':voyage_id,'count':len(group),'provenance':provenance})
        kept=group[0]
        if kept['status']=='included':
            subject=dict(kept['subject'])
            subject['provenance']=kept['provenance']
            subjects.append(subject)

    excluded_out=[
        {'id':item['id'],'route':item['route'],'reason':item['reason'],
         'event_kind':item['event_kind'],'event_time':item['event_time'],
         'provenance':item['provenance']}
        for item in excluded if item['id'] not in conflict_ids
    ]
    return {'subjects':subjects,'diagnostics':{
        'invalid':invalid,'excluded':excluded_out,'duplicates':duplicates,'conflicts':conflicts}}

def _without_provenance(result):
    return {k:v for k,v in result.items() if k!='provenance'}

def analyze(rows):
    """完整分析：校验入队后按 route 分层并单独计算 overall。"""
    cohort=build_cohort(rows)
    subjects=cohort['subjects']
    groups={}
    for route in sorted({s['route'] for s in subjects}):
        groups[route]=analyze_stratum(route,[s for s in subjects if s['route']==route])
    groups[OVERALL]=analyze_stratum(OVERALL,subjects)
    return {'time_origin':'departure','time_unit':'integer_seconds','arithmetic':'exact_fraction',
            'assumptions':list(ASSUMPTIONS),'groups':groups,
            'subject_count':len(subjects),'diagnostics':cohort['diagnostics']}

def analyze_stratum(name,subjects):
    """单层风险集递推。subjects 为 build_cohort 产出的入队航次。"""
    ordered=sorted(subjects,key=lambda s:(s['entry'],s['exit'],s['id']))
    times=sorted({s['entry'] for s in ordered}|{s['exit'] for s in ordered})
    active=set()
    S=Fraction(1);F_a=Fraction(0);F_c=Fraction(0)
    total={'arrival':0,'cancel':0,'censor':0}
    timeline=[];steps=[];suspended=False;breaks=[];median=None
    started=False;gap_exit=None

    for t in times:
        entrants=sorted(s['id'] for s in ordered if s['entry']==t)
        if started and not active and entrants:
            suspended=True
            breaks.append({'after_time':gap_exit,'before_time':t})
        active.update(entrants)
        y=len(active)
        ev_arrival=sorted(s['id'] for s in ordered if s['exit']==t and s['kind']=='arrival')
        ev_cancel=sorted(s['id'] for s in ordered if s['exit']==t and s['kind']=='cancel')
        censored=sorted(s['id'] for s in ordered if s['exit']==t and s['kind']=='censor')
        d_a,d_c=len(ev_arrival),len(ev_cancel);d=d_a+d_c

        before_S=S
        row={'time':t,'entries':entrants,'at_risk':sorted(active),'n_risk':y,
             'events_arrival':ev_arrival,'events_cancel':ev_cancel,'censored':censored}
        if breaks and breaks[-1]['before_time']==t:
            row['coverage_break']=dict(breaks[-1])
        if y==0:
            row.update({'estimated':False,'reason':'empty_risk_set',
                        'S':S,'F_arrival':F_a,'F_cancel':F_c})
        else:
            row['estimated']=not suspended
            if not suspended:
                S-=S*Fraction(d,y)
                F_a+=before_S*Fraction(d_a,y)
                F_c+=before_S*Fraction(d_c,y)
                if median is None and d_a and F_a>=Fraction(1,2):
                    median=t
            row.update({'S':S,'F_arrival':F_a,'F_cancel':F_c})
        timeline.append(row)

        if d:
            total['arrival']+=d_a;total['cancel']+=d_c
            steps.append({'time':t,'n_risk':y,'events_arrival':d_a,'events_cancel':d_c,
                          'estimated':not suspended,'S':S,'F_arrival':F_a,'F_cancel':F_c})
        if censored:total['censor']+=len(censored)
        active.difference_update(ev_arrival);active.difference_update(ev_cancel)
        active.difference_update(censored)
        started=True
        gap_exit=t if not active else None

    if not ordered:
        median_status={'status':'not_estimable','reason':'no_subjects'}
    elif suspended and median is None:
        median_status={'status':'not_estimable','reason':'suspended_coverage_break'}
    elif median is None:
        median_status={'status':'not_estimable','reason':'threshold_not_reached'}
    else:
        median_status={'status':'estimated','time':median}

    return {
        'stratum':name,'subject_count':len(ordered),
        'subjects':[dict(s) for s in ordered],
        'event_counts':dict(total),'censor_count':total['censor'],
        'median_arrival_time':median_status,
        'coverage':{'suspended':suspended,'breaks':breaks,
                    'end_reason':'coverage_break' if suspended else 'observed_end'},
        'initial':{'time':0,'S':Fraction(1),'F_arrival':Fraction(0),'F_cancel':Fraction(0)},
        'steps':steps,'final':{'S':S,'F_arrival':F_a,'F_cancel':F_c},
        'timeline':timeline,
    }
