import aiohttp
from collections import namedtuple
import pathlib
from pathlib import Path
from sys import path as syspath
import yaml

import pytest
from unittest.mock import MagicMock
from raven.versioning import fetch_git_sha

from redbot.pytest.downloader import *

from redbot.cogs.downloader.repo_manager import RepoManager
from redbot.cogs.downloader.repos.git import GitRepo
from redbot.cogs.downloader.errors import ExistingGitRepo, InvalidRepoName


def test_existing_git_repo(tmpdir, repo_manager):
    repo_folder = Path(tmpdir) / "repos" / "squid" / ".git"
    repo_folder.mkdir(parents=True, exist_ok=True)

    repo = GitRepo(
        manager=repo_manager,
        name="squid",
        folder_path=repo_folder.parent,
        url="https://github.com/tekulvw/Squid-Plugins",
        branch="rewrite_cogs",
    )

    assert repo.is_git_repo


def test_from_bot_folder(bot_folder_repo):
    assert bot_folder_repo.is_git_repo


@pytest.mark.asyncio
async def test_clone_repo(git_repo, repo_manager_norun, capsys):
    git_repo.manager = repo_manager_norun
    await git_repo.clone()

    clone_cmd, _ = capsys.readouterr()
    clone_cmd = clone_cmd.strip("[']\n").split("', '")
    assert clone_cmd[:5] == "git clone -b rewrite_cogs".split() + [git_repo.url]
    assert pathlib.Path(clone_cmd[5]).parts[-2:] == ("repos", "squid")


@pytest.mark.asyncio
async def test_add_remove_git_repo(monkeypatch, repo_manager):
    monkeypatch.setattr("redbot.cogs.downloader.repo_manager.RepoManager._run", fake_run_noprint)

    repo = await repo_manager.add_git_repo(
        url="https://github.com/tekulvw/Squid-Plugins", name="squid", branch="rewrite_cogs"
    )
    assert repo.available_modules == ()
    assert repo_manager.get_repo("squid") is repo
    await repo_manager.delete_repo("squid")
    assert repo_manager.get_repo("squid") is None


@pytest.mark.asyncio
async def test_add_remove_folder_repo(monkeypatch, repo_manager):
    monkeypatch.setattr("redbot.cogs.downloader.repo_manager.RepoManager._run", fake_run_noprint)

    repo = await repo_manager.add_folder_repo(name="test_add_del")
    assert repo.available_modules == ()
    assert repo_manager.get_repo("test_add_del") is repo
    await repo_manager.delete_repo("test_add_del")
    assert repo_manager.get_repo("test_add_del") is None


@pytest.mark.asyncio
async def test_invalid_repos(monkeypatch, repo_manager):
    monkeypatch.setattr("redbot.cogs.downloader.repo_manager.RepoManager._run", fake_run_noprint)

    with pytest.raises(InvalidRepoName):
        await repo_manager.add_git_repo(url="test_dup_1", name="http://test.com")

    with pytest.raises(InvalidRepoName):
        await repo_manager.add_folder_repo(name="invalid!repo:name")


@pytest.mark.asyncio
async def test_current_branch(bot_git_repo):
    branch = await bot_git_repo.current_branch()

    # So this does work, just not sure how to fully automate the test

    assert branch not in ("WRONG", "")


@pytest.mark.asyncio
async def test_repo_hash(bot_git_repo):
    branch = await bot_git_repo.current_branch()
    bot_git_repo.branch = branch

    commit = await bot_git_repo.current_commit()

    sentry_sha = fetch_git_sha(str(bot_git_repo.folder_path))

    assert sentry_sha == commit


@pytest.mark.asyncio
async def test_subdir_hash(bot_git_repo):
    branch = await bot_git_repo.current_branch()
    bot_git_repo.branch = branch

    commit = await bot_git_repo.current_commit(relative_file_path="redbot")

    assert commit  # fetch_git_sha only works in repo root


@pytest.mark.asyncio
async def test_untracked_hash(bot_git_repo):
    branch = await bot_git_repo.current_branch()
    bot_git_repo.branch = branch

    commit = await bot_git_repo.current_commit(relative_file_path=".git")

    assert commit is None


@pytest.mark.asyncio
async def test_does_repo_exist(repo_manager):
    repo_manager.does_repo_exist = MagicMock(return_value=True)

    with pytest.raises(ExistingGitRepo):
        await repo_manager.add_git_repo(name="test_dup_1", url="http://test.com")

    repo_manager.does_repo_exist.assert_called_once_with("test_dup_1")


@pytest.mark.asyncio
async def test_existing_repo(repo_manager_norun):
    await repo_manager_norun.add_git_repo(name="test_dup_2", url="http://test.com", branch="master")

    with pytest.raises(ExistingGitRepo):
        await repo_manager_norun.add_git_repo(name="test_dup_2", url="http://test.com", branch="master")


@pytest.mark.asyncio
async def test_pip_show(repo_manager, tmpdir):
    fake_downloader = namedtuple("Downloader", "LIB_PATH")(Path(tmpdir) / "lib")
    packages = {"pyyaml": yaml, "aiohttp": aiohttp}

    versions = await repo_manager.pip_show(fake_downloader, packages.keys())

    for name, module in packages.items():
        assert versions[name] == module.__version__


@pytest.mark.asyncio
async def test_pip_install(repo_manager, tmpdir):
    fake_libpath = Path(tmpdir) / "lib"
    fake_libpath.mkdir(exist_ok=True, parents=True)
    fake_downloader = namedtuple("Downloader", "LIB_PATH")(fake_libpath)

    installed_ok = await repo_manager.pip_install(
        fake_downloader, ("aiorwlock==0.5.0",), force_venv=False
    )

    assert installed_ok
    old_path = syspath.copy()
    syspath.insert(0, str(fake_libpath))

    try:
        import aiorwlock

        assert aiorwlock.__version__ == "0.5.0"
        assert Path(aiorwlock.__path__[0]).parent == fake_libpath
    finally:
        syspath[:] = old_path


def test_tree_url_parse(repo_manager):
    cases = [
        {
            "input": ("https://github.com/Tobotimus/Tobo-Cogs", None),
            "expected": ("https://github.com/Tobotimus/Tobo-Cogs", None),
        },
        {
            "input": ("https://github.com/Tobotimus/Tobo-Cogs", "V3"),
            "expected": ("https://github.com/Tobotimus/Tobo-Cogs", "V3"),
        },
        {
            "input": ("https://github.com/Tobotimus/Tobo-Cogs/tree/V3", None),
            "expected": ("https://github.com/Tobotimus/Tobo-Cogs", "V3"),
        },
        {
            "input": ("https://github.com/Tobotimus/Tobo-Cogs/tree/V3", "V4"),
            "expected": ("https://github.com/Tobotimus/Tobo-Cogs", "V4"),
        },
    ]

    for test_case in cases:
        assert test_case["expected"] == repo_manager._parse_url(*test_case["input"])
