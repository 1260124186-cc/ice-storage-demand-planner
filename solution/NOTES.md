# 领域说明与验算

## 场景解释

冰蓄冷站用小时间尺度的冷机出力同时满足园区冷负荷和蓄冰槽充能。谷段多制冰并不一定省钱，因为制冰会增加当时和全天的用电峰值；峰段融冰能降低冷机出力，但槽体有静置损耗，充放能也有各自效率。园区月度电费由电度费和按最大需量计收的需量费组成，因此调度目标必须同时看分时电价和全天峰值。

## 正确值复算

每个时段先把期初库存乘以 `1 - standing_loss_per_h`，再按：

```text
end = available + charge_efficiency * charge - discharge
served = discharge_efficiency * discharge
direct = load - served
chiller = direct + charge
grid = chiller / cop
```

计算状态和功率。期末库存被限制在 `inventory_step_kwh_th` 网格上，充放能不能同段发生，并受最大充放功率、冷机容量和期末库存约束。

计费需量取 `max(previous_peak_kw, 全天最大 grid_power_kw)`，向上取整到 `rounding_kw` 的倍数。电度费是逐小时 `grid_power_kw * price_per_kwh` 的和，需量费只计一次，两者相加得到总费用。

## 独立验算方法

`tests/test_outputs.py` 中的 `_reference()` 不调用待修模块，而是在库存网格上枚举每小时可达状态，保存 `(当前库存, 已计费需量)` 对应的最低电度费和库存期末序列，最后比较全天总费用。小规模案例还可以用递归枚举所有库存路径复核。平局按完整 `storage_end_kwh_th` 序列的字典序选择，比较前不四舍五入。

固定种子样例来自 `solution/generate_data.py`，负荷由班次曲线叠加固定随机扰动生成，电价按谷、平、峰三段给定，不冒充现场采集记录。

## 四个独立难点

- C1：静置损耗、充电效率、放电效率和充放功率上限共同决定库存递推。
- C2：历史峰值棘轮、向上取整和全天只计一次的需量费。
- C3：在库存网格、冷机容量和期末库存约束下求全局最低总费用，并处理平局。
- C4：输入结构、有限性、库存网格与不可行工况的拒收，以及失败时不覆盖已有输出。
