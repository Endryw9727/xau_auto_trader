from scripts import run_paper_forward_once as script


def test_run_paper_forward_once_pauses_on_stale_data(monkeypatch, capsys):
    calls = {"load_data": 0, "engine": 0}

    monkeypatch.setattr(
        script,
        "run_preflight_checks",
        lambda: [
            {"name": "live_mode_false", "passed": True, "detail": "ok"},
            {
                "name": "data_freshness",
                "passed": False,
                "detail": "STALE: last=2026-05-07, age=10000 min",
                "status": "STALE",
            },
        ],
    )

    def fail_load(_path):
        calls["load_data"] += 1
        raise AssertionError("market data should not be loaded when data is stale")

    def fail_engine(_data):
        calls["engine"] += 1
        raise AssertionError("paper-forward engine should not run when data is stale")

    monkeypatch.setattr(script, "load_csv_data", fail_load)
    monkeypatch.setattr(script, "run_paper_forward_once", fail_engine)

    script.main()
    output = capsys.readouterr().out

    assert "Signal: PAUSE" in output
    assert "Reason: DATA_STALE" in output
    assert "update local XAUUSD data" in output
    assert calls == {"load_data": 0, "engine": 0}


def test_run_paper_forward_once_stops_on_data_error(monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "run_preflight_checks",
        lambda: [
            {
                "name": "data_freshness",
                "passed": False,
                "detail": "ERROR: file missing",
                "status": "ERROR",
            },
        ],
    )

    script.main()
    output = capsys.readouterr().out

    assert "Preflight status: FAIL" in output
    assert "Decision: STOP" in output
