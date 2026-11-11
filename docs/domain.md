# 领域数据约定

所有时刻是含偏移ISO时间，精确到整数秒；entry>=departure、cutoff>=entry。arrival和cancel最多一个；终点在entry之前为不入队，终点在cutoff之后则在cutoff处删失。终点等于entry或cutoff可计事件。正常样本有同刻事件与删失；bad_records单独保留输入错误。时间单位秒，分组默认route，overall单独计算而非合并分组概率。

全部资料为本地合成。samples保留来源状态，读取和存档不等于业务验证通过；异常记录不被自动修改。workbench/domain.py中的现有函数可独立调用，tests/domain_checks.py演示其行为。
