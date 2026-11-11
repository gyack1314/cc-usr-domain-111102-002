# 领域数据约定

所有时刻是含偏移ISO时间，精确到整数秒；entry>=departure、cutoff>=entry。arrival和cancel最多一个；终点在entry之前为不入队，终点在cutoff之后则在cutoff处删失。终点等于entry或cutoff可计事件。正常样本有同刻事件与删失；bad_records单独保留输入错误。时间单位秒，分组默认route，overall单独计算而非合并分组概率。

全部资料为本地合成。samples保留来源状态，读取和存档不等于业务验证通过；异常记录不被自动修改。workbench/domain.py中的现有函数可独立调用，tests/domain_checks.py演示其行为。

## 竞争风险统计（workbench/competing.py）

时长以各航次自身启航时刻为零，取整数秒。校验通过且可入队的航次记为
{id,route,entry,exit,kind}，kind 取 arrival、cancel 或 censor。

- arrival 与 cancel 互斥，二者都是竞争终点；只有缺失终点的航次在 cutoff
  处右删失（censor）。禁止把 cancel 转成普通删失。
- 观察入组前已发生终点的记录不入队（diagnostics.excluded，reason=before_entry）；
  截止之后才发生的终点按截止当时未知处理，exit 取 cutoff、kind=censor，
  不填写预计到港时间，在途记录原样保留。
- 同一航次 id 内容完全一致的重复行去重（diagnostics.duplicates，保留一份并
  登记全部来源行）；同 id 内容冲突整组旁路（diagnostics.conflicts），不参与统计。
- 领域关系非法（区间倒置、终点互斥被破坏、终点早于启航等）进入 diagnostics.invalid，
  不静默改写。

### 风险集递推

风险集 Y(t) 为满足 entry<=t<=exit 的航次数。同一时刻按固定顺序处理：

1. 该刻入组航次进入风险集，确定本刻共同的 Y；
2. 用同一个 Y 同时处理该刻 arrival 与 cancel 两类终点（数量 d_a、d_c），
   S(t)=S(t-)-S(t-)*(d_a+d_c)/Y，
   F_arrival(t)=F_arrival(t-)+S(t-)*d_a/Y，
   F_cancel(t)=F_cancel(t-)+S(t-)*d_c/Y；
3. 再移除该刻终点航次与右删失航次。

全程用 fractions.Fraction 精确计算，每个估计时点满足
S+F_arrival+F_cancel=1。overall 在合并后的风险集上独立递推，不合并各航线概率。

到港中位时长取 F_arrival 首次达到 0.5 的时刻；全程未达到返回
not_estimable（threshold_not_reached），不得从已到港子样本取中位数。
若层估计因覆盖断裂暂停且断裂前未达到 0.5，原因记为 suspended_coverage_break。

### 延迟入组与覆盖断裂

入组延迟按独立截断（delayed entry）假设解释；算法只实现条件风险集递推，
不消除、也不声称消除选择偏倚。若某刻风险集已排空、其后又出现新入组，
空档两侧不延续同一条无条件曲线：在 coverage.breaks 报告断裂区间，
该层 coverage.suspended=true，断裂后的时点 estimated=false、曲线数值冻结，
但事件数、删失数与逐时点成员仍继续输出以便核对。

### 输出与核对

每个航线与总体均输出：阶梯曲线 steps、逐时点 timeline（entries/at_risk/
events_arrival/events_cancel/censored 展开到航次 ID）、风险数 n_risk、
各类事件数 event_counts、删失数 censor_count、中位数状态与覆盖状态。
航次 ID 经 provenance / provenance_index 可回溯到来源文件与零起始 ordinal。

workbench/checks.py 用独立重算复核风险集成员、同刻顺序、曲线递推、恒等式、
计数闭合、中位数与覆盖断裂；tests/competing_checks.py 给出同刻入组/撤航/
删失、观察前完结、未达中位数、无事件队列与覆盖断裂的手算可对照例子。
