"""Official MCP Streamable HTTP surface for SmartStay tools."""

from __future__ import annotations

import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .calculator import calculate_room_cost as calculate_cost
from .calendar_tool import create_calendar_event as create_event
from .crm import crm_profile as manage_profile
from .weather import get_weather as lookup_weather


mcp = FastMCP(
    "SmartStay Tools",
    instructions="CRM, pricing, calendar, and weather tools for the SmartStay hotel assistant.",
    json_response=True,
    stateless_http=True,
    host="0.0.0.0",
    port=int(os.getenv("MCP_PORT", "8001")),
)


@mcp.tool()
async def crm_profile(
    action: str,
    user_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    preference: Optional[str] = None,
    interaction: Optional[str] = None,
) -> dict:
    """Get, create, update, or append an interaction to a guest profile."""
    return await manage_profile(action, user_id, name, email, phone, preference, interaction)


@mcp.tool()
async def calculate_room_cost(
    room_type: str, check_in: str, check_out: str, guests: int = 1
) -> dict:
    """Calculate a hotel room total for an ISO-date stay window."""
    return await calculate_cost(room_type, check_in, check_out, guests)


@mcp.tool()
async def create_calendar_event(
    user_id: str,
    room_type: str,
    check_in: str,
    check_out: str,
    guest_name: str = "Guest",
) -> dict:
    """Create a local iCalendar hold for requested hotel stay dates."""
    return await create_event(user_id, room_type, check_in, check_out, guest_name)


@mcp.tool()
async def get_weather(city: str, date: Optional[str] = None) -> dict:
    """Get current or forecast daily weather through Open-Meteo."""
    return await lookup_weather(city, date)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

