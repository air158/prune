import subprocess
from pathlib import Path
from typing import Union


class GitError(Exception):
    pass


def is_git_repo(path: Union[str, Path]) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(path),
        capture_output=True,
    )
    return result.returncode == 0


def git_commit(repo_dir: Union[str, Path], message: str, paths: list[str]) -> None:
    repo = str(repo_dir)
    try:
        subprocess.run(
            ["git", "add", "--"] + paths,
            cwd=repo, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo, check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise GitError(e.stderr.decode().strip()) from e
