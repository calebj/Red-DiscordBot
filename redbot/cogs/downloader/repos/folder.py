import pkgutil
from pathlib import Path
from typing import Collection, Tuple

from redbot.core.utils import safe_delete
from ..errors import MissingModule, InstallationError
from ..installable import FolderInstallable
from ..json_mixins import RepoJSONMixin
from ..utils import is_path_git_repo
from ..repo import Repo


class FolderRepo(Repo, RepoJSONMixin):
    def __init__(
        self,
        manager: "RepoManager",
        name: str,
        folder_path: Path,
        available_modules: Tuple[FolderInstallable, ...] = (),
    ):

        Repo.__init__(self, manager, name, available_modules=available_modules)

        self.folder_path = folder_path
        RepoJSONMixin.__init__(self, self.folder_path)

    @property
    def is_git_repo(self) -> bool:
        return is_path_git_repo(self.folder_path)

    async def get_repo_version(self) -> str:
        raise NotImplementedError

    async def get_repo_module_version(self, module: FolderInstallable) -> str:
        raise NotImplementedError

    def _update_available_modules(self):
        curr_modules = []

        for file_finder, name, is_pkg in pkgutil.walk_packages(
            path=[str(self.folder_path)], onerror=lambda name: None
        ):
            if is_pkg:
                curr_modules.append(FolderInstallable(self, location=self.folder_path / name))

        self.available_modules = tuple(curr_modules)

        return self.available_modules

    async def _update(self):
        raise NotImplementedError

    async def delete(self) -> None:
        safe_delete(self.folder_path)

    async def install_cog(self, downloader, cog: FolderInstallable) -> bool:
        if cog.repo is not self:
            raise ValueError(f"the {cog.name} cog does not belong to the {self.name} repo")
        elif cog not in self.available_cogs:
            raise MissingModule(f"the {cog.name} cog is not available in the {self.name} repo")

        target_dir = await downloader.cog_install_path()

        if not target_dir.exists():
            raise InstallationError(f"install target {target_dir} does not exist")
        elif not target_dir.is_dir():
            raise InstallationError(f"install target {target_dir} is not a directory")

        return await cog.copy_to(target_dir=target_dir)

    async def install_libraries(
        self, downloader, libraries: Collection[FolderInstallable] = ()
    ) -> Tuple[FolderInstallable, ...]:
        target_dir = downloader.SHAREDLIB_PATH
        failed = []

        libraries = set(libraries)

        if libraries:
            if not all(lib.repo is self for lib in libraries):
                raise ValueError(f"not all libraries belong to the {self.name} repo")
            elif not libraries.issubset(self.available_libraries):
                raise MissingModule("not all libraries are available in the {self.name} repo")
        else:
            libraries = self.available_libraries

        for lib in libraries:
            await lib.copy_to(target_dir=target_dir)

        return failed

    def populate(self) -> None:
        self.folder_path.mkdir(parents=True, exist_ok=True)
        self._read_info_file()
        return self._update_available_modules()

    @classmethod
    async def from_folder(cls, manager: "RepoManager", folder: Path):
        repo = cls(name=folder.stem, manager=manager, folder_path=folder)
        repo.populate()
        return repo
