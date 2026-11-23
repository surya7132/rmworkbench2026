"""Static data that the mockup did not have: identities, extra clients, sectors,
supply-chain edges and the facts that justify each edge.

Everything here is invented. Names are fictional; identifier formats are real.
"""

# ---------------------------------------------------------------------------
# External ratings for client groups: agency, grade, outlook comes from trend.
# ---------------------------------------------------------------------------
AGENCY = {"g_vantage": "CRISIL", "g_meridian": "CARE Ratings", "g_nordholm": "ICRA", "g_bluewater": "CRISIL",
          "g_corvina": "ICRA", "g_delta": "CARE Ratings", "g_evergreen": "India Ratings", "g_fulcrum": "ICRA",
          "g_granite": "CRISIL", "g_helix": "CARE Ratings", "g_kestrel": "CARE Ratings", "g_astra": "India Ratings"}
OUTLOOK = {"up": "Positive", "flat": "Stable", "down": "Negative"}
INTERNAL_GRADE = {"A+": "IG-3", "A": "IG-4", "A-": "IG-4", "BBB+": "IG-5", "BBB": "IG-6", "BBB-": "IG-7"}

# ---------------------------------------------------------------------------
# Company identities. kind: listed | private | firm | govt | foreign | lender
#   nic = 5-digit NIC code used inside the CIN; st = 2-letter ROC state code
# ---------------------------------------------------------------------------
COMPANIES = {
    # --- Vantage group (from the mockup) ---
    "e_vip":    dict(kind="listed",  nic="45201", st="MH", yr=2005, city="Mumbai (BKC)", state="Maharashtra", display="Vantage Infra Projects Limited"),
    "e_vhold":  dict(kind="private", nic="74999", st="MH", yr=2001, city="Mumbai", state="Maharashtra"),
    "e_spv1":   dict(kind="private", nic="45203", st="MH", yr=2022, city="Mumbai", state="Maharashtra", display="Vantage Highway SPV 1 Private Limited"),
    "e_spv2":   dict(kind="private", nic="45203", st="MH", yr=2023, city="Mumbai", state="Maharashtra", display="Vantage Highway SPV 2 Private Limited"),
    "e_sha":    dict(kind="govt", city="Mumbai", state="Maharashtra"),
    "e_steel":  dict(kind="private", nic="27109", st="MH", yr=2008, city="Raigad", state="Maharashtra"),
    "e_ridge":  dict(kind="firm", city="Pune", state="Maharashtra"),
    "e_cons":   dict(kind="lender"),
    # --- Meridian group ---
    "e_mer":    dict(kind="listed",  nic="17121", st="GJ", yr=1998, city="Surat", state="Gujarat", display="Meridian Fabrics Limited"),
    "e_mprom":  dict(kind="private", nic="74999", st="GJ", yr=1999, city="Surat", state="Gujarat", display="Patil Family Holdings Private Limited"),
    "e_eub":    dict(kind="foreign", country="Germany", note="Name withheld by client"),
    "e_coastal": dict(kind="private", nic="17111", st="TN", yr=2009, city="Tiruppur", state="Tamil Nadu"),
    "e_dyeing": dict(kind="firm", city="Surat", state="Gujarat"),
    "e_weave":  dict(kind="firm", city="Surat", state="Gujarat"),
    "e_sunrise": dict(kind="firm", city="Daman", state="Daman and Diu"),
    # --- Nordholm group ---
    "e_nord":   dict(kind="private", nic="34300", st="MH", yr=1996, city="Pune (Chakan)", state="Maharashtra"),
    "e_npar":   dict(kind="foreign", country="Sweden", note="Parent"),
    "e_oem":    dict(kind="foreign", country="India / MNC", note="Tier-1 OEM customer, name withheld"),
    "e_rt":     dict(kind="foreign", country="Singapore", note="Regional treasury centre of the parent"),
    # --- other clients ---
    "e_bluewater": dict(kind="listed",  nic="61100", st="MH", yr=1992, city="Mumbai", state="Maharashtra"),
    "e_corvina":   dict(kind="listed",  nic="24231", st="AP", yr=2003, city="Hyderabad", state="Telangana"),
    "e_delta":     dict(kind="private", nic="15141", st="MP", yr=1999, city="Indore", state="Madhya Pradesh"),
    "e_evergreen": dict(kind="listed",  nic="70100", st="MH", yr=2007, city="Mumbai (Andheri)", state="Maharashtra"),
    "e_fulcrum":   dict(kind="private", nic="34300", st="MH", yr=2002, city="Chhatrapati Sambhajinagar", state="Maharashtra"),
    "e_granite":   dict(kind="listed",  nic="26941", st="KA", yr=1994, city="Bengaluru", state="Karnataka"),
    "e_helix":     dict(kind="private", nic="25209", st="GJ", yr=2004, city="Vapi", state="Gujarat"),
    "e_kestrel":   dict(kind="private", nic="24117", st="GJ", yr=2000, city="Dahej", state="Gujarat"),
    "e_astra":     dict(kind="private", nic="63090", st="MH", yr=2006, city="Mumbai (Vashi)", state="Maharashtra"),
    "e_wmb":       dict(kind="lender", note="Competing lender named in the MCA charge filing"),
}
LISTED_SUFFIX = {"listed": "Ltd", "private": "Pvt Ltd"}

# (id, name, role, group, kind='company'|'person'|'bank', sector node)
NEW_NODES = [
    ("e_bluewater", "Bluewater Marine Ltd", "Primary borrower", "g_bluewater", "company", "s_shipping"),
    ("e_corvina", "Corvina Pharma Ltd", "Primary borrower", "g_corvina", "company", "s_pharma"),
    ("e_delta", "Delta Agro Foods Ltd", "Primary borrower", "g_delta", "company", "s_food"),
    ("e_evergreen", "Evergreen Realty Ltd", "Primary borrower", "g_evergreen", "company", "s_realty"),
    ("e_fulcrum", "Fulcrum Auto Ltd", "Primary borrower", "g_fulcrum", "company", "s_auto"),
    ("e_granite", "Granite Cement Ltd", "Primary borrower", "g_granite", "company", "s_cement"),
    ("e_helix", "Helix Packaging Ltd", "Primary borrower", "g_helix", "company", "s_packaging"),
    ("e_kestrel", "Kestrel Polymers Ltd", "Primary borrower", "g_kestrel", "company", "s_chemicals"),
    ("e_astra", "Astra Logistics Ltd", "Primary borrower", "g_astra", "company", "s_logistics"),
    ("e_wmb", "Western Mercantile Bank", "Other lender (charge holder)", None, "bank", None),
    ("p_hormuz", "Hormuz Dastur", "Chairman and Managing Director", "g_bluewater", "person", None),
    ("p_srinivas", "Srinivas Reddy", "Managing Director", "g_corvina", "person", None),
    ("p_mahendra", "Mahendra Jain", "Promoter and Chairman", "g_delta", "person", None),
    ("p_sanjay", "Sanjay Bhatia", "Chairman and Managing Director", "g_evergreen", "person", None),
    ("p_gurpreet", "Gurpreet Sethi", "Promoter and Managing Director", "g_fulcrum", "person", None),
    ("p_venkatesh", "Venkatesh Hegde", "Managing Director", "g_granite", "person", None),
    ("p_jignesh", "Jignesh Desai", "Promoter and Managing Director", "g_helix", "person", None),
    ("p_prakash", "Prakash Naik", "Promoter and Managing Director", "g_kestrel", "person", None),
    ("p_faisal", "Faisal Ansari", "Promoter and Managing Director", "g_astra", "person", None),
]
PROMOTER_OF = {"p_hormuz": "e_bluewater", "p_srinivas": "e_corvina", "p_mahendra": "e_delta", "p_sanjay": "e_evergreen",
               "p_gurpreet": "e_fulcrum", "p_venkatesh": "e_granite", "p_jignesh": "e_helix", "p_prakash": "e_kestrel",
               "p_faisal": "e_astra"}
DIN_PERSONS = {"p_dilip", "p_anil", "p_hormuz", "p_srinivas", "p_mahendra", "p_sanjay", "p_gurpreet", "p_venkatesh",
               "p_jignesh", "p_prakash", "p_faisal"}

SECTORS = [("s_infra", "EPC and infrastructure"), ("s_textile", "Textiles and apparel"), ("s_auto", "Auto components"),
           ("s_shipping", "Shipping"), ("s_pharma", "Pharmaceuticals"), ("s_food", "Food and FMCG"),
           ("s_realty", "Real estate"), ("s_cement", "Cement"), ("s_packaging", "Packaging"),
           ("s_chemicals", "Chemicals"), ("s_logistics", "Logistics"), ("s_steel", "Steel and metals")]
SECTOR_OF_GROUP = {"g_vantage": "s_infra", "g_meridian": "s_textile", "g_nordholm": "s_auto", "g_bluewater": "s_shipping",
                   "g_corvina": "s_pharma", "g_delta": "s_food", "g_evergreen": "s_realty", "g_fulcrum": "s_auto",
                   "g_granite": "s_cement", "g_helix": "s_packaging", "g_kestrel": "s_chemicals", "g_astra": "s_logistics"}
# sector for mockup companies that are not primaries
SECTOR_OF_NODE = {"e_steel": "s_steel", "e_vip": "s_infra", "e_spv1": "s_infra", "e_spv2": "s_infra", "e_ridge": "s_infra",
                  "e_mer": "s_textile", "e_coastal": "s_textile", "e_dyeing": "s_textile", "e_weave": "s_textile",
                  "e_sunrise": "s_packaging", "e_nord": "s_auto"}
PRODUCT_FAMILIES = [("pf_lending", "Lending"), ("pf_trade", "Trade"), ("pf_treasury", "Treasury"),
                    ("pf_scf", "Supply-chain finance"), ("pf_cash", "Cash management")]
FAMILY_NODE = {"Lending": "pf_lending", "Trade": "pf_trade", "Treasury": "pf_treasury",
               "Supply-chain finance": "pf_scf", "Cash management": "pf_cash"}

# ---------------------------------------------------------------------------
# Extra facilities for the 9 groups that were table rows only in the mockup.
# (type, sanctioned, outstanding, pricing, security, covenants, authority, maturity_year)
# Sums per group equal the sanctioned / utilised totals already in the mockup.
# ---------------------------------------------------------------------------
EXTRA_FACILITIES = {
    "g_bluewater": [("Term Loan (vessel acquisition)", 280, 220, "9.35% p.a. floating", "First preferred ship mortgage; assignment of earnings", "DSCR at least 1.25x; TOL/TNW at most 2.5x", "Credit committee", 2031),
                    ("Cash Credit", 90, 58, "9.20% p.a. floating", "First charge on current assets", "Current ratio at least 1.1x", "Credit committee", None),
                    ("Bank Guarantee", 40, 20, "1.10% p.a. commission", "Counter-guarantee and margin", "None specific", "Delegated", None)],
    "g_corvina": [("Term Loan (capex, API block)", 150, 90, "9.05% p.a. floating", "First charge on plant and machinery at Genome Valley unit", "DSCR at least 1.3x; TOL/TNW at most 2.0x", "Credit committee", 2030),
                  ("Cash Credit", 120, 60, "8.85% p.a. floating", "First pari passu charge on current assets", "Current ratio at least 1.2x", "Credit committee", None),
                  ("Letter of Credit", 60, 25, "0.85% p.a. commission", "Lien on goods; first charge on current assets", "None specific", "Delegated", None),
                  ("Forward contract limit", 30, 15, "Per treasury rate card", "Margin and counter-indemnity", "None specific", "Delegated", None)],
    "g_delta": [("Cash Credit", 80, 62, "9.50% p.a. floating", "Hypothecation of stock and book debts", "Current ratio at least 1.15x", "Delegated", None),
                ("Term Loan", 40, 29, "9.65% p.a. floating", "First charge on plant at Indore unit", "DSCR at least 1.2x", "Delegated", 2029),
                ("Letter of Credit", 20, 10, "0.90% p.a. commission", "Lien on goods", "None specific", "Delegated", None)],
    "g_evergreen": [("Construction finance term loan", 400, 370, "10.10% p.a. floating", "Mortgage on project land and receivables; escrow of sale proceeds", "Pre-sales at least 60% before 2nd tranche", "Credit committee", 2029),
                    ("Lease rental discounting", 90, 75, "9.60% p.a. floating", "Assignment of lease rentals; mortgage on commercial block", "DSCR at least 1.2x", "Credit committee", 2032),
                    ("Bank Guarantee", 30, 10, "1.25% p.a. commission", "Margin and counter-guarantee", "None specific", "Delegated", None)],
    "g_fulcrum": [("Cash Credit", 50, 34, "9.55% p.a. floating", "Hypothecation of stock and book debts", "Current ratio at least 1.15x", "Delegated", None),
                  ("Term Loan", 40, 28, "9.70% p.a. floating", "First charge on plant and machinery", "DSCR at least 1.2x", "Delegated", 2028),
                  ("Letter of Credit", 20, 8, "0.95% p.a. commission", "Lien on goods", "None specific", "Delegated", None)],
    "g_granite": [("Term Loan (kiln line 2)", 200, 170, "9.15% p.a. floating", "First charge on plant and machinery; mortgage on land", "DSCR at least 1.3x; TOL/TNW at most 2.0x", "Credit committee", 2031),
                  ("Cash Credit", 120, 100, "8.95% p.a. floating", "First pari passu charge on current assets", "Current ratio at least 1.2x", "Credit committee", None),
                  ("Bank Guarantee", 60, 40, "1.05% p.a. commission", "Counter-guarantee and margin", "None specific", "Delegated", None)],
    "g_helix": [("Cash Credit", 30, 20, "10.10% p.a. floating", "Hypothecation of stock and book debts", "Current ratio at least 1.15x", "Delegated", None),
                ("Term Loan", 20, 14, "10.25% p.a. floating", "First charge on machinery at Vapi unit", "DSCR at least 1.2x", "Delegated", 2028),
                ("Letter of Credit", 10, 4, "1.00% p.a. commission", "Lien on goods", "None specific", "Delegated", None)],
    "g_kestrel": [("Cash Credit", 60, 44, "9.70% p.a. floating", "Hypothecation of stock and book debts", "Current ratio at least 1.15x", "Delegated", None),
                  ("Term Loan", 40, 28, "9.85% p.a. floating", "First charge on plant at Dahej unit", "DSCR at least 1.25x", "Delegated", 2029),
                  ("Letter of Credit", 20, 12, "0.90% p.a. commission", "Lien on goods", "None specific", "Delegated", None)],
    "g_astra": [("Cash Credit", 40, 30, "9.60% p.a. floating", "Hypothecation of receivables", "Current ratio at least 1.1x", "Delegated", None),
                ("Term Loan (fleet purchase)", 40, 26, "9.75% p.a. floating", "Hypothecation of vehicles", "DSCR at least 1.2x", "Delegated", 2029),
                ("Bank Guarantee", 10, 6, "1.10% p.a. commission", "Margin", "None specific", "Delegated", None)],
}

# ---------------------------------------------------------------------------
# Extra facts. (id, group, node, statement, label, share, source, date, connector, match, value, unit)
# date as YYYY-MM-DD. 'int' = verified internal, 'ext' = external, 'rm' = RM-entered.
# ---------------------------------------------------------------------------
EXTRA_FACTS = [
    # payment-flow evidence behind the cross-client supply links (core banking, entity-matched)
    ("F-5001", "g_fulcrum", "e_steel", "Fulcrum Auto paid Steelco Suppliers Rs 22.0 cr in the last 12 months (41 payments)", "int", "internal", "Outward payment flows", "2026-11-09", "core-banking", 0.91, 22.0, "INR crore"),
    ("F-5002", "g_astra", "e_steel", "Astra Logistics bills Steelco Suppliers about Rs 5.4 cr a year for freight; Rs 1.9 cr outstanding on 17 Nov", "int", "internal", "Inward payment flows; receivables ledger", "2026-11-14", "core-banking", 0.90, 1.9, "INR crore"),
    ("F-5003", "g_vantage", "e_granite", "Vantage paid Granite Cement Rs 31.0 cr in the last 12 months (27 payments)", "int", "internal", "Outward payment flows", "2026-11-09", "core-banking", 0.96, 31.0, "INR crore"),
    ("F-5004", "g_evergreen", "e_granite", "Evergreen Realty paid Granite Cement Rs 26.0 cr in the last 12 months (19 payments)", "int", "internal", "Outward payment flows", "2026-11-09", "core-banking", 0.95, 26.0, "INR crore"),
    ("F-5005", "g_helix", "e_kestrel", "Helix Packaging paid Kestrel Polymers Rs 9.0 cr in the last 12 months (24 payments)", "int", "internal", "Outward payment flows", "2026-11-09", "core-banking", 0.97, 9.0, "INR crore"),
    ("F-5006", "g_delta", "e_helix", "Delta Agro Foods paid Helix Packaging Rs 6.5 cr in the last 12 months (18 payments)", "int", "internal", "Outward payment flows", "2026-11-09", "core-banking", 0.94, 6.5, "INR crore"),
    ("F-5007", "g_corvina", "e_helix", "Corvina Pharma paid Helix Packaging Rs 8.0 cr in the last 12 months (22 payments)", "int", "internal", "Outward payment flows", "2026-11-09", "core-banking", 0.96, 8.0, "INR crore"),
    ("F-5008", "g_meridian", "e_bluewater", "Meridian Fabrics paid Bluewater Marine Rs 3.2 cr in freight in the last 12 months (9 payments)", "int", "internal", "Outward payment flows", "2026-11-03", "core-banking", 0.92, 3.2, "INR crore"),
    ("F-5009", "g_fulcrum", "e_fulcrum", "Steelco Suppliers is Fulcrum's largest steel vendor, about 38% of steel purchases (per Finance Head)", "client", "discuss", "Meeting note, 6 Nov", "2026-11-06", "crm", 1.0, 38.0, "percent"),
    ("F-5010", "g_vantage", "e_spv1", "Steelco Suppliers is the structural steel vendor for the highway package (SPV 1 and SPV 2)", "client", "discuss", "Meeting note, 2 Nov", "2026-11-02", "crm", 1.0, None, None),
]
# Group limit facts for the nine thin groups are generated in build_db from facility totals.

# ---------------------------------------------------------------------------
# Edges the mockup did not have. (from, to, type, attrs, source_fact_id, confidence)
# Direction of supplies_to: supplier -> buyer. transports_for: carrier -> shipper.
# ---------------------------------------------------------------------------
EXTRA_EDGES = [
    ("e_steel", "e_fulcrum", "supplies_to", {"note": "steel, about 38% of Fulcrum purchases"}, "F-5001", 0.91),
    ("e_astra", "e_steel", "transports_for", {"note": "freight services, Rs 5.4 cr a year"}, "F-5002", 0.90),
    ("e_granite", "e_vip", "supplies_to", {"note": "cement"}, "F-5003", 0.96),
    ("e_granite", "e_evergreen", "supplies_to", {"note": "cement"}, "F-5004", 0.95),
    ("e_kestrel", "e_helix", "supplies_to", {"note": "polymer granules"}, "F-5005", 0.97),
    ("e_helix", "e_delta", "supplies_to", {"note": "flexible packaging"}, "F-5006", 0.94),
    ("e_helix", "e_corvina", "supplies_to", {"note": "blister packaging"}, "F-5007", 0.96),
    ("e_bluewater", "e_mer", "transports_for", {"note": "export freight"}, "F-5008", 0.92),
]
