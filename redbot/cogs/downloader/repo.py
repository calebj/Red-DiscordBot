import abc
import asyncio
from typing import Collection, Optional, Tuple

from redbot.core import commands
from .errors import UpdateError
from .installable import Installable, InstallableType
from .update_tracker import UpdateTracker, UpdateResult


class Repo(abc.ABC):
    def __init__(
        self, manager: "RepoManager", name: str, available_modules: Tuple[Installable, ...] = ()
    ):
        self.name = name
        self.available_modules = available_modules
        self._manager = manager
        # noinspection PyProtectedMember
        self._repo_lock = asyncio.Lock(loop=manager._loop)

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> "Repo":
        downloader_cog = ctx.bot.get_cog("Downloader")

        if downloader_cog is None:
            raise commands.CommandError("No Downloader cog found.")

        repo_manager = downloader_cog._repo_manager
        poss_repo = repo_manager.get_repo(argument)

        if poss_repo is None:
            raise commands.BadArgument("Repo by the name {} does not exist.".format(argument))

        return poss_repo

    async def _run(self, *args, **kwargs):
        async with self._repo_lock:
            # noinspection PyProtectedMember
            return await self._manager._run(*args, **kwargs)

    async def update(self, wrap_exception=False) -> Optional[UpdateResult]:
        """
        Update the repo.

        Returns
        -------
        Optional[:class:`~.update_tracker.UpdateResult`]
            A :class:`~.update_tracker.UpdateResult` object if the repo was updated,
            otherwise `None`

        Raises
        -------
        :class:`~.errors.UpdateError`
            When the update failed somehow.
        """
        update_tracker = UpdateTracker(repo=self)
        await update_tracker.populate()

        try:
            await self._update()
        except Exception as e:
            if wrap_exception:
                raise UpdateError(repo=self, original=e) from e
            raise

        return await update_tracker.compare()

    @abc.abstractmethod
    async def get_repo_version(self) -> Optional[str]:
        """
        Retreives the current repo version string.

        Depending on the type of repo, this can be a semver string, SHA1 hash, etc.

        Returns
        -------
        Optional[`str`]
            The current overall version of the repo's contents, if applicable.

        Raises
        ------
        :class:`NotImplementedError`
            When the repo type does not have an overall "version".

        """
        pass

    @abc.abstractmethod
    async def get_repo_module_version(self, module: Installable) -> Optional[str]:
        """
        Retreives the version string of a module in the repo, if applicable.

        Depending on the type of repo, this can be a semver string, SHA1 hash, etc.

        Returns
        -------
        Optional[`str`]
            The current overall version of the :code:`module`

        Raises
        ------
        :class:`NotImplementedError`
            When the repo type does not support module versioning.

        """
        pass

    @abc.abstractmethod
    def _update_available_modules(self) -> Tuple[Installable, ...]:
        """
        Updates the available modules attribute for this repo.

        Returns
        -------
        Tuple[:class:`~.installable.Installable`, ...]
            The updated list of available modules.

        """
        pass

    @abc.abstractmethod
    async def delete(self) -> None:
        """
        Deletes the repo's files.
        """
        pass

    @abc.abstractmethod
    def populate(self) -> None:
        """
        (Re)populates the repo's data from disk.
        """
        pass

    @abc.abstractmethod
    async def _update(self) -> None:
        """
        Abstract method which performs the update.
        """
        pass

    @abc.abstractmethod
    async def install_cog(self, downloader: "Downloader", cog: Installable) -> bool:
        """
        Install a cog from the repo.

        Parameters
        ----------
        downloader : :class:`~.downloader.Downloader`
            The Downloader cog which is calling the installation
        cog : :class:`~.installable.Installable`
            The cog to install.

        Raises
        ------
        :class:`~.errors.MissingModule`
            If the provided cog is not available in this repo.
        :class:`~.errors.InstallationError`
            When something went amiss while installing the cog.

        Returns
        -------
        `bool`
            Whether the installation succeeded.

        """
        pass

    @abc.abstractmethod
    async def install_libraries(
        self, downloader: "Downloader", libraries: Collection[Installable] = ()
    ) -> bool:
        """
        Install shared libraries.

        If :code:`libraries` is not specified, all shared libraries in the repo
        will be installed.

        Parameters
        ----------
        downloader : :class:`~.downloader.Downloader`
            The Downloader cog which is calling the installation
        libraries : Collection[:class:`~.installable.Installable`]
            The subset of available libraries to install.

        Raises
        ------
        :class:`~.errors.MissingModule`
            If any of the provided libraries are not available in this repo.

        Returns
        -------
        Tuple[:class:`~.installable.Installable`, ...]
            Any libraries that failed to install.

        """
        pass

    @property
    def available_cogs(self) -> Tuple[Installable, ...]:
        """
        Tuple[:class:`~.installable.Installable`, ...] : All available cogs in this Repo.

        This excludes hidden or shared packages.
        """
        return tuple(
            m for m in self.available_modules if m.type == InstallableType.COG and not m.disabled
        )

    @property
    def available_libraries(self) -> Tuple[Installable, ...]:
        """
        Tuple[:class:`~.installable.Installable`, ...] : All available shared libraries in this Repo.
        """
        return tuple(m for m in self.available_modules if m.type == InstallableType.SHARED_LIBRARY)
