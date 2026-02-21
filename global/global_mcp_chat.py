#!/usr/bin/env python3
"""
MCP Chat Module for GEBV Explorer — Global Collection
Connects to the global GEBV MCP server and uses Claude API with tool use.
"""

import os
import asyncio
import json
from dotenv import load_dotenv

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import pandas as pd

# Load environment variables from the repo root .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, "..", ".env"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# MCP server and Python interpreter paths
MCP_SERVER_SCRIPT = os.path.join(BASE_DIR, "global_mcp_server.py")
PYTHON_PATH = os.path.join(BASE_DIR, "..", "venv", "bin", "python")
TRAIT_METADATA_PATH = os.path.join(BASE_DIR, "..", "data", "Trait_Metadata_with_Synonyms.xlsx")


def load_trait_metadata() -> str:
    """Load trait metadata and format it for the system prompt."""
    try:
        df = pd.read_excel(TRAIT_METADATA_PATH)

        lines = []
        for _, row in df.iterrows():
            trait_name = row.get('Trait_in_app_name', row.get('Trait', ''))
            full_label = row.get('Full label', '')
            unit = row.get('Unit', '')
            description = row.get('Description', '')
            synonyms = row.get('Synonyms', '')

            line = f"- {trait_name}: {full_label}"
            if unit:
                line += f" ({unit})"
            if description:
                line += f" - {description}"
            if synonyms:
                line += f" [Also known as: {synonyms}]"
            lines.append(line)

        return "\n".join(lines)
    except Exception as e:
        return f"(Could not load trait metadata: {e})"


# Cache the metadata on module load
TRAIT_METADATA = load_trait_metadata()


def convert_mcp_tools_to_claude(mcp_tools) -> list:
    """Convert MCP tool definitions to Claude's tool format."""
    claude_tools = []
    for tool in mcp_tools.tools:
        claude_tools.append({
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema
        })
    return claude_tools


async def run_mcp_chat(user_message: str, context: str = "") -> dict:
    """
    Run a chat with Claude using MCP tools.

    Args:
        user_message: The user's question or command
        context: Optional context about the current data/state

    Returns:
        dict with 'response' (text) and 'tool_calls' (list of executed tools)
    """
    if not ANTHROPIC_API_KEY:
        return {
            "response": "Error: ANTHROPIC_API_KEY not set in .env file",
            "tool_calls": []
        }

    server_params = StdioServerParameters(
        command=PYTHON_PATH,
        args=[MCP_SERVER_SCRIPT],
    )

    tool_calls = []
    final_response = ""

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = await session.list_tools()
            claude_tools = convert_mcp_tools_to_claude(mcp_tools)

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            system_prompt = f"""You are an assistant for the GEBV Explorer application, which visualizes genomic estimated breeding values (GEBVs) for pepper/Capsicum crop traits from the **Global Capsicum Collection** (~10,232 accessions, including control lines).

## Available GEBV Traits and Their Meanings:
{TRAIT_METADATA}

## Tools Available:
1. **adjust_slider** - Adjust a trait slider by percentile range (0-100)
2. **get_available_traits** - List all available GEBV trait names
3. **reset_all_sliders** - Reset ALL sliders to full range (removes all filters)
4. **get_current_filters** - See which filters are currently active

## How Percentiles Work:
- "top 10%" = start_percent=90, end_percent=100 (highest values)
- "bottom 20%" = start_percent=0, end_percent=20 (lowest values)
- "middle 50%" = start_percent=25, end_percent=75

## IMPORTANT - Filter Management:
- **ALWAYS call reset_all_sliders FIRST** before setting any new filters.
- Then adjust only the sliders the user specifically requested.

## Trait Naming Convention:
This dataset merges two CSVs with the same 13 trait columns. After merging:
- **_x** suffix = value from the quality/phenotyping CSV
- **_y** suffix = value from the agronomic averages CSV (averaged across 3 timepoints)
For example: GEBV_yield_x (quality CSV) and GEBV_yield_y (agronomic average CSV).
When a user asks for a trait without specifying, prefer the **_y** (averaged) variant.

## Guidelines:
- When users mention traits by common names or synonyms, match them to the correct GEBV trait name
- Explain what each trait means and which variant (_x or _y) you're using when adjusting sliders
- You can adjust multiple sliders in one response if the user requests multiple traits
- The app will automatically update after you adjust sliders"""

            if context:
                system_prompt += f"\n\nCurrent context:\n{context}"

            messages = [{"role": "user", "content": user_message}]

            while True:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1024,
                    system=system_prompt,
                    tools=claude_tools,
                    messages=messages
                )

                if response.stop_reason == "tool_use":
                    assistant_content = response.content
                    tool_results = []

                    for block in assistant_content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_input = block.input
                            tool_use_id = block.id

                            try:
                                result = await session.call_tool(tool_name, tool_input)
                                tool_result_content = result.content[0].text if result.content else "Tool executed successfully"
                            except Exception as e:
                                tool_result_content = f"Error executing tool: {str(e)}"

                            tool_calls.append({
                                "tool": tool_name,
                                "input": tool_input,
                                "result": tool_result_content
                            })

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": tool_result_content
                            })

                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results})

                else:
                    for block in response.content:
                        if hasattr(block, 'text'):
                            final_response += block.text
                    break

    return {
        "response": final_response,
        "tool_calls": tool_calls
    }


def chat_with_mcp(user_message: str, context: str = "") -> dict:
    """
    Synchronous wrapper for run_mcp_chat.
    Use this from Streamlit or other sync code.
    """
    return asyncio.run(run_mcp_chat(user_message, context))


if __name__ == "__main__":
    print("Testing Global MCP Chat...")
    result = chat_with_mcp("What traits are available?")
    print(f"Response: {result['response']}")
    print(f"Tool calls: {result['tool_calls']}")
