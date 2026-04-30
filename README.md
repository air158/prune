# prune

A skill lifecycle manager for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Keeps your skill registry healthy by surfacing cold, low-utility, and duplicate skills before they degrade your agent's routing quality.

```
Skill                  Status   Utility  Cold Days  Data Source  Recommendation
────────────────────────────────────────────────────────────────────────────────
old-file-converter     active   0.21     75         fitness      LOW_UTILITY ⚠
image-downloader       active   0.85     68         fitness      COLD ❄
web-search-v2          staging  —        3          mtime        INVESTIGATE
web-search             active   0.91     0          fitness      KEEP
research-assistant     active   0.87     2          fitness      KEEP
```

## The problem

Hermes auto-generates skills from completed tasks. There's no upper bound and no exit. Over time, skill registries accumulate duplicates, low-utility skills that nobody calls, and cold skills that used to matter but don't anymore. Hermes loads all skill names and descriptions at session start (~3,000 tokens for Level 0). More skills = worse routing.

The research community has ADD/UPDATE/DELETE pipelines for memory. The skill ecosystem only has ADD and UPDATE. **prune fills the DELETE primitive.**

## Install

```bash
git clone https://github.com/air158/prune.git
cd prune
pip install -r requirements.txt
```

## Usage

```bash
# Scan your ~/.hermes/skills/ registry
python -m prune check

# Scan a custom directory
python -m prune check --dir /path/to/skills/
```

## How it works

`prune check` reads the `lifecycle.fitness` block in each skill's frontmatter:

```yaml
lifecycle:
  status: active        # active | staging | deprecated
  fitness:
    total_calls: 847
    success_count: 770
    last_called: 2026-04-29
```

If a skill doesn't have fitness data yet, `prune check` falls back to the file's `mtime` to estimate cold days. The `Data Source` column tells you which method was used.

### Recommendation logic

| Condition | Recommendation |
|---|---|
| `cold_days >= 60` AND `total_calls >= 20` | COLD ❄ |
| `utility_score < 0.30` AND `total_calls >= 20` | LOW_UTILITY ⚠ |
| `total_calls < 20` OR `status == staging` | INVESTIGATE |
| everything else | KEEP |

`utility_score = success_count / total_calls`

### Git-based audit trail

All skill changes — fitness updates, deprecations, promotions — go through Git commits with a consistent prefix so you can filter by event type:

```bash
# See only structural changes
git log --oneline --grep="^deprecate\|^promote\|^merge\|^feat"

# See fitness history for one skill
git log --oneline --grep="fitness(web-search)"
```

## Roadmap

- [x] `prune check` — scan registry, output ranked fitness report
- [ ] `prune update-fitness` — update frontmatter after each session, git commit
- [ ] `prune deprecate` — archive a skill, write RETIRE.md, git commit
- [ ] `prune promote` — move staging skill to active
- [ ] `prune similarity-check` — pre-commit hook, block duplicate skills
- [ ] PyPI packaging (`pip install prune-cli`)

## Design

The full design is in [`doc/`](doc/):

- [`01-background-requirements.md`](doc/01-background-requirements.md) — why this exists
- [`02-system-design.md`](doc/02-system-design.md) — architecture and Git conventions
- [`03-delete-mechanism.md`](doc/03-delete-mechanism.md) — the three exit paths

## Philosophy

Skills that don't earn their keep get evicted. Not a garbage collector — an immune system.

prune suggests. You decide. `prune check` only reads. `prune deprecate` requires explicit confirmation.

## License

MIT
