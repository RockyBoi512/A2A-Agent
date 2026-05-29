# ══════════════════════════════════════════════════════════════════════════
#  LangChain Tools — MILP Engine wrapped for the agent
# ══════════════════════════════════════════════════════════════════════════

import pandas as pd
from typing import Optional
from langchain_core.tools import tool

from .engine import (
    clean_dataframe, calculate_scores,
    run_full_engine, compute_willingness_recommendations, display_client_id,
    REGION_LABELS,
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
    lines = ["## Regional Capacity Overview\n"]
    lines.append("| Region | Active | Total | Capacity | Avg Score |")
    lines.append("|---|---|---|---|---|")

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
    lines = [f"## Top {len(top)} Consultants by Score\n"]
    lines.append("| # | Consultant | Region | Score | Rating | Available Slots | Current Load |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        lines.append(
            f"| {i} | {r['Consultant']} | {r['Region']} | {r['Final_Score']} | "
            f"{r['Rating']} | {int(r['Can_Take'])} | {int(r['Current_Clients'])} |"
        )
    return "\n".join(lines)


@tool
def run_assignment(customer_data: dict, cross_region_pcts: Optional[dict] = None) -> str:
    """Run the MILP optimization to assign customers to consultants.
    Input: customer_data dict with region keys (APJ, MEE, EMEA, GC, LAC, NA) and lists of customer ID strings.
    Optional: cross_region_pcts dict e.g. {"MEE": 20, "EMEA": 0, "NA": 10, "LAC": 0} — % of customers to redirect to APJ.
    Example: {"APJ": ["C001", "C002"], "NA": ["C003"], "EMEA": [], "MEE": [], "GC": [], "LAC": []}
    Use when user wants to run assignment, optimize, or allocate customers."""
    if store.df_scored is None:
        return "No consultant data loaded. Please provide consultant data first."

    cust_data = {k.upper(): [str(v) for v in vals] for k, vals in customer_data.items()}
    cross_pcts = {}
    if cross_region_pcts:
        cross_pcts = {k.upper(): int(v) for k, v in cross_region_pcts.items() if int(v) > 0}

    valid_regions = set(REGION_LABELS.keys())
    for region in cust_data:
        if region not in valid_regions:
            return f"Unknown region '{region}'. Valid: {', '.join(sorted(valid_regions))}"

    total_customers = sum(len(v) for v in cust_data.values())
    if total_customers == 0:
        return "No customers to assign. Add customer IDs to the region arrays."

    df = store.df.copy()
    result = run_full_engine(df, cust_data, cross_region_pcts=cross_pcts)

    assignments        = result['assignments']
    total_assigned     = result['total_assigned']
    scores             = result['score']
    region_map         = dict(zip(result['df']['Consultant'], result['df']['Region']))
    unassignable_count = result['unassignable_count']
    df                 = result['df']

    lines = [f"**Assignment Complete — {total_assigned}/{total_customers} Customers Assigned**\n"]
    if unassignable_count > 0:
        lines.append(f"> Warning: {unassignable_count} customers could not be assigned "
                     f"(no consultants in their region).\n")

    rows = []
    assigned_primaries = set()
    for consultant, cls in assignments.items():
        if not cls:
            continue
        region = region_map.get(consultant, '?')
        score = scores.get(consultant, 0)
        cons_row = df[df['Consultant'] == consultant]
        rating = cons_row['Rating'].values[0] if not cons_row.empty else '?'
        assigned_primaries.add(consultant)
        for cid in cls:
            rows.append({
                'consultant': consultant,
                'region': region,
                'score': score,
                'rating': rating,
                'customer': display_client_id(cid),
            })

    rows.sort(key=lambda x: -x['score'])

    lines.append("| Consultant | Region | Score | Rating | Customer |")
    lines.append("|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['consultant']} | {r['region']} | {r['score']}% | {r['rating']} | {r['customer']} |"
        )

    # ── Regional Backup Consultants (top 5 per region, excluding primaries) ──
    lines.append("\n---\n")
    lines.append("### Regional Backup Consultants\n")

    assigned_regions = sorted(set(r['region'] for r in rows))
    for region in assigned_regions:
        region_df = df[(df['Region'] == region) & (df['Is_Available'] == 1)]
        region_df_sorted = region_df.sort_values('Final_Score', ascending=False)
        backups = region_df_sorted[~region_df_sorted['Consultant'].isin(assigned_primaries)].head(5)

        lines.append(f"\n**{region}**")
        if backups.empty:
            lines.append("No backup consultants available.")
            continue
        lines.append("| # | Consultant | Score | Rating | Available Slots |")
        lines.append("|---|---|---|---|---|")
        for rank, (_, row) in enumerate(backups.iterrows(), 1):
            lines.append(
                f"| {rank} | {row['Consultant']} | {row['Final_Score']}% | "
                f"{row['Rating']} | {int(row['Can_Take'])} |"
            )

    store.last_assignment = {
        'assignments': assignments,
        'total_assigned': total_assigned,
        'total_customers': total_customers,
    }

    return "\n".join(lines)


@tool
def explain_scoring() -> str:
    """Explain the MILP scoring methodology and weights. Use when user asks
    how scoring works, what factors matter, or how consultants are rated."""
    return """## Scoring Methodology

The MILP engine scores consultants using a weighted composite (0-100 scale):

| Factor | Weight | Scale |
|---|---|---|
| Bandwidth (available slots) | 30% | 1-5 based on Can_Take |
| UTR (Update Tool Regularly) | 30% | Binary (Yes=1, No=0) |
| Willingness to take customers | 10% | Binary (Yes=1, No=0) |
| COMS (completed customers experience) | 10% | 1-5 based on count |
| Feedback (net positive - negative) | 10% | 1-5 based on net score |
| Attendance (meeting regularity) | 10% | Binary (Yes=1, No=0) |

**Ratings:**
- Outstanding: 75+
- Exceeds Expectations: 60-74
- Meets Expectations: 45-59
- Needs Improvement: 30-44
- Critical: Below 30

**Two-phase assignment:**
1. Phase 1: Assigns to willing consultants (Willingness=1)
2. Phase 2: Falls back to unwilling but active consultants for remaining demand

**Constraints:** Max 25 customers per consultant. Region matching enforced.
**Regions:** APJ, MEE, EMEA, GC, LAC, NA."""


# ── Tool Registry ─────────────────────────────────────────────────────

ALL_TOOLS = [
    load_consultant_data,
    get_capacity_overview,
    lookup_consultant,
    get_top_consultants,
    run_assignment,
    explain_scoring,
]
