from typing import Optional

from prune.registry import load_registry, Skill


def _skill_text(skill: Skill) -> str:
    parts = [skill.name.replace("-", " ").replace("_", " ")]
    if skill.description:
        parts.append(skill.description)
    return " ".join(parts).lower()


def check_similarity(
    skill_name: str,
    description: Optional[str],
    skills_dir: Optional[str],
    threshold: float = 0.85,
) -> list[tuple[str, float]]:
    """
    Returns list of (existing_skill_name, similarity_score) pairs above threshold,
    sorted by score descending.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np

    existing, _ = load_registry(skills_dir)
    if not existing:
        return []

    # Build a temporary Skill-like object for the new skill
    _desc = description

    class _Mock:
        name = skill_name
        description = _desc

    new_text = _skill_text(_Mock())  # type: ignore
    corpus = [_skill_text(s) for s in existing]

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    all_texts = corpus + [new_text]
    tfidf = vectorizer.fit_transform(all_texts)

    new_vec = tfidf[-1]
    existing_vecs = tfidf[:-1]
    scores = cosine_similarity(new_vec, existing_vecs).flatten()

    results = [
        (existing[i].name, float(scores[i]))
        for i in range(len(existing))
        if scores[i] >= threshold
    ]
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def cmd_similarity_check(
    skills_dir: Optional[str],
    skill_name: str,
    description: Optional[str],
    threshold: float,
) -> None:
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()

    console.print(f"Checking similarity for [bold]{skill_name}[/bold] (threshold: {threshold})")

    matches = check_similarity(skill_name, description, skills_dir, threshold)

    if not matches:
        console.print("[green]✓ No similar skills found. Safe to create.[/green]")
        return

    console.print(f"[red]BLOCKED:[/red] {skill_name} is too similar to existing skills:\n")

    table = Table(box=box.SIMPLE_HEAD)
    table.add_column("Existing skill", style="bold")
    table.add_column("Similarity", justify="right")

    for name, score in matches:
        table.add_row(name, f"{score:.2f}")

    console.print(table)
    console.print(
        "\n[yellow]Suggestion:[/yellow]\n"
        "  A) Extend the existing skill instead of creating a new one\n"
        "  B) If truly different, add a [bold]differentiation[/bold] field to your SKILL.md "
        "explaining the distinction"
    )
    raise SystemExit(1)
