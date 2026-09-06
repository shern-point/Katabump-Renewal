import json
import os
import unittest
from contextlib import ExitStack, chdir
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import requests
import proxy_handler


with patch.dict(os.environ, {}, clear=True), patch("builtins.print"):
    import main


class FakeClashAPI:
    """Keep the selected node unchanged when a simulated API request fails."""

    url = "http://127.0.0.1:9090"

    def __init__(self, auto_node="node-1"):
        self.current = "auto"
        self.auto_node = auto_node
        self.get_outcomes = []
        self.put_outcomes = []
        self.get_paths = []
        self.put_nodes = []
        self.sessions = []

    @property
    def active_node(self):
        return self.auto_node if self.current == "auto" else self.current

    def new_session(self):
        session = MagicMock()
        session.trust_env = True
        session.__enter__.return_value = session
        session.get.side_effect = self.get
        session.put.side_effect = self.put
        self.sessions.append(session)
        return session

    @staticmethod
    def response(url, payload, status):
        if isinstance(status, Exception):
            raise status
        response = requests.Response()
        response.status_code = status
        response.url = url
        response._content = json.dumps(payload).encode("utf-8")
        return response

    def get(self, url, **kwargs):
        self.get_paths.append(url)
        if url == self.url + "/proxies/proxy":
            node = self.current
        elif url == self.url + "/proxies/auto":
            node = self.auto_node
        else:
            raise AssertionError("Unexpected Clash API URL: " + url)
        status = self.get_outcomes.pop(0) if self.get_outcomes else 200
        return self.response(url, {"now": node}, status)

    def put(self, url, *, json, **kwargs):
        if url != self.url + "/proxies/proxy":
            raise AssertionError("Unexpected Clash API URL: " + url)
        node = json["name"]
        self.put_nodes.append(node)
        status = self.put_outcomes.pop(0) if self.put_outcomes else 204
        response = self.response(url, {}, status)
        if 200 <= status < 300:
            self.current = node
        return response


class ProxyTestCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(TemporaryDirectory())
        self.stack.enter_context(chdir(directory))
        self.stack.enter_context(patch.dict(os.environ, {
            "IS_PROXY": "true",
            "NODE_ATTEMPTS": "3",
            "PROXY_SERVER": "http://127.0.0.1:8080",
        }, clear=True))
        self.stack.enter_context(patch("builtins.print"))

    def write_config(self, pool_size=3, proxy_url="anytls://test-password@proxy.example.invalid:443"):
        pool_file = "missing-pool.json"
        if pool_size is not None:
            pool_file = "test-pool.json"
            nodes = [
                {"server": "proxy.example.invalid", "port": 10000 + index,
                 "sni": f"node-{index}.example.invalid"}
                for index in range(1, pool_size + 1)
            ]
            Path(pool_file).write_text(json.dumps(nodes), encoding="utf-8")
        with patch.dict(os.environ, {"PROXY_URL": proxy_url, "POOL_FILE": pool_file}):
            proxy_handler.main()
        return json.loads(Path("config.json").read_text(encoding="utf-8"))

    def mock_api(self, auto_node="node-1"):
        self.api = FakeClashAPI(auto_node)
        self.session_factory = self.stack.enter_context(
            patch.object(main.requests, "Session", side_effect=self.api.new_session)
        )


class ProxyConfigurationTests(ProxyTestCase):
    def test_pool_preserves_automatic_initial_selection_and_exposes_real_nodes(self):
        config = self.write_config()
        outbounds = {outbound["tag"]: outbound for outbound in config["outbounds"]}
        nodes = ["node-1", "node-2", "node-3"]
        self.assertEqual(outbounds["auto"]["type"], "urltest")
        self.assertEqual(outbounds["auto"]["outbounds"], nodes)
        self.assertEqual(outbounds["proxy"]["type"], "selector")
        self.assertEqual(outbounds["proxy"]["outbounds"], ["auto", *nodes])
        self.assertEqual(outbounds["proxy"]["default"], "auto")
        self.assertTrue(outbounds["proxy"]["interrupt_exist_connections"])
        self.assertEqual(config["route"]["final"], "proxy")
        self.assertEqual(config["experimental"]["clash_api"]["external_controller"], "127.0.0.1:9090")
        self.assertEqual(main._get_proxy_rotation(), {
            "nodes": nodes,
            "api_url": FakeClashAPI.url,
            "current_node": None,
        })

    def test_missing_and_non_pool_configurations_do_not_enable_rotation(self):
        self.assertIsNone(main._get_proxy_rotation())
        for proxy_url in ("anytls://test-password@proxy.example.invalid:443",
                          "http://proxy.example.invalid:8080"):
            with self.subTest(proxy_url=proxy_url):
                config = self.write_config(pool_size=None, proxy_url=proxy_url)
                self.assertNotIn("clash_api", config.get("experimental", {}))
                self.assertEqual(config["route"]["final"], "proxy")
                self.assertIsNone(main._get_proxy_rotation())

    def test_single_node_pool_does_not_enable_rotation(self):
        self.write_config(pool_size=1)
        self.assertIsNone(main._get_proxy_rotation())

    def test_rotation_ignores_groups_direct_and_unreferenced_nodes(self):
        config = self.write_config()
        config["outbounds"].extend([
            {"type": "urltest", "tag": "latency", "outbounds": ["node-1"]},
            {"type": "selector", "tag": "nested", "outbounds": ["node-2"]},
            {"type": "anytls", "tag": "unreferenced", "server": "unused.example.invalid"},
        ])
        selector = next(outbound for outbound in config["outbounds"] if outbound["tag"] == "proxy")
        selector["outbounds"] = ["auto", "direct", "latency", "nested", "node-3", "missing", "node-1"]
        Path("config.json").write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(main._get_proxy_rotation()["nodes"], ["node-3", "node-1"])


class ProxySelectionTests(ProxyTestCase):
    def setUp(self):
        super().setUp()
        self.write_config()
        self.mock_api(auto_node="node-2")

    def test_first_selection_pins_the_automatic_node_and_bypasses_environment_proxy(self):
        rotation = main._get_proxy_rotation()
        with patch.dict(os.environ, {"HTTP_PROXY": "http://unreachable.example.invalid:8888"}):
            self.assertTrue(main._select_proxy_node(rotation))
        self.assertEqual(self.api.get_paths, [
            FakeClashAPI.url + "/proxies/proxy",
            FakeClashAPI.url + "/proxies/auto",
        ])
        self.assertEqual(self.api.put_nodes, ["node-2"])
        self.assertEqual(rotation["current_node"], "node-2")
        self.assertTrue(self.api.sessions)
        self.assertTrue(all(session.trust_env is False for session in self.api.sessions))

    def test_existing_manual_selection_advances_and_wraps_from_the_selected_node(self):
        self.api.current = "node-3"
        rotation = main._get_proxy_rotation()
        self.assertTrue(main._select_proxy_node(rotation))
        self.assertTrue(main._select_proxy_node(rotation, advance=True))
        self.assertEqual(self.api.put_nodes, ["node-3", "node-1"])
        self.assertNotIn(FakeClashAPI.url + "/proxies/auto", self.api.get_paths)
        self.assertEqual(rotation["current_node"], "node-1")

    def test_unavailable_or_invalid_initial_selection_never_pins_a_node(self):
        cases = (503, requests.ConnectionError("API unavailable"), "unknown-node")
        for outcome in cases:
            with self.subTest(outcome=str(outcome)):
                api = FakeClashAPI()
                self.session_factory.side_effect = api.new_session
                if isinstance(outcome, str):
                    api.auto_node = outcome
                else:
                    api.get_outcomes = [outcome]
                rotation = main._get_proxy_rotation()
                self.assertFalse(main._select_proxy_node(rotation))
                self.assertIsNone(rotation["current_node"])
                self.assertEqual(api.put_nodes, [])


class AccountProxyRotationTests(ProxyTestCase):
    def setUp(self):
        super().setUp()
        self.write_config()
        self.mock_api()
        self.accounts = []
        self.outcomes = []
        self.runs = []
        self.notified_accounts = []
        self.stack.enter_context(patch.object(main, "ACCOUNTS", self.accounts))
        self.stack.enter_context(patch.object(main, "CURRENT_EMAIL", ""))
        clock = self.stack.enter_context(patch.object(main, "datetime"))
        clock.now.return_value = datetime(2026, 9, 6, 12, tzinfo=main.RENEWAL_TIMEZONE)
        self.run_account = self.stack.enter_context(
            patch.object(main, "_run_account", side_effect=self.record_run)
        )
        self.restart_proxy = self.stack.enter_context(patch.object(main, "_restart_proxy"))
        self.notify = self.stack.enter_context(patch.object(
            main, "send_tg_message",
            side_effect=lambda *args, **kwargs: self.notified_accounts.append(main.CURRENT_EMAIL),
        ))

    @staticmethod
    def account(name, **fields):
        return {"email": name + "@example.invalid", "password": "test-password", **fields}

    def record_run(self, sb_kwargs, email, password):
        self.runs.append((email.split("@")[0], self.api.active_node))
        return self.outcomes.pop(0) if self.outcomes else True

    def test_only_pending_accounts_rotate_and_cycle_through_the_pool(self):
        self.accounts.extend([
            self.account("skip-first", renewal_date="2026-09-03"),
            self.account("a", renewal_date="2026-09-02"),
            self.account("skip-middle", renewal_date="2026-09-10"),
            self.account("b"),
            self.account("c", renewal_date=" "),
            self.account("d", renewal_date=None),
        ])
        main.main()
        self.assertEqual(self.runs, [("a", "node-1"), ("b", "node-2"), ("c", "node-3"), ("d", "node-1")])
        self.assertEqual(self.api.put_nodes, ["node-1", "node-2", "node-3", "node-1"])
        self.restart_proxy.assert_not_called()

    def test_cf_failure_changes_node_before_retry_then_changes_once_for_next_account(self):
        self.accounts.extend([self.account("a"), self.account("b")])
        self.outcomes = [False, True, True]
        main.main()
        self.assertEqual(self.runs, [("a", "node-1"), ("a", "node-2"), ("b", "node-3")])
        self.assertEqual(self.api.put_nodes, ["node-1", "node-2", "node-3"])
        self.restart_proxy.assert_not_called()

    def test_one_attempt_per_account_still_rotates_between_accounts(self):
        self.accounts.extend([self.account("a"), self.account("b"), self.account("c")])
        with patch.dict(os.environ, {"NODE_ATTEMPTS": "1"}):
            main.main()
        self.assertEqual(self.runs, [("a", "node-1"), ("b", "node-2"), ("c", "node-3")])

    def test_exhausted_account_still_advances_for_the_next_account(self):
        self.accounts.extend([self.account("a"), self.account("b")])
        self.outcomes = [False, False, True]
        with patch.dict(os.environ, {"NODE_ATTEMPTS": "2"}), self.assertRaises(SystemExit) as result:
            main.main()
        self.assertEqual(result.exception.code, 1)
        self.assertEqual(self.runs, [("a", "node-1"), ("a", "node-2"), ("b", "node-3")])
        self.notify.assert_called()

    def test_api_errors_retry_the_same_target_without_running_on_the_old_node(self):
        self.accounts.extend([self.account("a"), self.account("b")])
        self.api.put_outcomes = [204, 503, requests.Timeout("API timeout"), 204]
        main.main()
        self.assertEqual(self.api.put_nodes, ["node-1", "node-2", "node-2", "node-2"])
        self.assertEqual(self.runs, [("a", "node-1"), ("b", "node-2")])
        self.restart_proxy.assert_not_called()

    def test_failed_initial_pin_retries_without_skipping_the_initial_node(self):
        self.accounts.extend([self.account("a"), self.account("b")])
        self.api.put_outcomes = [503, 204, 204]
        main.main()
        self.assertEqual(self.api.put_nodes, ["node-1", "node-1", "node-2"])
        self.assertEqual(self.runs, [("a", "node-1"), ("b", "node-2")])

    def test_api_failure_exhausts_account_without_reusing_previous_node_for_next_account(self):
        self.accounts.extend([self.account("a"), self.account("b"), self.account("c")])
        self.api.put_outcomes = [204, 503, 204]
        with patch.dict(os.environ, {"NODE_ATTEMPTS": "1"}), self.assertRaises(SystemExit) as result:
            main.main()
        self.assertEqual(result.exception.code, 1)
        self.assertEqual(self.api.put_nodes, ["node-1", "node-2", "node-2"])
        self.assertEqual(self.runs, [("a", "node-1"), ("c", "node-2")])
        self.assertEqual(self.notified_accounts, ["b@example.invalid"])

    def test_single_node_retains_restart_on_failed_account_attempt(self):
        self.write_config(pool_size=1)
        self.accounts.extend([self.account("a"), self.account("b")])
        self.outcomes = [False, True, True]
        main.main()
        self.assertEqual([name for name, node in self.runs], ["a", "a", "b"])
        self.restart_proxy.assert_called_once_with()
        self.session_factory.assert_not_called()
        for args in self.run_account.call_args_list:
            self.assertEqual(args.args[0]["proxy"], "http://127.0.0.1:8080")

    def test_proxy_disabled_keeps_direct_access_and_existing_retry_behavior(self):
        self.accounts.extend([self.account("a"), self.account("b")])
        self.outcomes = [False, True, True]
        with patch.dict(os.environ, {"IS_PROXY": "false"}):
            main.main()
        self.assertEqual([name for name, node in self.runs], ["a", "a", "b"])
        self.restart_proxy.assert_called_once_with()
        self.session_factory.assert_not_called()
        for args in self.run_account.call_args_list:
            self.assertNotIn("proxy", args.args[0])


if __name__ == "__main__":
    unittest.main()
