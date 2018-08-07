import json
from pathlib import Path
from typing import AbstractSet

import pytest

from redbot.pytest.downloader import *
from redbot.cogs.downloader.installable import (
    Installable,
    InstallableType,
    from_json as installable_from_json,
)


def test_process_info_file(installable):
    for k, v in INFO_JSON.items():
        iv = getattr(installable, k)

        if isinstance(iv, InstallableType):
            v = InstallableType[v]
        elif isinstance(iv, AbstractSet):
            v = frozenset(v)

        assert iv == v


# noinspection PyProtectedMember
def test_location_is_dir(installable):
    assert installable._location.exists()
    assert installable._location.is_dir()


# noinspection PyProtectedMember
def test_info_file_is_file(installable):
    assert installable._info_file.exists()
    assert installable._info_file.is_file()


def test_name(installable):
    assert installable.name == "test_cog"


def test_repo_name(installable):
    assert installable.repo.name == "test_repo"


def test_serialization(installable):
    data = installable.to_json()

    assert data["cog_name"] == installable.name
    assert data["repo_name"] == installable.repo.name


def test_roundtrip(installable, repo_manager, folder_repo):
    data = installable.to_json()
    restored = installable_from_json(data, repo_manager)
    assert installable == restored


def test_comparisons(folder_repo):
    pass
