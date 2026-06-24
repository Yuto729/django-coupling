import subprocess

from django_coupling.volatility import commit_counts


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True, text=True)


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    return repo


def _commit(repo, files, msg):
    for name in files:
        # vary content per commit so re-touching a file is a real change
        (repo / name).write_text(f"# {msg}\nx = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def test_no_git_returns_empty(tmp_path):
    counts, diag = commit_counts(str(tmp_path))
    assert counts == {} and diag is None


def test_counts_and_bulk_exclusion(tmp_path):
    repo = _make_repo(tmp_path)
    # small commit: 2 files
    _commit(repo, ["a.py", "b.py"], "small")
    # touch a.py again in another small commit
    _commit(repo, ["a.py"], "small2")
    # bulk commit: 5 files (over the threshold we pass below)
    _commit(repo, [f"bulk{i}.py" for i in range(5)], "bulk")

    counts, diag = commit_counts(str(repo), max_files=4)
    assert diag is not None
    # a.py touched in 2 (non-bulk) commits, b.py in 1
    assert counts[str(repo / "a.py")] == 2
    assert counts[str(repo / "b.py")] == 1
    # the 5-file bulk commit is excluded -> its files are not counted
    assert str(repo / "bulk0.py") not in counts
    assert diag["excluded_bulk"] == 1
    assert diag["commits"] == 3
    assert diag["counted_commits"] == 2


def test_confidence_high_for_small_commits(tmp_path):
    repo = _make_repo(tmp_path)
    _commit(repo, ["a.py", "b.py"], "c1")
    _commit(repo, ["a.py"], "c2")
    _, diag = commit_counts(str(repo), max_files=30)
    assert diag["confidence"] == "high"
