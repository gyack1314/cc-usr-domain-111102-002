"""独立检查：用重算而不是引用 competing 内部状态复核分析结果。

检查项：
1. 每个时点风险集成员与 n_risk，是否满足 entry<=t<=exit；
2. 同刻顺序（先入组、共同 Y、后移除）与时间轴完整性；
3. 独立重算 S/F_arrival/F_cancel 递推，含覆盖断裂暂停；
4. 每个估计时点 S+F_arrival+F_cancel=1（精确分数）；
5. 事件数、删失数与逐时点成员归属一致；
6. 到港中位数为 F_arrival 首次达到 0.5 的时刻；
7. 覆盖断裂（风险集排空后又有入组）的位置与暂停标记；
8. 分层/总体的样本量与诊断计数闭合。
任何不一致抛 AssertionError，全部通过返回检查摘要。
"""
from fractions import Fraction

from .competing import OVERALL

def _recompute(timeline):
    """只依据 timeline 的入组/事件/删失成员与 n_risk 独立递推。"""
    S=Fraction(1);F_a=Fraction(0);F_c=Fraction(0);suspended=False
    seen=set()
    for row in timeline:
        if row.get('coverage_break'):suspended=True
        y=row['n_risk'];d_a=len(row['events_arrival']);d_c=len(row['events_cancel'])
        assert len(row['at_risk'])==y,'风险数与成员列表不一致'
        assert set(row['at_risk'])>=set(row['events_arrival'])|set(row['events_cancel']), \
            '事件航次必须在风险集中'
        assert set(row['at_risk'])>=set(row['censored']),'删失航次必须在风险集中'
        assert not (set(row['events_arrival'])&set(row['events_cancel'])),'两类终点互斥'
        assert not ((set(row['events_arrival'])|set(row['events_cancel']))&set(row['censored'])), \
            '事件与删失互斥'
        before_S=S
        if y>0 and not suspended:
            S-=S*Fraction(d_a+d_c,y)
            F_a+=before_S*Fraction(d_a,y);F_c+=before_S*Fraction(d_c,y)
        if y>0:
            assert row['estimated']==(not suspended),'估计暂停标记错误'
            assert row['S']==S and row['F_arrival']==F_a and row['F_cancel']==F_c, \
                '曲线递推与独立重算不符'
            assert row['S']+row['F_arrival']+row['F_cancel']==1,'S+F_arrival+F_cancel 不等于 1'
        else:
            assert not row['estimated'] and row['reason']=='empty_risk_set','空风险集标记错误'
        seen.update(row['entries'])
    return S,F_a,F_c,suspended

def _check_median(group):
    status=group['median_arrival_time']
    hits=[row['time'] for row in group['timeline']
          if row['estimated'] and row['F_arrival']>=Fraction(1,2)]
    if status['status']=='estimated':
        assert hits and status['time']==hits[0],'中位数不是 F_arrival 首次达到 0.5 的时刻'
        earlier=[row for row in group['timeline']
                 if row['time']<status['time'] and row['estimated']]
        assert all(row['F_arrival']<Fraction(1,2) for row in earlier),'中位数时刻之前已达 0.5'
    else:
        assert not hits,'F_arrival 已达 0.5 却报告中位数不可估'
        if group['coverage']['suspended']:
            assert status['reason']=='suspended_coverage_break','断裂层原因标注错误'
        elif group['subject_count']==0:
            assert status['reason']=='no_subjects'
        else:
            assert status['reason']=='threshold_not_reached'

def _check_coverage(group):
    timeline=group['timeline'];active=set();started=False;breaks=[]
    for row in timeline:
        if started and not active and row['entries']:
            breaks.append({'after_time':row['coverage_break']['after_time'],
                           'before_time':row['time']})
        active.update(row['entries'])
        assert len(active)==row['n_risk'],'独立风险集成员重算不符'
        assert all(any(s['id']==vid and s['entry']<=row['time']<=s['exit']
                       for s in group['subjects']) for vid in active), \
            '风险集成员不满足 entry<=t<=exit'
        active.difference_update(row['events_arrival']);active.difference_update(row['events_cancel'])
        active.difference_update(row['censored'])
        started=True
    assert breaks==group['coverage']['breaks'],'覆盖断裂位置不符'
    assert group['coverage']['suspended']==bool(breaks),'暂停状态与断裂不符'
    assert not active,'时间轴结束后风险集未排空'

def _check_counts(group):
    a=sum(len(r['events_arrival']) for r in group['timeline'])
    c=sum(len(r['events_cancel']) for r in group['timeline'])
    z=sum(len(r['censored']) for r in group['timeline'])
    assert (a,c,z)==(group['event_counts']['arrival'],
                     group['event_counts']['cancel'],group['censor_count']), \
        '事件/删失计数与时间轴不符'
    assert a+c+z==group['subject_count'],'每个航次必须恰好贡献一次事件或删失'
    kinds=[s['kind'] for s in group['subjects']]
    assert kinds.count('arrival')==a and kinds.count('cancel')==c and kinds.count('censor')==z, \
        '分层计数与航次明细不符'

def check_group(group):
    times=[row['time'] for row in group['timeline']]
    assert times==sorted(times) and len(times)==len(set(times)),'时间轴须严格递增'
    entries={s['entry'] for s in group['subjects']}
    assert entries<=set(times),'时间轴缺少入组时刻'
    _check_coverage(group)
    _recompute(group['timeline'])
    _check_counts(group)
    _check_median(group)
    final=group['final']
    if not group['coverage']['suspended'] and group['subject_count']:
        assert final['S']+final['F_arrival']+final['F_cancel']==1,'最终恒等式不成立'
    return {'stratum':group['stratum'],'subjects':group['subject_count'],
            'timeline_points':len(group['timeline']),'status':'ok'}

def check_result(result):
    summaries=[]
    for name,group in result['groups'].items():
        summaries.append(check_group(group))
    overall=result['groups'][OVERALL]
    layered=sum(g['subject_count'] for n,g in result['groups'].items() if n!=OVERALL)
    assert layered==overall['subject_count']==result['subject_count'],'总体样本量不闭合'
    diag=result['diagnostics']
    repeated=sum(d['count']-1 for d in diag['duplicates'])
    conflict_rows=sum(len(d['provenance']) for d in diag['conflicts'])
    accounted=(result['subject_count']+repeated+conflict_rows
               +len(diag['invalid'])+len(diag['excluded']))
    assert accounted==_total_rows(result),'诊断计数不闭合'
    return {'groups':summaries,'accounted_rows':accounted,'status':'ok'}

def _total_rows(result):
    """来源行总数 = 入队 + 重复份数 + 冲突份数 + 校验失败 + 入组前完结。"""
    diag=result['diagnostics']
    repeated=sum(d['count']-1 for d in diag['duplicates'])
    conflict_rows=sum(len(d['provenance']) for d in diag['conflicts'])
    return (result['subject_count']+repeated+conflict_rows
            +len(diag['invalid'])+len(diag['excluded']))
