# Visum Network Cleaning

World Bank ECA Transport Unit

Automated detection and removal of duplicate nodes and links in multi-country Visum transport networks.

## Overview

When two national transport networks are merged in PTV Visum, the border overlap area typically contains duplicate nodes and links representing the same physical road segments under different country codes. Identifying and removing these manually is difficult to reproduce consistently.

This repository provides a two step automated workflow that detects duplicate links and nodes by analysing exported Visum attribute files, then deletes the confirmed duplicates directly inside Visum via the COM interface. The workflow is designed to be reusable for any country pair by changing only the configuration section.

## Repository Structure

```
visum-network-cleaning/
├── scripts/
│   ├── 01_visum_overlap_cleanup.py
│   └── 02_visum_delete_links.py
└── outputs_example/
    ├── cleanup_report.txt
    ├── links_to_delete.csv
    └── nodes_to_delete.csv
```

## Prerequisites

Python 3.8 or later, PTV Visum, Windows operating system. No external Python packages are required beyond the standard library.

## Workflow

### Step 1 - Detect Duplicates (run outside Visum)

Script: `01_visum_overlap_cleanup.py`

This script reads exported `.att` files from a spatial selection in Visum and identifies duplicate links and nodes between two overlapping country networks.

A link is considered a duplicate if it shares the same OSM_WAY_ID as a base country link and has matching FROM and TO coordinates within the defined tolerance. A node is considered a duplicate if it shares the same coordinates as a base country node within tolerance, with country assignment derived from the connected links rather than node number ranges.

The script produces the following outputs:

- `cleanup_report.txt` - full analysis summary, review this before proceeding
- `links_to_delete.csv` - duplicate link numbers with from and to nodes
- `nodes_to_delete.csv` - duplicate node numbers
- `node_merge_map.csv` - mapping of smaller country nodes to base country nodes
- `_FLAGGED.att` files - original exports with duplicates flagged, for visual review in Visum

### Step 2 - Delete Duplicates (run inside Visum)

Script: `02_visum_delete_links.py`

This script reads the CSV files produced in Step 1 and deletes the duplicate links directly inside Visum using the COM interface. It suspends Visum recalculations during deletion to avoid recalculating the full network after each individual removal, triggering a single recalculation at the end. After deletion it reports which nodes are now isolated and ready for removal.

## How to Use

**Export from Visum**

Make a spatial selection around the border overlap area. Export a nodes `.att` file including NO, XCOORD, YCOORD, and OVERLAPPING_NODE. Export a links `.att` file including NO, FROMNODENO, TONODENO, FROMNODE\XCOORD, FROMNODE\YCOORD, TONODE\XCOORD, TONODE\YCOORD, COUNTRY, OSM_WAY_ID, TSYSSET, and OVERLAP_TOBE_DELETED. Both exports must come from the same spatial selection.

**Configure Script 1**

Open `01_visum_overlap_cleanup.py` and edit the configuration section at the top of the file:

```python
NODE_FILE       = r"C:\path\to\nodes.att"
LINK_FILE       = r"C:\path\to\links.att"
BASE_COUNTRY    = "Romania"    # Network to keep
SMALLER_COUNTRY = ""           # Network to flag for deletion
MATCH_TOLERANCE = 1.0          # Coordinate tolerance in metres
OUTPUT_DIR      = ""           # Leave empty to save alongside script
```

**Run Script 1**

```
python scripts/01_visum_overlap_cleanup.py
```

Review `cleanup_report.txt` before proceeding. Pay particular attention to any rail links flagged for deletion, as these require manual verification.

**Run Script 2**

Back up your Visum network file before this step. Open Visum with the network loaded, go to Scripts, select Run Script, and select `02_visum_delete_links.py`. Save the network after the completion dialog appears.

## Reusing for Other Country Pairs

Only the configuration section in Script 1 needs to change. Examples:

| Border | BASE_COUNTRY | SMALLER_COUNTRY |
|---|---|---|
| Moldova and Romania | Romania | (blank) |
| Ukraine and Poland | Poland | Ukraine |
| Georgia and Turkey | Turkey | Georgia |

## Safety Notes

Always back up the Visum network file before running Script 2. Both `.att` exports must come from the same spatial selection. Links with OSM_WAY_ID of zero or blank are excluded from duplicate detection as they have no reliable match key. The default tolerance of 1.0 metre is recommended increasing it raises the risk of false positives.

## Authors

World Bank ECA Transport Unit

## License

MIT License
