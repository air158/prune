# prune — 系统设计

## 总体架构

```
skills-registry/                    ← Git monorepo，team 共享
├── active/                         ← 生产环境 skill
├── staging/                        ← 试用期 skill（新生）
├── deprecated/                     ← 归档（永不删除）
│   └── 2026-04/
├── registry.yaml                   ← 全局索引 + 依赖图
└── .git/hooks/pre-commit           ← 提交前自动检查
```

Hermes agent 是这个 repo 的主要 committer，团队成员也可以直接操作（人工编写 skill、人工触发归档等）。

---

## Frontmatter Schema

在 Hermes 原生 frontmatter 基础上扩展，原有字段保持不变，新增字段全部放在 `lifecycle` 命名空间下，不影响 Hermes 原生加载。

```yaml
---
# ── Hermes 原生字段（不变）────────────────────────────
name: web-search
description: 搜索网络获取实时信息
version: 1.4.2
author: hermes-agent
metadata:
  hermes:
    tags: [search, web, realtime]
    category: information

# ── 生命周期扩展字段 ─────────────────────────────────
lifecycle:
  status: active              # active | staging | deprecated
  created_at: 2026-01-10
  status_changed_at: 2026-02-15

  # 适应度数据（agent 每次 session 后自动更新）
  fitness:
    total_calls: 847
    success_count: 770
    success_rate: 0.91
    utility_score: 0.87       # 有 skill 时成功率 - 无 skill 时成功率
    last_called: 2026-04-29
    cold_days: 0

  # 依赖声明
  depends_on:
    - http-client
    - result-parser
  used_by:                    # 由 registry.yaml 自动维护，不手动填写
    - research-assistant

  # 阈值覆盖（可选，不填则使用 registry.yaml 全局默认值）
  thresholds:
    utility_min: 0.30
    cold_days_max: 60
    similarity_merge: 0.85

  # 竞争历史
  competition_log:
    - date: 2026-03-15
      competitor: web-search-v2
      outcome: won
      absorbed_triggers:
        - "实时信息"
        - "最新新闻"
---
```

**兼容性说明**：Hermes 读取 skill 时只看它认识的字段，`lifecycle` 命名空间会被忽略，不影响正常调用。

---

## 目录结构详解

### active/

```
active/
└── web-search/
    ├── SKILL.md          ← 完整 frontmatter + 正文
    └── reference.md      ← 可选参考文件（Hermes Level 2 加载）
```

### staging/

新 skill 必须从 staging 开始，满足毕业条件后才能 promote 到 active。staging 中的 skill 对 Hermes 可见（不隐藏），但在 registry.yaml 中标记为 `staging`，方便监控。

### deprecated/YYYY-MM/

```
deprecated/
└── 2026-04/
    └── old-web-search/
        ├── SKILL.md      ← 退出时的最终状态快照
        └── RETIRE.md     ← 退出记录（见下文）
```

RETIRE.md 格式：

```markdown
---
retired_at: 2026-04-15
retired_by: hermes-evolver       # hermes-evolver | human | lifecycle-bot
reason: merged                   # merged | cold | low-utility | superseded | security
successor: active/web-search     # 替代者（如有）
---

## 退出原因

utility_score 连续 30 天低于阈值（最终值 0.21）。
功能已被 web-search@1.4.2 完整覆盖，triggers 已合并。

## 最终适应度快照

total_calls: 312
success_rate: 0.61
utility_score: 0.21
cold_days: 8
```

---

## registry.yaml

```yaml
version: "2026-04-30"

# 全局生命周期阈值（可被单个 skill 的 thresholds 覆盖）
lifecycle_defaults:
  staging_min_calls: 50           # staging → active 最低调用次数
  staging_min_rate: 0.70          # staging → active 最低成功率
  utility_min: 0.30               # 低于此值触发降级或归档
  cold_days_max: 60               # 超过此天数触发归档
  min_calls_to_evaluate: 20       # 少于此值不触发淘汰判定
  similarity_merge_threshold: 0.85

# Skill 索引（由 prune check 自动维护）
skills:
  web-search:
    path: active/web-search
    status: active
    utility_score: 0.87
    last_updated: 2026-04-29
  web-search-v2:
    path: staging/web-search-v2
    status: staging
    utility_score: null
  old-web-search:
    path: deprecated/2026-04/old-web-search
    status: deprecated
    retired_at: 2026-04-15

# 依赖图（自动维护）
dependency_graph:
  web-search:
    depends_on: [http-client, result-parser]
    used_by: [research-assistant, fact-checker]
  http-client:
    depends_on: []
    used_by: [web-search, api-caller]
```

---

## Git 操作规范

所有变更通过标准化的 commit message 记录，便于 git log 检索和自动化解析。

| 事件 | 分支 | Commit message 格式 |
|---|---|---|
| 新 skill 进入 staging | `skill/name` | `feat(skill): create web-search-v2` |
| fitness 更新 | main | `fitness(web-search): calls=848 rate=0.91 utility=0.87` |
| staging → active | main | `promote(web-search-v2): staging→active rate=0.82 calls=67` |
| skill 被 refine | main | `refine(web-search): fix timeout v1.4.1→v1.4.2` |
| merge 竞争胜出 | main | `merge(web-search): absorb web-search-v2 triggers` |
| 归档 | main | `deprecate(old-web-search): reason=low-utility utility=0.21` |
| 紧急回滚 | main | 标准 `git revert <hash>` |

新 skill 在 feature branch 上开发，通过 PR 合并到 main，PR 合并即代表进入 staging。

---

## 自动化脚本职责划分

> 脚本实现细节见后续单独文档，此处只定义职责边界。

| 脚本 | 触发时机 | 职责 |
|---|---|---|
| `prune update-fitness` | 每次 session 结束后 | 更新被调用 skill 的 fitness 数据，写入 frontmatter，git commit |
| `prune update-cold` | 每日定时（cron） | 扫描所有 active/staging skill，更新 cold_days |
| `prune check` | 每日定时（cron） | 检查所有 skill 的适应度，输出需要状态转换的 skill 列表 |
| `prune similarity-check` | pre-commit hook | 新 skill 提交前检测与现有 skill 的语义重复度 |
| `prune dependency-check` | pre-commit hook | 归档操作前检查反向依赖，阻断不安全的删除 |
| `prune promote` | 人工触发 | 将 staging skill promote 到 active |
| `prune deprecate` | 人工触发 / prune check 建议后人工确认 | 执行归档，写 RETIRE.md，移动目录，git commit |

**设计原则**：`prune check` 只输出建议，不自动执行归档。归档操作（`prune deprecate`）需要人工确认后执行，防止自动化误删。

---

## Delete 机制

详见《Skill Delete 机制设计》文档。

---

## Eval 设计

### 层一：Delete 机制正确性测试

验证核心判断逻辑是否准确。

**合成数据集构造**：

```python
# 构造已知结果的测试 skill
test_cases = [
    # 应该死的
    {"name": "cold-skill",       "cold_days": 90,  "total_calls": 50,  "utility": 0.85, "expected": "deprecate"},
    {"name": "useless-skill",    "cold_days": 5,   "total_calls": 100, "utility": 0.15, "expected": "deprecate"},
    {"name": "new-bad-skill",    "cold_days": 3,   "total_calls": 10,  "utility": 0.10, "expected": "skip"},   # 调用次数不足，不判定

    # 应该活的
    {"name": "healthy-skill",    "cold_days": 2,   "total_calls": 500, "utility": 0.88, "expected": "keep"},
    {"name": "rare-skill",       "cold_days": 45,  "total_calls": 25,  "utility": 0.80, "expected": "keep"},   # 冷但有效

    # 边界情况
    {"name": "borderline-skill", "cold_days": 60,  "total_calls": 20,  "utility": 0.31, "expected": "keep"},  # 刚好在阈值上
]
```

测试通过条件：`prune check` 对每个 case 输出与 `expected` 一致的建议。

**重复检测测试**：

```python
duplicate_cases = [
    # 应该被阻断的（高度重叠）
    {"new": "search-web-info",  "existing": "web-search",   "sim": 0.91, "expected": "block"},
    # 应该通过的（功能不同）
    {"new": "search-local-db",  "existing": "web-search",   "sim": 0.42, "expected": "allow"},
]
```

**依赖安全测试**：

```python
# 尝试归档有反向依赖的 skill，应该被阻断
assert deprecate("http-client") == "blocked"  # web-search 依赖它
# 先移除依赖，再归档，应该成功
update_dependency("web-search", remove="http-client")
assert deprecate("http-client") == "success"
```

---

### 层二：生态健康指标测试

验证在一段时间的模拟运行后，生态整体是否向健康方向演化。

**模拟数据生成**：

构造 100 个模拟 session，每个 session 随机调用 3-8 个 skill，success/fail 结果按照 skill 的预设质量分布生成。

**健康指标**：

| 指标 | 期望方向 | 测量方法 |
|---|---|---|
| skill 总数 | 收敛（不无限增长） | 每轮后统计 active + staging 数量 |
| 平均 utility_score | 上升 | 对比第 1 轮和第 10 轮的均值 |
| 重复 skill 对数 | 趋近 0 | 两两计算 embedding 相似度，统计超过阈值的对数 |
| deprecated 比例 | 合理（10%-30%） | deprecated 数 / 总数 |

**回放测试**（有真实数据时）：

如果团队有 Hermes 历史 session 记录，可以直接回放：

```bash
python prune replay --sessions ~/.hermes/history/ --registry ./skills-registry/
# 输出每轮后的生态健康报告
```

---

### 测试执行方式

```bash
# 单元测试（不需要真实数据）
pytest tests/test_prune check
pytest tests/test_prune similarity-check
pytest tests/test_prune dependency-check

# 生态模拟测试
python tests/prune simulate --rounds 10 --skills 50 --sessions-per-round 20

# 回放测试（需要真实 session 数据）
python tests/prune replay --sessions <path>
```

---

## 渐进部署计划

不需要一次性全量上线，按阶段部署：

**阶段 1（当前可做）**：只部署 fitness 追踪。在每个 skill 的 frontmatter 加入 `lifecycle.fitness` 字段，`prune update-fitness` 开始记录数据。这一步零风险，只是多了几个字段。

**阶段 2**：加入 `prune check`，每日生成健康报告，但不执行任何操作。团队观察 2-4 周，验证指标是否符合直觉。

**阶段 3**：加入重复检测 pre-commit hook，阻断明显重复的新 skill 进入。

**阶段 4**：开启人工确认的归档流程，`prune check` 输出建议，团队每周 review 一次，手动执行 `prune deprecate`。

**阶段 5**：数据积累足够后，评估是否开启半自动归档（`cold` 类型可以全自动，`low-utility` 类型仍需人工确认）。
