# prune — 背景与需求

## 背景

### Hermes Agent 与 Skill 机制

Hermes Agent 是 Nous Research 开源的自改进 AI agent 框架（MIT 协议，当前约 105,000 GitHub stars）。其核心设计理念是**闭环学习**：agent 不仅执行任务，还能将解决复杂任务的过程固化为可复用的 skill，供后续任务直接调用。

Skill 的本质是存储在 `~/.hermes/skills/` 下的结构化 Markdown 文件，遵循 agentskills.io 开放标准。每个 skill 是一个目录，包含：

- `SKILL.md`：核心文件，YAML frontmatter（元数据）+ Markdown 正文（流程、pitfalls、验证步骤）
- 可选的参考文件、脚本、模板

Hermes 使用三级渐进加载机制控制 token 消耗：

```
Level 0  session 启动时加载所有 skill 的名称和描述（约 3,000 tokens）
Level 1  agent 判断需要时加载某个 skill 的完整 SKILL.md
Level 2  agent 按需加载 skill 目录内的某个具体参考文件
```

### Skill 的三种来源

**自动生成**：完成 5+ 工具调用的复杂任务后，Hermes 通过 `skill_manage` 工具自动将解决过程提炼为 skill，提取流程、记录已知 pitfalls、定义验证步骤。

**自我改进**：skill 在后续使用中被调用时，agent 发现更优方案后可直接更新 skill 内容，不需要人工介入。

**人工编写**：团队成员手动在 skills 目录中创建 SKILL.md，适合已有成熟流程但尚未被 agent 自动发现的场景。

### 现存问题：Skill 生态失控

Hermes 的自动生成机制没有内置的上限控制。随着使用时间增长，skill 库面临以下问题：

**重复膨胀**：同一类任务（如"搜索网络信息"）可能产生多个高度相似的 skill，每个都宣称自己是处理该类任务的正确方式。在 Level 0 加载时，这些 skill 的 description 语义接近，导致 agent 选择混乱。

**相互干扰**：多个同类 skill 并存时，它们的 trigger 条件重叠，agent 在路由时无法可靠地选出最优者，实际表现为任务完成质量不稳定。

**无退出机制**：Hermes 原生只提供 Create 和 Refine 操作，没有 Delete 或 Deprecate 机制。skill 只增不减，生态无法自我净化。

**缺乏可观测性**：现有 frontmatter 没有记录 skill 被调用的次数、成功率、上次调用时间等适应度数据，团队无法判断哪些 skill 实际有用、哪些已经死亡。

---

## 需求

### 核心目标

构建一套基于 Git 的 Skill 生命周期管理系统，使 Hermes 的 skill 生态具备**有出生、有死亡、有优胜劣汰**的自我调节能力。

### 功能需求

#### 1. Skill 生命周期状态管理

每个 skill 应处于且仅处于以下三种状态之一：

| 状态 | 含义 | 存储位置 |
|---|---|---|
| `staging` | 新生，试用期，等待验证 | `staging/` |
| `active` | 通过验证，生产环境可用 | `active/` |
| `deprecated` | 退出，永久归档，不再调用 | `deprecated/YYYY-MM/` |

状态转换由可量化的适应度指标驱动，不依赖人工判断。

#### 2. 适应度追踪

agent 在每次 session 结束后自动更新 skill 的适应度数据，记录在 SKILL.md frontmatter 中，包括：

- 累计调用次数
- 成功率
- 上次调用时间 / 冷却天数
- utility score（有 skill 注入时的成功率提升）

#### 3. Delete 机制（核心需求）

skill 退出生态必须有明确的触发条件和执行流程，详见《Delete 机制设计》文档。退出的 skill 永远不硬删除，只归档到 `deprecated/` 目录，保留完整历史。

#### 4. 重复检测与 Merge

新 skill 进入 staging 前，系统自动检测与现有 skill 的语义相似度。相似度超过阈值时阻断创建，强制走 merge 流程：弱者的有效 trigger 和内容被合并进强者，弱者归档。

#### 5. 依赖安全

skill 之间存在调用依赖（例如 `research-assistant` 依赖 `web-search`）。删除任何 skill 之前，系统必须检查反向依赖，存在未解决依赖时阻断删除操作。

#### 6. Git 作为基础设施

所有 skill 变更通过 Git 提交，实现：

- 完整变更历史（每次 fitness 更新、每次 refine、每次状态转换）
- 任意版本回滚
- 团队协作（多人共享同一 skill registry repo）
- 归档可溯源（`deprecated/` 目录的 skill 可通过 git checkout 完整恢复）

#### 7. 测试与 Eval

系统需要可验证。需要：

- **单元测试**：各触发条件是否正确判断（该死的 skill 死了、不该死的活着）
- **生态健康指标测试**：skill 数量是否收敛、平均 utility score 是否随时间上升
- **合成数据集**：在没有足够真实 session 数据时，用构造的 skill + session 数据验证机制正确性

### 非功能需求

- **轻量**：不引入新的数据库或服务，只依赖 Git 和 Python 标准库
- **透明**：所有决策可通过 git log 审计，没有黑盒逻辑
- **渐进部署**：可以先只部署 fitness 追踪，再逐步加入自动归档，不需要一次性全量上线
- **兼容 Hermes 原生格式**：扩展 frontmatter，不破坏 Hermes 原有的 skill 加载机制

### 明确不做的事

- 不修改 Hermes agent 的核心代码，只在 skill registry 层操作
- 不引入参数级的 machine unlearning（模型权重层面的遗忘），只做文件层面的管理
- 不替代 SkillClaw 的 Refine/Create 功能，两者互补
