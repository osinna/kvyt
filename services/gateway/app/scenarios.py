"""Scenarios owned by gateway. None are implemented in the code yet."""

from kvyt_common import load_scenarios

from .config import get_settings

SERVICE_NAME = "gateway"

_settings = get_settings()
scenarios = load_scenarios(_settings.bug_scenario, SERVICE_NAME, _settings.log_level)
