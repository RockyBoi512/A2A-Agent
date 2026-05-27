# ══════════════════════════════════════════════════════════════════════════
#  LangChain Tools — MILP Engine wrapped for the agent
# ══════════════════════════════════════════════════════════════════════════

import json
import pandas as pd
from typing import Optional
from langchain_core.tools import tool

from .engine import (
    clean_dataframe, calculate_scores, run_milp_optimization,
    compute_willingness_recommendations, display_client_id,
    MAX_CAPACITY, REGION_LABELS,
)

# ── Shared State ──────────────────────────────────────────────────────

class DataStore:
    """Singleton holding loaded consultant data."""
    df: Optional[pd.DataFrame] = None
    df_scored: Optional[pd.DataFrame] = None
    weights: Optional[dict] = None
    last_assignment: Optional[dict] = None

store = DataStore()


# ── Tools ──────────────────────────────────────────────────────────────

@tool
def load_consultant_data(csv_content: str) -> str:
    """Load consultant data from CSV content. Use this when the user provides
    consultant data as CSV text. Returns a summary of loaded data."""
    try:
        from io import StringIO
        raw_df = pd.read_csv(StringIO(csv_content), keep_default_na=False)
        df = clean_dataframe(raw_df)
        df_scored, weights = calculate_scores(df)
        store.df = df
        store.df_scored = df_scored
        store.weights = weights

        active = df_scored[df_scored['Is_Available'] == 1]
        return (
            f"Data loaded successfully.\n"
            f"- {len(df_scored)} consultants processed\n"
            f"- {len(active)} available (Active + Willing)\n"
            f"- {int(active['Can_Take'].sum())} total customer slots available\n"
            f"- Regions: {', '.join(sorted(df_scored['Region'].unique()))}"
        )
    except Exception as e:
        return f"Error loading data: {str(e)}"


@tool
def get_capacity_overview() -> str:
    """Get regional capacity overview showing available consultants and slots
    per region. Use when user asks about capacity, availability, or regional status."""
    if store.df_scored is None:
        return "No consultant data loaded. Please provide consultant data first."

    df = store.df_scored
    lines = ["Regional Capacity Overview:\n"]
    lines.append("| Region | Active | Total | Capacity | Avg Score |")
    lines.append("|--------|--------|-------|----------|-----------|")

    for region in sorted(REGION_LABELS.keys()):
        rdf = df[df['Region'] == region]
        active = rdf[rdf['Is_Available'] == 1]
        cap = int(active['Can_Take'].sum()) if len(active) > 0 else 0
        avg = round(active['Final_Score'].mean(), 1) if len(active) > 0 else 0
        lines.append(f"| {region} | {len(active)} | {len(rdf)} | {cap} | {avg} |")

    total_active = df[df['Is_Available'] == 1]
    lines.append(f"\nTotal: {len(total_active)} active consultants, "
                 f"{int(total_active['Can_Take'].sum())} slots available")
    return "\n".join(lines)


@tool
def lookup_consultant(name: str) -> str:
    """Look up a consultant by name (partial match). Returns their full profile
    including score, region, workload, and all metrics."""
    if store.df_scored is None:
        return "No consultant data loaded."

    df = store.df_scored
    matches = df[df['Consultant'].str.contains(name, case=False, na=False)]
    if matches.empty:
        return f"No consultant found matching '{name}'."

    results = []
    for _, r in matches.iterrows():
        results.append(
            f"**{r['Consultant']}**\n"
            f"- Region: {r['Region']}\n"
            f"- Status: {r['Status']}\n"
            f"- FTE: {r['FTE']}\n"
            f"- Score: {r['Final_Score']} ({r['Rating']})\n"
            f"- Workload: {int(r['Current_Clients'])}/{int(r['Max_Capacity'])}\n"
            f"- Available Slots: {int(r['Can_Take'])}\n"
            f"- Bandwidth Score: {r['S_Bandwidth']}/5\n"
            f"- Willingness: {'Yes' if r['Willingness'] == 1 else 'No'}\n"
            f"- COMS (Experience): {int(r['COMS'])} (Score: {r['S_COMS']}/5)\n"
            f"- UTR: {'Yes' if r['UTR_Binary'] == 1 else 'No'}\n"
            f"- Feedback (net): {int(r['Net_Feedback'])} (Score: {r['S_Feedback']}/5)\n"
            f"- Attendance: {'Yes' if r['Attendance_Binary'] == 1 else 'No'}"
        )
    return "\n\n".join(results)


@tool
def get_top_consultants(n: int = 10) -> str:
    """Get the top N consultants ranked by score. Use when user asks about
    best performers, top consultants, or rankings."""
    if store.df_scored is None:
        return "No consultant data loaded."

    df = store.df_scored
    top = df.nlargest(min(n, 20), 'Final_Score')
    lines = [f"Top {len(top)} Consultants by Score:\n"]
    lines.append("| # | Consultant | Region | Score | Rating | Available | Current |")
    lines.append("|---|-----------|--------|-------|--------|-----------|---------|")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        lines.append(
            f"| {i} | {r['Consultant']} | {r['Region']} | {r['Final_Score']} | "
            f"{r['Rating']} | {int(r['Can_Take'])} | {int(r['Current_Clients'])} |"
        )
    return "\n".join(lines)


@tool
def run_assignment(customer_data_json: str) -> str:
    """Run the MILP optimization to assign customers to consultants.
    Input: JSON string with region keys and customer ID arrays.
    Example: {"APJ": ["C001", "C002"], "NA": ["C003"], "EMEA": [], "MEE": [], "GC": [], "LAC": []}
    Use when user wants to run assignment, optimize, or allocate customers."""
    if store.df_scored is None:
        return "No consultant data loaded. Please provide consultant data first."

    try:
        cust_data = json.loads(customer_data_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}. Expected format: {{\"APJ\": [\"id1\"], \"NA\": [\"id2\"], ...}}"

    valid_regions = set(REGION_LABELS.keys())
    for region in cust_data:
        if region not in valid_regions:
            return f"Unknown region '{region}'. Valid: {', '.join(sorted(valid_regions))}"

    total_customers = sum(len(v) for v in cust_data.values())
    if total_customers == 0:
        return "No customers to assign. Add customer IDs to the region arrays."

    df = store.df_scored.copy()
    client_demand = {r: len(ids) for r, ids in cust_data.items()}
    result = run_milp_optimization(df, client_demand, customer_data=cust_data)

    (success, assignments, clients, total_assigned, active_cons,
     scores, current, can_take, max_90, region_map,
     unassignable_count, _, client_regions) = result

    store.last_assignment = {
        'assignments': assignments,
        'total_assigned': total_assigned,
        'total_customers': total_customers,
    }

    # Format output
    lines = [f"Assignment Results: {total_assigned}/{total_customers} customers assigned.\n"]
    if unassignable_count > 0:
        lines.append(f"Warning: {unassignable_count} customers could not be assigned "
                     f"(no consultants in their region).\n")

    region_assignments = {}
    for consultant, cls in assignments.items():
        if not cls:
            continue
        region = region_map.get(consultant, '?')
        if region not in region_assignments:
            region_assignments[region] = []
        region_assignments[region].append({
            'consultant': consultant,
            'customers': [display_client_id(c) for c in cls],
            'score': scores.get(consultant, 0),
            'new_workload': current.get(consultant, 0) + len(cls),
        })

    for region in sorted(region_assignments.keys()):
        lines.append(f"\n**{region}:**")
        lines.append("| Consultant | Assigned | Score | New Load |")
        lines.append("|-----------|----------|-------|----------|")
        for entry in sorted(region_assignments[region], key=lambda x: -x['score']):
            custs = ', '.join(entry['customers'][:5])
            if len(entry['customers']) > 5:
                custs += f" +{len(entry['customers'])-5} more"
            lines.append(f"| {entry['consultant']} | {custs} | {entry['score']} | {entry['new_workload']} |")

    return "\n".join(lines)


@tool
def explain_scoring() -> str:
    """Explain the MILP scoring methodology and weights. Use when user asks
    how scoring works, what factors matter, or how consultants are rated."""
    return """Scoring Methodology:

The MILP engine scores consultants using a weighted composite (0-100 scale):

| Factor | Weight | Scale |
|--------|--------|-------|
| Bandwidth (available slots) | 30% | 1-5 based on Can_Take |
| UTR (Update Tool Regularly) | 30% | Binary (Yes=1, No=0) |
| Willingness to take customers | 10% | Binary (Yes=1, No=0) |
| COMS (completed customers experience) | 10% | 1-5 based on count |
| Feedback (net positive - negative) | 10% | 1-5 based on net score |
| Attendance (meeting regularity) | 10% | Binary (Yes=1, No=0) |

Ratings:
- Outstanding: 75+
- Exceeds Expectations: 60-74
- Meets Expectations: 45-59
- Needs Improvement: 30-44
- Critical: Below 30

Two-phase assignment:
1. Phase 1: Assigns to willing consultants (Willingness=1)
2. Phase 2: Falls back to unwilling but active consultants for remaining demand

Constraints: Max 25 customers per consultant. Region matching enforced.
Regions: APJ, MEE, EMEA, GC, LAC, NA."""


# ── Tool Registry ─────────────────────────────────────────────────────

ALL_TOOLS = [
    load_consultant_data,
    get_capacity_overview,
    lookup_consultant,
    get_top_consultants,
    run_assignment,
    explain_scoring,
]
