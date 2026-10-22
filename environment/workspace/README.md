# 冰蓄冷日前调度

`coldstore_planner` 读取一个逐小时工况 JSON，并输出冷机直接供冷、蓄冰充放能和电费汇总。

```bash
python -m coldstore_planner data/day.json /tmp/plan.json
```

`data/day.json` 是按固定种子生成的演示班次，不是现场采集记录。当前实现是在早先只看电价、没有需量费的项目版本上改出来的，尚未按现在的园区结算口径复核。
