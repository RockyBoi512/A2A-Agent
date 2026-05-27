# ══════════════════════════════════════════════════════════════════════════
#  CONSULTANT MILP ENGINE — Business Logic Module
#  Extracted from Tkinter app for Streamlit deployment
# ══════════════════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import math
from pulp import *
import warnings
warnings.filterwarnings('ignore')

MAX_CAPACITY = 25  # global hard cap

REGION_LABELS = {
    'APJ':  'APJ',
    'MEE':  'MEE',
    'EMEA': 'EMEA',
    'GC':   'GC',
    'LAC':  'LAC',
    'NA':   'NA',
}


def display_client_id(cid):
    """Strip the internal '{region}|' prefix added for uniqueness."""
    return cid.split('|', 1)[1] if '|' in cid else cid


# ══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════

def safe_name(c):
    return str(c).strip().replace(' ', '_').replace('.', '').replace('(', '').replace(')', '')


def clean_pct(val):
    if isinstance(val, str):
        val = val.strip()
        if '%' in val:
            try:
                return float(val.replace('%', '').strip())
            except:
                return 0.0
        if val in ['#DIV/0!', '#VALUE!', '#N/A', '#REF!', '', '-']:
            return 0.0
        try:
            return float(val)
        except:
            return 0.0
    if pd.isna(val):
        return 0.0
    try:
        f = float(val)
        return f * 100 if 0 < f <= 1 else f
    except:
        return 0.0


# ══════════════════════════════════════════════════════════════════════════
#  DATA CLEANING
# ══════════════════════════════════════════════════════════════════════════

def clean_dataframe(raw_df):
    df = raw_df.copy()
    df.columns = [str(c).replace('\n', '').replace('\r', '').strip() for c in df.columns]

    rename_map = {
        'Monthly Capacity':                              'Total_Capacity',
        'Current Workload':                              'Current_Clients',
        'WT(Willingness to take)':                       'Willingness',
        'COMS(Customers completed from day 1)':          'COMS',
        'Experience(Customers completed from day 1)':    'COMS',
        'Positive':                                      'Positive_Feedback',
        'Nuetral':                                       'Neutral_Feedback',
        'Neutral':                                       'Neutral_Feedback',
        'Negative':                                      'Negative_Feedback',
        'MA(Meeting Attendence)':                        'Attendance_Binary',
        'Attending Meeting regularly':                   'Attendance_Binary',
        'Meeting':                                       'Attendance_Binary',
        'UTR':                                           'UTR_Binary',
        'Update tool regularly':                         'UTR_Binary',
        'Intake Monthly':                                'Can_Take_Raw',
    }

    for old, new in rename_map.items():
        if old in df.columns:
            df = df.rename(columns={old: new})

    required = ['Consultant', 'Status', 'FTE', 'Region', 'Total_Capacity', 'Current_Clients',
                'Bandwidth_Pct', 'Willingness', 'COMS', 'UTR_Binary', 'Positive_Feedback',
                'Negative_Feedback', 'Attendance_Binary', 'Prev_Workload']
    for col in required:
        if col not in df.columns:
            df[col] = 0

    def to_binary(val):
        if isinstance(val, str):
            return 1 if val.strip().lower() in ('yes', 'y', '1', 'true') else 0
        try:
            return 1 if float(val) >= 1 else 0
        except:
            return 0

    df['UTR_Binary'] = df['UTR_Binary'].apply(to_binary)
    df['Attendance_Binary'] = df['Attendance_Binary'].apply(to_binary)
    df['Willingness'] = df['Willingness'].apply(to_binary)

    df['Status'] = df['Status'].astype(str).str.strip().str.title()
    df['Status'] = df['Status'].replace({
        'Opted Out': 'Opted Out', 'Opted out': 'Opted Out',
        'On Hold': 'On Hold', 'On hold': 'On Hold',
        'Under Training': 'Under Training', 'Under Train': 'Under Training'
    })
    df['Region'] = df['Region'].fillna('').astype(str).str.strip().str.upper()
    df['Region'] = df['Region'].replace({'NAN': '', 'NONE': ''})

    for col in ['FTE', 'Total_Capacity', 'Current_Clients',
                'COMS', 'Positive_Feedback', 'Negative_Feedback',
                'Prev_Workload']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(float)

    df = df.loc[:, df.columns.notna()]
    df = df[(df['FTE'] > 0) & (df['Total_Capacity'] > 0)].reset_index(drop=True)

    df['Total_Capacity'] = df['Total_Capacity'].astype(int)
    df['Current_Clients'] = df['Current_Clients'].astype(int)
    df['Prev_Workload'] = df['Current_Clients']
    df['Max_Capacity'] = df['Total_Capacity']
    df['Can_Take_Raw'] = np.minimum(MAX_CAPACITY - df['Current_Clients'], df['Total_Capacity']).clip(lower=0)
    df['Bandwidth_Pct'] = df['Can_Take_Raw']
    df['Is_Available'] = ((df['Status'] == 'Active') & (df['Willingness'] == 1)).astype(int)
    df['Can_Take'] = df['Can_Take_Raw'] * df['Is_Available']

    overloaded = df['Current_Clients'] >= MAX_CAPACITY
    df.loc[overloaded, 'Is_Available'] = 0
    df.loc[overloaded, 'Can_Take'] = 0
    df.loc[overloaded, 'Can_Take_Raw'] = 0

    if 'Training_Start_Date' not in df.columns:
        df['Training_Start_Date'] = None

    return df


# ══════════════════════════════════════════════════════════════════════════
#  SCORING
# ══════════════════════════════════════════════════════════════════════════

def calculate_scores(df):
    weights = {'Bandwidth': 0.30, 'Willingness': 0.10, 'COMS': 0.10,
               'UTR': 0.30, 'Feedback': 0.10, 'Attendance': 0.10}

    df['S_Bandwidth'] = df['Can_Take_Raw'].apply(
        lambda x: 5 if x >= 12 else 4 if x >= 8 else 3 if x >= 5 else 2 if x >= 2 else 1 if x > 0 else 0)
    df['S_Willingness'] = df['Willingness'].apply(lambda x: 5 if x == 1 else 1)
    df['S_COMS'] = df['COMS'].apply(
        lambda x: 5 if x >= 15 else 4 if x >= 12 else 3 if x >= 9 else 2 if x >= 5 else 1)

    df['Net_Feedback'] = df['Positive_Feedback'] - df['Negative_Feedback']
    df['S_Feedback'] = df['Net_Feedback'].apply(
        lambda x: 5 if x >= 3 else 4 if x >= 2 else 3 if x >= 1 else 2 if x >= -1 else 1)

    df['Final_Score'] = (
        (df['S_Bandwidth'] / 5 * weights['Bandwidth']) +
        (df['S_Willingness'] / 5 * weights['Willingness']) +
        (df['S_COMS'] / 5 * weights['COMS']) +
        (df['S_Feedback'] / 5 * weights['Feedback']) +
        (df['UTR_Binary'] * weights['UTR']) +
        (df['Attendance_Binary'] * weights['Attendance'])
    ) * 100
    df['Final_Score'] = df['Final_Score'].round(1)

    df['Rating'] = df['Final_Score'].apply(
        lambda s: "Outstanding" if s >= 75 else "Exceeds" if s >= 60
        else "Meets" if s >= 45 else "Needs Improvement" if s >= 30 else "Critical")

    return df, weights


# ══════════════════════════════════════════════════════════════════════════
#  MILP OPTIMIZATION — TWO-PHASE
# ══════════════════════════════════════════════════════════════════════════

def _run_single_milp(active_cons, assignable_clients, client_regions,
                     can_take, score, region_map,
                     all_consultants, existing_assignments, region_groups=None,
                     label="", objective_score=None):
    if region_groups is None:
        region_groups = {}

    already = {c: len(existing_assignments.get(c, [])) for c in all_consultants}
    eff_can_take = {c: max(0, can_take[c] - already[c]) for c in active_cons}

    valid_cons = [c for c in active_cons if eff_can_take[c] > 0]
    if not valid_cons or not assignable_clients:
        return {}

    client_region_to_cons = {}
    for c in valid_cons:
        cr = region_map[c]
        client_region_to_cons.setdefault(cr, []).append(c)
        for combined_key, sub_set in region_groups.items():
            if cr in sub_set:
                client_region_to_cons.setdefault(combined_key, []).append(c)

    this_assignable = [cl for cl in assignable_clients
                       if client_regions[cl] in client_region_to_cons]
    if not this_assignable:
        return {}

    model = LpProblem(f"Assignment_{label}", LpMaximize)
    valid_set = set((c, cl) for c in valid_cons for cl in this_assignable
                    if c in client_region_to_cons.get(client_regions[cl], []))
    valid_pairs = list(valid_set)
    if not valid_pairs:
        return {}

    x = LpVariable.dicts(f"x{label}", valid_pairs, cat='Binary')

    obj_score = objective_score if objective_score is not None else score
    model += lpSum(obj_score[c] * x[(c, cl)] for (c, cl) in valid_pairs)

    for cl in this_assignable:
        mc = [c for c in valid_cons if (c, cl) in valid_set]
        if mc:
            model += lpSum(x[(c, cl)] for c in mc) <= 1, f"One_{safe_name(cl)}_{label}"

    for c in valid_cons:
        cc = [cl for cl in this_assignable if (c, cl) in valid_set]
        if cc:
            model += lpSum(x[(c, cl)] for cl in cc) <= eff_can_take[c], \
                     f"Cap_{safe_name(c)}_{label}"

    def _rating_weight(c):
        s = score[c]
        return 4 if s >= 75 else 3 if s >= 60 else 2 if s >= 45 else 1

    for client_reg in set(client_regions[cl] for cl in this_assignable):
        region_clients = [cl for cl in this_assignable if client_regions[cl] == client_reg]
        actual_demand = len(region_clients)
        region_cons_w = [c for c in client_region_to_cons.get(client_reg, [])
                         if eff_can_take[c] > 0]
        n = len(region_cons_w)
        if n == 0 or actual_demand == 0:
            continue

        total_w = sum(_rating_weight(c) for c in region_cons_w)
        mins = {}
        caps = {}
        for c in region_cons_w:
            raw = actual_demand * _rating_weight(c) / total_w
            remaining = eff_can_take[c]
            base = max(1, int(raw)) if actual_demand >= n else int(raw)
            mins[c] = min(base, eff_can_take[c], remaining)
            caps[c] = min(math.ceil(raw), eff_can_take[c], remaining)

        total_min = sum(mins.values())
        if total_min > actual_demand:
            for c in sorted(region_cons_w, key=lambda c: score[c]):
                if total_min <= actual_demand:
                    break
                cut = min(mins[c], total_min - actual_demand)
                mins[c] -= cut
                total_min -= cut

        for c in region_cons_w:
            cc = [cl for cl in this_assignable if (c, cl) in valid_set]
            if not cc:
                continue
            actual_min = min(mins.get(c, 0), len(cc))
            if actual_min > 0:
                model += lpSum(x[(c, cl)] for cl in cc) >= actual_min, \
                         f"Base_{safe_name(c)}_{label}"
            actual_cap = min(caps.get(c, actual_demand), len(cc))
            if actual_cap < len(cc):
                model += lpSum(x[(c, cl)] for cl in cc) <= actual_cap, \
                         f"Cap_W_{safe_name(c)}_{label}"

    model.solve(PULP_CBC_CMD(msg=0))

    result = {}
    if model.status == 1:
        for (c, cl) in valid_pairs:
            if x[(c, cl)].varValue and x[(c, cl)].varValue > 0.5:
                result.setdefault(c, []).append(cl)
    return result


def run_milp_optimization(df, client_demand, customer_data=None):
    consultants = df['Consultant'].tolist()
    can_take = dict(zip(df['Consultant'], df['Can_Take']))
    score = dict(zip(df['Consultant'], df['Final_Score']))
    current = dict(zip(df['Consultant'], df['Current_Clients'].astype(int)))
    max_90 = dict(zip(df['Consultant'], df['Max_Capacity']))
    region_map = dict(zip(df['Consultant'], df['Region']))

    prev_workload = dict(zip(df['Consultant'], df['Prev_Workload'].astype(int)))
    effective_score = {c: score[c] + max(0, 25 - prev_workload.get(c, 0)) * 2
                       for c in score}

    tier1 = df[(df['Is_Available'] == 1)]['Consultant'].tolist()

    fallback_df = df[(df['Status'] == 'Active') & (df['Willingness'] == 0)].copy()
    tier2 = fallback_df['Consultant'].tolist()
    can_take_full = dict(zip(df['Consultant'], df['Can_Take']))
    for c in tier2:
        can_take_full[c] = int(df.loc[df['Consultant'] == c, 'Can_Take_Raw'].values[0])

    clients, client_regions = [], {}
    if customer_data:
        for region_key, ids in customer_data.items():
            for cid in ids:
                internal_cid = f"{region_key}|{cid}"
                clients.append(internal_cid)
                client_regions[internal_cid] = region_key
    else:
        for region, count in client_demand.items():
            for i in range(count):
                cl = f'{region}_Cl{i+1}'
                clients.append(cl)
                client_regions[cl] = region

    all_active_regions = set(region_map[c] for c in tier1 + tier2)
    assignable_clients = [cl for cl in clients if client_regions[cl] in all_active_regions]
    unassignable_clients = [cl for cl in clients if cl not in assignable_clients]

    assignments = {c: [] for c in consultants}

    if not assignable_clients:
        return (None, assignments, clients, 0, tier1,
                score, current, can_take, max_90, region_map,
                len(unassignable_clients), [], client_regions)

    # PHASE 1 — Willing=1
    tier1_regions = set(region_map[c] for c in tier1)
    p1_clients = [cl for cl in assignable_clients if client_regions[cl] in tier1_regions]

    p1_result = _run_single_milp(
        tier1, p1_clients, client_regions,
        can_take, score, region_map,
        consultants, {}, label="P1",
        objective_score=effective_score
    )
    for c, cls in p1_result.items():
        assignments[c].extend(cls)

    # PHASE 2 — Fallback Willing=0
    assigned_set = set(cl for cls in assignments.values() for cl in cls)
    unmet_clients = [cl for cl in assignable_clients if cl not in assigned_set]

    if unmet_clients and tier2:
        unmet_regions = set(client_regions[cl] for cl in unmet_clients)
        tier2_active = [c for c in tier2 if region_map[c] in unmet_regions]

        if tier2_active:
            p2_result = _run_single_milp(
                tier2_active, unmet_clients, client_regions,
                can_take_full, score, region_map,
                consultants, assignments, label="P2",
                objective_score=effective_score
            )
            for c, cls in p2_result.items():
                assignments[c].extend(cls)

    total_assigned = sum(len(v) for v in assignments.values())
    active_consultants = tier1 + [c for c in tier2
                                   if len(assignments.get(c, [])) > 0]

    return (True if total_assigned > 0 else None,
            assignments, clients, total_assigned, active_consultants,
            score, current, can_take_full, max_90, region_map,
            len(unassignable_clients), [], client_regions)


# ══════════════════════════════════════════════════════════════════════════
#  WILLINGNESS ADVISOR
# ══════════════════════════════════════════════════════════════════════════

def compute_willingness_recommendations(df, client_demand, regional_status):
    recs = {}
    for region_key, info in regional_status.items():
        if info['gap'] >= 0:
            continue
        deficit = abs(info['gap'])
        candidates = df[
            (df['Region'] == region_key) &
            (df['Status'] == 'Active') &
            (df['Willingness'] == 0)
        ].copy()
        candidates = candidates.sort_values('Final_Score', ascending=False)
        rows = []
        cumulative = 0
        for _, r in candidates.iterrows():
            slots = int(r['Can_Take_Raw'])
            if slots == 0:
                continue
            cumulative += slots
            rows.append({
                'name': str(r['Consultant']),
                'score': r['Final_Score'],
                'rating': r['Rating'],
                'slots': slots,
                'cumulative': cumulative,
                'covers': cumulative >= deficit,
                'current': int(r['Current_Clients']),
                'max_cap': int(r['Max_Capacity']),
            })
        recs[region_key] = {'deficit': deficit, 'candidates': rows}
    return recs


def compute_backup_recommendations(df_sorted, assignments, client_regions, n=3):
    client_to_primary = {cl: cons for cons, cls in assignments.items() for cl in cls}

    region_pool = {}
    for _, r in df_sorted.iterrows():
        if r['Is_Available'] == 1 and r['Can_Take'] > 0:
            region_pool.setdefault(r['Region'], []).append(r['Consultant'])

    backups = {}
    for cl, primary in client_to_primary.items():
        region = client_regions.get(cl, '')
        candidates = [c for c in region_pool.get(region, []) if c != primary]
        backups[cl] = candidates[:n]
    return backups


# ══════════════════════════════════════════════════════════════════════════
#  CROSS-REGION REDISTRIBUTION
# ══════════════════════════════════════════════════════════════════════════

def apply_cross_region(customer_data, cross_region_pcts):
    """
    For MEE, EMEA, NA, LAC: move the first int(n * pct/100) clients into the APJ pool.
    cross_region_pcts: dict {region: pct_int}
    Returns (modified_customer_data, cross_moved)
    """
    modified = {k: list(v) for k, v in customer_data.items()}
    apj_extras = []
    cross_moved = {}
    for region in ('MEE', 'EMEA', 'NA', 'LAC'):
        if region not in modified or region not in cross_region_pcts:
            continue
        pct = cross_region_pcts.get(region, 0)
        if pct <= 0:
            continue
        ids = modified[region]
        if len(ids) <= 5:
            continue
        # Tiered mapping: 5–14% → 1, 15–24% → 2, 25–34% → 3, … (every 10-point band = 1 customer)
        n_cross = min(int((pct + 5) / 10), len(ids)) if pct >= 5 else 0
        if n_cross <= 0:
            continue
        for cid in ids[:n_cross]:
            cross_moved[cid] = region
        apj_extras.extend(ids[:n_cross])
        modified[region] = ids[n_cross:]
        if not modified[region]:
            del modified[region]
    if apj_extras:
        modified['APJ'] = list(modified.get('APJ', [])) + apj_extras
    return modified, cross_moved


# ══════════════════════════════════════════════════════════════════════════
#  FULL ENGINE RUNNER
# ══════════════════════════════════════════════════════════════════════════

def run_full_engine(df_raw, customer_data, cross_region_pcts=None):
    """
    Main entry point. Takes raw dataframe and customer data dict.
    Returns a results dict with all data needed for display.
    """
    if cross_region_pcts is None:
        cross_region_pcts = {}

    df = clean_dataframe(df_raw)
    df, weights = calculate_scores(df)
    df_sorted = df.sort_values('Final_Score', ascending=False).reset_index(drop=True)

    customer_data, cross_moved = apply_cross_region(customer_data, cross_region_pcts)
    client_demand = {r: len(ids) for r, ids in customer_data.items()}
    NEW_CLIENTS = sum(client_demand.values())

    # Demand-Supply
    regional_status = {}
    for region_key, demand in client_demand.items():
        avail = df[(df['Region'] == region_key) & (df['Is_Available'] == 1)]
        supply = int(avail['Can_Take'].sum())
        gap = supply - demand
        status = "OK" if gap >= 0 else "TIGHT" if gap >= -3 else "DEFICIT"
        regional_status[region_key] = {
            'demand': demand, 'supply': supply, 'gap': gap, 'status': status,
            'available_consultants': avail['Consultant'].tolist()
        }

    total_supply = int(df['Can_Take'].sum())
    total_demand = NEW_CLIENTS
    gap_total = total_supply - total_demand
    ds_ratio = (total_demand / total_supply * 100) if total_supply > 0 else float('inf')

    # MILP
    result = run_milp_optimization(df, client_demand, customer_data)
    (model_ok, assignments, clients, total_assigned, active_consultants,
     score, current, can_take, max_90, region_map,
     unassignable_count, _, client_regions) = result

    milp_status = "Optimal" if total_assigned > 0 else "No Solution"
    obj_val = float(sum(score.get(c, 0) * len(v) for c, v in assignments.items()))

    # Willingness Advisor
    will_recs = compute_willingness_recommendations(df_sorted, client_demand, regional_status)
    backup_recs = compute_backup_recommendations(df_sorted, assignments, client_regions)

    return {
        'df': df,
        'df_sorted': df_sorted,
        'weights': weights,
        'assignments': assignments,
        'client_demand': client_demand,
        'client_regions': client_regions,
        'cross_moved': cross_moved,
        'backup_recs': backup_recs,
        'regional_status': regional_status,
        'total_supply': total_supply,
        'total_demand': total_demand,
        'gap_total': gap_total,
        'ds_ratio': ds_ratio,
        'total_assigned': total_assigned,
        'new_clients': NEW_CLIENTS,
        'unassignable_count': unassignable_count,
        'obj_val': obj_val,
        'milp_status': milp_status,
        'will_recs': will_recs,
        'active_consultants': active_consultants,
        'score': score,
    }
