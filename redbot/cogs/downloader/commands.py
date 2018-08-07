from types import SimpleNamespace

from .utils import CommandTemplate

COMMANDS = SimpleNamespace(
    GIT_CHECKOUT_LOCAL=CommandTemplate("git -C {path} checkout {branch} --", extras_kw="paths"),
    GIT_CHECKOUT_REMOTE=CommandTemplate(
        "git -C {path} checkout {remote}/{branch} --",
        extras_kw="paths",
        defaults={"remote": "origin"},
    ),
    GIT_CLONE=CommandTemplate("git clone -b {branch} {url} {folder}"),
    GIT_CLONE_NO_BRANCH=CommandTemplate("git clone {url} {folder}"),
    GIT_CURRENT_BRANCH=CommandTemplate("git -C {path} rev-parse --abbrev-ref HEAD"),
    # GIT_LATEST_COMMIT=CommandTemplate("git -C {path} rev-parse {branch}"),
    GIT_LATEST_COMMIT=CommandTemplate(
        "git -C {path} rev-list -1 {branch} --", extras_kw="relative_file_path"
    ),
    GIT_HARD_RESET=CommandTemplate(
        "git -C {path} reset --hard {remote}/{branch} -q", defaults={"remote": "origin"}
    ),
    GIT_PULL=CommandTemplate("git -C {path} pull -q --ff-only"),
    GIT_DIFF_FILE_STATUS=CommandTemplate(
        "git -C {path} diff --no-commit-id --name-status {old_ref}..{new_ref}"
    ),
    GIT_LOG=CommandTemplate(
        "git -C {path} log --relative-date --reverse {old_ref}.. {relative_file_path}"
    ),
    GIT_DISCOVER_REMOTE_URL=CommandTemplate(
        "git -C {path} config --get remote.{remote}.url", defaults={"remote": "origin"}
    ),
    PIP_INSTALL=CommandTemplate("{python} -m pip install -U -t {target_dir}", extras_kw="reqs"),
    PIP_INSTALL_NO_TARGET=CommandTemplate(
        "{python} -m pip --disable-pip-version-check install -U", extras_kw="reqs"
    ),
    PIP_SHOW=CommandTemplate(
        "{python} -m pip --disable-pip-version-check show", extras_kw="packages"
    ),
)
