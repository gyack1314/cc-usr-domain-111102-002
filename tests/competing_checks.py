"""竞争风险统计的手算可对照例子与独立复核。

所有时长以秒给出，构造航例行时由统一基线加偏移得到 ISO 时刻，
便于人工按整数秒直接核对风险集与曲线。
"""
from fractions import Fraction as F

from workbench.competing import analyze,build_cohort,OVERALL
from workbench.checks import check_result
from workbench.export import export_result
from workbench.domain import classify

BASE='2026-10-01T00:00:00Z'

def row(vid,route,entry,exit_,kind,departure=0,cutoff=None,source='synthetic.json',ordinal=0):
    """按整数秒偏移构造一条原始航次记录。

    kind 为 arrival/cancel 时该终点落在 exit_；None 表示无终点，
    cutoff 缺省取 exit_（即无终点航次在 exit_ 处截止删失）。
    """
    from datetime import datetime,timezone
    def iso(seconds):
        return datetime.fromtimestamp(seconds,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    if cutoff is None:cutoff=exit_ if kind is None else max(exit_,entry)
    data={'id':vid,'route':route,'departure':iso(departure),'entry':iso(entry),
          'cutoff':iso(cutoff),'arrival':None,'cancel':None}
    if kind in ('arrival','cancel'):data[kind]=iso(exit_)
    data['_source']=source;data['_ordinal']=ordinal
    return data

def check(c):
    _tie_example(c)
    _before_entry_example(c)
    _median_not_reached_example(c)
    _no_event_example(c)
    _gap_example(c)
    _dedupe_and_conflict_example(c)
    _export_example(c)

def _curve(group,time):
    return next(r for r in group['timeline'] if r['time']==time)

def _tie_example(c):
    """例1：同刻入组/撤航/删失，共同 Y 同时处理两类终点。"""
    rows=[
        row('a','north',0,2,'arrival',ordinal=0),
        row('b','north',1,3,'censor',ordinal=1),
        row('c','north',2,2,'cancel',ordinal=2),   # 同刻入组且撤航
        row('d','north',2,2,'censor',ordinal=3),   # 同刻入组且截止删失
    ]
    result=analyze(rows);check_result(result)
    north=result['groups']['north']
    c.assertEqual(north['subject_count'],4)
    t2=_curve(north,2)
    # 同刻先入组：c、d 进入后风险集为 {a,b,c,d}
    c.assertEqual(t2['n_risk'],4)
    c.assertEqual(t2['at_risk'],['a','b','c','d'])
    c.assertEqual(t2['entries'],['c','d'])
    c.assertEqual(t2['events_arrival'],['a'])
    c.assertEqual(t2['events_cancel'],['c'])
    c.assertEqual(t2['censored'],['d'])
    # 共同 Y=4：S=1-2/4=1/2，两类各得 1/4
    c.assertEqual(t2['S'],F(1,2))
    c.assertEqual(t2['F_arrival'],F(1,4))
    c.assertEqual(t2['F_cancel'],F(1,4))
    t3=_curve(north,3)
    c.assertEqual(t3['at_risk'],['b'])
    c.assertEqual(t3['censored'],['b'])
    c.assertEqual(north['final']['S'],F(1,2))
    c.assertEqual(north['final']['F_arrival'],F(1,4))
    c.assertEqual(north['final']['F_cancel'],F(1,4))
    c.assertEqual(north['event_counts'],{'arrival':1,'cancel':1,'censor':2})
    # F_arrival 仅 1/4，中位数不可估且理由明确（禁止取已到港子样本中位数）
    c.assertEqual(north['median_arrival_time'],
                  {'status':'not_estimable','reason':'threshold_not_reached'})
    # cancel 必须是终点事件而不是普通删失
    c.assertEqual(sum(1 for s in north['subjects'] if s['kind']=='cancel'),1)
    c.assertEqual(sum(1 for s in north['subjects'] if s['kind']=='censor'),2)

def _before_entry_example(c):
    """例2：观察入组前完结的记录不可入队；非法关系旁路。"""
    rows=[
        row('e','south',5,8,None,ordinal=0),                 # 正常：8 处删失
        row('f','south',5,3,'arrival',ordinal=1),            # 到港早于入组 -> excluded
        row('g','south',5,4,'cancel',ordinal=2),             # 撤航早于入组 -> excluded
    ]
    cohort=build_cohort(rows)
    c.assertEqual([s['id'] for s in cohort['subjects']],['e'])
    c.assertEqual({x['id'] for x in cohort['diagnostics']['excluded']},{'f','g'})
    reasons={x['id']:x['reason'] for x in cohort['diagnostics']['excluded']}
    c.assertTrue(all(v=='before_entry' for v in reasons.values()))
    result=analyze(rows);check_result(result)
    south=result['groups']['south']
    c.assertEqual(south['subject_count'],1)
    c.assertEqual(south['event_counts'],{'arrival':0,'cancel':0,'censor':1})
    # 入组前的 arrival 没有被挪到 cutoff 当删失
    c.assertEqual(south['censor_count'],1)
    # 非法观察区间（entry<departure）
    bad=row('x','south',1,5,None,departure=2,ordinal=3)
    with c.assertRaises(ValueError):classify(bad)
    cohort2=build_cohort(rows+[bad])
    c.assertEqual([i['id'] for i in cohort2['diagnostics']['invalid']],['x'])

def _median_not_reached_example(c):
    """例3：F_arrival 始终低于 0.5，中位数返回不可估。"""
    rows=[
        row('m1','west',0,1,'cancel',ordinal=0),
        row('m2','west',0,2,'arrival',ordinal=1),
        row('m3','west',0,2,None,ordinal=2),
    ]
    result=analyze(rows);check_result(result)
    west=result['groups']['west']
    t1=_curve(west,1)
    c.assertEqual(t1['n_risk'],3)
    c.assertEqual(t1['S'],F(2,3))           # 1 - 1/3
    c.assertEqual(t1['F_cancel'],F(1,3))
    t2=_curve(west,2)
    c.assertEqual(t2['n_risk'],2)
    c.assertEqual(t2['F_arrival'],F(1,3))   # 2/3 * 1/2
    c.assertEqual(west['median_arrival_time']['status'],'not_estimable')
    c.assertEqual(west['median_arrival_time']['reason'],'threshold_not_reached')
    # 已到港子样本只有 m2，其“中位数”是 2，但正确答案仍是不可估
    c.assertNotEqual(west['median_arrival_time'].get('time'),2)

def _no_event_example(c):
    """例4：无事件队列，曲线恒为初值，全部在各自 cutoff 右删失。"""
    rows=[
        row('q1','east',0,3,None,ordinal=0),
        row('q2','east',1,4,None,ordinal=1),
    ]
    result=analyze(rows);check_result(result)
    east=result['groups']['east']
    c.assertEqual(east['steps'],[])
    c.assertEqual(east['event_counts'],{'arrival':0,'cancel':0,'censor':2})
    for point in east['timeline']:
        c.assertEqual(point['S'],F(1))
        c.assertEqual(point['F_arrival'],F(0))
        c.assertEqual(point['F_cancel'],F(0))
        c.assertTrue(point['estimated'])
    c.assertEqual(east['final'],{'S':F(1),'F_arrival':F(0),'F_cancel':F(0)})
    c.assertEqual(east['coverage']['suspended'],False)
    c.assertEqual(east['median_arrival_time'],
                  {'status':'not_estimable','reason':'threshold_not_reached'})

def _gap_example(c):
    """例5：风险集排空后又有入组 -> 覆盖断裂，暂停该层无条件估计。"""
    rows=[
        row('g1','gap',0,1,'arrival',ordinal=0),
        row('g2','gap',0,1,None,ordinal=1),
        row('g3','gap',3,4,'arrival',ordinal=2),   # t=1 与 t=3 之间风险集为空
        row('g4','gap',3,5,None,ordinal=3),
    ]
    result=analyze(rows);check_result(result)
    g=result['groups']['gap']
    c.assertEqual(g['coverage']['breaks'],[{'after_time':1,'before_time':3}])
    c.assertTrue(g['coverage']['suspended'])
    t1=_curve(g,1);t3=_curve(g,3);t4=_curve(g,4)
    # 断裂前正常递推：Y=2，1 到港 1 删失
    c.assertEqual(t1['n_risk'],2)
    c.assertEqual(t1['F_arrival'],F(1,2))
    c.assertEqual(t1['S'],F(1,2))
    # 断裂后不延续同一条曲线：数值冻结、估计暂停
    c.assertFalse(t3['estimated'])
    c.assertEqual(t3['coverage_break'],{'after_time':1,'before_time':3})
    c.assertEqual(t3['at_risk'],['g3','g4'])
    c.assertEqual(t3['S'],F(1,2))
    c.assertFalse(t4['estimated'])
    # 事件计数仍继续，便于逐时点核对
    c.assertEqual(g['event_counts']['arrival'],2)
    c.assertEqual(g['censor_count'],2)
    # 断裂前 t=1 的 F_arrival 已达 0.5，中位数取首次达到时刻，不受后续断裂影响
    c.assertEqual(g['median_arrival_time'],{'status':'estimated','time':1})
    # 断裂前未达 0.5：断裂后暂停估计，中位数不可估
    rows0=[row('k1','gap0',0,1,'arrival',ordinal=0),
           row('k2','gap0',0,1,'cancel',ordinal=1),
           row('k3','gap0',0,1,None,ordinal=2),
           row('k4','gap0',4,5,'arrival',ordinal=3)]
    g0=analyze(rows0)['groups']['gap0']
    # 断裂前 t=1：Y=3，到港/撤航/删失各一，F_arrival=1/3、F_cancel=1/3
    point=next(p for p in g0['timeline'] if p['time']==1)
    c.assertEqual(point['F_arrival'],F(1,3))
    c.assertTrue(g0['coverage']['suspended'])
    c.assertEqual(g0['coverage']['breaks'],[{'after_time':1,'before_time':4}])
    c.assertEqual(g0['median_arrival_time'],
                  {'status':'not_estimable','reason':'suspended_coverage_break'})
    # 断裂前全员到港：中位数仍可估，取断裂前首次达到的时刻
    rows2=[row('h1','gap2',0,1,'arrival',ordinal=0),
           row('h2','gap2',0,1,'arrival',ordinal=1),
           row('h3','gap2',3,4,'cancel',ordinal=2)]
    g2=analyze(rows2)['groups']['gap2']
    c.assertEqual(g2['median_arrival_time'],{'status':'estimated','time':1})
    c.assertTrue(g2['coverage']['suspended'])

def _dedupe_and_conflict_example(c):
    """重复航次同内容去重；内容冲突整组旁路，且带来源行。"""
    base=row('d1','north',0,2,'arrival',source='a.json',ordinal=0)
    dup=dict(base);dup['_source']='b.json';dup['_ordinal']=7
    conflict=dict(base);conflict['cancel']=base['arrival'];conflict['arrival']=None
    conflict['_source']='c.json';conflict['_ordinal']=3
    cohort=build_cohort([base,dup,conflict])
    c.assertEqual([d['id'] for d in cohort['diagnostics']['conflicts']],['d1'])
    c.assertEqual(cohort['subjects'],[])
    prov=cohort['diagnostics']['conflicts'][0]['provenance']
    c.assertEqual(prov,[{'source':'a.json','ordinal':0},
                        {'source':'b.json','ordinal':7},
                        {'source':'c.json','ordinal':3}])
    # 纯重复：保留一份
    cohort2=build_cohort([base,dup])
    c.assertEqual([s['id'] for s in cohort2['subjects']],['d1'])
    c.assertEqual(cohort2['diagnostics']['duplicates'][0]['count'],2)
    # 时间轴可展开到航次 ID 与来源行
    result=analyze([base,dup]);check_result(result)
    subject=result['groups']['north']['subjects'][0]
    c.assertEqual(subject['provenance'],{'source':'a.json','ordinal':0})
    point=_curve(result['groups']['north'],2)
    c.assertEqual(point['events_arrival'],['d1'])

def _export_example(c):
    """导出保留精确分数与十进制值，独立检查在导出结构上仍可重建。"""
    rows=[row('e1','port',0,1,'arrival',ordinal=0),
          row('e2','port',0,1,'cancel',ordinal=1)]
    result=analyze(rows);check_result(result)
    exported=export_result(result)
    point=exported['groups']['port']['steps'][0]
    c.assertEqual(point['S']['numerator'],0)
    c.assertEqual(point['S']['denominator'],1)
    c.assertEqual(point['F_arrival']['value'],0.5)
    c.assertEqual(exported['decimal_places'],12)
    # 恒等式在导出的分子分母上仍精确成立
    for group in exported['groups'].values():
        for p in group['timeline']:
            if p['estimated']:
                total=(F(p['S']['numerator'],p['S']['denominator'])
                       +F(p['F_arrival']['numerator'],p['F_arrival']['denominator'])
                       +F(p['F_cancel']['numerator'],p['F_cancel']['denominator']))
                c.assertEqual(total,1)
    # overall 单独计算而非合并分层概率
    c.assertIn(OVERALL,exported['groups'])
    # 来源行索引可从航次 ID 展开到 source/ordinal
    c.assertEqual(exported['provenance_index']['e1'],
                  [{'source':'synthetic.json','ordinal':0}])
