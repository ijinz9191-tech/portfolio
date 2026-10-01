"""경계값·불변조건·큰 합성 입력으로 기존 공개 API를 검증한다."""

import unittest

from reconcile import InputError, reconcile


class DepthTests(unittest.TestCase):
    def test_invalid_calendar_year(self):
        for period in ("0000-01", "２０２６-10"):
            with self.assertRaises(InputError):
                reconcile(
                    {
                        "payments": [
                            {
                                "payment_id": "p",
                                "subscription_id": "A",
                                "period": period,
                                "status": "CAPTURED",
                                "amount_won": 1,
                            }
                        ],
                        "entitlements": [],
                        "partner_acks": [],
                    }
                )

    def test_cross_subscription_reference(self):
        doc = {
            "payments": [
                {
                    "payment_id": "p",
                    "subscription_id": "A",
                    "period": "2026-10",
                    "status": "CAPTURED",
                    "amount_won": 1,
                }
            ],
            "entitlements": [
                {
                    "payment_id": "p",
                    "subscription_id": "B",
                    "period": "2026-10",
                    "status": "ACTIVE",
                }
            ],
            "partner_acks": [],
        }
        issues = reconcile(doc)["issues"]
        self.assertIn(
            "CROSS_SUBSCRIPTION_PAYMENT_REFERENCE", [i["issue"] for i in issues]
        )


if __name__ == "__main__":
    unittest.main()
