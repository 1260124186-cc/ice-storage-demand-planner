# 冰蓄冷站日前调度复核

园区制造部的冰蓄冷站每天上午按夜间留下的冰量安排冷机。原先的程序只比较电价高低，没有把需量电费、蓄冰损耗和期末库存一起算进去，最近几次月度复核都出现“电价省了但总费用更高”的情况。请修复 `/workspace/coldstore_planner`，保持下面的入口和 JSON 字段不变：

```bash
python -m coldstore_planner INPUT.json OUTPUT.json
```

## 输入约定

输入是一个 JSON 对象。`site_id` 是非空字符串，`cop` 和 `chiller_capacity_kw_th` 必须为正数。`periods` 是 1 至 24 个逐小时对象，每项含非负的 `cooling_load_kw_th` 和 `price_per_kwh`。每个时段固定为一小时。

`storage` 包含：

- `capacity_kwh_th`：槽体容量，非负且必须是 `inventory_step_kwh_th` 的整数倍；
- `inventory_step_kwh_th`：库存状态步长，必须为正；
- `initial_kwh_th`、`terminal_kwh_th`：期初与期末库存，必须在 0 到容量之间，并且落在库存步长网格上；
- `max_charge_kw_th`、`max_discharge_kw_th`：每小时最大充能量与最大放能量，均非负；
- `charge_efficiency`、`discharge_efficiency`：分别位于 `(0, 1]`；
- `standing_loss_per_h`：静置损耗率，位于 `[0, 1)`。

`demand` 包含非负的 `previous_peak_kw`、正的 `rounding_kw` 和非负的 `charge_per_kw`。所有数值必须是有限数，不用字符串代替数字。

## 能量与费用口径

每个时段的 `storage_start_kwh_th` 是上一时段期末库存，期初时段使用 `initial_kwh_th`。先按静置损耗得到可用库存：

```text
available = storage_start_kwh_th * (1 - standing_loss_per_h)
```

`charge_kwh_th` 是冷机送往蓄冰槽的冷量，入库时乘 `charge_efficiency`；`discharge_kwh_th` 是从槽内取用的冷量，对外供冷时乘 `discharge_efficiency`：

```text
storage_end_kwh_th = available
                   + charge_efficiency * charge_kwh_th
                   - discharge_kwh_th

discharge_served_kw_th = discharge_efficiency * discharge_kwh_th
direct_chiller_kw_th = cooling_load_kw_th - discharge_served_kw_th
chiller_output_kw_th = direct_chiller_kw_th + charge_kwh_th
grid_power_kw = chiller_output_kw_th / cop
```

不允许同一小时同时充电和放电。`charge_kwh_th` 不得超过最大充能，`discharge_kwh_th` 不得超过最大放能；`direct_chiller_kw_th` 不得为负，`chiller_output_kw_th` 不得超过冷机容量。每个时段期末库存只能落在 0、`inventory_step_kwh_th`、`2*inventory_step_kwh_th`，直到容量的离散点上；时段之间不另做取整。最后一个时段期末库存必须精确等于 `terminal_kwh_th`。

全天最大 Grid power 为各时段 `grid_power_kw` 的最大值。计费需量要在当日峰值和历史峰值中取较大者，再向上取整到 `rounding_kw` 的整数倍：

```text
raw_peak = max(previous_peak_kw, max(grid_power_kw))
billed_demand_kw = ceil(raw_peak / rounding_kw) * rounding_kw
```

电度费为各时段 `grid_power_kw * price_per_kwh` 之和，需量费为 `billed_demand_kw * charge_per_kw`，两者相加得到 `total_cost`。需量费全天只计一次。

选择调度时先使 `total_cost` 最小。若多个调度的总费用完全相同，则比较完整的小时级 `storage_end_kwh_th` 序列，选择字典序更小的一个。比较过程不能先四舍五入成两位小数。`coldstore_planner.storage.advance_inventory` 应继续返回 `(storage_end_kwh_th, discharge_served_kw_th)`，`coldstore_planner.billing.billed_demand_kw` 应返回取整后的计费需量。

## 输出要求

成功时输出一个 JSON 对象，包含 `site_id`、`schedule` 和 `summary`。`schedule` 每个时段一项，字段固定为：

```text
hour
cooling_load_kw_th
storage_start_kwh_th
charge_kwh_th
discharge_kwh_th
direct_chiller_kw_th
chiller_output_kw_th
grid_power_kw
storage_end_kwh_th
```

`hour` 从 0 开始递增。`summary` 必须包含：

```text
energy_cost
daytime_peak_kw
billed_demand_kw
demand_charge
total_cost
terminal_storage_kwh_th
```

`daytime_peak_kw` 是未取整的当日最大 Grid power，`terminal_storage_kwh_th` 是最后一个时段的期末库存。数值不提前取整，也不能写出 `NaN` 或无穷值。

输入对象、字段类型、有限性、范围或库存网格有问题，或者负荷与冷机容量使期末库存不可达时，程序应以非零状态退出。失败时不能新建输出，也不能覆盖已经存在的输出文件；全部校验和求解成功后才能一次性写出最终结果。`/workspace/data/day.json` 是按固定种子生成的演示班次，不是现场采集记录，可用于本地核对。
