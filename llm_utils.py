import os
import json
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

# Load API key from .env
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY not set in .env or environment.")

# Initialize OpenAI client
client = OpenAI(api_key=api_key)

# Compact schema function
def _summarize_schema(df: pd.DataFrame, max_cols: int = 40) -> str:
    """
    Compact JSON schema: only column names, dtypes, and up to 12 'Group' values.
    """
    keep = []
    if "Line" in df.columns:
        keep.append("Line")
    if "Group" in df.columns:
        keep.append("Group")
    trait_cols = [c for c in df.columns if c.startswith("GEBV_")]
    keep.extend(trait_cols[:max_cols])

    dtypes = {}
    for c in keep:
        if pd.api.types.is_numeric_dtype(df[c]):
            dtypes[c] = "number"
        elif c == "Group":
            dtypes[c] = "category"
        else:
            dtypes[c] = "string"

    categories = {}
    if "Group" in df.columns:
        categories["Group"] = df["Group"].dropna().astype(str).unique().tolist()[:12]

    return json.dumps(
        {"columns": keep, "dtypes": dtypes, "categories": categories},
        separators=(",", ":")
    )

# Apply model's filter plan to the dataframe
def _apply_filters(df: pd.DataFrame, plan: dict) -> pd.DataFrame:
    out = df.copy()
    for f in plan.get("filters", []):
        col, op, val = f.get("column"), f.get("op"), f.get("value")
        if col not in out.columns:
            continue
        s = out[col]

        if op == "between" and isinstance(val, list) and len(val) == 2:
            lo, hi = val
            out = out[s.between(lo, hi)]
        elif op in (">", ">=", "<", "<="):
            try:
                val = float(val)
                if op == ">": out = out[s > val]
                if op == ">=": out = out[s >= val]
                if op == "<": out = out[s < val]
                if op == "<=": out = out[s <= val]
            except ValueError:
                continue
        elif op == "==":
            out = out[s == val]
        elif op == "!=":
            out = out[s != val]
        elif op == "contains":
            out = out[s.astype(str).str.contains(str(val), case=False, na=False)]
        elif op == "in" and isinstance(val, list):
            out = out[s.isin(val)]

    sort_spec = plan.get("sort")
    if sort_spec:
        by = sort_spec.get("by")
        asc = sort_spec.get("ascending", True)
        if by in out.columns:
            out = out.sort_values(by=by, ascending=asc)

    limit = plan.get("limit", 100)
    try:
        limit = int(limit)
    except Exception:
        limit = 100
    return out.head(limit)

# Main function called by Streamlit app
def ask_model(user_input: str, df: pd.DataFrame, model: str = "gpt-4o-mini") -> dict:
    """
    Returns a dict with:
      - 'answer': text answer from model
      - 'plan': parsed JSON plan
      - 'result_df': filtered DataFrame
    """
    schema_json = _summarize_schema(df)

    system_prompt = """You are a data query planner for a pandas DataFrame.
Given the schema and a user query, return ONLY JSON with:
{
  "answer": "<short text answer>",
  "filters": [
    {"column": "<name>", "op": "<==, !=, >, >=, <, <=, between, contains, in>", "value": "<single value or list>"}
  ],
  "select": ["optional","columns","to","show"],
  "limit": <int>,
  "sort": {"by": "<column>", "ascending": true}
}
Do not include any commentary or rows from the table itself.
"""

    user_prompt = f"SCHEMA (JSON):\n{schema_json}\n\nUSER QUERY:\n{user_input}"

    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=500,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    content = resp.choices[0].message.content.strip()
    try:
        plan = json.loads(content)
    except json.JSONDecodeError:
        plan = {"answer": "Could not parse model output.", "filters": [], "limit": 100}

    result_df = _apply_filters(df, plan)
    answer = plan.get("answer", "")
    return {"answer": answer, "plan": plan, "result_df": result_df}

