from pathlib import Path
import pytest

from redbot.cogs.downloader.utils import CommandTemplate, is_path_git_repo


def test_command_template():
    test_template = CommandTemplate("command arg1 {0} {1} {param1}")
    assert test_template.format("foo", "bar", param1="baz") == "command arg1 foo bar baz".split()

    test_template = CommandTemplate("foo", extras_kw="extras")
    test_template.format(extras=("baz", "asdf")) == "foo baz asdf".split()

    test_template = CommandTemplate("foo {0} {1} bar", num_args=2)
    assert test_template.format("a", "b", "c", "d") == "foo a b bar c d".split()

    test_template = CommandTemplate("foo {skipme1} bar skipme2")
    assert test_template.format(_skip=("{skipme1}", "skipme2")) == "foo bar".split()


def test_command_template_errors():

    # test missing, invalid and empty command spec

    with pytest.raises(TypeError):
        CommandTemplate()

    for value in (None, 1, [1]):
        with pytest.raises(TypeError):
            CommandTemplate(value)

    for value in ("", [], [""]):
        with pytest.raises(TypeError):
            CommandTemplate(ValueError)

    # Test invalid optional parameters

    with pytest.raises(TypeError):
        CommandTemplate(["foo"], num_args="asdf")  # num_args must be int

    with pytest.raises(ValueError):
        CommandTemplate(["foo", "{}"])  # numberless positional field

    with pytest.raises(KeyError):
        CommandTemplate(["foo", "{asdf}"]).format()


def test_is_git_dir(tmpdir):
    testdir = Path(tmpdir) / "testgitdir"
    (testdir / ".git").mkdir(parents=True, exist_ok=False)
    assert is_path_git_repo(testdir)


def test_is_not_git_dir(tmpdir):
    testdir = Path(tmpdir) / "testnotgitdir"
    assert not is_path_git_repo(testdir)
    testdir.mkdir(parents=True, exist_ok=False)
    assert not is_path_git_repo(testdir)
    (testdir / ".git").touch()
    assert not is_path_git_repo(testdir)
