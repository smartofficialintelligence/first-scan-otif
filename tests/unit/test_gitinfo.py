"""Git provenance shared by model artifacts and decision records."""

from __future__ import annotations

import subprocess

import pytest

from olist_ml.gitinfo import current_git_sha


@pytest.fixture(autouse=True)
def _clear_sha_cache() -> None:
    current_git_sha.cache_clear()
    yield
    current_git_sha.cache_clear()


def test_git_sha_prefers_git_sha_over_github_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    monkeypatch.setenv("GITHUB_SHA", "deadbeefcafebabe")
    assert current_git_sha() == "abc1234"


def test_git_sha_falls_back_to_github_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.setenv("GITHUB_SHA", "  cafebabe  ")
    assert current_git_sha() == "cafebabe"


def test_git_sha_truncated_to_40(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_SHA", "a" * 64)
    assert current_git_sha() == "a" * 40


def test_git_sha_none_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    def boom(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise FileNotFoundError("git")

    monkeypatch.setattr("olist_ml.gitinfo.subprocess.check_output", boom)
    assert current_git_sha() is None


def test_git_sha_none_when_git_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(
        "olist_ml.gitinfo.subprocess.check_output",
        lambda *_args, **_kwargs: "  \n",
    )
    assert current_git_sha() is None


def test_git_sha_none_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    def boom(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise subprocess.TimeoutExpired(cmd="git", timeout=2)

    monkeypatch.setattr("olist_ml.gitinfo.subprocess.check_output", boom)
    assert current_git_sha() is None
