#!/usr/bin/env python3
"""
MCP Chat Module for GEBV Explorer
Connects to the GEBV MCP server and uses Claude API with tool use.
"""

import os
import sys
import asyncio
import json
import platform
from contextlib import asynccontextmanager
from dotenv import load_dotenv

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import anthropic
import pandas as pd
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_SERVER_SCRIPT = os.path.join(BASE_DIR, "gebv_mcp_server.py")
PYTHON_PATH = sys.executable
TRAIT_METADATA_PATH = os.path.join(BASE_DIR, "data", "Trait_Metadata_with_Synonyms.xlsx")


def load_trait_metadata() -> str:
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


TRAIT_METADATA = load_trait_metadata()


def convert_mcp_tools_to_claude(mcp_tools) -> list:
    return [
        {"name": tool.name, "description": tool.description or "", "input_schema": tool.inputSchema}
        for tool in mcp_tools.tools
    ]


async def run_mcp_chat(user_message: str, context: str = "", api_key: str = None) -> dict:
    effective_key = api_key or ANTHROPIC_API_KEY
    if not effective_key:
        return {
            "response": "No API key provided. Enter your Anthropic API key in the sidebar to use this feature.",
            "tool_calls": []
        }

    server_params = StdioServerParameters(command=PYTHON_PATH, args=[MCP_SERVER_SCRIPT])
    tool_calls = []
    final_response = ""

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = await session.list_tools()
            claude_tools = convert_mcp_tools_to_claude(mcp_tools)
            client = anthropic.Anthropic(api_key=effective_key)

            system_prompt = f"""You are an assistant for the GEBV Explorer application, which visualizes genomic estimated breeding values (GEBVs) for pepper/Capsicum crop traits.

## Available GEBV Traits and Their Meanings:
{TRAIT_METADATA}

## Tools Available:

### Slider tools (hard AND filters — lines must pass every threshold):
1. **adjust_slider** - Adjust a trait slider by percentile range (0-100)
2. **get_available_traits** - List all available GEBV trait names
3. **reset_all_sliders** - Reset ALL sliders to full range (removes all filters)
4. **get_current_filters** - See which filters are currently active

### Ranking index tools (soft ranking — all lines scored and ranked):
5. **compute_genomic_selection_index** - Rank lines using an accuracy-adjusted genomic selection index.
   Uses b = (RGR)⁻¹(RGa) where G is the GEBV covariance matrix, R is a diagonal matrix of
   trait prediction accuracies, and a is the vector of economic weights.
   This is NOT the classic Smith-Hazel equation — it was modified to avoid collinearity
   issues that arise when using training GEBVs and phenotypic data together.
   Takes trait_weights (e.g. {{"GEBV_yield": 2.0, "GEBV_Brix": 1.0}}) and optional top_n.
   Requires at least 2 traits. The page will update automatically.

6. **compute_selection_index** - Rank lines using a simpler weighted linear index.
   Scores lines as I = Σ(wⱼ × zᵢⱼ) where zᵢⱼ is the z-score of trait j for line i.
   Treats traits as independent (no covariance or accuracy adjustment).
   Takes trait_weights and optional top_n. The page will update automatically.

## When to use which tool:
- Use **sliders** when the user wants to filter/exclude lines (hard cutoffs)
- Use **compute_genomic_selection_index** when the user wants a ranking that accounts for
  genetic covariance between traits and unequal prediction accuracies
- Use **compute_selection_index** when the user wants a simple, transparent weighted ranking
- You can use BOTH index methods to compare results, or combine with sliders

## How Percentiles Work (for sliders):
- "top 10%" = start_percent=90, end_percent=100 (highest values)
- "bottom 20%" = start_percent=0, end_percent=20 (lowest values)
- "middle 50%" = start_percent=25, end_percent=75

## IMPORTANT - Filter Management:
- **ALWAYS call reset_all_sliders FIRST** before setting any new filters.
- Then adjust only the sliders the user specifically requested.

## Guidelines:
- When users mention traits by common names or synonyms, match them to the correct GEBV trait name
- For example: "spicy" or "heat" refers to GEBV_Fruit_pungency, "sugar content" refers to GEBV_Brix
- The app will automatically update after you adjust sliders or compute an index
- When computing an index, explain what method was used and what the weights mean"""

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
                            try:
                                result = await session.call_tool(block.name, block.input)
                                tool_result_content = result.content[0].text if result.content else "Tool executed successfully"
                            except Exception as e:
                                tool_result_content = f"Error executing tool: {str(e)}"

                            tool_calls.append({
                                "tool": block.name,
                                "input": block.input,
                                "result": tool_result_content
                            })
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": tool_result_content
                            })

                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results})

                else:
                    for block in response.content:
                        if hasattr(block, 'text'):
                            final_response += block.text
                    break

    return {"response": final_response, "tool_calls": tool_calls}


def chat_with_mcp(user_message: str, context: str = "", api_key: str = None) -> dict:
    """Synchronous wrapper for run_mcp_chat."""
    import threading

    result = {}
    exception_holder = []

    def run_in_thread():
        if platform.system() == "Windows":
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result.update(loop.run_until_complete(run_mcp_chat(user_message, context, api_key)))
        except Exception as e:
            exception_holder.append(e)
        finally:
            loop.close()

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join()

    if exception_holder:
        raise exception_holder[0]
    return result


if __name__ == "__main__":
    print("Testing MCP Chat...")
    result = chat_with_mcp("What traits are available?")
    print(f"Response: {result['response']}")
    print(f"Tool calls: {result['tool_calls']}")
