__all__ = [
    "DownloaderException",
    "GitException",
    "InvalidRepoName",
    "ExistingRepo",
    "ExistingGitRepo",
    "MissingRepo",
    "MissingGitRepo",
    "MissingModule",
    "CloningError",
    "CurrentHashError",
    "HardResetError",
    "GitUpdateError",
    "GitDiffError",
    "PipError",
    "UpdateError",
]


class DownloaderException(Exception):
    """
    Base class for Downloader exceptions.
    """

    pass


class GitException(DownloaderException):
    """
    Generic class for git exceptions.
    """


class InvalidRepoName(DownloaderException):
    """
    Throw when a repo name is invalid. Check
    the message for a more detailed reason.
    """

    pass


class MissingRepo(DownloaderException):
    """
    Thrown when a repo is expected to exist but does not.
    """

    pass


class ExistingRepo(DownloaderException):
    """
    Thrown when trying to add a repo tha already exists.
    """

    pass


class ExistingGitRepo(ExistingRepo):
    """
    Thrown when trying to clone into a folder where a
    git repo already exists.
    """

    pass


class MissingGitRepo(MissingRepo):
    """
    Thrown when a git repo is expected to exist but
    does not.
    """

    pass


class MissingModule(DownloaderException):
    """
    Thrown when a git repo is expected to exist but
    does not.
    """

    pass


class CloningError(GitException):
    """
    Thrown when git clone returns a non zero exit code.
    """

    pass


class CurrentHashError(GitException):
    """
    Thrown when git returns a non zero exit code attempting
    to determine the current commit hash.
    """

    pass


class HardResetError(GitException):
    """
    Thrown when there is an issue trying to execute a hard reset
    (usually prior to a repo update).
    """

    pass


class GitUpdateError(GitException):
    """
    Thrown when git pull returns a non zero error code.
    """

    pass


class GitDiffError(GitException):
    """
    Thrown when a git diff fails.
    """

    pass


class PipError(DownloaderException):
    """
    Thrown when pip returns a non-zero return code.
    """

    pass


class UpdateError(DownloaderException):
    """
    Thrown when a repo update fails. Wraps the original exception.
    """

    def __init__(self, repo, original):
        self.repo = repo
        self.original = original


class InstallationError(DownloaderException):
    """
    Thrown when a cog or shared library installation fails for any reason.
    """

    pass
