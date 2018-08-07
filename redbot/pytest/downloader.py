from collections import namedtuple
from pathlib import Path
import json

import pytest

from redbot.cogs.downloader.repo_manager import RepoManager
from redbot.cogs.downloader.repos.git import GitRepo
from redbot.cogs.downloader.repos.folder import FolderRepo
from redbot.cogs.downloader.installable import FolderInstallable

__all__ = [
    "patch_relative_to",
    "repo_manager",
    "folder_repo",
    "git_repo",
    "repo_manager_norun",
    "bot_folder_repo",
    "bot_git_repo",
    "INFO_JSON",
    "installable",
    "fake_run_noprint",
]


async def fake_run(*args, **kwargs):
    fake_result_tuple = namedtuple("fake_result", "returncode result")
    res = fake_result_tuple(0, (args, kwargs))
    print(args[0])
    return res


async def fake_run_noprint(*args, **kwargs):
    fake_result_tuple = namedtuple("fake_result", "returncode result")
    res = fake_result_tuple(0, (args, kwargs))
    return res


@pytest.fixture(scope="module", autouse=True)
def patch_relative_to(monkeysession):
    def fake_relative_to(self, some_path: Path):
        return self

    monkeysession.setattr("pathlib.Path.relative_to", fake_relative_to)


@pytest.fixture
def repo_manager(monkeypatch, tmpdir_factory, event_loop):
    rm = RepoManager()
    repos_folder = Path(str(tmpdir_factory.getbasetemp())) / "repos"
    monkeypatch.setattr(
        "redbot.cogs.downloader.repo_manager.RepoManager.repos_folder", repos_folder
    )
    return rm


@pytest.fixture
def git_repo(tmpdir, repo_manager):
    repo_folder = Path(str(tmpdir)) / "repos" / "squid"
    repo_folder.mkdir(parents=True, exist_ok=True)

    repo = GitRepo(
        manager=repo_manager,
        name="squid",
        folder_path=repo_folder,
        url="https://github.com/tekulvw/Squid-Plugins",
        branch="rewrite_cogs",
    )
    repo.populate()
    repo_manager._repos[repo.name] = repo
    return repo


@pytest.fixture
def folder_repo(tmpdir, repo_manager):
    repo_folder = Path(str(tmpdir)) / "repos" / "test_repo"
    repo_folder.mkdir(parents=True, exist_ok=True)

    repo = FolderRepo(manager=repo_manager, name="test_repo", folder_path=repo_folder)
    repo.populate()
    repo_manager._repos[repo.name] = repo
    return repo


@pytest.fixture
def repo_manager_norun(repo_manager):
    repo_manager._run = fake_run
    return repo_manager


@pytest.fixture
def bot_git_repo(repo_manager):
    repo = GitRepo(manager=repo_manager, name="Red-DiscordBot", folder_path=Path.cwd())
    repo.populate()
    repo_manager._repos[repo.name] = repo
    return repo


@pytest.fixture
def bot_folder_repo(repo_manager):
    repo = FolderRepo(manager=repo_manager, name="Red-DiscordBot", folder_path=Path.cwd())
    repo.populate()
    repo_manager._repos[repo.name] = repo
    return repo


# Installable
INFO_JSON = {
    "author": ("tekulvw",),
    "bot_version": (3, 0, 0),
    "description": "A long description",
    "hidden": False,
    "install_msg": "A post-installation message",
    "required_cogs": {},
    "requirements": ("tabulate"),
    "short": "A short description",
    "tags": ("tag1", "tag2"),
    "type": "COG",
}


@pytest.fixture
def installable(repo_manager, folder_repo):
    cog_path = folder_repo.folder_path / "test_cog"
    info_path = cog_path / "info.json"
    init_path = cog_path / "__init__.py"

    cog_path.mkdir(parents=True, exist_ok=True)
    init_path.touch(exist_ok=True)

    with info_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(INFO_JSON))

    folder_repo.populate()

    cog = FolderInstallable(folder_repo, Path(str(cog_path)))
    return cog
