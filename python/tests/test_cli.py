from openclaw_apple_bridge.cli import capabilities


def test_capabilities_do_not_claim_notes_ready() -> None:
    result = capabilities()

    assert result["status"] == "scaffold"
    assert "notes.read.research" in result["capabilities"]
