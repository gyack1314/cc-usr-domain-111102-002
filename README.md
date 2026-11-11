# 在途航次的延迟入组与竞争终点统计资料库

航次日期解析、观察片段规范化、来源行检查与延迟入组竞争风险统计工具。
资料在samples，数据语义见docs/domain.md，本地存档说明见docs/catalog.md。

## 运行

需要Python 3.11以上，仅使用标准库。

```bash
python -m workbench.cli inspect samples
python -m workbench.cli ingest samples state/raw.sqlite3
python -m workbench.cli catalog state/raw.sqlite3
python -m workbench.cli competing samples --out output/stats.json
python -m workbench.cli competing-db state/raw.sqlite3 1 --out output/stats_db.json
python -m unittest discover -s tests -v
python -m compileall -q workbench tests
```

inspect查看文件行数和摘要；ingest将原始包放入SQLite；catalog列出原始包。
competing对资料包做带延迟入组的竞争风险统计（Aalen-Johansen），competing-db
对已存档的import_id计算；二者在写出前都会跑独立复核，--out可省略，省略时
结果直接打印。测试覆盖已有资料读取、存档幂等、领域原语与竞争风险手算例子，
compileall检查源码编译。业务计算不会由存档命令自动执行。

## 统计口径（摘要）

- 时间轴以启航为零、整数秒；Y(t)=满足 entry<=t<=exit 的航次数。
- arrival 与 cancel 是互斥竞争终点，cancel 不转普通删失；仅缺失终点的航次
  在 cutoff 处右删失；截止后的终点按当时未知处理，不填预计到港时间。
- 同刻先入组确定共同 Y，再同时处理两类终点更新 S、F_arrival、F_cancel，
  最后移除终点与删失；精确分数计算，估计时点恒有 S+F_arrival+F_cancel=1。
- 到港中位时长取 F_arrival 首次达到 0.5 的时刻，未达到返回不可估。
- 风险集排空后又有入组即覆盖断裂，报告空档并暂停该层无条件曲线估计。
- 入组延迟按独立截断假设解释，不声称算法消除选择偏倚。
- 逐时点结果展开到航次 ID，经 provenance_index 回溯来源文件与行号。

完整约定见docs/domain.md。

## 模块

- workbench/domain.py：时刻解析与单行校验/规范化（classify、observation）。
- workbench/competing.py：去重冲突旁路、入队、风险集递推与覆盖断裂处理。
- workbench/export.py：精确分数到十进制 JSON 的统计导出与来源行索引。
- workbench/checks.py：独立重算复核，analyze 的导出路径默认调用。
- workbench/io.py：JSON与文件边界；catalog.py：原始资料事务。

## 容器

```bash
docker build -t local-workbench .
docker run --rm --network none local-workbench
docker run --rm --network none local-workbench python -m unittest discover -s tests -v
```

程序不需要外部账号或常驻服务，容器默认查看合成资料。state与output为本地工作目录，不进入版本控制。
