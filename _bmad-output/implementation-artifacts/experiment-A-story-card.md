---
title: 实验 A · 等价任务故事卡（供实验组 X 使用）
type: experiment-card
created: 2026-11-11
---

# Story EXP-A：slot 区间格式化

## 为什么用这张卡

实验 A 要求 X 与 Y 难度相当。两者交付面完全相同（一个新模块 + 一个测试文件、不触碰任何现有行为），
差别只在上下文供给：X 读得到 `project-context.md` 与本卡，Y 只有一句口述需求。

## 需求

把一组连续的 slot 渲染成人类可读区间，供管理员周表与"我的预约"复用。

- 输入：`slot_start` 列表，元素为 20 字符 UTC 字符串 `YYYY-MM-DDTHH:MM:SSZ`；
  已按时间升序、同一设备、30 分钟一格、首尾相接。
- 输出：
  - 单格 → `11-11 10:00`
  - 同日多格 → `11-11 10:00–14:00`（结束时刻 = 最后一格 `slot_start` + 30 分钟）
  - 跨日 → `11-11 22:00–11-12 02:00`
- 函数签名：`format_slot_range(slots: list[str]) -> str`

## 交付面

- 新增 `src/core/slotfmt.py`
- 新增 `tests/test_slotfmt.py`
- 不改任何现有模块，不新增依赖

## 验收标准（每条一行断言）

1. 单格 `10:00` 返回 `11-11 10:00`
2. 同日 8 格（10:00 起）返回 `11-11 10:00–14:00`
3. 跨日输入返回同时含两个日期
4. 空列表抛 `ValueError`
5. 非连续输入抛 `ValueError`
6. 输出为本地墙钟（UTC+8），不是 UTC 原样

## 不在本卡范围内

不要求改 `admin_service._slot_label()` 或 `SlotCell.label()` 去复用它——是否复用由实现者判断并说明理由。
