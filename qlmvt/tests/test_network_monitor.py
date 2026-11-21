import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.test import SimpleTestCase
from rest_framework.exceptions import AuthenticationFailed
from socketio.exceptions import ConnectionRefusedError

from qlmvt import realtime
from qlmvt.services.network_monitor_service import probe_ip_address


class NetworkMonitorProbeTests(SimpleTestCase):
    @patch("qlmvt.services.network_monitor_service.subprocess.run")
    def test_pings_a_valid_configured_ipv4_without_a_shell(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout="64 bytes from 192.0.2.10: time=1.25 ms",
            stderr="",
        )

        result = probe_ip_address("192.0.2.10")

        self.assertEqual(result["status"], "RESPONSIVE")
        self.assertEqual(result["latency_ms"], 1.25)
        self.assertEqual(result["sample_loss_percent"], 0)
        self.assertIn("192.0.2.10", mock_run.call_args.args[0])
        self.assertNotIn("shell", mock_run.call_args.kwargs)

    @patch("qlmvt.services.network_monitor_service.subprocess.run")
    def test_rejects_non_ip_targets_without_running_ping(self, mock_run):
        result = probe_ip_address("example.test")

        self.assertEqual(result["status"], "UNKNOWN")
        mock_run.assert_not_called()

    @patch("qlmvt.services.network_monitor_service.subprocess.run")
    def test_marks_a_timed_out_probe_offline(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("ping", 3)

        result = probe_ip_address("192.0.2.10")

        self.assertEqual(result["status"], "NO_RESPONSE")
        self.assertEqual(result["sample_loss_percent"], 100)


class NetworkMonitorSocketIOTests(SimpleTestCase):
    async def test_rejects_a_missing_or_invalid_jwt(self):
        with self.assertRaises(ConnectionRefusedError):
            await realtime.connect("missing-token", {}, {})

        with patch.object(
            realtime,
            "_authenticate_token",
            new_callable=AsyncMock,
            side_effect=AuthenticationFailed("invalid"),
        ):
            with self.assertRaises(ConnectionRefusedError):
                await realtime.connect("invalid-token", {}, {"token": "invalid"})

    async def test_emits_snapshots_to_an_authenticated_socket_client(self):
        snapshot = {
            "success": True,
            "serverTime": "2026-01-01T00:00:00+00:00",
            "devices": [],
            "links": [],
        }
        with patch.object(
            realtime,
            "_authenticate_token",
            new_callable=AsyncMock,
            return_value=time.time() + 3600,
        ), patch.object(
            realtime,
            "_load_snapshot",
            new_callable=AsyncMock,
            return_value=snapshot,
        ), patch.object(
            realtime.socketio_server,
            "emit",
            new_callable=AsyncMock,
        ) as emit:
            sid = "authenticated-client"
            accepted = await realtime.connect(sid, {}, {"token": "valid"})
            self.assertTrue(accepted)
            await realtime.subscribe_network_monitor(sid)
            await asyncio.sleep(0.01)
            await realtime.disconnect(sid)

        emit.assert_awaited_with("network_snapshot", snapshot, to=sid)
