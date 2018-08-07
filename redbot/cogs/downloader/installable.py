import abc
from collections import namedtuple
import distutils.dir_util
from enum import Enum
import json
from pathlib import Path
import shutil
from typing import Any, Dict, TYPE_CHECKING
from packaging.specifiers import SpecifierSet

from .errors import MissingRepo
from .log import log
from .json_mixins import RepoJSONMixin

if TYPE_CHECKING:
    from .repo import Repo
    from .repo_manager import RepoManager


class InstallableType(Enum):
    UNKNOWN = 0
    COG = 1
    SHARED_LIBRARY = 2


class InstallableRequirementRepoType(Enum):
    UNKNOWN = 0
    GIT = 1
    PYPI = 2


InstallableRequirementRepo = namedtuple("InstallableRequirementRepo", "")
InstallableRequirementRepo.__doc__ = """
A named tuple describing a reference to a 
"""


InstallableRequirement = namedtuple("InstallableRequirement", "name specifier repo")
InstallableRequirement.__doc__ = """
A named tuple describing an installable's requirement (for Red, not pip).

Attributes
----------
name : `str`
    The name of the required installable.
specifier : Optional[:class:`~packaging.specifiers.SpecifierSet`]
    A specifier for the version of the required installable.
    If this attribute is :code:`None`, then any version will work.
repo : 
    A reference to the repository containing the required installable.

"""


class Installable(abc.ABC):
    """
    Base class for anything the Downloader cog can install.

     - Modules
     - Repo Libraries
     - Other stuff?

    .. _specifier set: https://www.python.org/dev/peps/pep-0440/#version-specifiers

    Attributes
    ----------
    repo : :class:`~.repo.Repo`
        The repository which this package belongs to.
    name : `str`
        Name of the installable package.
    author : Tuple[`str`, ...]
        Name(s) of the author(s).
    bot_version : Optional[:class:`~packaging.specifiers.SpecifierSet`]
        A `specifier set`_ for the Red version required for this installable.
        Defaults to :code:`>=3.0.0a0`.
    python_version : Optional[:class:`~packaging.specifiers.SpecifierSet`]
        A `specifier set`_ for the Python version required for this installable.
        Defaults to :code:`>=3.6.0`.
    hidden : `bool`
        Whether or not this cog will be hidden from the user in Downloader.
    required_cogs : FrozenSet[:class:`~.installable.RequiredInstallable`]
        The cogs which are required for this installation. Format:

        .. code-block:: python

            {
                "cog_name" : {
                    "version" : "specifier_set",  # see PEP 440
                    "repo" : {
                        "url"  : "https://github.com/repo_owner/repo_name.git@branch",
                        "type" : "git",  # optional, defaults to "git", but can be "pypi"
                        "name" : "repo_name"  # optional, used for missing repo display
                    }
                }, ...
            }

        :code:`version` and :code:`repo` are optional.
        If :code:`repo` is not specified, it is assumed to be the same repo.
    requirements : Tuple[`str`, ...]
        Pip requirement expresions for this installable.
    tags : `frozenset` of `str`
        List of tags to assist in searching. Converted to lowercase upon load.
    type : :class:`InstallationType`
        The type of this installable, as specified by the :class:`InstallationType` enum.

    """

    TYPE_NAME = "ABSTRACT"

    def __init__(self, repo: "Repo", name: str, **kwargs):
        """Base installable initializer.

        Parameters
        ----------
        repo : :class:`~.repo.Repo`
            The repository which this package belongs to.
        name : `str`
            Name of the installable package.

        """
        self.repo = repo
        self.name = name

        self.author = kwargs.get("author", ())
        self.bot_version = kwargs.get("bot_version", SpecifierSet(">=3.0a0"))
        self.python_version = kwargs.get("python_version", SpecifierSet(">=3.6"))
        self.hidden = kwargs.get("hidden", False)
        self.disabled = kwargs.get("disabled", False)
        self.required_cogs = kwargs.get("required_cogs", {})
        self.requirements = kwargs.get("requirements", ())
        self.tags = frozenset(s.lower() for s in kwargs.get("tags", ()))
        self.type = kwargs.get("type", InstallableType.UNKNOWN)

    def __eq__(self, other):
        # noinspection PyProtectedMember
        return isinstance(other, type(self)) and self._key == other._key

    def __hash__(self):
        return hash(self._key)

    def to_json(self):
        return {"cog_name": self.name, "repo_name": self.repo.name, "inst_type": self.TYPE_NAME}

    @property
    @abc.abstractmethod
    def _key(self):
        pass

    @classmethod
    @abc.abstractmethod
    def from_json(cls, data: dict, repo_mgr: "RepoManager") -> "Installable":
        pass


class FolderInstallable(Installable, RepoJSONMixin):
    """
    An installable that comes from a local folder with info.json metadata.

    The attributes of this class mostly come from the installation's info.json.
    """

    TYPE_NAME = "FOLDER"

    def __init__(self, repo: "FolderRepo", location: Path, **kwargs):
        """
        Folder installable initializer.

        Parameters
        ----------
        repo : :class:`~.repos.folder.FolderRepo`
            The repository which this package belongs to.
        location : :class:`~pathlib.Path`
            Location (file or folder) of the installable.
            The last element (stem) of the path is used as the installable name.

        """
        Installable.__init__(self, repo, location.stem, **kwargs)
        RepoJSONMixin.__init__(self, location)

        self._location = location

        if self._info_file.exists():
            self._process_info_file(self._info_file)

        if self._info == {}:
            self.type = InstallableType.COG

    @property
    def _key(self):
        return self.repo, self._location

    async def copy_to(self, target_dir: Path) -> bool:
        """
        Copies this cog/shared_lib to the given directory. This will overwrite any files in the
        target directory.

        Parameters
        ----------
        target_dir : :class:`~pathlib.Path`
            The path or directory to install to.

        Returns
        -------
        `bool`
            Whether the copy was successful.

        """
        if self._location.is_file():
            copy_func = shutil.copy2
        else:
            copy_func = distutils.dir_util.copy_tree

        try:
            copy_func(src=str(self._location), dst=str(target_dir / self._location.stem))
        except Exception:
            log.exception("Error occurred when copying path: {}".format(self._location))
            return False
        return True

    def _read_info_file(self):
        super()._read_info_file()

        if self._info_file.exists():
            self._process_info_file()

    def _process_info_file(self, info_file_path: Path = None) -> Dict[str, Any]:
        """
        Processes an information file. Loads dependencies among other
        information into this object.

        Parameters
        ----------
        info_file_path : Optional[:class:`~pathlib.Path`]
            Optional path to information file, defaults to `self._info_file`.

        Returns
        -------
        Dict[`str`, Any]
            The raw information dictionary read from the info file.
        """
        info_file_path = info_file_path or self._info_file
        if info_file_path is None or not info_file_path.is_file():
            raise ValueError("No valid information file path was found.")

        info = {}
        with info_file_path.open(encoding="utf-8") as f:
            try:
                info = json.load(f)
            except json.JSONDecodeError:
                info = {}
                log.exception("Invalid JSON information file at path: {}".format(info_file_path))
            else:
                self._info = info

        try:
            self.author = tuple(info.get("author", []))
        except ValueError:
            self.author = ()

        try:
            self.bot_version = tuple(info.get("bot_version", [3, 0, 0]))
        except ValueError:
            pass

        try:
            self.python_version = tuple(info.get("python_version", [3, 6, 0]))
        except ValueError:
            self.python_version = self.python_version

        try:
            self.hidden = bool(info.get("hidden", False))
        except ValueError:
            self.hidden = False

        try:
            self.disabled = bool(info.get("disabled", False))
        except ValueError:
            self.disabled = False

        self.required_cogs = info.get("required_cogs", {})
        self.requirements = info.get("requirements", ())

        try:
            self.tags = frozenset(s.lower() for s in info.get("tags", ()))
        except ValueError:
            self.tags = frozenset()

        try:
            installable_type = self.type = InstallableType[info.get("type", "COG")]

            if installable_type is InstallableType.SHARED_LIBRARY:
                self.hidden = True
        except KeyError:
            self.type = InstallableType.UNKNOWN

        return info

    @classmethod
    def from_json(cls, data: dict, repo_mgr: "RepoManager"):
        repo_name = data["repo_name"]
        cog_name = data["cog_name"]

        repo = repo_mgr.get_repo(repo_name)
        if repo is None:
            raise MissingRepo("There is no repo with the name {}".format(repo_name))

        location = repo.folder_path / cog_name

        return cls(repo=repo, location=location)


INSTALLABLE_TYPES = {FolderInstallable.TYPE_NAME: FolderInstallable}


def from_json(data: dict, repo_mgr: "RepoManager") -> Installable:
    type_name = data["inst_type"]
    cls = INSTALLABLE_TYPES[type_name]
    return cls.from_json(data, repo_mgr)
