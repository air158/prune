# prune — Delete 机制设计

## 核心原则

**永远不硬删除。** 所有被"删除"的 skill 实际上是移动到 `deprecated/YYYY-MM/` 目录并写入 RETIRE.md，Git 历史完整保留，随时可以通过 `git checkout` 恢复。

**Delete 只有三条路。** 不允许任意原因触发归档，每条路有明确的触发条件和执行流程。

**自动建议，人工确认。** `prune check` 只输出建议列表，`prune deprecate` 执行归档时需要人工确认（或明确传入 `--yes` 参数才能批量执行）。

---

## 三条退出路径

### 路径 1：COLD（冷死）

**触发条件**（同时满足）：
- `cold_days >= cold_days_max`（默认 60 天）
- `total_calls >= min_calls_to_evaluate`（默认 20 次，排除从未被真实调用过的新 skill）

**逻辑**：skill 曾经被用过，但很长时间无人问津，说明它覆盖的场景已经不再出现，或者被其他 skill 自然替代了。

**执行流程**：

```
prune check 发现 cold_days=75, total_calls=35
    ↓
输出建议：[COLD] old-file-converter — 75 天无调用，建议归档
    ↓
人工 review（或 CI 自动执行）
    ↓
prune deprecate --skill old-file-converter --reason cold
    ↓
移动到 deprecated/2026-04/old-file-converter/
写入 RETIRE.md（reason: cold）
git commit "deprecate(old-file-converter): reason=cold cold_days=75"
```

---

### 路径 2：LOW-UTILITY（效用不足）

**触发条件**（同时满足）：
- `utility_score < utility_min`（默认 0.30）
- `total_calls >= min_calls_to_evaluate`（默认 20 次）

**两阶段处理**（不直接归档，先降级观察）：

```
第一次触发 → 状态从 active 降级到 staging，打标记 "under-review"
    ↓
继续观察 14 天
    ↓
若 utility_score 回升到阈值以上 → 重新升回 active
若仍低于阈值 → 触发归档
```

**设计原因**：utility_score 可能因为短期任务类型变化而暂时下降，不应该立刻归档。给 14 天缓冲期。

**执行流程**：

```
prune check 发现 utility_score=0.22, total_calls=45
    ↓
输出建议：[LOW-UTILITY] slow-search — utility=0.22，建议降级到 staging 观察
    ↓
人工确认
    ↓
在 frontmatter 中更新 status: staging，添加 under_review_since 字段
git commit "demote(slow-search): utility=0.22 → staging/under-review"
    ↓
14 天后 prune check 再次检查
    ↓
仍低于阈值 → prune deprecate --skill slow-search --reason low-utility
```

---

### 路径 3：MERGED（竞争败北，被合并）

**触发条件**：人工或 prune similarity-check 发现两个 skill 高度重叠（相似度 > 0.85），触发 merge 流程。

**Merge 流程**：

```
1. 确定强者和弱者
   - 主要依据：utility_score 高的为强者
   - 次要依据：total_calls 多的为强者
   - 平局时：created_at 早的（更成熟）为强者

2. 提取弱者的有效内容
   - 弱者的 trigger 描述中有强者没有覆盖的部分 → 合并进强者的 triggers
   - 弱者的 Pitfalls 章节有强者没有的条目 → 合并进强者的 Pitfalls

3. 更新强者
   - bump version（patch 版本号 +1）
   - 在 competition_log 中记录本次合并
   - git commit "merge(web-search): absorb web-search-v2 triggers v1.4.1→v1.4.2"

4. 归档弱者
   - prune deprecate --skill web-search-v2 --reason merged --successor web-search
   - 写入 RETIRE.md（reason: merged, successor: active/web-search）
   - git commit "deprecate(web-search-v2): reason=merged successor=web-search"
```

**RETIRE.md 示例**：

```markdown
---
retired_at: 2026-04-15
retired_by: human
reason: merged
successor: active/web-search
---

## 退出原因

与 web-search 功能高度重叠（embedding 相似度 0.91）。
web-search 的 utility_score（0.87）显著高于本 skill（0.54）。
本 skill 的以下 triggers 已合并进 web-search：
- "实时信息"
- "最新新闻"

## 最终适应度快照

total_calls: 134
success_rate: 0.71
utility_score: 0.54
cold_days: 3
```

---

## 依赖安全检查

任何归档操作执行前，`prune dependency-check` 自动运行：

```
准备归档 http-client
    ↓
prune dependency-check 查询 registry.yaml
    ↓
发现 used_by: [web-search, api-caller]
    ↓
阻断归档，输出错误：

  ERROR: 无法归档 http-client
  以下 skill 依赖它：
    - active/web-search
    - active/api-caller
  请先处理这些依赖关系后重试。
  选项：
    1. 更新 web-search 和 api-caller，移除对 http-client 的依赖
    2. 同时归档所有依赖者（危险操作，需要 --cascade 参数）
```

只有当 `used_by` 为空时，归档才能继续执行。

---

## 阻断新 Skill 无限产生（预防性 Delete）

比"生了再删"更好的是"不让重复的出生"。

`prune similarity-check` 作为 pre-commit hook 运行，新 skill 提交前自动触发：

```
计算新 skill 的 trigger embedding
    ↓
与所有 active + staging skill 计算 cosine similarity
    ↓
发现相似度 > 0.85 的已有 skill
    ↓
阻断提交，输出：

  BLOCKED: web-search-v3 与以下 skill 高度重叠：
    - active/web-search  (相似度: 0.91)
  
  建议操作：
    A. 直接扩展 active/web-search 而不是新建
    B. 如果确实有差异化，在 SKILL.md 中添加 differentiation 字段说明区别，
       然后用 git commit --no-verify 强制提交（需要在 PR 中解释原因）
```

---

## 状态转换汇总

```
[新建]
    ↓ PR 合并到 main
  staging
    ↓ total_calls >= 50 且 success_rate >= 0.70
  active ←────────────────────────────────┐
    │                                     │
    ├─ utility_score < 0.30 ──→ staging(under-review) ──→ （14天后回升）
    │                                ↓ 仍低于阈值
    │                           deprecated（low-utility）
    │
    ├─ cold_days >= 60 ──→ deprecated（cold）
    │
    └─ merge 败北 ──→ deprecated（merged）

staging（under-review）
    ↓ utility 回升
  active

staging（普通新 skill）
    ↓ 长期不达标（由团队 review 决定）
  deprecated（low-utility）
```

---

## Utility Score 计算方法

Utility score 衡量"有这个 skill 比没有这个 skill 好多少"，参考 D2Skill 论文（arxiv 2603.28716）的 hindsight utility 思想。

**简化实现**（适合当前阶段）：

```
utility_score = success_count / total_calls
```

这是最简单的近似，代表"调用这个 skill 时的成功率"。

**进阶实现**（有足够数据后）：

在 A/B 路由机制下，同一类任务随机分配到有 skill 和无 skill 两组：

```
utility_score = success_rate_with_skill - success_rate_without_skill
```

这才是真正衡量 skill 贡献的值。进阶实现需要路由层的配合，留待后续迭代。

---

## 与 SkillClaw 的关系

SkillClaw（AMAP-ML/SkillClaw）提供 Refine 和 Create 操作，原生不支持 Delete。本设计与 SkillClaw 互补：

- SkillClaw 负责：让好 skill 变得更好（Refine），识别新的重复模式（Create）
- 本系统负责：让坏 skill 退出（Delete），防止重复 skill 诞生（`prune similarity-check`）

两套系统可以共存，SkillClaw 的 session 数据也可以作为本系统 fitness 更新的输入来源。
