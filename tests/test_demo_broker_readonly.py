from src.broker.demo_broker_readonly import DemoBrokerReadOnlyClient, MT5_MOCK_STATUS


def test_demo_broker_mock_mode_returns_readonly_snapshots():
    client = DemoBrokerReadOnlyClient.from_config_file(mode="mock")

    account = client.account_snapshot()
    symbol = client.symbol_snapshot()
    positions = client.open_positions()
    history = client.order_history()

    assert account.status == MT5_MOCK_STATUS
    assert account.connected is False
    assert symbol.status == MT5_MOCK_STATUS
    assert symbol.symbol == "XAUUSD"
    assert positions == []
    assert history == []


def test_demo_broker_mt5_mode_is_safe_placeholder():
    client = DemoBrokerReadOnlyClient.from_config_file(mode="mt5")

    account = client.account_snapshot()

    assert client.mode == "mt5"
    assert account.status == MT5_MOCK_STATUS
    assert account.connected is False
