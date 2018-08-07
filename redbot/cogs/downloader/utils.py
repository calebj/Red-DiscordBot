import sys
from pathlib import Path
import re
from typing import Any, Collection, List, MutableMapping, Optional, Iterable, Union


def is_venv():
    """
    Returns `True` if the interpreter is running inside a venv or virtualenv, otherwise `False`.
    """
    return hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )


def is_path_git_repo(folder_path: Path) -> bool:
    """
    Returns `True` if a path named ``.git`` exists in the folder specified, otherwise `False`.
    """
    git_path = folder_path / ".git"
    return git_path.is_dir()


class CommandTemplate:
    """
    A utility class to easily add and substitute command arguments from a template.
    """

    __slots__ = ["_components", "_num_args", "_extras_kw", "_defaults"]

    def __init__(
        self,
        command: Union[str, Collection[str]],
        num_args: Optional[int] = None,
        *,
        extras_kw: Optional[str] = None,
        defaults: Optional[MutableMapping[str, Any]] = None
    ):
        """
        CommandTemplate constructor.

        Parameters
        ----------
        command : Union[`str`, Iterable[`str`]]
            The command to build the template on. If a string is passed, it is :meth:`str.split()`
            on whitespace.
        num_args : Optional[`int`]
            The maximum number of arguments to pass to format. Additional positional arguments to
            :meth:`format()` will be appended to the command template and formatted as if they
            were a part of the original. Defaults to pass all arguments to format if not given.
        extras_kw : Optional[`str`]
            The name of a keyword argument whose value will, if passed to :meth:format, will be
            appended to the returned argument list. If a string is passed, it is :meth:`str`split`
            before being appended. Extras are formatted as if they were part of the template.
        defaults : Optional[MutableMapping[`str`, Any]]
            A mapping of field name to substitution value to use if not passed to :meth:format.

        Raises
        ------
        TypeError
            When any of the provided arguments are invalid.
        ValueError
            If the input command template contains unnumbered positional fields (:code:`{}`).
        """
        if type(command) is str:
            components = self._components = tuple(command.split())
        elif isinstance(command, Iterable):
            components = self._components = tuple(command)

            if not all(isinstance(c, str) for c in components):
                raise TypeError("command must be a string or iterable of string")
        else:
            raise TypeError("command must be a string or iterable of string")

        # Matches {}, foo{}} or {{}foo, but not {{}}
        unnumbered_positional = re.compile(r"(?!(?<=\{)\{\}\})\{\}")

        if not (components and components[0]):
            raise ValueError("command cannot be empty")
        elif any(unnumbered_positional.search(c) for c in components):
            raise ValueError("all positional substitutions must be numbered")
        elif num_args is not None and not isinstance(num_args, int):
            raise TypeError("num_args must be an int or None")

        self._num_args = num_args
        self._extras_kw = extras_kw
        self._defaults = defaults.copy() if defaults else {}

    def format(self, *args, _skip=(), **kwargs) -> List[str]:
        """
        Substitute the provided positional or keyword arguments into the original template.

        Parameters
        ----------
        *args : str
            The positional (numbered) fields to substitute into the original command.
        _skip : Union[`str`, Container[`str`]]
            The command pre-substitution elements(s) to leave out of the returned list.
        **kwargs : str
            The named fields to substitute into the original command.

        Returns
        -------
        List[`str`]
            The formatted command + argument list, to pass to :class:`subprocess.Popen` and family.
        """
        params = list(self._components)

        if self._num_args is not None:
            params.extend(args[self._num_args :])
            args = args[: self._num_args]

        if self._extras_kw in kwargs:
            extra = kwargs.pop(self._extras_kw, None)

            if isinstance(extra, str):
                extra = extra.split()

            if isinstance(extra, Collection):
                params.extend(extra)

        format_kwargs = self._defaults.copy()
        format_kwargs.update(kwargs)

        return [x.format(*args, **format_kwargs) for x in params if x not in _skip]

    def __call__(self, *args, **kwargs):
        """
        An alias for :meth:format.
        """
        return self.format(*args, **kwargs)
