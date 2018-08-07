import discord
import os
from pathlib import Path
import shutil
import sys
from sys import path as syspath
from typing import Collection, FrozenSet, Tuple, Union


from redbot.core import Config
from redbot.core import checks
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core import commands

from redbot.core.bot import Red
from .checks import do_install_agreement
from .converters import InstalledCog
from .errors import CloningError, ExistingRepo, InvalidRepoName
from .installable import Installable, from_json as installable_from_json
from .log import log
from .repo import Repo
from .repo_manager import RepoManager

_ = Translator("Downloader", __file__)


@cog_i18n(_)
class Downloader:
    def __init__(self, bot: Red):
        self.bot = bot

        self.conf = Config.get_conf(self, identifier=998240343, force_registration=True)

        self.conf.register_global(installed=[])

        self.already_agreed = False

        self.LIB_PATH = cog_data_path(self) / "lib"
        self.SHAREDLIB_PATH = self.LIB_PATH / "cog_shared"
        self.SHAREDLIB_INIT = self.SHAREDLIB_PATH / "__init__.py"

        self.LIB_PATH.mkdir(parents=True, exist_ok=True)
        self.SHAREDLIB_PATH.mkdir(parents=True, exist_ok=True)

        if not self.SHAREDLIB_INIT.exists():
            with self.SHAREDLIB_INIT.open(mode="w", encoding="utf-8") as _:
                pass

        if str(self.LIB_PATH) not in syspath:
            syspath.insert(1, str(self.LIB_PATH))

        self._repo_manager = RepoManager(loop=self.bot.loop)

    async def cog_install_path(self):
        """
        Get the current cog install path.

        Returns
        -------
        :class:`pathlib.Path`
            The default cog install path.

        """
        return await self.bot.cog_mgr.install_path()

    async def installed_cogs(self) -> Tuple[Installable, ...]:
        """Get info on installed cogs.

        Returns
        -------
        Tuple[:class:`~.installable.Installable`, ...]
            All installed cogs / shared libs in existing repos.

        """
        installed_json = await self.conf.installed()
        installed = []

        for v in installed_json:
            try:
                installed.append(installable_from_json(v, self._repo_manager))
            except Exception as e:
                log.exception(e)
                continue

        return tuple(installed)

    async def _add_to_installed(self, cog: Installable, version: str = None):
        """
        Mark a cog as installed.

        Parameters
        ----------
        cog : :class:`~.installable.Installable`
            The cog to check off.

        """
        installed = await self.conf.installed()
        cog_json = cog.to_json()

        if cog_json not in installed:
            cog_json["cog_version"] = version
            installed.append(cog_json)
            await self.conf.installed.set(installed)

    async def _remove_from_installed(self, cog: Installable):
        """
        Remove a cog from the saved list of installed cogs.

        Parameters
        ----------
        cog : :class:`~.installable.Installable`
            The cog to remove from the installed list.

        """
        installed = await self.conf.installed()
        cog_json = cog.to_json()

        if cog_json in installed:
            installed.remove(cog_json)
            await self.conf.installed.set(installed)

    async def _reinstall_cogs(self, cogs: Collection[Installable]) -> FrozenSet[Installable]:
        """
        Installs a list of cogs, used when updating.

        Parameters
        ----------
        cogs : Collection[:class:`~.installable.Installable`]
            The cogs to (re)install.

        Returns
        -------
        FrozenSet[:class:`~.installable.Installable`]
            Any cogs that failed to install.
        """
        failed = []
        for cog in cogs:
            if not await cog.repo.install_cog(cog):
                failed.append(cog)

        return frozenset(failed)

    async def _reinstall_libraries(self, cogs: Collection[Installable]) -> FrozenSet[Installable]:
        """
        Reinstalls any shared libraries from the repos of cogs that were updated.

        Parameters
        ----------
        cogs : Collection[:class:`~.installable.Installable`]
            The cogs whose libraries should be (re)installed.

        Returns
        -------
        FrozenSet[:class:`~.installable.Installable`]
            Any libraries that failed to install.
        """
        repos = set(c.repo for c in cogs if c.repo)
        failed = []

        for repo in repos:
            repo_failed = await repo.install_libraries()
            failed.extend(repo_failed)

        return frozenset(failed)

    async def _reinstall_requirements(self, cogs: Collection[Installable]) -> FrozenSet[str]:
        """
        Reinstalls requirements for given cogs that have been updated.

        Parameters
        ----------
        cogs : Collection[:class:`~.installable.Installable`]
            The cogs whose requirements should be (re)installed.

        Returns
        -------
        FrozenSet[`str`]
            The names of the requirements that failed to install.

        """
        requirements = set(r for c in cogs for r in c.requirements)
        failed = []

        for req in requirements:
            if not await self._repo_manager.pip_install(downloader=self, requirements=(req,)):
                failed.append(req)

        return frozenset(failed)

    @staticmethod
    async def _delete_cog(target: Path):
        """
        Removes an (installed) cog's files.

        Parameters
        ----------
        target : :class:`~pathlib.Path`
            The path to be removed

        """
        if not target.exists():
            return

        if target.is_dir():
            shutil.rmtree(str(target))
        elif target.is_file():
            os.remove(str(target))

    @commands.command()
    @checks.is_owner()
    async def pipinstall(self, ctx, *packages: str):
        """
        Installs a group of packages using pip.
        """
        success = await self._repo_manager.pip_install(downloader=self, requirements=packages)

        if success:
            await ctx.send(_("Libraries installed."))
        else:
            await ctx.send(
                _(
                    "Some libraries failed to install. Please check"
                    " your logs for a complete list."
                )
            )

    @commands.group()
    @checks.is_owner()
    async def repo(self, ctx):
        """
        Command group for managing Downloader repos.
        """
        pass

    @repo.command(name="add")
    async def _repo_add(self, ctx, name: str, repo_url: str, branch: str = None):
        """
        Add a new repo to Downloader.

        Name can only contain characters A-z, numbers and underscore
        Branch will default to master if not specified
        """
        if not self.already_agreed:
            if not await do_install_agreement(ctx):
                return

            self.already_agreed = True

        try:
            repo = await self._repo_manager.add_git_repo(name=name, url=repo_url, branch=branch)
        except InvalidRepoName:
            await ctx.send(_("`{}` is not a valid repository name.").format(name))
        except ExistingRepo:
            await ctx.send(_("That repo has already been added under another name."))
        except CloningError:
            await ctx.send(_("Something went wrong during the cloning process."))
            log.exception("Something went wrong during the cloning process.")
        else:
            msg = _("Repo `{}` successfully added.").format(repo.name)
            if repo.install_msg is not None:
                msg = "{}\n---\n{}".format(msg, repo.install_msg.replace("[p]", ctx.prefix))

            await ctx.send(msg)

    @repo.command(name="delete")
    async def _repo_del(self, ctx, repo: Repo):
        """
        Removes a repo from Downloader and its files.
        """
        await self._repo_manager.delete_repo(repo.name)

        await ctx.send(_("The `{}` repo has been successfully deleted.").format(repo.name))

    @repo.command(name="list")
    async def _repo_list(self, ctx):
        """
        Lists all installed repos.
        """
        lines = [_("Installed Repos:") + "\n"]
        repos = self._repo_manager.get_all_repos()
        repos = sorted(repos, key=lambda r: r.name.lower())

        for repo in repos:
            lines.append(
                "+ {}{}".format(repo.name, ": {}".format(repo.short) if repo.short else "")
            )

        if not repos:
            await ctx.send(_("No repos found."))
            return

        for page in pagify("\n".join(lines), ["\n"], shorten_by=16):
            await ctx.send(box(page.lstrip(" "), lang="diff"))

    @repo.command(name="info")
    async def _repo_info(self, ctx, repo: Repo):
        """
        Lists information about a single repo
        """

        msg = _("Information on {}:\n{}").format(repo.name, repo.description or "")
        await ctx.send(box(msg))

    @commands.group()
    @checks.is_owner()
    async def cog(self, ctx):
        """
        Command group for managing installable Cogs.
        """
        pass

    @cog.command(name="install")
    async def _cog_install(self, ctx, repo: Repo, cog_name: str):
        """
        Installs a cog from the given repo.
        """
        cog = discord.utils.get(repo.available_cogs, name=cog_name)  # type: Installable
        if cog is None:
            await ctx.send(
                _("There is no cog by the name of `{}` in the `{}` repo.").format(
                    cog_name, repo.name
                )
            )
            return
        elif cog.min_python_version > sys.version_info:
            await ctx.send(
                _("This cog requires at least python version {}, aborting install.").format(
                    ".".join([str(n) for n in cog.min_python_version])
                )
            )
            return

        if not await self._repo_manager.install_requirements(downloader=self, module=cog):
            await ctx.send(
                _("Failed to install the required libraries for `{}`: `{}`").format(
                    cog.name, ", ".join(cog.requirements)
                )
            )
            return

        async with ctx.typing():
            try:
                version = await repo.get_repo_module_version(cog)
            except NotImplementedError:
                version = None

            await repo.install_cog(downloader=self, cog=cog)
            await self._add_to_installed(cog, version=version)
            await repo.install_libraries(downloader=self)

        msg = _("Cog `{}` successfully installed.").format(cog_name)

        if cog.install_msg is not None:
            msg = "{}\n---\n{}".format(msg, cog.install_msg.replace("[p]", ctx.prefix))

        await ctx.send(msg)

    @cog.command(name="uninstall")
    async def _cog_uninstall(self, ctx, cog: InstalledCog):
        """
        Allows you to uninstall cogs that were previously installed
            through Downloader.
        """
        real_name = cog.name

        poss_installed_path = (await self.cog_install_path()) / real_name

        if poss_installed_path.exists():
            await self._delete_cog(poss_installed_path)
            await self._remove_from_installed(cog)
            await ctx.send(_("`{}` was successfully removed.").format(real_name))
        else:
            await ctx.send(
                _(
                    "That cog was installed but can no longer"
                    " be located. You may need to remove it's"
                    " files manually if it is still usable."
                )
            )

    @cog.command(name="update")
    async def _cog_update(self, ctx, cog: InstalledCog = None):
        """
        Updates all cogs or one of your choosing.
        """
        installed_cogs = set(await self.installed_cogs())
        error_repos = {}
        updates = {}

        async with ctx.typing():
            if cog is None:
                update_results = await self._repo_manager.update_all_repos()
            else:
                try:
                    update_results = {cog.repo: await cog.repo.update()}
                except Exception as e:
                    update_results = {cog.repo: e}

            for repo, result in update_results.items():
                if isinstance(result, Exception):
                    error_repos[repo] = result
                elif result:
                    updates[repo] = result

            updated_cogs = set().union(*(result.updated.cogs for result in updates.values()))
            installed_updated = updated_cogs & installed_cogs

            if cog:
                installed_updated &= {cog}

            if not installed_updated:
                if cog:
                    msg = _("`{}` is already up to date.").format(cog.name)
                else:
                    msg = _("All installed cogs are already up to date.")

                await ctx.send(msg)
                return
            else:
                lines = []

                await self._reinstall_requirements(installed_updated)
                await self._reinstall_cogs(installed_updated)
                await self._reinstall_libraries(installed_updated)

                for repo in sorted(updates, key=lambda r: r.name):
                    update = updates[repo]
                    repo_installed_updated = update and (update.updated.cogs & installed_updated)

                    if repo_installed_updated:
                        lines.append("\n{}:".format(repo.name))
                        lines.extend("+ {}".format(c.name) for c in repo_installed_updated)

                header = _("The following cogs were updated:")
                footer = _("Run `[p]reload COG_NAME` to reload an updated cog.")
                margin = len(header) + len(footer) + 18  # \n```diff\n\ndiff```\n

                pages = pagify("\n".join(lines), ["\n"], shorten_by=margin)
                pages = list(box(p, lang="diff") for p in pages)
                pages[0] = "{}\n{}".format(header, pages[0])
                pages[-1] = "{}\n{}".format(pages[-1], header)

                for page in pages:
                    await ctx.send(page)

    @cog.command(name="list")
    async def _cog_list(self, ctx, repo: Repo):
        """
        Lists all available cogs from a single repo.
        """
        installed = [c for c in await self.installed_cogs() if c.repo is repo]
        installed_set = set(installed)
        cogs = [c for c in repo.available_cogs if not (c.hidden or c in installed_set)]
        lines = []

        if cogs:
            cogs.sort(key=lambda c: c.name)
            lines.append(_("Available Cogs:"))
            lines.extend(
                "+ {}{}".format(c.name, ": {}".format(c.short) if c.short else "") for c in cogs
            )

        if installed:
            if cogs:
                lines.append("")

            installed.sort(key=lambda i: i.name)
            lines.append(_("Installed Cogs:"))
            lines.extend(
                "- {}{}".format(i.name, ": {}".format(i.short) if i.short else "")
                for i in installed
            )

        if not lines:
            await ctx.send(_("There are no cogs in the `{}` repo.").format(repo.name))
            return

        for page in pagify("\n".join(lines), ["\n"], shorten_by=16):
            await ctx.send(box(page.lstrip(" "), lang="diff"))

    @cog.command(name="info")
    async def _cog_info(self, ctx, repo: Repo, cog_name: str):
        """
        Lists information about a single cog.
        """
        cog = discord.utils.get(repo.available_cogs, name=cog_name)
        if cog is None:
            await ctx.send(_("There is no cog `{}` in the repo `{}`").format(cog_name, repo.name))
            return

        msg = _("Information on {}:\n{}\n\nRequirements: {}").format(
            cog.name, cog.description or "", ", ".join(cog.requirements) or "None"
        )
        await ctx.send(box(msg))

    async def is_installed(
        self, cog_name: str
    ) -> Union[Tuple[bool, Installable], Tuple[bool, None]]:
        """Check to see if a cog has been installed through Downloader.

        Parameters
        ----------
        cog_name : str
            The name of the cog to check for.

        Returns
        -------
        `tuple` of (`bool`, :class:`~.installable.Installable`)
            :code:`(True, Installable)` if the cog is installed, else
            :code:`(False, None)`.

        """
        for installable in await self.installed_cogs():
            if installable.name == cog_name:
                return True, installable
        return False, None

    def format_findcog_info(
        self, command_name: str, cog_installable: Union[Installable, object] = None
    ) -> str:
        """Format a cog's info for output to discord.

        Parameters
        ----------
        command_name : str
            Name of the command which belongs to the cog.
        cog_installable : :class:`~.installable.Installable` or `object`
            Can be an :class:`~.installable.Installable` instance or a Cog instance.

        Returns
        -------
        str
            A formatted message for the user.

        """
        if isinstance(cog_installable, Installable):
            made_by = ", ".join(cog_installable.author) or _("Missing from info.json")
            repo = self._repo_manager.get_repo(cog_installable.repo.name)
            repo_url = repo.url
            cog_name = cog_installable.name
        else:
            made_by = "26 & co."
            repo_url = "https://github.com/Cog-Creators/Red-DiscordBot"
            cog_name = cog_installable.__class__.__name__

        msg = _("Command: {}\nMade by: {}\nRepo: {}\nCog name: {}")

        return msg.format(command_name, made_by, repo_url, cog_name)

    def cog_name_from_instance(self, instance: object) -> str:
        """Determines the cog name that Downloader knows from the cog instance.

        Probably.

        Parameters
        ----------
        instance : object
            The cog instance.

        Returns
        -------
        str
            The name of the cog according to Downloader.

        """
        splitted = instance.__module__.split(".")
        return splitted[-2]

    @commands.command()
    async def findcog(self, ctx: commands.Context, command_name: str):
        """
        Figures out which cog a command comes from. Only works with loaded cogs.
        """
        command = ctx.bot.all_commands.get(command_name)

        if command is None:
            await ctx.send(_("That command doesn't seem to exist."))
            return

        # Check if in installed cogs
        cog_name = self.cog_name_from_instance(command.instance)
        installed, cog_installable = await self.is_installed(cog_name)
        if installed:
            msg = self.format_findcog_info(command_name, cog_installable)
        else:
            # Assume it's in a base cog
            msg = self.format_findcog_info(command_name, command.instance)

        await ctx.send(box(msg))
