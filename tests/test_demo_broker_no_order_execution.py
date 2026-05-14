from pathlib import Path

from scripts import check_demo_broker_readonly
from src.broker.demo_broker_guardrails import FORBIDDEN_ORDER_METHODS, assert_no_real_order_method_available
from src.broker.demo_broker_readonly import DemoBrokerReadOnlyClient


def test_demo_broker_client_exposes_no_order_execution_methods():
    client = DemoBrokerReadOnlyClient.from_config_file()

    for method_name in FORBIDDEN_ORDER_METHODS:
        assert not callable(getattr(client, method_name, None))
    assert_no_real_order_method_available(client)


def test_demo_broker_readonly_source_does_not_import_live_broker():
    source = Path("src/broker/demo_broker_readonly.py").read_text(encoding="utf-8")

    assert "live_broker" not in source
    assert ".env" not in source
    assert "api_key" not in source.lower()


def test_check_demo_broker_readonly_script_runs_in_mock_mode(capsys):
    check_demo_broker_readonly.main()
    output = capsys.readouterr().out

    assert "Demo Broker Read-Only Check" in output
    assert "allow_live: False" in output
    assert "execution_enabled: False" in output
    assert "MT5_NOT_CONNECTED_MOCK_ONLY" in output
