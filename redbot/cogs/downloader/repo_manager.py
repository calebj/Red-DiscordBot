import asyncio
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesHeaderParser
import functools
import os
from pathlib import Path
import re
from subprocess import run as sp_run, PIPE
from sys import executable
from typing import Optional, MutableMapping, Collection, Tuple, Union, TYPE_CHECKING

from redbot.core import data_manager
from .commands import COMMANDS
from .errors import (
    DownloaderException,
    InvalidRepoName,
    ExistingRepo,
    ExistingGitRepo,
    MissingRepo,
    UpdateError,
)
from .installable import Installable
from .log import log
from .repo import Repo
from .repos.git import GitRepo
from .repos.folder import FolderRepo
from .update_tracker import UpdateResult
from .utils import is_path_git_repo, is_venv


if TYPE_CHECKING:
    from .downloader import Downloader


class RepoManager:
    GITHUB_OR_GITLAB_RE = re.compile("https?://git(?:hub)|(?:lab)\.com/")
    TREE_URL_RE = re.compile(r"(?P<tree>/tree)/(?P<branch>\S+)$")

    def __init__(self, threads: int = 4, loop=None):

        loop = loop or asyncio.get_event_loop()

        self._repos = {}
        self._executor = ThreadPoolExecutor(threads)
        self._loop = loop
        self._threads = threads
        self._pip_lock = asyncio.Lock(loop=loop)

        self._loop.create_task(self._load_repos(update=True))  # str_name: Repo

    @property
    def repos_folder(self) -> Path:
        data_folder = data_manager.cog_data_path(self)
        return data_folder / "repos"

    def does_repo_exist(self, name: str) -> bool:
        return name in self._repos

    @staticmethod
    def validate_and_normalize_repo_name(name: str) -> str:
        if not name.isidentifier():
            raise InvalidRepoName(name)

        return name.lower()

    async def add_folder_repo(self, name: str, path: Optional[Path] = None) -> FolderRepo:
        """
        Add and clone a git repository.

        Parameters
        ----------
        name : str
            Internal name of the repository.
        path : optional[:class:`~pathlib.Path`]
            Path to the repository

        Returns
        -------
        :class:`~.repos.folder.FolderRepo`
            The newly added repository.

        """
        name = RepoManager.validate_and_normalize_repo_name(name)

        if self.does_repo_exist(name):
            raise ExistingRepo(name)

        r = FolderRepo(manager=self, name=name, folder_path=path or (self.repos_folder / name))
        r.populate()

        self._repos[name] = r

        return r

    async def add_git_repo(self, name: str, url: str, branch: Optional[str] = None) -> GitRepo:
        """
        Add and clone a git repository.

        Parameters
        ----------
        url : str
            URL to the git repository.
        name : str
            Internal name of the repository.
        branch : Optional[`str`]
            Name of the default branch to checkout into.

        Returns
        -------
        :class:`~.repos.git.GitRepo`
            The newly added and cloned repository.

        """
        name = RepoManager.validate_and_normalize_repo_name(name)

        if self.does_repo_exist(name):
            raise ExistingGitRepo(name)

        url, branch = self._parse_url(url, branch)

        r = GitRepo(
            manager=self, name=name, folder_path=self.repos_folder / name, url=url, branch=branch
        )
        await r.clone()

        self._repos[name] = r

        return r

    def get_repo(self, name: str) -> Optional[Repo]:
        """
        Get a Repo object for a repository.

        Parameters
        ----------
        name : str
            The name of the repository to retrieve.

        Returns
        -------
        Optional[:class:`~.repo.Repo`]
            Repo object for the repository, if it exists.

        """
        return self._repos.get(name, None)

    def get_all_repo_names(self) -> Tuple[str, ...]:
        """Get all repo names.

        Returns
        -------
        Tuple[`str`, ...]
            The names of all configured repositories.

        """
        return tuple(self._repos.keys())

    def get_all_repos(self) -> Tuple[Repo, ...]:
        """Get all repos.

        Returns
        -------
        Tuple[:class:`~.repo.Repo`, ...]
            All configured repositories.

        """
        return tuple(self._repos.keys())

    async def delete_repo(self, name: str):
        """
        Delete a repository and its folders.

        This is the same as calling :meth:`Repo.delete()`

        Parameters
        ----------
        name : str
            The name of the repository to delete.

        Raises
        ------
        :class:`~.errors.MissingRepo`
            If the repo does not exist.

        """
        repo = self.get_repo(name)

        if repo is None:
            raise MissingRepo(name)

        await repo.delete()

        try:
            del self._repos[name]
        except KeyError:
            pass

    async def update_repo(self, name: str) -> Optional[UpdateResult]:
        """
        Updates a repository.

        Parameters
        ----------
        name : str
            The name of the repository to update.

        Raises
        ------
        :class:`~.errors.MissingRepo`
            If the repo does not exist.

        """
        repo = self.get_repo(name)

        if repo is None:
            raise MissingRepo(name)

        return await repo.update()

    async def update_all_repos(self) -> MutableMapping[Repo, Union[Exception, UpdateResult]]:
        """
        Call `Repo.update()` on all repositories.

        Returns
        -------
        dict
            A mapping of :class:`~.repo.Repo` objects that received updates to
            :class:`~.update_tracker.UpdateResult` objects if successful, or any
            :class:`Exception` that occured during the process.

        """
        ret = {}

        for repo in self._repos.values():
            try:
                result = await repo.update(wrap_exception=True)
                if result:
                    ret[result.repo] = result
            except UpdateError as e:
                ret[e.repo] = e.original

        return ret

    async def pip_show(
        self,
        downloader: "Downloader",
        packages: Collection[str],
        force_venv: Optional[bool] = None,
    ) -> MutableMapping[str, Optional[str]]:
        """
        Checks which versions of packages are installed using ``pip show``.

        Parameters
        ----------
        downloader : Downloader
            The Downloader cog which is calling the check.
        packages : Collection[`str`]
            List of package names to check via pip.
        force_venv : Optional[bool]
            If not `None`, override venv detection to be this value.

        Returns
        -------
        dict
            A mapping of the found package names and their version if installed or `None` if not.
        """
        if not packages:
            return {}

        if is_venv() if force_venv is None else force_venv:
            env = None
        else:
            env = os.environ.copy()
            env["PYTHONPATH"] = downloader.LIB_PATH

        packages = set(packages)  # deduplicate

        cmd = COMMANDS.PIP_SHOW(python=executable, packages=packages)

        async with self._pip_lock:
            p = await self._run(cmd, env=env)

        parser = BytesHeaderParser()
        versions = {}

        for msg in p.stdout.split(b"\n---\n"):
            msg = dict(parser.parsebytes(msg))
            versions[msg["Name"].lower()] = msg["Version"]

        return {p: versions.get(p.lower()) for p in packages}

    async def pip_install(
        self,
        downloader: "Downloader",
        requirements: Collection[str],
        force_venv: Optional[bool] = None,
    ) -> bool:
        """
        Install a list of requirements using ``pip install``.

        Parameters
        ----------
        downloader : Downloader
            The Downloader cog which is calling the installation
        requirements : Collection[`str`]
            List of requirement names to install via pip.
        force_venv : Optional[`bool`]
            If not `None`, override venv detection to be this value.

        Returns
        -------
        bool
            Whether the installation succeeded.

        """
        if not requirements:
            return True

        if is_venv() if force_venv is None else force_venv:
            cmd = COMMANDS.PIP_INSTALL_NO_TARGET(python=executable, reqs=requirements)
        else:
            target_dir = downloader.LIB_PATH
            cmd = COMMANDS.PIP_INSTALL(python=executable, target_dir=target_dir, reqs=requirements)

        async with self._pip_lock:
            p = await self._run(cmd)

        if p.returncode == 0:
            return True

        log.error("Error while installing requirements: {}".format(", ".join(requirements)))
        return False

    async def install_requirements(self, downloader: "Downloader", module: Installable) -> bool:
        """
        Install a module's requirements using pip.

        Parameters
        ----------
        downloader : Downloader
            The Downloader cog which is calling the installation
        module : Installable
            Module for which to install requirements.

        Returns
        -------
        bool
            Success of the installation.

        """
        return await self.pip_install(downloader, module.requirements)

    async def _run(self, *args, **kwargs):
        return await self._loop.run_in_executor(
            self._executor, functools.partial(sp_run, *args, stdout=PIPE, **kwargs)
        )

    async def _load_repos(self, update=False) -> MutableMapping[str, Repo]:
        ret = {}
        self.repos_folder.mkdir(parents=True, exist_ok=True)

        for folder in self.repos_folder.iterdir():
            if not folder.is_dir():
                continue

            repo_cls = GitRepo if is_path_git_repo(folder) else FolderRepo

            try:
                repo = await repo_cls.from_folder(manager=self, folder=folder)
                ret[folder.stem] = repo
            except DownloaderException as e:
                # Thrown when there's no findable git remote URL
                log.exception(e)

        if update:
            self._repos = ret

        return ret

    def _parse_url(self, url: str, branch: Optional[str]) -> Tuple[str, Optional[str]]:
        if self.GITHUB_OR_GITLAB_RE.match(url):
            tree_url_match = self.TREE_URL_RE.search(url)

            if tree_url_match:
                url = url[: tree_url_match.start("tree")]

                if branch is None:
                    branch = tree_url_match["branch"]

        return url, branch
