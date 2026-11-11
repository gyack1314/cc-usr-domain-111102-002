"""统计导出：把精确分数结果转为可存档的十进制 JSON 结构。

计算接口 workbench.competing 内部全程使用 fractions.Fraction，保证 S+F=1
可被精确核验；导出时按固定小数位四舍五入，并保留分子分母便于复核。
来源行（source/ordinal）随诊断与逐时点航次 ID 一并展开。
"""
from fractions import Fraction

from .competing import OVERALL

DECIMALS=12

def provenance_index(result):
    """航次 ID -> 来源行列表，覆盖入队、入组前完结、校验失败与冲突旁路。

    返回的 source/ordinal 可直接回到资料包（或存档 source_rows 表）定位
    原始 JSON 行，配合分层 subjects/timeline 逐时点核对。
    """
    index={}
    def add(vid,prov):
        if vid is None or prov is None:return
        index.setdefault(vid,[])
        if prov not in index[vid]:index[vid].append(prov)
    for diag in result['diagnostics'].get('invalid',[]):
        add(diag.get('id'),diag.get('provenance'))
    for diag in result['diagnostics'].get('excluded',[]):
        add(diag.get('id'),diag.get('provenance'))
    for diag in result['diagnostics'].get('duplicates',[]):
        for prov in diag.get('provenance',[]):add(diag.get('id'),prov)
    for diag in result['diagnostics'].get('conflicts',[]):
        for prov in diag.get('provenance',[]):add(diag.get('id'),prov)
    for group in result['groups'].values():
        if group['stratum']==OVERALL:continue
        for subject in group['subjects']:
            add(subject['id'],subject.get('provenance'))
    return index

def _fraction(value):
    if not isinstance(value,Fraction):return value
    return {'value':round(float(value),DECIMALS),
            'numerator':value.numerator,'denominator':value.denominator}

def _walk(value):
    if isinstance(value,dict):return {k:_walk(v) for k,v in value.items()}
    if isinstance(value,list):return [_walk(v) for v in value]
    if isinstance(value,Fraction):return _fraction(value)
    return value

def export_result(result):
    """导出整份分析结果，分数字段变为 {value,numerator,denominator}。"""
    out=dict(result)
    out['decimal_places']=DECIMALS
    out['groups']={name:_walk(group) for name,group in result['groups'].items()}
    out['diagnostics']=_walk(result['diagnostics'])
    out['provenance_index']=provenance_index(result)
    return out
