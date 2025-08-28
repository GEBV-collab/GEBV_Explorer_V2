#!/usr/bin/env python3
"""
Simple GEBV Explorer MCP Server
Single tool to adjust slider values by trait name and percentile range.
Calls the GEBV API server to actually update slider state.
"""

import fastmcp
import requests

# Initialize FastMCP server
mcp = fastmcp.FastMCP("gebv-explorer")

# API server configuration
API_BASE_URL = "http://127.0.0.1:5001"

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
    Get a list of all available GEBV trait column names from the API server.
    
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

if __name__ == "__main__":
    print("🌶️  GEBV Explorer MCP Server starting...")
    print(f"Will connect to API server at: {API_BASE_URL}")
    mcp.run()