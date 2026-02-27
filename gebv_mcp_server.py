#!/usr/bin/env python3
"""
Simple GEBV Explorer MCP Server
Single tool to adjust slider values by trait name and percentile range.
Calls the GEBV API server to actually update slider state.
"""

import sys
import fastmcp
import requests
from datetime import datetime

def log(msg: str):
    """Write timestamped debug info to stderr. stdout is reserved for the MCP protocol."""
    print(f"[MCP {datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

# Initialize FastMCP server
mcp = fastmcp.FastMCP("gebv-explorer")

# API server configuration
API_BASE_URL = "http://127.0.0.1:5001"

log("GEBV Explorer MCP Server loaded successfully")
log(f"Python: {sys.executable}")
log(f"API target: {API_BASE_URL}")

@mcp.tool()
def adjust_slider(trait: str, start_percent: float, end_percent: float) -> str:
    """
    Adjust a GEBV trait slider by percentile range.
    
    Args:
        trait: Name of the GEBV trait (e.g., "GEBV_pungency", "GEBV_yield", "GEBV_Brix")
        start_percent: Starting percentile (0-100)
        end_percent: Ending percentile (0-100)
    
    Returns:
        Confirmation message
    """
    log(f"adjust_slider called: trait={trait}, range={start_percent}%-{end_percent}%")
    try:
        # Call the API server to update the slider
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
            log(f"adjust_slider OK: {data['message']}")
            return data["message"]
        else:
            error_msg = response.json().get("error", "Unknown error")
            log(f"adjust_slider API error: {error_msg}")
            return f"Error: {error_msg}"

    except requests.exceptions.ConnectionError:
        log(f"adjust_slider connection error: API not reachable at {API_BASE_URL}")
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        log("adjust_slider timeout")
        return "Error: Request timed out"
    except Exception as e:
        log(f"adjust_slider exception: {e}")
        return f"Error: {str(e)}"

@mcp.tool()
def get_available_traits() -> str:
    """
    Get a list of all available GEBV trait column names from the API server.

    Returns:
        Comma-separated list of trait names, or error message if API unavailable
    """
    log("get_available_traits called")
    try:
        response = requests.get(f"{API_BASE_URL}/traits", timeout=5)

        if response.status_code == 200:
            data = response.json()
            traits = data.get("traits", [])
            log(f"get_available_traits OK: {len(traits)} traits")
            return f"Available traits: {', '.join(traits)}"
        else:
            log(f"get_available_traits API error: status {response.status_code}")
            return f"Error: API returned status {response.status_code}"

    except requests.exceptions.ConnectionError:
        log(f"get_available_traits connection error: API not reachable at {API_BASE_URL}")
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        log("get_available_traits timeout")
        return "Error: Request timed out"
    except Exception as e:
        log(f"get_available_traits exception: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
def reset_all_sliders() -> str:
    """
    Reset ALL sliders to their full range (0-100 percentile), removing all filters.
    Use this before setting new filters to ensure a clean state.

    Returns:
        Confirmation message
    """
    log("reset_all_sliders called")
    try:
        response = requests.post(f"{API_BASE_URL}/sliders/reset", timeout=5)

        if response.status_code == 200:
            log("reset_all_sliders OK")
            return "All sliders have been reset to full range (no filters active)"
        else:
            log(f"reset_all_sliders API error: status {response.status_code}")
            return f"Error: API returned status {response.status_code}"

    except requests.exceptions.ConnectionError:
        log(f"reset_all_sliders connection error: API not reachable at {API_BASE_URL}")
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        log("reset_all_sliders timeout")
        return "Error: Request timed out"
    except Exception as e:
        log(f"reset_all_sliders exception: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
def get_current_filters() -> str:
    """
    Get the current state of all active slider filters.
    Shows which traits are currently filtered and their percentile ranges.

    Returns:
        JSON string of current filter state, or message if no filters active
    """
    log("get_current_filters called")
    try:
        response = requests.get(f"{API_BASE_URL}/sliders", timeout=5)

        if response.status_code == 200:
            data = response.json()
            if not data:
                log("get_current_filters OK: no active filters")
                return "No filters currently active - all sliders at full range"

            filters = []
            for trait, state in data.items():
                filters.append(f"{trait}: {state['start_percent']}% - {state['end_percent']}%")
            log(f"get_current_filters OK: {len(data)} active filter(s)")
            return "Active filters:\n" + "\n".join(filters)
        else:
            log(f"get_current_filters API error: status {response.status_code}")
            return f"Error: API returned status {response.status_code}"

    except requests.exceptions.ConnectionError:
        log(f"get_current_filters connection error: API not reachable at {API_BASE_URL}")
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        log("get_current_filters timeout")
        return "Error: Request timed out"
    except Exception as e:
        log(f"get_current_filters exception: {e}")
        return f"Error: {str(e)}"


if __name__ == "__main__":
    try:
        mcp.run()
    except KeyboardInterrupt:
        log("MCP Server shutting down")