import json
import os
import unittest
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from unittest.mock import ANY, call, patch


# Import with no configured accounts or real notification credentials.
with patch.dict(os.environ, {}, clear=True), patch("builtins.print"):
    import main


class RenewalDateTests(unittest.TestCase):
    def test_unconfigured_dates_keep_daily_processing(self):
        for value in (None, "", " ", "\t\n"):
            with self.subTest(value=value):
                self.assertIsNone(main.get_next_renewal_date(value, date(2026, 9, 6)))

    def test_anchor_and_each_fourth_day_are_renewal_days(self):
        for today in (date(2026, 9, 2), date(2026, 9, 6), date(2026, 9, 10)):
            with self.subTest(today=today):
                self.assertEqual(main.get_next_renewal_date("2026-09-02", today), today)

    def test_intermediate_days_return_the_next_renewal(self):
        cases = (
            (date(2026, 9, 3), date(2026, 9, 6)),
            (date(2026, 9, 4), date(2026, 9, 6)),
            (date(2026, 9, 5), date(2026, 9, 6)),
            (date(2026, 9, 7), date(2026, 9, 10)),
        )
        for today, expected in cases:
            with self.subTest(today=today):
                self.assertEqual(main.get_next_renewal_date("2026-09-02", today), expected)

    def test_future_anchor_does_not_create_earlier_renewal_days(self):
        self.assertEqual(
            main.get_next_renewal_date("2026-09-10", date(2026, 9, 2)),
            date(2026, 9, 10),
        )

    def test_calendar_boundaries(self):
        cases = (
            ("2026-01-30", date(2026, 2, 1), date(2026, 2, 3)),
            ("2025-12-30", date(2026, 1, 1), date(2026, 1, 3)),
            ("2024-02-25", date(2024, 2, 28), date(2024, 2, 29)),
            ("2024-02-25", date(2024, 2, 29), date(2024, 2, 29)),
            ("2024-02-29", date(2024, 3, 1), date(2024, 3, 4)),
            ("2026-02-26", date(2026, 2, 28), date(2026, 3, 2)),
        )
        for anchor, today, expected in cases:
            with self.subTest(anchor=anchor, today=today):
                self.assertEqual(main.get_next_renewal_date(anchor, today), expected)

    def test_invalid_dates_and_non_strings_are_rejected(self):
        values = (
            "2026-02-29", "2026-09-31", "2026-13-01", "0000-01-01",
            "2026/09/02", "2026-9-02", "2026-09-2", "20260902",
            "2026-W36-3", "2026-09-02T00:00:00", "tomorrow",
            0, False, 20260902, [], {}, date(2026, 9, 2),
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                main.get_next_renewal_date(value, date(2026, 9, 6))

    def test_default_today_changes_at_utc_plus_eight_midnight(self):
        self.assertEqual(main.RENEWAL_TIMEZONE.utcoffset(None), timedelta(hours=8))
        cases = (
            (datetime(2026, 9, 5, 15, 59, 59, tzinfo=timezone.utc), date(2026, 9, 5)),
            (datetime(2026, 9, 5, 16, 0, 0, tzinfo=timezone.utc), date(2026, 9, 9)),
        )
        for instant, expected in cases:
            with self.subTest(instant=instant), patch.object(main, "datetime") as clock:
                clock.now.side_effect = lambda tz: instant.astimezone(tz)
                self.assertEqual(main.get_next_renewal_date("2026-09-01"), expected)
                clock.now.assert_called_once_with(main.RENEWAL_TIMEZONE)


class AccountConfigurationTests(unittest.TestCase):
    def test_json_preserves_optional_dates_and_existing_email_aliases(self):
        users = [
            {"username": "dated@example.invalid", "password": "first", "renewal_date": "2026-09-02"},
            {"email": "legacy@example.invalid", "password": "second"},
            {"email": "null@example.invalid", "renewal_date": None},
            {"email": "invalid@example.invalid", "renewal_date": False},
        ]
        with patch.dict(os.environ, {"USERS_JSON": json.dumps(users)}, clear=True):
            self.assertEqual(main.load_accounts(), [
                {"email": "dated@example.invalid", "password": "first", "renewal_date": "2026-09-02"},
                {"email": "legacy@example.invalid", "password": "second", "renewal_date": None},
                {"email": "null@example.invalid", "password": "", "renewal_date": None},
                {"email": "invalid@example.invalid", "password": "", "renewal_date": False},
            ])

    def test_single_account_environment_preserves_renewal_date(self):
        env = {
            "KATABUMP_EMAIL": "single@example.invalid",
            "KATABUMP_PASSWORD": "test-password",
            "KATABUMP_RENEWAL_DATE": "2026-09-02",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(main.load_accounts(), [{
                "email": "single@example.invalid",
                "password": "test-password",
                "renewal_date": "2026-09-02",
            }])

    def test_single_account_without_date_keeps_daily_processing(self):
        env = {"KATABUMP_EMAIL": "legacy@example.invalid", "KATABUMP_PASSWORD": "test-password"}
        with patch.dict(os.environ, env, clear=True):
            accounts = main.load_accounts()
        self.assertEqual(len(accounts), 1)
        self.assertIsNone(main.get_next_renewal_date(accounts[0].get("renewal_date"), date(2026, 9, 6)))


class AccountSchedulingTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {
            "NODE_ATTEMPTS": "3",
            "IS_PROXY": "true",
            "PROXY_SERVER": "http://proxy.example.invalid:8080",
        }, clear=True))
        self.accounts = []
        stack.enter_context(patch.object(main, "ACCOUNTS", self.accounts))
        stack.enter_context(patch.object(main, "CURRENT_EMAIL", ""))
        stack.enter_context(patch("builtins.print"))
        self.clock = stack.enter_context(patch.object(main, "datetime"))
        self.clock.now.return_value = datetime(2026, 9, 6, 12, tzinfo=main.RENEWAL_TIMEZONE)
        self.run_account = stack.enter_context(patch.object(main, "_run_account", return_value=True))
        self.restart_proxy = stack.enter_context(patch.object(main, "_restart_proxy"))
        self.notify = stack.enter_context(patch.object(main, "send_tg_message"))

    @staticmethod
    def account(name, **fields):
        return {"email": name + "@example.invalid", "password": "test-password", **fields}

    def test_all_not_due_accounts_exit_success_without_browser_or_proxy(self):
        self.accounts.extend([
            self.account("between", renewal_date="2026-09-03"),
            self.account("future", renewal_date="2026-09-10"),
        ])
        main.main()
        self.run_account.assert_not_called()
        self.restart_proxy.assert_not_called()
        self.notify.assert_not_called()

    def test_mixed_accounts_only_run_due_and_unconfigured_accounts(self):
        self.accounts.extend([
            self.account("skip", renewal_date="2026-09-03"),
            self.account("due", renewal_date="2026-09-02"),
            self.account("legacy"),
            self.account("blank", renewal_date="  "),
            self.account("null", renewal_date=None),
        ])
        main.main()
        self.assertEqual(self.run_account.call_args_list, [
            call(ANY, name + "@example.invalid", "test-password")
            for name in ("due", "legacy", "blank", "null")
        ])
        self.restart_proxy.assert_not_called()

    def test_invalid_account_fails_run_but_valid_accounts_still_continue(self):
        self.accounts.extend([
            self.account("invalid", renewal_date="2026-02-29"),
            self.account("non-string", renewal_date=False),
            self.account("skip", renewal_date="2026-09-03"),
            self.account("due", renewal_date="2026-09-02"),
            self.account("legacy"),
        ])
        with self.assertRaises(SystemExit) as result:
            main.main()
        self.assertEqual(result.exception.code, 1)
        self.assertEqual(self.run_account.call_args_list, [
            call(ANY, "due@example.invalid", "test-password"),
            call(ANY, "legacy@example.invalid", "test-password"),
        ])
        self.restart_proxy.assert_not_called()

    def test_invalid_account_without_due_accounts_fails_without_browser(self):
        self.accounts.extend([
            self.account("invalid", renewal_date="not-a-date"),
            self.account("skip", renewal_date="2026-09-03"),
        ])
        with self.assertRaises(SystemExit) as result:
            main.main()
        self.assertEqual(result.exception.code, 1)
        self.run_account.assert_not_called()
        self.restart_proxy.assert_not_called()

    def test_processing_failure_retries_and_preserves_failure_exit_status(self):
        self.accounts.extend([
            self.account("skip", renewal_date="2026-09-03"),
            self.account("failed", renewal_date="2026-09-02"),
            self.account("legacy"),
        ])
        self.run_account.side_effect = [False, False, False, True]
        with self.assertRaises(SystemExit) as result:
            main.main()
        self.assertEqual(result.exception.code, 1)
        self.assertEqual(self.run_account.call_args_list, [
            call(ANY, "failed@example.invalid", "test-password"),
            call(ANY, "failed@example.invalid", "test-password"),
            call(ANY, "failed@example.invalid", "test-password"),
            call(ANY, "legacy@example.invalid", "test-password"),
        ])
        self.assertEqual(self.restart_proxy.call_count, 2)
        self.notify.assert_called()

    def test_retry_success_is_not_counted_as_failure_when_other_accounts_skip(self):
        self.accounts.extend([
            self.account("skip", renewal_date="2026-09-03"),
            self.account("due", renewal_date="2026-09-02"),
        ])
        self.run_account.side_effect = [False, True]
        main.main()
        self.assertEqual(self.run_account.call_count, 2)
        self.restart_proxy.assert_called_once_with()

    def test_main_uses_utc_plus_eight_date_at_midnight(self):
        self.accounts.append(self.account("due", renewal_date="2026-09-02"))
        instant = datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)
        self.clock.now.side_effect = lambda tz: instant.astimezone(tz)
        main.main()
        self.run_account.assert_called_once_with(ANY, "due@example.invalid", "test-password")
        self.clock.now.assert_called_with(main.RENEWAL_TIMEZONE)


if __name__ == "__main__":
    unittest.main()
