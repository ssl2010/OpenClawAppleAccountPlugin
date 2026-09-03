from openclaw_apple_bridge.rail12306 import plan_email, station_city


def test_station_city_normalizes_prefecture_level_destination() -> None:
    assert station_city("温州南站") == "温州"
    assert station_city("平阳站") == "温州"
    assert station_city("瑞安站") == "温州"


def test_purchase_parsing() -> None:
    result = plan_email(
        {
            "messageId": "mail-1",
            "subject": "网上购票系统-用户支付通知",
            "body": "订单号码 AB12345678。1.测试旅客，2026年09月08日12:12开，武汉站-深圳北站，G395次列车。",
        }
    )
    assert result["mailAction"] == "book"
    assert result["plans"][0]["operation"] == "upsert"
    assert result["plans"][0]["event"]["title"] == "火车行程：武汉→深圳"


def test_transfer_segments_are_merged_and_destination_is_city() -> None:
    body = """
    订单号码 CD12345678。
    1.测试旅客，2026年09月08日08:00开，武汉站-南京南站，G100次列车。
    2.测试旅客，2026年09月08日12:00开，南京南站-苏州站，G200次列车。
    3.测试旅客，2026年09月08日15:00开，苏州站-上海虹桥站，G300次列车。
    """
    result = plan_email({"messageId": "mail-2", "subject": "购票成功", "body": body})
    assert len(result["plans"]) == 1
    assert result["plans"][0]["segments"] == 3
    assert result["plans"][0]["event"]["title"] == "火车行程：武汉→上海"


def test_refund_creates_delete_plan() -> None:
    result = plan_email(
        {
            "messageId": "mail-3",
            "subject": "退票成功通知",
            "body": "订单号码 EF12345678。测试旅客，2026年09月08日12:12开，武汉站-温州南站，G395次列车。",
        }
    )
    assert result["plans"][0]["operation"] == "delete"
    assert result["plans"][0]["event"]["title"] == "火车行程：武汉→温州"


def test_change_creates_reconciliation_plan() -> None:
    result = plan_email(
        {
            "messageId": "mail-4",
            "subject": "改签成功通知",
            "body": "订单号码 GH12345678。测试旅客，2026年09月09日14:30开，武汉站-瑞安站，G999次列车。",
        }
    )
    assert result["plans"][0]["operation"] == "reconcile-update"
