"""
================================================================================
VISUM DUPLICATE LINKS DELETION TOOL
================================================================================
Author:       The World Bank ECA Transport Unit Team
Version:      1.0
Date:         2026-05

PURPOSE
-------
Deletes duplicate Moldova links that overlap with Romania links.

HOW IT WORKS
------------
  1. Suspends Visum recalculations (SetEnableComUpdateAndRun False)
  2. For each link in links_to_delete.csv:
       - Fetches forward direction directly by ItemByKey(from_node, to_node)
       - Fetches reverse direction directly by ItemByKey(to_node, from_node)
       - Deletes both
  3. Re-enables recalculations (one single recalculation at the end)
  4. Reports how many Moldova nodes are now isolated

  ItemByKey() = direct lookup, no network scan
  SetEnableComUpdateAndRun(False) = no recalculation after each deletion

HOW TO USE
----------
  1. Run visum_overlap_cleanup.py outside Visum first
  2. Open Visum with your network loaded
  3. Scripts menu → Run Script → select this file
  4. Save network after completion popup

CONFIGURATION
-------------
  SCRIPT_DIR: folder containing links_to_delete.csv and nodes_to_delete.csv
  Leave empty to use same folder as this script
================================================================================
"""

import os
import sys
import ctypes
from datetime import datetime


# ================================================================================
# CONFIGURATION
# ================================================================================

SCRIPT_DIR = ""

# ================================================================================
# END OF CONFIGURATION
# ================================================================================


def read_links_to_delete(filepath):
    links = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = line.strip().split(',')
            if len(parts) >= 3:
                links.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return links


def read_nodes_to_delete(filepath):
    nodes = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            val = line.strip()
            if val:
                nodes.append(int(val))
    return nodes


def show_error(msg):
    ctypes.windll.user32.MessageBoxW(0, msg, "Visum Delete Links — Error", 0x10)


def show_info(msg):
    ctypes.windll.user32.MessageBoxW(0, msg, "Visum Delete Links — Complete", 0x40)


def set_status(msg):
    try:
        Visum.SetStatusBar(msg)
    except Exception:
        pass
    print(msg)


def main():
    start_time = datetime.now()

    folder = SCRIPT_DIR or os.path.dirname(os.path.abspath(__file__))
    links_csv = os.path.join(folder, "links_to_delete.csv")
    nodes_csv = os.path.join(folder, "nodes_to_delete.csv")

    for fp in [links_csv, nodes_csv]:
        if not os.path.exists(fp):
            show_error(f"File not found:\n{fp}\n\nPlease run visum_overlap_cleanup.py first.")
            sys.exit(1)

    links_to_delete = read_links_to_delete(links_csv)
    nodes_to_delete = read_nodes_to_delete(nodes_csv)

    set_status(f"Starting — {len(links_to_delete)} duplicate links to delete...")

    Net = Visum.Net

    # ------------------------------------------------------------------
    # Suspend recalculations — prevents Visum recalculating the whole
    # network after each individual deletion.
    # One single recalculation happens when re-enabled at the end.
    # ------------------------------------------------------------------
    Visum.SetEnableComUpdateAndRun(False)
    set_status("Recalculations suspended — deleting links...")

    # ------------------------------------------------------------------
    # Delete duplicate links
    # ItemByKey(from_no, to_no) = direct lookup, no network scan
    # Both forward and reverse directions deleted
    # ------------------------------------------------------------------
    links_deleted = 0
    links_skipped = 0
    total = len(links_to_delete)

    for i, (link_no, from_no, to_no) in enumerate(links_to_delete, 1):

        # Forward direction
        try:
            link = Net.Links.ItemByKey(from_no, to_no)
            Net.RemoveLink(link)
            links_deleted += 1
        except Exception:
            links_skipped += 1

        # Reverse direction
        try:
            link_rev = Net.Links.ItemByKey(to_no, from_no)
            Net.RemoveLink(link_rev)
            links_deleted += 1
        except Exception:
            links_skipped += 1

        if i % 10 == 0 or i == total:
            pct = int(i / total * 100)
            set_status(
                f"Deleting links: {i}/{total} ({pct}%) | "
                f"deleted: {links_deleted} | skipped: {links_skipped}"
            )

    # ------------------------------------------------------------------
    # Re-enable recalculations — triggers one single recalculation
    # ------------------------------------------------------------------
    set_status("Re-enabling recalculations...")
    Visum.SetEnableComUpdateAndRun(True)

    # ------------------------------------------------------------------
    # Check how many Moldova nodes are now isolated
    # ------------------------------------------------------------------
    set_status("Checking isolated nodes...")

    isolated = []
    still_connected = []

    for node_no in nodes_to_delete:
        try:
            node = Net.Nodes.ItemByKey(node_no)
            if len(list(node.InLinks)) == 0 and len(list(node.OutLinks)) == 0:
                isolated.append(node_no)
            else:
                still_connected.append(node_no)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    elapsed = (datetime.now() - start_time).seconds
    set_status("Link deletion complete — please save your network.")

    connected_info = ""
    if still_connected:
        connected_info = (
            f"\n\n⚠ Nodes still connected: {len(still_connected)}\n"
            f"{still_connected[:5]}"
            + (f"\n...and {len(still_connected)-5} more" if len(still_connected) > 5 else "")
        )

    show_info(
        f"LINKS DELETION COMPLETE\n\n"
        f"Links deleted:             {links_deleted}\n"
        f"Links skipped:             {links_skipped}\n"
        f"Time elapsed:              {elapsed}s\n\n"
        f"--- Node Status ---\n"
        f"Nodes now isolated:        {len(isolated)}\n"
        f"Nodes still connected:     {len(still_connected)}\n"
        f"{connected_info}\n\n"
        f"Please save your network.\n"
        f"Isolated nodes ready to delete next."
    )


main()