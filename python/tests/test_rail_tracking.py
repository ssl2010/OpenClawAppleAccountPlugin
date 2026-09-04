from test_rail12306_worker import FakeProvider
from test_rail_safety_regressions import params

from openclaw_apple_bridge.rail12306 import plan_email
from openclaw_apple_bridge.rail12306_worker import apply_plan


def test_notes_are_human_only_and_tracking_is_stable() -> None:
    first = plan_email(params())["plans"][0]
    second = plan_email({**params(), "messageId": "new-copy"})["plans"][0]
    assert "[OpenClaw:" not in first["event"]["notes"]
    assert "ZZ12345678" not in first["event"]["url"]
    assert first["event"]["url"].startswith("urn:uuid:")
    assert first["event"]["url"] == second["event"]["url"]


def test_legacy_notes_migrate_without_recreating() -> None:
    plan = plan_email(params())["plans"][0]
    old = {"eventId": "old-guid", "url": "", "notes": plan["lookup"]["marker"] + "\n" + plan["event"]["notes"]}
    provider = FakeProvider([old])
    apply_plan(provider, plan, "cal-1", apply=True)
    assert not provider.created
    assert provider.updated[0]["eventId"] == "old-guid"
    assert provider.updated[0]["url"] == plan["event"]["url"]
    assert "[OpenClaw:" not in provider.updated[0]["notes"]


def test_clean_notes_still_match_for_repeat_update() -> None:
    plan = plan_email(params())["plans"][0]
    provider = FakeProvider([{"eventId": "old-guid", **plan["event"]}])
    apply_plan(provider, plan, "cal-1", apply=True)
    assert not provider.created
    assert provider.updated[0]["eventId"] == "old-guid"
