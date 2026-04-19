"""
40 carrier fixtures used by seed_call_logs.py.

Layout within CARRIERS list (0-indexed):
  [0..4]   dormant carriers — all calls dated >25 days ago, ≥2 bookings each
  [5..9]   top-5 non-dormant — high call volume (20,15,12,8,5 calls)
  [10..22] middle 13 non-dormant — moderate volume
  [23..39] bottom 17 non-dormant — 1 call each
"""

CARRIERS = [
    # ── Dormant (indices 0-4) ──────────────────────────────────────────────
    {"mc": "MC-001234", "name": "HERITAGE HAULING LLC",    "dot": "DOT-1012345"},
    {"mc": "MC-002345", "name": "DELTA LONGHAUL LLC",      "dot": "DOT-1023456"},
    {"mc": "MC-003456", "name": "CASCADE TRUCKING CO",     "dot": "DOT-1034567"},
    {"mc": "MC-004567", "name": "GULF COAST FREIGHT INC",  "dot": "DOT-1045678"},
    {"mc": "MC-005678", "name": "IRONHORSE LOGISTICS LLC", "dot": "DOT-1056789"},
    # ── Top-5 non-dormant (indices 5-9) ────────────────────────────────────
    {"mc": "MC-100001", "name": "SWIFT LOGISTICS LLC",      "dot": "DOT-2001001"},
    {"mc": "MC-100002", "name": "BLUE RIDGE TRANSPORT INC", "dot": "DOT-2001002"},
    {"mc": "MC-100003", "name": "PACIFIC HAUL INC",         "dot": "DOT-2001003"},
    {"mc": "MC-100004", "name": "ATLAS FREIGHT CO",         "dot": "DOT-2001004"},
    {"mc": "MC-100005", "name": "MIDWEST CARRIERS LLC",     "dot": "DOT-2001005"},
    # ── Middle 13 non-dormant (indices 10-22) ──────────────────────────────
    {"mc": "MC-200001", "name": "EAGLE LINE LOGISTICS",    "dot": "DOT-2002001"},
    {"mc": "MC-200002", "name": "NORTHSTAR TRUCKING INC",  "dot": "DOT-2002002"},
    {"mc": "MC-200003", "name": "RIO GRANDE FREIGHT LLC",  "dot": "DOT-2002003"},
    {"mc": "MC-200004", "name": "SILVERLINE HAULERS CO",   "dot": "DOT-2002004"},
    {"mc": "MC-200005", "name": "APEX TRANSPORT INC",      "dot": "DOT-2002005"},
    {"mc": "MC-200006", "name": "JEFFERSON TRANS INC",     "dot": "DOT-2002006"},
    {"mc": "MC-200007", "name": "KEYSTONE CARRIERS LLC",   "dot": "DOT-2002007"},
    {"mc": "MC-200008", "name": "LONE STAR TRANSPORT CO",  "dot": "DOT-2002008"},
    {"mc": "MC-200009", "name": "MAPLE LEAF FREIGHT INC",  "dot": "DOT-2002009"},
    {"mc": "MC-200010", "name": "NEXUS HAUL LLC",          "dot": "DOT-2002010"},
    {"mc": "MC-200011", "name": "OLYMPIA FREIGHT LLC",     "dot": "DOT-2002011"},
    {"mc": "MC-200012", "name": "PINNACLE TRANSPORT INC",  "dot": "DOT-2002012"},
    {"mc": "MC-200013", "name": "REDROCK LOGISTICS LLC",   "dot": "DOT-2002013"},
    # ── Bottom 17 non-dormant (indices 23-39) — 1 call each ────────────────
    {"mc": "MC-300001", "name": "SUMMIT HAUL INC",          "dot": "DOT-2003001"},
    {"mc": "MC-300002", "name": "TRAILBLAZER FREIGHT LLC",  "dot": "DOT-2003002"},
    {"mc": "MC-300003", "name": "UNION ROAD CARRIERS INC",  "dot": "DOT-2003003"},
    {"mc": "MC-300004", "name": "VALOR TRANSPORT CO",       "dot": "DOT-2003004"},
    {"mc": "MC-300005", "name": "WESTWIND LOGISTICS LLC",   "dot": "DOT-2003005"},
    {"mc": "MC-300006", "name": "XPRESS HAUL INC",          "dot": "DOT-2003006"},
    {"mc": "MC-300007", "name": "YELLOWSTONE FREIGHT CO",   "dot": "DOT-2003007"},
    {"mc": "MC-300008", "name": "ZEPHYR TRANSPORT LLC",     "dot": "DOT-2003008"},
    {"mc": "MC-300009", "name": "ACME FREIGHT INC",         "dot": "DOT-2003009"},
    {"mc": "MC-300010", "name": "BACKROADS HAULING LLC",    "dot": "DOT-2003010"},
    {"mc": "MC-300011", "name": "CENTRAL COAST FREIGHT CO", "dot": "DOT-2003011"},
    {"mc": "MC-300012", "name": "DEEPWATER TRANSPORT INC",  "dot": "DOT-2003012"},
    {"mc": "MC-300013", "name": "EMERALD FREIGHT LLC",      "dot": "DOT-2003013"},
    {"mc": "MC-300014", "name": "FRONTIER CARRIERS INC",    "dot": "DOT-2003014"},
    {"mc": "MC-300015", "name": "GRANITE STATE HAUL LLC",   "dot": "DOT-2003015"},
    {"mc": "MC-300016", "name": "HIGHLINE TRANSPORT CO",    "dot": "DOT-2003016"},
    {"mc": "MC-300017", "name": "INLAND FREIGHT LLC",       "dot": "DOT-2003017"},
]

assert len(CARRIERS) == 40, f"Expected 40 carriers, got {len(CARRIERS)}"

# Quick lookup by mc number
CARRIER_BY_MC: dict[str, dict] = {c["mc"]: c for c in CARRIERS}
