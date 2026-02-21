#!/usr/bin/env python3
"""
GEBV Explorer MCP Server — Global Collection
Provides tools for Claude to adjust slider filters.
Calls the global GEBV API server (port 5002).
"""

import fastmcp
import requests

mcp = fastmcp.FastMCP("gebv-explorer-global")

API_BASE_URL = "http://127.0.0.1:5002"


@mcp.tool()
def adjust_slider(trait: str, start_percent: float, end_percent: float) -> str:
    """
    Adjust a GEBV trait slider by percentile range.

    Args:
        trait: Name of the GEBV trait (e.g., "GEBV_yield_y", "GEBV_fruitno_x")
              Note: traits ending in _x come from the quality CSV; _y from the averaged agronomic CSV.
        start_percent: Starting percentile (0-100)
        end_percent: Ending percentile (0-100)

    Returns:
        Confirmation message
    """
    try:
        response = requests.post(
            f"{API_BASE_URL}/sliders/{trait}",
            json={
                "start_percent": start_percent,
                "end_percent": end_percent
            },
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            return data["message"]
        else:
            error_msg = response.json().get("error", "Unknown error")
            return f"Error: {error_msg}"

    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        return "Error: Request timed out"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_available_traits() -> str:
    """
    Get a list of all available GEBV trait column names from the global collection.

    Returns:
        Comma-separated list of trait names, or error message if API unavailable
    """
    try:
        response = requests.get(f"{API_BASE_URL}/traits", timeout=5)

        if response.status_code == 200:
            data = response.json()
            traits = data.get("traits", [])
            return f"Available traits: {', '.join(traits)}"
        else:
            return f"Error: API returned status {response.status_code}"

    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        return "Error: Request timed out"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def reset_all_sliders() -> str:
    """
    Reset ALL sliders to their full range (0-100 percentile), removing all filters.
    Use this before setting new filters to ensure a clean state.

    Returns:
        Confirmation message
    """
    try:
        response = requests.post(f"{API_BASE_URL}/sliders/reset", timeout=5)

        if response.status_code == 200:
            return "All sliders have been reset to full range (no filters active)"
        else:
            return f"Error: API returned status {response.status_code}"

    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        return "Error: Request timed out"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_current_filters() -> str:
    """
    Get the current state of all active slider filters.

    Returns:
        JSON string of current filter state, or message if no filters active
    """
    try:
        response = requests.get(f"{API_BASE_URL}/sliders", timeout=5)

        if response.status_code == 200:
            data = response.json()
            if not data:
                return "No filters currently active - all sliders at full range"

            filters = []
            for trait, state in data.items():
                filters.append(f"{trait}: {state['start_percent']}% - {state['end_percent']}%")
            return "Active filters:\n" + "\n".join(filters)
        else:
            return f"Error: API returned status {response.status_code}"

    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        return "Error: Request timed out"
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    print("🌍 GEBV Explorer Global MCP Server starting...")
    print(f"Will connect to API server at: {API_BASE_URL}")
    mcp.run()
