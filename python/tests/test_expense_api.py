from __future__ import annotations

import json

import pytest

from openclaw_apple_bridge.errors import BridgeError
from openclaw_apple_bridge.expense_api import import_attachment, pending, status


def configured(tmp_path):
    inbound = tmp_path / "inbound"
    inbound.mkdir()
    state = tmp_path / "state"
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "stateDir": str(state), "allowedInboundRoots": [str(inbound)]
    }))
    return {"expenseConfig": str(config_file)}, inbound


def test_feishu_attachment_import_is_bounded_and_visible(tmp_path) -> None:
    config, inbound = configured(tmp_path)
    receipt = inbound / "hotel.pdf"
    receipt.write_bytes(b"not a real PDF")
    result = import_attachment(config, {"path": str(receipt), "label": "温州酒店"})
    assert result["status"] == "ingested" and result["needsReview"] == 1
    assert status(config)["messages"] == 1
    assert pending(config)["total"] == 1
    assert import_attachment(config, {"path": str(receipt)})["artifacts"] == 0


def test_feishu_attachment_rejects_outside_and_symlink(tmp_path) -> None:
    config, inbound = configured(tmp_path)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"x")
    with pytest.raises(BridgeError):
        import_attachment(config, {"path": str(outside)})
    link = inbound / "link.pdf"
    link.symlink_to(outside)
    with pytest.raises(BridgeError):
        import_attachment(config, {"path": str(link)})
