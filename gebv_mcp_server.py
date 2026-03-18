#!/usr/bin/env python3
"""
GEBV Explorer MCP Server
Exposes tools for Claude to interact with the core GEBV app (port 5001).
"""

import sys
import fastmcp
import requests
from datetime import datetime

def log(msg: str):
    print(f"[MCP {datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

mcp = fastmcp.FastMCP("gebv-explorer")
API_BASE_URL = "http://127.0.0.1:5001"

log("GEBV Explorer MCP Server loaded successfully")
log(f"Python: {sys.executable}")
log(f"API target: {API_BASE_URL}")


@mcp.tool()
def adjust_slider(trait: str, start_percent: float, end_percent: float) -> str:
    """
    Adjust a GEBV trait slider by percentile range.

    Args:
        trait: Name of the GEBV trait (e.g., "GEBV_yield", "GEBV_Brix", "GEBV_Fruit_pungency")
        start_percent: Starting percentile (0-100)
        end_percent: Ending percentile (0-100)

    Returns:
        Confirmation message
    """
    log(f"adjust_slider called: trait={trait}, range={start_percent}%-{end_percent}%")
    try:
        response = requests.post(
            f"{API_BASE_URL}/sliders/{trait}",
            json={"start_percent": start_percent, "end_percent": end_percent},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            log(f"adjust_slider OK: {data['message']}")
            return data["message"]
        error_msg = response.json().get("error", "Unknown error")
        log(f"adjust_slider API error: {error_msg}")
        return f"Error: {error_msg}"
    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        return "Error: Request timed out"
    except Exception as e:
        log(f"adjust_slider exception: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
def get_available_traits() -> str:
    """
    Get a list of all available GEBV trait column names.

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
    log("reset_all_sliders called")
    try:
        response = requests.post(f"{API_BASE_URL}/sliders/reset", timeout=5)
        if response.status_code == 200:
            log("reset_all_sliders OK")
            return "All sliders have been reset to full range (no filters active)"
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
        Current filter state, or message if no filters active
    """
    log("get_current_filters called")
    try:
        response = requests.get(f"{API_BASE_URL}/sliders", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if not data:
                return "No filters currently active - all sliders at full range"
            filters = [f"{trait}: {state['start_percent']}% - {state['end_percent']}%"
                       for trait, state in data.items()]
            return "Active filters:\n" + "\n".join(filters)
        return f"Error: API returned status {response.status_code}"
    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        return "Error: Request timed out"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def compute_genomic_selection_index(trait_weights: dict, top_n: int = 20) -> str:
    """
    Compute an accuracy-adjusted genomic selection index across multiple GEBV traits.

    This is Anna McCormick's modified genomic selection index — NOT the classic Smith-Hazel.
    The classic Smith-Hazel requires a phenotypic covariance matrix P, which causes
    collinearity issues when training GEBVs and phenotypic data overlap.

    Instead, this uses:

        b = (R G R)^-1 (R G a)

    where:
    - G is the covariance matrix estimated from the selected GEBV traits
    - R is a diagonal matrix of trait prediction accuracies (from PA file)
    - a is the vector of user-supplied economic weights

    The resulting coefficients reflect both the genetic covariance between traits
    and their prediction accuracies, giving a more reliable genomic ranking.

    Requires at least 2 traits.

    Args:
        trait_weights: Dict mapping trait names to economic weights.
                       Example: {"GEBV_yield": 2.0, "GEBV_Brix": 1.0}
        top_n: Number of top-ranked lines to return (default 20)

    Returns:
        Ranked lines with genomic selection index scores and derived coefficients.
    """
    log(f"compute_genomic_selection_index called: traits={list(trait_weights.keys())}, top_n={top_n}")
    try:
        response = requests.post(
            f"{API_BASE_URL}/genomic_selection_index",
            json={"trait_weights": trait_weights, "top_n": top_n},
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            lines = data.get("ranked_lines", [])
            coeffs = data.get("index_coefficients", {})
            econ_w = data.get("economic_weights", {})
            trait_acc = data.get("trait_accuracies", {})

            coeff_lines = []
            for t in econ_w:
                acc_str = f"  |  accuracy={trait_acc[t]:.3f}" if t in trait_acc else ""
                coeff_lines.append(
                    f"  {t}: economic weight={econ_w[t]:.3f}  ->  index coefficient={coeffs.get(t, 0):.4f}{acc_str}"
                )

            ranked = [
                f"  {i}. {row.get('Line', '?')} (score={row.get('Genomic_Selection_Index', 0):.4f})"
                for i, row in enumerate(lines, 1)
            ]

            return (
                f"Genomic Selection Index [b=(RGR)^-1(RGa)] — top {len(lines)} lines\n"
                f"(scored {data.get('n_lines_scored', '?')} lines total)\n\n"
                f"Index coefficients (economic weights adjusted for covariance and prediction accuracy):\n"
                + "\n".join(coeff_lines)
                + "\n\nRanked lines:\n"
                + "\n".join(ranked)
                + f"\n\nNote: {data.get('note', '')}"
            )
        else:
            error_msg = response.json().get("error", "Unknown error")
            log(f"compute_genomic_selection_index API error: {error_msg}")
            return f"Error: {error_msg}"

    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        return "Error: Request timed out"
    except Exception as e:
        log(f"compute_genomic_selection_index exception: {e}")
        return f"Error: {str(e)}"


@mcp.tool()
def compute_selection_index(trait_weights: dict, top_n: int = 20) -> str:
    """
    Compute a weighted linear selection index across multiple GEBV traits.

    Lines are scored as I = sum(w_j * z_ij), where z_ij is the z-score
    normalized GEBV for line i on trait j. Weights are automatically
    normalized to sum to 1, so only relative values matter.

    This is a simpler approach than the genomic selection index — traits are
    treated as independent and no prediction accuracy or genetic covariance
    information is used. Choose this when you want a straightforward weighted
    ranking without the genomic covariance adjustment.

    Args:
        trait_weights: Dict mapping trait names to relative weights.
                       Example: {"GEBV_yield": 0.6, "GEBV_Brix": 0.3, "GEBV_Fruit_pungency": 0.1}
        top_n: Number of top-ranked lines to return (default 20)

    Returns:
        Ranked list of lines with their composite index scores
    """
    log(f"compute_selection_index called: weights={trait_weights}, top_n={top_n}")
    try:
        response = requests.post(
            f"{API_BASE_URL}/selection_index",
            json={"trait_weights": trait_weights, "top_n": top_n},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            norm_w = data.get("normalized_weights", {})

            weight_summary = ", ".join(f"{t}={w:.3f}" for t, w in norm_w.items())
            lines = [f"  {r['rank']}. {r['Line']}  score={r['index_score']:.4f}" for r in results]
            log(f"compute_selection_index OK: {len(results)} results")
            return (
                f"Weighted Selection Index (normalized weights: {weight_summary})\n"
                + "\n".join(lines)
            )
        else:
            error_msg = response.json().get("error", "Unknown error")
            log(f"compute_selection_index API error: {error_msg}")
            return f"Error: {error_msg}"

    except requests.exceptions.ConnectionError:
        return f"Error: Could not connect to GEBV API server at {API_BASE_URL}"
    except requests.exceptions.Timeout:
        return "Error: Request timed out"
    except Exception as e:
        log(f"compute_selection_index exception: {e}")
        return f"Error: {str(e)}"


if __name__ == "__main__":
    try:
        mcp.run()
    except KeyboardInterrupt:
        log("MCP Server shutting down")
