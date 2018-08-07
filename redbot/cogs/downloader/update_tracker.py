from collections import namedtuple
from typing import AbstractSet, MutableMapping, Optional

from .installable import Installable, InstallableType


UpdateResult = namedtuple("UpdateResult", "repo old_version new_version new updated removed")
UpdateResult.__doc__ = """
A named tuple describing updates to a repo.

Attributes
----------
repo : :class:`~.repo.Repo`
    The repository the UpdateResult is for.
old_version : Optional[`str`]
    The version of the repo before the update was performed, if applicable.
old_version : Optional[`str`]
    The version of the repo after the update was performed, if applicable.
new : :class:`~ModuleLists`
    Any modules that did not exist before the update.
updated : :class:`~ModuleLists`
    Any modules that were updated. If the repo type doesn't support this comparison, this contains all modules.
removed : :class:`~ModuleLists`
    Any modules that no longer exist after the update.
    The objects from before the updates are used, and do not reflect the current state of the repo or its files.
"""

ModuleLists = namedtuple("ModuleLists", "cogs shared_libraries others")
ModuleLists.__doc__ = """
A named tuple constructed by categorizing a repo's modules.

Attributes
----------
cogs : `frozenset` of :class:`~.installable.Installable`
    Contains all cog-type modules.
shared_libraries : `frozenset` of :class:`~.installable.Installable`
    Contains all shared library-type modules.
others : `frozenset` of :class:`~.installable.Installable`
    Contains modules which don't fit into any other category.
"""


def _build_module_lists(modules: AbstractSet[Installable]) -> ModuleLists:
    cogs = frozenset(m for m in modules if m.type is InstallableType.COG)
    libs = frozenset(m for m in modules if m.type is InstallableType.SHARED_LIBRARY)
    others = frozenset(modules - cogs - libs)
    return ModuleLists(cogs, libs, others)


class UpdateTracker:
    """
    A factory class for capturing repo state and generating :class:`~UpdateResult`s.
    """

    def __init__(self, repo: "Repo"):
        self.repo = repo
        self.snapshot_version = None
        self.snapshot_modules = {m.name: m for m in repo.available_modules}
        self.snapshot_module_names = set(self.snapshot_modules)
        self.snapshot_module_versions = {}

    async def _get_module_versions(self) -> MutableMapping[str, str]:
        ret = {}

        try:
            for module in self.repo.available_modules:
                ret[module.name] = await self.repo.get_repo_module_version(module)
        except NotImplementedError:
            pass

        return ret

    async def populate(self) -> None:
        """
        Calls the appropriate functions to populate repo and module version information.

        Async because the interface for fetching this information is as well.
        """
        try:
            self.snapshot_version = await self.repo.get_repo_version()
        except NotImplementedError:
            pass

        module_versions = await self._get_module_versions()
        self.snapshot_module_versions.update(module_versions)

    async def compare(self) -> Optional[UpdateResult]:
        """
        Compares the repo's current state to when the tracker was constructed and :meth:`populate`d.

        Returns
        -------
        Optional[:class:`~UpdateResult`]
            A representation of any updates made to the repo since the tracker was constructed.
        """
        compare_version = await self.repo.get_repo_version()
        compare_modules = {m.name: m for m in self.repo.available_modules}
        compare_module_names = set(compare_modules)
        compare_module_versions = await self._get_module_versions()

        new = compare_module_names - self.snapshot_module_names
        inter = compare_module_names & self.snapshot_module_names
        removed = self.snapshot_module_names - compare_module_names

        if not compare_module_versions:
            updated = inter  # assume everything is updated
        else:
            updated = set(
                k for k in inter if compare_module_versions[k] != self.snapshot_module_versions[k]
            )

        if not (compare_version != self.snapshot_version or new or updated or removed):
            return None

        kwargs = dict(
            new=set(compare_modules[k] for k in new),
            updated=set(compare_modules[k] for k in updated),
            removed=set(self.snapshot_modules[k] for k in removed),
        )

        for k, v in kwargs.items():
            kwargs[k] = _build_module_lists(v)

        return UpdateResult(
            repo=self.repo,
            old_version=self.snapshot_version,
            new_version=compare_version,
            **kwargs
        )
