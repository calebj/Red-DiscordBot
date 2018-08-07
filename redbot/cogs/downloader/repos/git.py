import os
from pathlib import Path
from typing import Optional, MutableMapping, Tuple

from ..commands import COMMANDS
from ..errors import (
    GitUpdateError,
    MissingGitRepo,
    GitDiffError,
    CloningError,
    GitException,
    ExistingGitRepo,
    CurrentHashError,
    HardResetError,
)
from ..installable import FolderInstallable
from .folder import FolderRepo


class GitRepo(FolderRepo):
    def __init__(
        self,
        manager: "RepoManager",
        name: str,
        folder_path: Path,
        url: str = None,
        branch: str = None,
        available_modules: Tuple[FolderInstallable, ...] = (),
    ):

        self.url = url
        self.branch = branch

        super().__init__(manager, name, folder_path, available_modules=available_modules)

    async def get_repo_version(self):
        return await self.current_commit()

    async def get_repo_module_version(self, module):
        # noinspection PyProtectedMember
        path = module._location.relative_to(self.folder_path.resolve())
        return await self.current_commit(relative_file_path=str(path))

    async def _run(self, *args, **kwargs):
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        kwargs["env"] = env

        return await super()._run(*args, **kwargs)

    async def _update(self):
        curr_branch = await self.current_branch()

        await self.hard_reset(branch=curr_branch)

        p = await self._run(COMMANDS.GIT_PULL(path=self.folder_path))

        if p.returncode != 0:
            raise GitUpdateError(
                "Git pull returned a non zero exit code"
                " for the repo located at path: {}".format(self.folder_path)
            )

        self._update_available_modules()
        self._read_info_file()

    async def _get_file_update_statuses(
        self, old_ref: str, new_ref: str
    ) -> MutableMapping[str, str]:
        """
        Gets the file update status letters for each changed file between
            two refs.

        :param old_ref: Pre-update
        :param new_ref: Post-update
        :return: Mapping of filename -> status_letter
        """
        if not self.is_git_repo:
            raise MissingGitRepo("A git repo does not exist at path: {}".format(self.folder_path))

        p = await self._run(
            COMMANDS.GIT_DIFF_FILE_STATUS(path=self.folder_path, old_ref=old_ref, new_ref=new_ref)
        )

        if p.returncode != 0:
            raise GitDiffError("Git diff failed for repo at path: {}".format(self.folder_path))

        stdout = p.stdout.strip().decode().split("\n")

        ret = {}

        for filename in stdout:
            # TODO: filter these filenames by ones in self.available_modules
            status, _, filepath = filename.partition("\t")
            ret[filepath] = status

        return ret

    async def _get_commit_notes(self, old_commit_hash: str, relative_file_path: str) -> str:
        """
        Gets the commit notes from git log.
        :param old_commit_hash: Point in time to start getting messages
        :param relative_file_path: Path relative to the repo folder of the file
            to get messages for.
        :return: Git commit note log
        """
        if not self.is_git_repo:
            raise MissingGitRepo("A git repo does not exist at path: {}".format(self.folder_path))

        p = await self._run(
            COMMANDS.GIT_LOG(
                path=self.folder_path,
                old_ref=old_commit_hash,
                relative_file_path=relative_file_path,
            )
        )

        if p.returncode != 0:
            raise GitException(
                "An exception occurred while executing git log on"
                " this repo: {}".format(self.folder_path)
            )

        return p.stdout.decode().strip()

    async def clone(self, populate=True) -> Tuple[FolderInstallable, ...]:
        """Clone a new repo.

        Returns
        -------
        tuple of `str`
            All available module names from this repo.

        """

        if self.is_git_repo:
            raise ExistingGitRepo("{} is already a git repo".format(self.folder_path))

        if self.branch is not None:
            p = await self._run(
                COMMANDS.GIT_CLONE(branch=self.branch, url=self.url, folder=self.folder_path)
            )
        else:
            p = await self._run(
                COMMANDS.GIT_CLONE_NO_BRANCH(url=self.url, folder=self.folder_path)
            )

        if p.returncode != 0:
            raise CloningError("Error when running git clone.")

        if self.branch is None:
            self.branch = await self.current_branch()

        if populate:
            return self.populate()

    async def current_branch(self) -> str:
        """Determine the current branch using git commands.

        Returns
        -------
        str
            The current branch name.

        """
        if not self.is_git_repo:
            raise MissingGitRepo("A git repo does not exist at path: {}".format(self.folder_path))

        p = await self._run(COMMANDS.GIT_CURRENT_BRANCH(path=self.folder_path))

        if p.returncode != 0:
            raise GitException(
                "Could not determine current branch at path: {}".format(self.folder_path)
            )

        return p.stdout.decode().strip()

    async def current_commit(
        self, branch: str = None, relative_file_path: str = "."
    ) -> Optional[str]:
        """Determine the current commit hash of the repo.

        Parameters
        ----------
        branch : Optional[`str`]
            Override for repo's branch attribute.

        Returns
        -------
        Optional[`str`]
            The requested commit hash, if the path is tracked.

        """
        if branch is None:
            branch = self.branch

        if not self.is_git_repo:
            raise MissingGitRepo("A git repo does not exist at path: {}".format(self.folder_path))

        p = await self._run(
            COMMANDS.GIT_LATEST_COMMIT(
                path=self.folder_path, branch=branch, relative_file_path=relative_file_path
            )
        )

        if p.returncode != 0:
            raise CurrentHashError("Unable to determine commit hash.")

        return p.stdout.decode().strip() or None

    async def current_url(self, folder: Path = None) -> str:
        """
        Discovers the FETCH URL for a Git repo.

        Parameters
        ----------
        folder : pathlib.Path
            The folder to search for a URL.

        Returns
        -------
        str
            The FETCH URL.

        Raises
        ------
        RuntimeError
            When the folder does not contain a git repo with a FETCH URL.
        """
        if folder is None:
            folder = self.folder_path

        if not self.is_git_repo:
            raise MissingGitRepo("A git repo does not exist at path: {}".format(self.folder_path))

        p = await self._run(COMMANDS.GIT_DISCOVER_REMOTE_URL(path=folder, remote="origin"))

        if p.returncode != 0:
            raise RuntimeError("Unable to discover a repo URL.")

        return p.stdout.decode().strip()

    async def hard_reset(self, branch: str = None) -> None:
        """Perform a hard reset on the current repo.

        Parameters
        ----------
        branch : str, optional
            Override for repo branch attribute.

        """
        if branch is None:
            branch = self.branch

        if not self.is_git_repo:
            raise MissingGitRepo("A git repo does not exist at path: {}".format(self.folder_path))

        p = await self._run(COMMANDS.GIT_HARD_RESET(path=self.folder_path, branch=branch))

        if p.returncode != 0:
            raise HardResetError(
                "Some error occurred when trying to"
                " execute a hard reset on the repo at"
                " the following path: {}".format(self.folder_path)
            )

    @classmethod
    async def from_folder(cls, manager: "RepoManager", folder: Path):
        repo = cls(name=folder.stem, manager=manager, folder_path=folder)
        repo._update_available_modules()
        repo.branch = await repo.current_branch()
        repo.url = await repo.current_url()
        return repo
