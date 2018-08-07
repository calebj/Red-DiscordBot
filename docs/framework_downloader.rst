.. downloader framework reference

Downloader Framework
====================

Info.json
*********

The optional info.json file may exist inside every package folder in the repo, 
as well as in the root of the repo. The following sections describe the valid 
keys within an info file (and maybe how the Downloader cog uses them).

Keys common to both repo and cog info.json (case sensitive)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- ``author`` (list of strings) - list of names of authors of the cog or repo.

- ``description`` (string) - A long description of the cog or repo. For cogs, this 
  is displayed when a user executes ``!cog info``.

- ``install_msg`` (string) - The message that gets displayed when a cog 
  is installed or a repo is added
  
  .. tip:: You can use the ``[p]`` key in your string to use the prefix
      used for installing.

- ``short`` (string) - A short description of the cog or repo. For cogs, this info 
  is displayed when a user executes ``!cog list``

Keys specific to the cog info.json (case sensitive)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- ``bot_version`` - A version string in the format ``"MAJOR.MINOR.PATCH"``

- ``hidden`` (bool) - Determines if a cog is visible in the cog list for a repo.

- ``disabled`` (bool) - Determines if a cog is available for install.

- ``required_cogs`` (map of cogname to repo URL) - A map of required cogs that this cog depends on.
  Downloader will not deal with this functionality but it may be useful for other cogs.

- ``requirements`` (list of strings) - list of required libraries that are
  passed to pip on cog install. ``SHARED_LIBRARIES`` do NOT go in this
  list.

- ``tags`` (list of strings) - A list of strings that are related to the
  functionality of the cog. Used to aid in searching.

- ``type`` (string) - Optional, defaults to ``COG``. Must be either ``COG`` or
  ``SHARED_LIBRARY``. If ``SHARED_LIBRARY`` then ``hidden`` will be ``True``.

API Reference
*************

..
    automodule:: redbot.cogs.downloader.json_mixins

..
    autoclass:: RepoJSONMixin
    :members:

Installable
^^^^^^^^^^^

.. automodule:: redbot.cogs.downloader.installable

.. autoclass:: Installable
    :members:

.. autoclass:: FolderInstallable
    :show-inheritance:
    :members:

Repo
^^^^

.. automodule:: redbot.cogs.downloader.repo

.. autoclass:: Repo
    :members:

.. autoclass:: redbot.cogs.downloader.repos.folder.FolderRepo
    :show-inheritance:
    :members:

.. autoclass:: redbot.cogs.downloader.repos.git.GitRepo
    :show-inheritance:
    :members:

Repo Manager
^^^^^^^^^^^^

.. automodule:: redbot.cogs.downloader.repo_manager

.. autoclass:: RepoManager
    :members:

Update Result
^^^^^^^^^^^^^

.. automodule:: redbot.cogs.downloader.update_tracker

.. autoclass:: UpdateResult

.. autoclass:: ModuleLists

Utilities
^^^^^^^^^

.. automodule:: redbot.cogs.downloader.utils
    :members:

Exceptions
^^^^^^^^^^

.. automodule:: redbot.cogs.downloader.errors
    :members:
