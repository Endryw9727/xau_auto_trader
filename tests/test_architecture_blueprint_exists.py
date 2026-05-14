from pathlib import Path


def test_system_architecture_blueprint_exists():
    path = Path("docs/system_architecture_blueprint.md")

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Market Data Layer" in text
    assert "AI Reasoning Layer" in text
    assert "Future Execution Layer" in text
    assert "allow_live=false" in text
    assert "No real orders" in text
