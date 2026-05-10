from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from conexus.core.llm.telemetry import UsageLogger, install


@pytest.mark.asyncio
async def test_success_writes_row():
    store = MagicMock()
    conn = store.connect.return_value.__enter__.return_value
    logger = UsageLogger(store)
    resp = SimpleNamespace(
        _hidden_params={"response_cost": 0.0042},
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        model="deepseek/deepseek-v4-flash",
    )
    kwargs = {"model": "deepseek/deepseek-v4-flash", "metadata": {"agent_name": "ana"}}
    start = datetime(2026, 5, 8, 12, 0, 0)
    end = datetime(2026, 5, 8, 12, 0, 1)
    await logger.async_log_success_event(kwargs, resp, start, end)
    assert conn.execute.call_count == 1
    args = conn.execute.call_args.args[1]
    assert args[1] == "ana"  # agent_name
    assert args[2] == "deepseek"
    assert args[3] == "deepseek-v4-flash"
    assert args[6] == 0.0042  # cost
    assert args[8] == 1000  # duration_ms


@pytest.mark.asyncio
async def test_failure_writes_error():
    store = MagicMock()
    conn = store.connect.return_value.__enter__.return_value
    logger = UsageLogger(store)
    kwargs = {"model": "x/y", "metadata": {"agent_name": "ana"}, "exception": "boom"}
    start = datetime(2026, 5, 8, 12, 0, 0)
    end = datetime(2026, 5, 8, 12, 0, 1)
    await logger.async_log_failure_event(kwargs, None, start, end)
    args = conn.execute.call_args.args[1]
    assert args[9] == "boom"


@pytest.mark.asyncio
async def test_reads_metadata_from_litellm_params():
    """Router places metadata under kwargs['litellm_params']['metadata']."""
    store = MagicMock()
    conn = store.connect.return_value.__enter__.return_value
    logger = UsageLogger(store)
    resp = SimpleNamespace(_hidden_params={"response_cost": 0.001},
                           usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                           model="x/y")
    kwargs = {"model": "x/y", "litellm_params": {"metadata": {"agent_name": "ana"}}}
    await logger.async_log_success_event(kwargs, resp, datetime(2026,5,8), datetime(2026,5,8))
    args = conn.execute.call_args.args[1]
    assert args[1] == "ana"


@pytest.mark.asyncio
async def test_skips_when_agent_name_missing():
    """Diagnostic litellm probes lack agent_name; must not write a row."""
    store = MagicMock()
    conn = store.connect.return_value.__enter__.return_value
    logger = UsageLogger(store)
    resp = SimpleNamespace(_hidden_params={}, usage=None, model="x/y")
    kwargs = {"model": "x/y"}  # no metadata
    await logger.async_log_success_event(kwargs, resp, datetime(2026,5,8), datetime(2026,5,8))
    conn.execute.assert_not_called()


def test_install_appends_logger_once():
    import litellm
    litellm.callbacks = []
    store = MagicMock()
    install(store)
    install(store)
    assert sum(1 for c in litellm.callbacks if isinstance(c, UsageLogger)) == 1
