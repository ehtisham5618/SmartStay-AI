from .calculator import CALCULATOR_SCHEMA, calculate_room_cost
from .calendar_tool import CALENDAR_SCHEMA, create_calendar_event
from .crm import CRM_SCHEMA, crm_profile
from .registry import ToolRegistry
from .weather import WEATHER_SCHEMA, get_weather


def create_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CRM_SCHEMA, crm_profile, timeout_seconds=3)
    registry.register(CALCULATOR_SCHEMA, calculate_room_cost, timeout_seconds=2)
    registry.register(CALENDAR_SCHEMA, create_calendar_event, timeout_seconds=3)
    registry.register(WEATHER_SCHEMA, get_weather, timeout_seconds=2)
    return registry


TOOL_SCHEMAS = [CRM_SCHEMA, CALCULATOR_SCHEMA, CALENDAR_SCHEMA, WEATHER_SCHEMA]

__all__ = ["TOOL_SCHEMAS", "create_registry"]
