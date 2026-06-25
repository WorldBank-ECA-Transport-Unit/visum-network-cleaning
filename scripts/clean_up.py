"""
================================================================================
VISUM NETWORK OVERLAP CLEANUP TOOL — STEP 1 of 2
================================================================================
Author:       The World Bank ECA Transport Unit Team
Version:      1.0
Date:         2026-05

PURPOSE
-------
Step 1 of 2 in the overlap cleanup workflow. Run this script OUTSIDE Visum.

Reads exported .att files from your spatial selection and identifies:
  1. Duplicate links  — Moldova and Romania links that represent the same
                        physical road segment (same OSM_WAY_ID AND same
                        FROM/TO coordinates within tolerance)
  2. Duplicate nodes  — Moldova and Romania nodes at the exact same
                        coordinates (within tolerance)

OUTPUTS
-------
  - spatial_selection_nodes_FLAGGED.att
      Same structure as input nodes file.
      OVERLAPPING_NODE column set to 1 for duplicate Moldova nodes.

  - spatial_selection_links_FLAGGED.att
      Same structure as input links file.
      OVERLAP_TOBE_DELETED column set to 1 for duplicate Moldova links.

  - nodes_to_delete.csv   — node numbers flagged for deletion
  - links_to_delete.csv   — link numbers flagged for deletion (with from/to)
  - cleanup_report.txt    — full analysis report

DUPLICATE DEFINITIONS
---------------------
  DUPLICATE LINK:
    A Moldova link is duplicate if ALL THREE are true:
      1. Same OSM_WAY_ID as a Romania link
      2. Same FROM coordinates (within MATCH_TOLERANCE metres)
      3. Same TO coordinates (within MATCH_TOLERANCE metres)

  DUPLICATE NODE:
    A Moldova node is duplicate if:
      1. Same coordinates as a Romania node (within MATCH_TOLERANCE metres)
      2. Identified as Moldova by node number (NO > MOLDOVA_NODE_MIN)

HOW TO USE
----------
  Step 1 — Export from Visum (same spatial selection for both):
    a. Make spatial selection around border overlap area
    b. Export nodes .att (include: NO, XCOORD, YCOORD, OVERLAPPING_NODE)
    c. Export links .att (include: NO, FROMNODENO, TONODENO,
       FROMNODE\XCOORD, FROMNODE\YCOORD, TONODE\XCOORD, TONODE\YCOORD,
       COUNTRY, OSM_WAY_ID, TSYSSET, OVERLAP_TOBE_DELETED)

  Step 2 — Configure CONFIGURATION section below

  Step 3 — Run outside Visum:
    python visum_overlap_cleanup.py

  Step 4 — Review cleanup_report.txt

  Step 5 — Run inside Visum:
    Scripts menu → Run Script → visum_delete.py

REUSE FOR OTHER COUNTRY PAIRS
------------------------------
  Only change the CONFIGURATION section.
  Examples:
    Ukraine + Poland:  BASE_COUNTRY="Poland",  SMALLER_COUNTRY="Ukraine"
    Georgia + Turkey:  BASE_COUNTRY="Turkey",  SMALLER_COUNTRY="Georgia"
    Moldova + Romania: BASE_COUNTRY="Romania", SMALLER_COUNTRY=""

NOTES
-----
  - Always keep backups of original .att files
  - Both .att files must be from the SAME spatial selection in Visum
  - Tested with Visum 2025 (version 15) .att format
================================================================================
"""

import os
import sys
from datetime import datetime
from collections import Counter


# ================================================================================
# CONFIGURATION — Edit this section for your specific use case
# ================================================================================

# Paths to your exported Visum .att files
NODE_FILE = r"D:\WorldBank\ECA Model\Scripts\Second Try\nodes.att"
LINK_FILE = r"D:\WorldBank\ECA Model\Scripts\Second Try\links.att"

# Base network country — as it appears in the COUNTRY attribute on links
# This network's nodes and links will be KEPT
BASE_COUNTRY = "Romania"

# Smaller network country — as it appears in the COUNTRY attribute on links
# This network's duplicate nodes and links will be flagged for DELETION
# Use "" (empty string) if the smaller network has a blank COUNTRY field
SMALLER_COUNTRY = ""

# Coordinate match tolerance in metres
# 1.0 = exact matches only (safest and recommended)
MATCH_TOLERANCE = 1.0

# Output folder — leave empty to save in same folder as this script
OUTPUT_DIR = ""

# ================================================================================
# END OF CONFIGURATION
# ================================================================================


def log(msg, f=None):
    print(msg)
    if f:
        f.write(msg + "\n")


def find_duplicate_links(link_file, base_country, smaller_country, tolerance):
    """
    Find duplicate links between two networks.

    DEFINITION: A smaller-network link is a duplicate if:
      1. Same OSM_WAY_ID as a base-network link
      2. Same FROM coordinates within tolerance
      3. Same TO coordinates within tolerance

    Returns:
      - duplicate_link_nos: set of smaller-network link numbers that are duplicates
      - link_details: dict of link_no -> full link info (for CSV and flagging)
      - shared_way_count: number of shared OSM_WAY_IDs
      - tsys_summary: Counter of transport systems on duplicate links
    """
    cols = None
    col_idx = {}
    base_links = {}    # osm_way_id -> list of row dicts
    smaller_links = {} # osm_way_id -> list of row dicts
    all_link_data = {} # link_no -> full row data

    with open(link_file, 'r', encoding='utf-8-sig') as f:
        for line in f:
            s = line.strip()
            if s.startswith('$LINK:'):
                cols = s.replace('$LINK:', '').split(';')
                col_idx = {c: i for i, c in enumerate(cols)}
                continue
            if not cols or s.startswith('*') or s.startswith('$') or not s:
                continue
            parts = s.split(';')
            try:
                way_id  = parts[col_idx['OSM_WAY_ID']].strip()
                country = parts[col_idx['COUNTRY']].strip()
                link_no = parts[col_idx['NO']].strip()
                tsysset = parts[col_idx['TSYSSET']].strip()
                from_no = parts[col_idx['FROMNODENO']].strip()
                to_no   = parts[col_idx['TONODENO']].strip()
                from_x  = float(parts[col_idx['FROMNODE\\XCOORD']])
                from_y  = float(parts[col_idx['FROMNODE\\YCOORD']])
                to_x    = float(parts[col_idx['TONODE\\XCOORD']])
                to_y    = float(parts[col_idx['TONODE\\YCOORD']])

                row = {
                    'NO':     link_no,
                    'FROM':   from_no,
                    'TO':     to_no,
                    'FROM_X': from_x,
                    'FROM_Y': from_y,
                    'TO_X':   to_x,
                    'TO_Y':   to_y,
                    'TSYSSET': tsysset,
                    'COUNTRY': country,
                }
                all_link_data[link_no] = row

                if way_id in ('0', ''):
                    continue
                if country == base_country:
                    base_links.setdefault(way_id, []).append(row)
                elif country == smaller_country:
                    smaller_links.setdefault(way_id, []).append(row)
            except (IndexError, KeyError, ValueError):
                continue

    shared_ways = set(base_links.keys()) & set(smaller_links.keys())
    duplicate_link_nos = set()
    link_details = {}  # link_no -> (from_node, to_node, tsysset)

    for way_id in shared_ways:
        for mol in smaller_links[way_id]:
            for rom in base_links[way_id]:
                from_dist = ((mol['FROM_X'] - rom['FROM_X'])**2 +
                             (mol['FROM_Y'] - rom['FROM_Y'])**2)**0.5
                to_dist   = ((mol['TO_X'] - rom['TO_X'])**2 +
                             (mol['TO_Y'] - rom['TO_Y'])**2)**0.5
                if from_dist <= tolerance and to_dist <= tolerance:
                    duplicate_link_nos.add(mol['NO'])
                    link_details[mol['NO']] = (mol['FROM'], mol['TO'], mol['TSYSSET'])
                    break

    tsys_summary = Counter(v[2] for v in link_details.values())
    return duplicate_link_nos, link_details, len(shared_ways), tsys_summary


def build_node_country_map(link_file, base_country, smaller_country):
    """
    Derive the country of each node from the links connected to it.
    Nodes do not have a COUNTRY attribute directly in Visum — but the
    links they connect to do. This avoids relying on node number ranges
    which are arbitrary and differ between networks.

    Returns: dict of {node_no -> country}
    """
    cols = None
    col_idx = {}
    node_country = {}

    with open(link_file, 'r', encoding='utf-8-sig') as f:
        for line in f:
            s = line.strip()
            if s.startswith('$LINK:'):
                cols = s.replace('$LINK:', '').split(';')
                col_idx = {c: i for i, c in enumerate(cols)}
                continue
            if not cols or s.startswith('*') or s.startswith('$') or not s:
                continue
            parts = s.split(';')
            try:
                country = parts[col_idx['COUNTRY']].strip()
                from_no = parts[col_idx['FROMNODENO']].strip()
                to_no   = parts[col_idx['TONODENO']].strip()
                # Only assign country if not already assigned
                # to avoid overwriting with a conflicting country
                if from_no not in node_country:
                    node_country[from_no] = country
                if to_no not in node_country:
                    node_country[to_no] = country
            except (IndexError, KeyError):
                continue

    return node_country


def find_duplicate_nodes(node_file, link_file, base_country, smaller_country, tolerance):
    """
    Find duplicate nodes between two networks.

    DEFINITION: A smaller-network node is a duplicate if:
      1. Same coordinates as a base-network node (within tolerance)
      2. Identified as smaller network via its connected links COUNTRY attribute
         (no node number threshold needed — works for any country pair)

    Returns:
      - duplicate_node_nos: set of smaller-network node numbers that are duplicates
      - node_pairs: list of dicts with moldova_node, romania_node, distance_m
      - total_nodes: total node count in file
      - ambiguous: list of coordinate-matching pairs where country is unclear
    """
    # Derive node country from connected links
    node_country = build_node_country_map(link_file, base_country, smaller_country)

    cols = None
    col_idx = {}
    nodes = []

    with open(node_file, 'r', encoding='utf-8-sig') as f:
        for line in f:
            s = line.strip()
            if s.startswith('$NODE:'):
                cols = s.replace('$NODE:', '').split(';')
                col_idx = {c: i for i, c in enumerate(cols)}
                continue
            if not cols or s.startswith('*') or s.startswith('$') or not s:
                continue
            parts = s.split(';')
            try:
                no = parts[col_idx['NO']].strip()
                nodes.append({
                    'NO':      no,
                    'X':       float(parts[col_idx['XCOORD']].strip()),
                    'Y':       float(parts[col_idx['YCOORD']].strip()),
                    'COUNTRY': node_country.get(no, 'UNKNOWN')
                })
            except (IndexError, KeyError, ValueError):
                continue

    duplicate_node_nos = set()
    node_pairs = []
    ambiguous = []

    for i, n1 in enumerate(nodes):
        for j, n2 in enumerate(nodes):
            if i >= j:
                continue
            dist = ((n1['X'] - n2['X'])**2 + (n1['Y'] - n2['Y'])**2)**0.5
            if dist <= tolerance:
                # Identify Moldova vs Romania using country from links
                if n1['COUNTRY'] == smaller_country and n2['COUNTRY'] == base_country:
                    mol, rom = n1, n2
                elif n2['COUNTRY'] == smaller_country and n1['COUNTRY'] == base_country:
                    mol, rom = n2, n1
                else:
                    # Country unclear — flag for manual review
                    ambiguous.append({
                        'node1': n1['NO'], 'country1': n1['COUNTRY'],
                        'node2': n2['NO'], 'country2': n2['COUNTRY'],
                        'distance_m': round(dist, 3)
                    })
                    continue
                duplicate_node_nos.add(mol['NO'])
                node_pairs.append({
                    'moldova_node': mol['NO'],
                    'romania_node': rom['NO'],
                    'distance_m':   round(dist, 3)
                })

    return duplicate_node_nos, node_pairs, len(nodes), ambiguous


def flag_and_save_links(src, dst, duplicate_link_nos):
    """
    Read links file line by line, set OVERLAP_TOBE_DELETED=1 for
    duplicate links, write output preserving exact file structure.
    """
    with open(src, 'rb') as f:
        raw = f.read()

    line_ending = b'\r\n' if b'\r\n' in raw else b'\n'
    lines_in = raw.split(line_ending)
    lines_out = []
    cols = None
    col_idx = {}
    flagged = 0

    for line_bytes in lines_in:
        line = line_bytes.decode('utf-8-sig')

        if line.startswith('$LINK:'):
            cols = line.replace('$LINK:', '').split(';')
            col_idx = {c: i for i, c in enumerate(cols)}
            lines_out.append(line_bytes)
            continue

        if not cols or line.startswith('*') or line.startswith('$') or not line.strip():
            lines_out.append(line_bytes)
            continue

        parts = line.split(';')
        try:
            link_no = parts[col_idx['NO']].strip()
            if link_no in duplicate_link_nos:
                parts[col_idx['OVERLAP_TOBE_DELETED']] = '1'
                flagged += 1
                lines_out.append(';'.join(parts).encode('utf-8'))
                continue
        except (IndexError, KeyError):
            pass

        lines_out.append(line_bytes)

    with open(dst, 'wb') as f:
        f.write(line_ending.join(lines_out))

    return flagged


def flag_and_save_nodes(src, dst, duplicate_node_nos):
    """
    Read nodes file line by line, set OVERLAPPING_NODE=1 for
    duplicate nodes, write output preserving exact file structure.
    """
    with open(src, 'rb') as f:
        raw = f.read()

    line_ending = b'\r\n' if b'\r\n' in raw else b'\n'
    lines_in = raw.split(line_ending)
    lines_out = []
    cols = None
    col_idx = {}
    flagged = 0

    for line_bytes in lines_in:
        line = line_bytes.decode('utf-8-sig')

        if line.startswith('$NODE:'):
            cols = line.replace('$NODE:', '').split(';')
            col_idx = {c: i for i, c in enumerate(cols)}
            lines_out.append(line_bytes)
            continue

        if not cols or line.startswith('*') or line.startswith('$') or not line.strip():
            lines_out.append(line_bytes)
            continue

        parts = line.split(';')
        try:
            node_no = parts[col_idx['NO']].strip()
            if node_no in duplicate_node_nos:
                parts[col_idx['OVERLAPPING_NODE']] = '1'
                flagged += 1
                lines_out.append(';'.join(parts).encode('utf-8'))
                continue
        except (IndexError, KeyError):
            pass

        lines_out.append(line_bytes)

    with open(dst, 'wb') as f:
        f.write(line_ending.join(lines_out))

    return flagged


def save_nodes_csv(filepath, node_pairs):
    """Save node deletion list to CSV."""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("node_no\n")
        for pair in sorted(node_pairs, key=lambda x: int(x['moldova_node'])):
            f.write(f"{pair['moldova_node']}\n")


def save_node_merge_map(filepath, node_pairs):
    """
    Save node merge map to CSV with both Moldova and Romania node numbers.
    Used by visum_merge_nodes.py to reconnect links before deleting nodes.
    Format: moldova_node,romania_node
    """
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("moldova_node,romania_node\n")
        for pair in sorted(node_pairs, key=lambda x: int(x['moldova_node'])):
            f.write(f"{pair['moldova_node']},{pair['romania_node']}\n")


def save_links_csv(filepath, link_details):
    """Save link deletion list to CSV with from/to nodes."""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("link_no,from_node,to_node\n")
        for link_no in sorted(link_details.keys(), key=lambda x: int(x)):
            from_no, to_no, _ = link_details[link_no]
            f.write(f"{link_no},{from_no},{to_no}\n")


def main():
    start = datetime.now()

    out_dir = OUTPUT_DIR or os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out_dir, exist_ok=True)

    # Output paths
    node_flagged  = os.path.join(out_dir, "spatial_selection_nodes_FLAGGED.att")
    link_flagged  = os.path.join(out_dir, "spatial_selection_links_FLAGGED.att")
    nodes_csv     = os.path.join(out_dir, "nodes_to_delete.csv")
    links_csv     = os.path.join(out_dir, "links_to_delete.csv")
    report_path   = os.path.join(out_dir, "cleanup_report.txt")

    with open(report_path, 'w', encoding='utf-8') as report:

        log("=" * 70, report)
        log("VISUM NETWORK OVERLAP CLEANUP — STEP 1 of 2", report)
        log(f"Run: {start.strftime('%Y-%m-%d %H:%M:%S')}", report)
        log("=" * 70, report)
        log(f"\n  Node file:       {os.path.abspath(NODE_FILE)}", report)
        log(f"  Link file:       {os.path.abspath(LINK_FILE)}", report)
        log(f"  Base country:    '{BASE_COUNTRY}' — KEPT", report)
        log(f"  Smaller country: '{SMALLER_COUNTRY}' — duplicates FLAGGED", report)
        log(f"  Tolerance:       {MATCH_TOLERANCE} m", report)

        for fp in [NODE_FILE, LINK_FILE]:
            if not os.path.exists(fp):
                log(f"\nERROR: File not found: {fp}", report)
                sys.exit(1)

        # ------------------------------------------------------------------
        log("\n" + "-" * 70, report)
        log("STEP 1: Finding duplicate links...", report)
        log("  Definition: same OSM_WAY_ID AND same FROM+TO coordinates", report)

        dup_link_nos, link_details, shared_ways, tsys_summary = find_duplicate_links(
            LINK_FILE, BASE_COUNTRY, SMALLER_COUNTRY, MATCH_TOLERANCE
        )

        log(f"\n  Shared OSM_WAY_IDs found:           {shared_ways}", report)
        log(f"  Duplicate links identified:          {len(dup_link_nos)}", report)
        log(f"  Link rows to delete (x2 directions): {len(dup_link_nos) * 2}", report)
        log(f"\n  Transport systems on duplicate links:", report)
        for tsys, count in tsys_summary.most_common():
            flag = " ⚠ RAIL — verify no active train routes" if 'RAIL' in tsys else ""
            log(f"    {tsys}: {count} links{flag}", report)

        # ------------------------------------------------------------------
        log("\n" + "-" * 70, report)
        log("STEP 2: Finding duplicate nodes...", report)
        log("  Definition: same coordinates within tolerance", report)

        dup_node_nos, node_pairs, total_nodes, ambiguous = find_duplicate_nodes(
            NODE_FILE, LINK_FILE, BASE_COUNTRY, SMALLER_COUNTRY, MATCH_TOLERANCE
        )

        log(f"\n  Total nodes in spatial selection:   {total_nodes}", report)
        log(f"  Duplicate node pairs found:          {len(node_pairs)}", report)
        log(f"\n  Duplicate node pairs (Moldova → Romania):", report)
        log(f"  {'Moldova Node':<16} {'Romania Node':<16} {'Distance (m)'}", report)
        log(f"  {'-'*45}", report)
        for pair in sorted(node_pairs, key=lambda x: int(x['moldova_node'])):
            log(f"  {pair['moldova_node']:<16} {pair['romania_node']:<16} {pair['distance_m']}",
                report)

        # ------------------------------------------------------------------
        log("\n" + "-" * 70, report)
        log("STEP 3: Flagging and saving .att files...", report)

        links_flagged = flag_and_save_links(LINK_FILE, link_flagged, dup_link_nos)
        log(f"  Links flagged (OVERLAP_TOBE_DELETED=1): {links_flagged}", report)
        log(f"  Saved: {link_flagged}", report)

        nodes_flagged = flag_and_save_nodes(NODE_FILE, node_flagged, dup_node_nos)
        log(f"  Nodes flagged (OVERLAPPING_NODE=1):     {nodes_flagged}", report)
        log(f"  Saved: {node_flagged}", report)

        # ------------------------------------------------------------------
        log("\n" + "-" * 70, report)
        log("STEP 4: Saving deletion lists...", report)

        save_nodes_csv(nodes_csv, node_pairs)
        log(f"  nodes_to_delete.csv: {len(node_pairs)} nodes — saved to {nodes_csv}",
            report)

        merge_map_csv = os.path.join(out_dir, "node_merge_map.csv")
        save_node_merge_map(merge_map_csv, node_pairs)
        log(f"  node_merge_map.csv:  {len(node_pairs)} pairs — saved to {merge_map_csv}",
            report)

        save_links_csv(links_csv, link_details)
        log(f"  links_to_delete.csv: {len(link_details)} links — saved to {links_csv}",
            report)

        # ------------------------------------------------------------------
        elapsed = (datetime.now() - start).seconds
        log("\n" + "=" * 70, report)
        log("ANALYSIS COMPLETE", report)
        log("=" * 70, report)
        log(f"  Duplicate links flagged:   {len(dup_link_nos)}", report)
        log(f"  Duplicate nodes flagged:   {len(dup_node_nos)}", report)
        log(f"  Time elapsed:              {elapsed}s", report)
        log(f"\nOutputs:", report)
        log(f"  {link_flagged}", report)
        log(f"  {node_flagged}", report)
        log(f"  {links_csv}", report)
        log(f"  {nodes_csv}", report)
        log(f"  {merge_map_csv}", report)
        log(f"  {report_path}", report)
        log(f"\nNext steps:", report)
        log(f"  1. Review cleanup_report.txt", report)
        log(f"  2. Run visum_merge_nodes.py inside Visum to merge duplicate nodes", report)
        log(f"  3. Run visum_delete.py inside Visum to delete duplicate links (after supervisor review)", report)
        log("=" * 70, report)


if __name__ == "__main__":
    main()