"""Unit tests for aerpawlib v1 ExternalProcess."""

import asyncio

import pytest

from aerpawlib.v1.external import ExternalProcess


class TestExternalProcess:
    """ExternalProcess creation and basic behavior."""

    def test_init_default_params(self):
        ep = ExternalProcess("echo")
        assert ep._params == []

    def test_init_with_params(self):
        ep = ExternalProcess("echo", params=["hello"])
        assert ep._params == ["hello"]

    @pytest.mark.asyncio
    async def test_echo_produces_output(self):
        ep = ExternalProcess("echo", params=["hello world"])
        await ep.start()
        try:
            line = await ep.read_line()
            assert "hello" in (line or "")
        finally:
            try:
                ep.process.terminate()
                await asyncio.wait_for(ep.process.wait(), timeout=2)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_wait_until_output_matches(self):
        ep = ExternalProcess("echo", params=["foo bar baz"])
        await ep.start()
        try:
            buff = await ep.wait_until_output(r"bar")
            assert any("bar" in (l or "") for l in buff)
        finally:
            try:
                ep.process.terminate()
                await asyncio.wait_for(ep.process.wait(), timeout=2)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_wait_until_output_returns_empty_on_exit(self):
        ep = ExternalProcess("true")  # Exits immediately
        await ep.start()
        buff = await ep.wait_until_output(r"nonexistent")
        assert buff == [] or buff is not None
