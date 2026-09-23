"""Unit tests for aerpawlib v2 ExternalProcess file redirection."""

import pytest

from aerpawlib.v2.external import ExternalProcess


@pytest.mark.asyncio
async def test_stdin_and_stdout_files_are_used(tmp_path):
    src = tmp_path / "in.txt"
    dst = tmp_path / "out.txt"
    src.write_text("alpha\nbeta\n")

    ep = ExternalProcess("cat", stdin=str(src), stdout=str(dst))
    await ep.start()
    await ep.wait_until_terminated()

    assert dst.read_text() == "alpha\nbeta\n"
    assert await ep.read_line() is None


@pytest.mark.asyncio
async def test_stdout_file_is_truncated(tmp_path):
    dst = tmp_path / "out.txt"
    dst.write_text("stale contents that are longer\n")

    ep = ExternalProcess("echo", params=["fresh"], stdout=str(dst))
    await ep.start()
    await ep.wait_until_terminated()

    assert dst.read_text() == "fresh\n"


@pytest.mark.asyncio
async def test_pipes_used_without_files():
    ep = ExternalProcess("cat")
    await ep.start()
    await ep.send_input("hello\n")
    ep.process.stdin.close()
    assert await ep.read_line() == "hello"
    await ep.wait_until_terminated()


@pytest.mark.asyncio
async def test_missing_stdin_file_raises(tmp_path):
    ep = ExternalProcess("cat", stdin=str(tmp_path / "nope.txt"))
    with pytest.raises(FileNotFoundError):
        await ep.start()
    assert ep.process is None
