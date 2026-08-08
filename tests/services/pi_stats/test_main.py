"""Tests for the Pi Stats service entrypoint."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.pi_stats import main as pi_stats


class RecordMqttDisconnectionTestCase(unittest.TestCase):
    """Test the sustained MQTT-disconnection watchdog."""

    @staticmethod
    def test_records_first_disconnection() -> None:
        """The first disconnected sample starts the recovery deadline."""
        with patch.object(pi_stats, "monotonic", return_value=100.0):
            assert pi_stats.record_mqtt_disconnection(None) == 100.0

    @staticmethod
    def test_preserves_timestamp_during_grace_period() -> None:
        """A short outage continues to use the original timestamp."""
        disconnected_since = 200.0 - pi_stats.MQTT_DISCONNECT_EXIT_SECONDS + 1

        with patch.object(pi_stats, "monotonic", return_value=200.0):
            assert (
                pi_stats.record_mqtt_disconnection(disconnected_since)
                == disconnected_since
            )

    @staticmethod
    def test_exits_after_recovery_deadline() -> None:
        """A sustained outage exits so systemd can restart the process."""
        disconnected_since = 500.0 - pi_stats.MQTT_DISCONNECT_EXIT_SECONDS
        exit_code: int | str | None = None

        with patch.object(pi_stats, "monotonic", return_value=500.0):
            try:
                pi_stats.record_mqtt_disconnection(disconnected_since)
            except SystemExit as exc:
                exit_code = exc.code

        assert exit_code == 1


if __name__ == "__main__":
    unittest.main()
