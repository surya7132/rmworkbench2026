"""Synthetic annual-report financials for two borrowers, built so every
statement ties out by construction (and the validator re-checks it).

Units: INR crore. Format follows Schedule III of the Companies Act 2013
(Balance Sheet, Statement of Profit and Loss) plus an Ind AS 7 cash flow.

Differences from the clickable mockup (so the statements articulate):
  * Vantage prior-year balance-sheet totals corrected so assets = liabilities
    (mockup FY25 and FY24 did not balance).
  * The Rs 180 cr NCD maturing on 9 Feb 2027 is shown as a current maturity
    inside short-term borrowings at 31 Mar 2026 (it falls due within 12 months),
    which is how an auditor would classify it. Short-term borrowings, current
    liabilities, total assets, investing and financing cash flows change with it.
"""

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def S(*xs):
    return round(sum(xs), 2)


def close(a, b, tol=0.005):
    return abs(a - b) <= tol


# ==========================================================================
# VANTAGE INFRA PROJECTS LTD, consolidated, FY2025-26 and FY2024-25
# ==========================================================================
def vantage():
    # ----- Statement of Profit and Loss -----
    pl = {
        "revenue":      (2410.00, 2105.00),
        "other_income": (49.00, 41.00),
        "materials":    (1190.00, 1042.00),
        "subcontract":  (590.00, 521.00),
        "employee":     (168.00, 150.00),
        "other_exp":    (150.00, 124.00),
        "dep":          (66.00, 59.00),
        "finance":      (118.00, 104.00),
        "tax_current":  (31.00, 23.00),
        "tax_deferred": (4.00, 5.00),
    }
    out = {}
    for i, y in enumerate(("fy26", "fy25")):
        g = lambda k: pl[k][i]
        total_income = S(g("revenue"), g("other_income"))
        opex = S(g("materials"), g("subcontract"), g("employee"), g("other_exp"))
        ebitda = round(g("revenue") - opex, 2)
        total_exp = S(opex, g("dep"), g("finance"))
        pbt = round(total_income - total_exp, 2)
        tax = S(g("tax_current"), g("tax_deferred"))
        pat = round(pbt - tax, 2)
        out[y] = dict(total_income=total_income, opex=opex, ebitda=ebitda, total_exp=total_exp,
                      pbt=pbt, tax=tax, pat=pat, eps=round(pat / 5.2, 2))
    assert out["fy26"]["ebitda"] == 312.00 and out["fy26"]["pat"] == 142.00
    assert out["fy25"]["ebitda"] == 268.00 and out["fy25"]["pat"] == 118.00
    PL = dict(items=pl, calc=out)

    # ----- Balance sheet: equity and liabilities -----
    el = {
        "share_capital": (52.00, 52.00),
        "other_equity":  (1068.00, 933.00),
        "ltb":           (1240.00, 1085.00),
        "dtl":           (62.00, 58.00),
        "other_ltl":     (70.00, 66.00),
        "lt_prov":       (48.00, 41.00),
        "stb":           (340.00, 140.00),     # FY26 includes Rs180cr NCD current maturity
        "payables":      (410.00, 372.00),
        "ocl_fin":       (38.00, 31.00),
        "ocl_adv":       (52.00, 46.00),
        "ocl_stat":      (15.00, 13.00),
    }
    # ----- assets -----
    asset = {
        "ppe":      (1020.00, 745.00), "cwip": (250.00, 150.00), "intang": (91.00, 88.00),
        "nc_inv":   (72.00, 55.00), "lt_loans": (108.00, 104.00), "other_nca": (86.00, 80.00),
        "inventories": (380.00, 342.00), "receivables": (560.00, 518.00),
        "contract_assets": (360.00, 372.00), "cash": (275.00, 210.00),
        "other_bank": (80.00, 70.00), "st_loans": (70.00, 61.00), "other_ca": (43.00, 42.00),
    }
    bs = {}
    for i, y in enumerate(("fy26", "fy25")):
        e = lambda k: el[k][i]
        a = lambda k: asset[k][i]
        equity = S(e("share_capital"), e("other_equity"))
        nc_liab = S(e("ltb"), e("dtl"), e("other_ltl"), e("lt_prov"))
        other_nc_liab = S(e("dtl"), e("other_ltl"), e("lt_prov"))
        ocl = S(e("ocl_fin"), e("ocl_adv"), e("ocl_stat"))
        cl = S(e("stb"), e("payables"), ocl)
        tot_el = S(equity, nc_liab, cl)
        nca = S(a("ppe"), a("cwip"), a("intang"), a("nc_inv"), a("lt_loans"), a("other_nca"))
        ca = S(a("inventories"), a("receivables"), a("contract_assets"), a("cash"),
               a("other_bank"), a("st_loans"), a("other_ca"))
        tot_a = S(nca, ca)
        bs[y] = dict(equity=equity, nc_liab=nc_liab, other_nc_liab=other_nc_liab, ocl=ocl, cl=cl,
                     tot_el=tot_el, nca=nca, ca=ca, tot_a=tot_a)
        assert close(tot_el, tot_a), (y, tot_el, tot_a)
    assert bs["fy26"]["tot_a"] == 3395.00 and bs["fy25"]["tot_a"] == 2837.00
    assert bs["fy26"]["cl"] == 855.00 and bs["fy26"]["equity"] == 1120.00
    # net worth roll: 985 + 142 - dividend 7 = 1120
    assert close(bs["fy25"]["equity"] + out["fy26"]["pat"] - 7.00, bs["fy26"]["equity"])
    assert close(933.00 + 142.00 - 7.00, 1068.00)

    # ----- Cash flow (indirect, Ind AS 7); interest paid classified in financing -----
    cf26 = dict(
        pbt=177.00, dep=66.00, finance=118.00, int_income=-31.00,
        inventories=-38.00, recv=-30.00, payables=38.00, other_assets=-10.00, other_liab=26.00,
        tax_paid=-31.00,
        capex=-448.00, disposal=4.00, nc_inv=-17.00, loans_other=-10.00, other_bank=-10.00, int_recv=31.00,
        lt_proceeds=560.00, lt_repay=-225.00, st_net=20.00, dividend=-7.00, int_paid=-118.00,
        opening=210.00)
    cf25 = dict(
        pbt=146.00, dep=59.00, finance=104.00, int_income=-26.00,
        inventories=-22.00, recv=-31.00, payables=28.00, other_assets=0.00, other_liab=10.00,
        tax_paid=-28.00,
        capex=-233.00, disposal=3.00, nc_inv=-14.00, loans_other=-9.00, other_bank=-6.00, int_recv=26.00,
        lt_proceeds=305.00, lt_repay=-180.00, st_net=20.00, dividend=-3.00, int_paid=-104.00,
        opening=165.00)
    cf = {}
    for y, c in (("fy26", cf26), ("fy25", cf25)):
        opwc = S(c["pbt"], c["dep"], c["finance"], c["int_income"])
        wc = S(c["inventories"], c["recv"], c["payables"], c["other_assets"], c["other_liab"])
        cash_ops = S(opwc, wc)
        cfo = S(cash_ops, c["tax_paid"])
        cfi = S(c["capex"], c["disposal"], c["nc_inv"], c["loans_other"], c["other_bank"], c["int_recv"])
        cff = S(c["lt_proceeds"], c["lt_repay"], c["st_net"], c["dividend"], c["int_paid"])
        net = S(cfo, cfi, cff)
        closing = S(c["opening"], net)
        cf[y] = dict(c, opwc=opwc, wc=wc, cash_ops=cash_ops, cfo=cfo, cfi=cfi, cff=cff, net=net, closing=closing)
    assert cf["fy26"]["cfo"] == 285.00 and cf["fy25"]["cfo"] == 240.00
    assert cf["fy26"]["closing"] == 275.00 and cf["fy25"]["closing"] == 210.00
    assert close(cf["fy26"]["pbt"], out["fy26"]["pbt"]) and close(cf["fy25"]["pbt"], out["fy25"]["pbt"])
    # cash flow closing equals balance-sheet cash and cash equivalents
    assert cf["fy26"]["closing"] == asset["cash"][0] and cf["fy25"]["closing"] == asset["cash"][1]
    # borrowings roll: LT 1085 - 180 (to current) + 335 = 1240; ST 140 + 20 + 180 = 340
    assert close(1085 - 180 + (560 - 225), 1240) and close(140 + 20 + 180, 340)

    # ----- Notes -----
    note14 = {   # Borrowings: (label, fy26, fy25)
        "noncurrent": [("Secured term loans from banks", 1090.00, 790.00),
                       ("Secured redeemable non-convertible debentures", 0.00, 180.00),
                       ("Rupee loans from financial institutions (secured)", 95.00, 80.00),
                       ("Vehicle and equipment loans (secured)", 25.00, 20.00),
                       ("Unsecured loans from related parties", 30.00, 15.00)],
        "current": [("Working capital facilities from banks (secured)", 112.00, 95.00),
                    ("Cash credit and WCDL from banks (secured)", 48.00, 45.00),
                    ("Current maturities of long-term debt: 9.15% secured NCDs, redeemable 9 February 2027",
                     180.00, 0.00)],
    }
    assert close(S(*[r[1] for r in note14["noncurrent"]]), 1240.00)
    assert close(S(*[r[2] for r in note14["noncurrent"]]), 1085.00)
    assert close(S(*[r[1] for r in note14["current"]]), 340.00)
    assert close(S(*[r[2] for r in note14["current"]]), 140.00)
    note31 = [("Claims against the Group not acknowledged as debt (arbitration and contractor claims)", 128.00, 105.00),
              ("Income tax matters under dispute", 94.00, 88.00),
              ("Indirect tax (GST and service tax) matters under dispute", 61.00, 58.00),
              ("Guarantees given on behalf of SPVs and joint ventures", 129.00, 99.00)]
    assert close(S(*[r[1] for r in note31]), 412.00) and close(S(*[r[2] for r in note31]), 350.00)

    # ----- Spread lines: (code, label, statement, fy26, fy25, fy24, page, pdf_page, note) -----
    tcl = bs["fy26"]["cl"]
    lines = [
        ("L01", "Revenue from operations", "P&L", 2410.00, 2105.00, 1880.00, "p. 82", 1),
        ("L02", "EBITDA", "P&L", out["fy26"]["ebitda"], out["fy25"]["ebitda"], 231.00, "p. 82", 1),
        ("L03", "Profit after tax", "P&L", out["fy26"]["pat"], out["fy25"]["pat"], 96.00, "p. 82", 1),
        ("L04", "Net worth (total equity)", "Balance sheet", 1120.00, 985.00, 870.00, "p. 84", 3),
        ("L05", "Long-term borrowings (balance sheet)", "Balance sheet", 1240.00, 1085.00, 960.00, "p. 84", 3),
        ("L06", "Other non-current liabilities", "Balance sheet", bs["fy26"]["other_nc_liab"], bs["fy25"]["other_nc_liab"], 150.00, "p. 84", 3),
        ("L07", "Trade payables", "Current liabilities", 410.00, 372.00, 340.00, "p. 85", 4),
        ("L08", "Short-term borrowings (incl. current maturities)", "Current liabilities", 340.00, 140.00, 120.00, "p. 85", 4),
        ("L09", "Other current liabilities", "Current liabilities", bs["fy26"]["ocl"], bs["fy25"]["ocl"], 84.00, "p. 85", 4),
        ("L10", "Total current liabilities (reported)", "Current liabilities", tcl, bs["fy25"]["cl"], 544.00, "p. 85", 4),
        ("L11", "Total equity and liabilities", "Balance sheet", bs["fy26"]["tot_el"], bs["fy25"]["tot_el"], 2524.00, "p. 85", 4),
        ("L12", "Total assets", "Balance sheet", bs["fy26"]["tot_a"], bs["fy25"]["tot_a"], 2524.00, "p. 83", 2),
        ("L13", "Contingent liabilities", "Notes", 412.00, 350.00, 310.00, "p. 112", 7),
        ("L14", "Net cash from operating activities", "Cash flow", cf["fy26"]["cfo"], cf["fy25"]["cfo"], 205.00, "p. 86", 5),
        ("L15", "Net cash from investing activities", "Cash flow", cf["fy26"]["cfi"], cf["fy25"]["cfi"], -200.00, "p. 86", 5),
        ("L16", "Net cash from financing activities", "Cash flow", cf["fy26"]["cff"], cf["fy25"]["cff"], 20.00, "p. 86", 5),
        ("L17", "Opening cash and cash equivalents", "Cash flow", 210.00, 165.00, 140.00, "p. 86", 5),
        ("L18", "Closing cash and cash equivalents", "Cash flow", cf["fy26"]["closing"], cf["fy25"]["closing"], 165.00, "p. 86", 5),
    ]
    # FY24 column ties on its own (spread from the FY2024-25 annual report)
    assert close(870 + 960 + 150 + 544, 2524) and close(340 + 120 + 84, 544)
    assert close(205 - 200 + 20, 25) and close(140 + 25, 165)
    return dict(pl=PL, el=el, asset=asset, bs=bs, cf=cf, note14=note14, note31=note31, lines=lines)


# --- planted *extraction* errors (the PDF itself is correct) -----------------
# What the extraction engine read, versus what the page prints.
VANTAGE_EXTRACTION_ERRORS = {
    # code: (extracted_fy26, confidence, note)
    "L05": (124.00, 91, "Decimal point dropped"),
    "L09": (98.80, 94, "Misread digits 105.00 as 98.80"),
    "L13": (412.00, 62, "Scanned table, low contrast"),
}
VANTAGE_NOTE_REFS = {"L05": ("Note 14 borrowings", 1240.00, "p. 97")}
VANTAGE_CONF = {"L01": 98, "L02": 97, "L03": 98, "L04": 96, "L06": 95, "L07": 96, "L08": 95, "L10": 96,
                "L11": 97, "L12": 97, "L14": 95, "L15": 95, "L16": 94, "L17": 95, "L18": 95}


# ==========================================================================
# MERIDIAN FABRICS LTD, standalone, FY2025-26 and FY2024-25 (clean document)
# ==========================================================================
def meridian():
    pl = {"revenue": (412.40, 371.20), "other_income": (6.10, 5.20),
          "materials": (248.00, 226.50), "employee": (40.20, 36.80), "power": (24.30, 22.10),
          "other_exp": (44.30, 40.20), "dep": (17.80, 16.90), "finance": (13.90, 14.30),
          "tax_current": (7.40, 4.80), "tax_deferred": (0.20, 0.20)}
    calc = {}
    for i, y in enumerate(("fy26", "fy25")):
        g = lambda k: pl[k][i]
        opex = S(g("materials"), g("employee"), g("power"), g("other_exp"))
        ebitda = round(g("revenue") - opex, 2)
        total_income = S(g("revenue"), g("other_income"))
        total_exp = S(opex, g("dep"), g("finance"))
        pbt = round(total_income - total_exp, 2)
        tax = S(g("tax_current"), g("tax_deferred"))
        pat = round(pbt - tax, 2)
        calc[y] = dict(opex=opex, ebitda=ebitda, total_income=total_income, total_exp=total_exp,
                       pbt=pbt, tax=tax, pat=pat, eps=round(pat / 2.4, 2))
    assert calc["fy26"]["pbt"] == 30.00 and calc["fy26"]["pat"] == 22.40
    assert calc["fy25"]["pbt"] == 19.60 and calc["fy25"]["pat"] == 14.60

    # equity: NW25 = 140.00, FY26 = 140.00 + 22.40 - 2.40 dividend = 160.00
    el = {"share_capital": (24.00, 24.00), "other_equity": (136.00, 116.00),
          "ltb": (70.00, 74.00), "dtl": (11.50, 11.30), "lt_prov": (4.50, 4.20),
          "stb": (120.00, 118.00), "payables": (68.00, 64.00),
          "ocl_fin": (9.00, 8.00), "ocl_adv": (5.00, 5.00), "ocl_stat": (4.00, 4.00)}
    asset = {"ppe": (148.00, 150.20), "cwip": (6.00, 4.10), "intang": (2.50, 2.80),
             "nc_inv": (4.00, 4.00), "lt_loans": (7.00, 6.40), "other_nca": (5.50, 5.10),
             "inventories": (112.00, 106.40), "cash": (None, 13.00), "other_bank": (9.00, 11.60),
             "st_loans": (24.00, 21.50), "other_ca": (16.00, 14.10), "receivables": (None, 89.30)}
    # cash flow FY26 (interest paid in financing); cash and receivables are derived
    c = dict(pbt=30.00, dep=17.80, finance=13.90, int_income=-3.20,
             inventories=-5.60, recv=None, payables=4.00, other_assets=-4.40, other_liab=1.30,
             tax_paid=-7.40,
             capex=-17.20, disposal=0.80, nc_inv=0.00, loans_other=-1.00, other_bank=2.60, int_recv=3.20,
             lt_proceeds=26.00, lt_repay=-30.00, st_net=2.00, dividend=-2.40, int_paid=-13.90, opening=13.00)
    equity26 = S(el["share_capital"][0], el["other_equity"][0])
    nc26 = S(el["ltb"][0], el["dtl"][0], el["lt_prov"][0])
    ocl26 = S(el["ocl_fin"][0], el["ocl_adv"][0], el["ocl_stat"][0])
    cl26 = S(el["stb"][0], el["payables"][0], ocl26)
    tot26 = S(equity26, nc26, cl26)
    nca26 = S(*[asset[k][0] for k in ("ppe", "cwip", "intang", "nc_inv", "lt_loans", "other_nca")])
    # receivables movement is the one unknown; solve it so cash flow closes to the balance sheet
    known_ca = S(asset["inventories"][0], asset["other_bank"][0], asset["st_loans"][0], asset["other_ca"][0])
    # cash26 + recv26 = tot26 - nca26 - known_ca ; cash26 = 13 + CFO + CFI + CFF ; CFO depends on recv
    cfi = S(c["capex"], c["disposal"], c["nc_inv"], c["loans_other"], c["other_bank"], c["int_recv"])
    cff = S(c["lt_proceeds"], c["lt_repay"], c["st_net"], c["dividend"], c["int_paid"])
    other_wc = S(c["inventories"], c["payables"], c["other_assets"], c["other_liab"])
    opwc = S(c["pbt"], c["dep"], c["finance"], c["int_income"])
    rest = round(tot26 - nca26 - known_ca, 2)           # = cash26 + recv26
    # cash26 = 13 + (opwc + other_wc + dRecv + tax) + cfi + cff, recv26 = 89.30 - dRecv
    base = S(13.00, opwc, other_wc, c["tax_paid"], cfi, cff)   # cash26 excluding dRecv
    # cash26 + recv26 = base + dRecv + 89.30 - dRecv  -> must equal rest
    delta = round(rest - (base + 89.30), 2)               # mismatch to absorb via other_assets
    c["other_assets"] = round(c["other_assets"] + delta, 2)   # keep the identity exact
    other_wc = S(c["inventories"], c["payables"], c["other_assets"], c["other_liab"])
    base = S(13.00, opwc, other_wc, c["tax_paid"], cfi, cff)
    recv_change = -9.60                                   # receivables grew by 9.60 (88 days -> 85 days)
    c["recv"] = recv_change
    cfo = S(opwc, other_wc, recv_change, c["tax_paid"])
    cash26 = S(13.00, cfo, cfi, cff)
    recv26 = round(89.30 - recv_change, 2)
    asset["cash"] = (cash26, 13.00)
    asset["receivables"] = (recv26, 89.30)
    return _meridian_finish(pl, calc, el, asset, c, cfo, cfi, cff, cash26)


def _meridian_finish(pl, calc, el, asset, c26, cfo26, cfi26, cff26, cash26):
    bs = {}
    for i, y in enumerate(("fy26", "fy25")):
        e = lambda k: el[k][i]
        a = lambda k: asset[k][i]
        equity = S(e("share_capital"), e("other_equity"))
        other_nc = S(e("dtl"), e("lt_prov"))
        nc_liab = S(e("ltb"), other_nc)
        ocl = S(e("ocl_fin"), e("ocl_adv"), e("ocl_stat"))
        cl = S(e("stb"), e("payables"), ocl)
        tot_el = S(equity, nc_liab, cl)
        nca = S(a("ppe"), a("cwip"), a("intang"), a("nc_inv"), a("lt_loans"), a("other_nca"))
        ca = S(a("inventories"), a("receivables"), a("cash"), a("other_bank"), a("st_loans"), a("other_ca"))
        tot_a = S(nca, ca)
        bs[y] = dict(equity=equity, other_nc_liab=other_nc, ocl=ocl, cl=cl, tot_el=tot_el, nca=nca, ca=ca, tot_a=tot_a)
        assert close(tot_el, tot_a, 0.011), (y, tot_el, tot_a)
    assert close(bs["fy25"]["equity"] + calc["fy26"]["pat"] - 2.40, bs["fy26"]["equity"])
    c25 = dict(pbt=19.60, dep=16.90, finance=14.30, int_income=-2.90, inventories=-9.60, recv=-9.80,
               payables=3.50, other_assets=-1.20, other_liab=0.90, tax_paid=-4.80,
               capex=-14.30, disposal=0.50, nc_inv=0.00, loans_other=-0.40, other_bank=-2.10, int_recv=2.90,
               lt_proceeds=18.00, lt_repay=-14.50, st_net=3.00, dividend=-1.20, int_paid=-14.30, opening=8.50)
    cf = {}
    for y, c in (("fy26", c26), ("fy25", c25)):
        opwc = S(c["pbt"], c["dep"], c["finance"], c["int_income"])
        wc = S(c["inventories"], c["recv"], c["payables"], c["other_assets"], c["other_liab"])
        cfo = S(opwc, wc, c["tax_paid"])
        cfi = S(c["capex"], c["disposal"], c["nc_inv"], c["loans_other"], c["other_bank"], c["int_recv"])
        cff = S(c["lt_proceeds"], c["lt_repay"], c["st_net"], c["dividend"], c["int_paid"])
        closing = S(c["opening"], cfo, cfi, cff)
        cf[y] = dict(c, opwc=opwc, wc=wc, cash_ops=S(opwc, wc), cfo=cfo, cfi=cfi, cff=cff, net=S(cfo, cfi, cff), closing=closing)
    assert close(cf["fy26"]["closing"], asset["cash"][0], 0.011), (cf["fy26"]["closing"], asset["cash"][0])
    assert close(cf["fy25"]["closing"], asset["cash"][1], 0.011), (cf["fy25"]["closing"], asset["cash"][1])
    note13 = {"noncurrent": [("Secured term loans from banks", 58.00, 61.00),
                             ("Vehicle loans (secured)", 3.00, 4.00),
                             ("Unsecured loans from promoters", 9.00, 9.00)],
              "current": [("Packing credit in foreign currency (secured)", 52.00, 50.00),
                          ("Working capital demand loans (secured)", 36.00, 38.00),
                          ("Current maturities of long-term debt", 32.00, 30.00)]}
    assert close(S(*[r[1] for r in note13["noncurrent"]]), 70.00) and close(S(*[r[2] for r in note13["noncurrent"]]), 74.00)
    assert close(S(*[r[1] for r in note13["current"]]), 120.00) and close(S(*[r[2] for r in note13["current"]]), 118.00)
    note29 = [("Bills discounted with banks (export bills)", 8.60, 7.20),
              ("Income tax matters under dispute", 4.10, 3.60),
              ("Customs and GST matters under dispute", 2.10, 1.80)]
    assert close(S(*[r[1] for r in note29]), 14.80) and close(S(*[r[2] for r in note29]), 12.60)
    lines = [
        ("L01", "Revenue from operations", "P&L", 412.40, 371.20, 338.60, "p. 58", 1),
        ("L02", "EBITDA", "P&L", calc["fy26"]["ebitda"], calc["fy25"]["ebitda"], 38.90, "p. 58", 1),
        ("L03", "Profit after tax", "P&L", calc["fy26"]["pat"], calc["fy25"]["pat"], 11.80, "p. 58", 1),
        ("L04", "Net worth (total equity)", "Balance sheet", bs["fy26"]["equity"], bs["fy25"]["equity"], 125.40, "p. 60", 3),
        ("L05", "Long-term borrowings (balance sheet)", "Balance sheet", 70.00, 74.00, 79.00, "p. 60", 3),
        ("L06", "Other non-current liabilities", "Balance sheet", bs["fy26"]["other_nc_liab"], bs["fy25"]["other_nc_liab"], 15.00, "p. 60", 3),
        ("L07", "Trade payables", "Current liabilities", 68.00, 64.00, 58.00, "p. 61", 4),
        ("L08", "Short-term borrowings (incl. current maturities)", "Current liabilities", 120.00, 118.00, 112.00, "p. 61", 4),
        ("L09", "Other current liabilities", "Current liabilities", bs["fy26"]["ocl"], bs["fy25"]["ocl"], 15.00, "p. 61", 4),
        ("L10", "Total current liabilities (reported)", "Current liabilities", bs["fy26"]["cl"], bs["fy25"]["cl"], 185.00, "p. 61", 4),
        ("L11", "Total equity and liabilities", "Balance sheet", bs["fy26"]["tot_el"], bs["fy25"]["tot_el"], 404.40, "p. 61", 4),
        ("L12", "Total assets", "Balance sheet", bs["fy26"]["tot_a"], bs["fy25"]["tot_a"], 404.40, "p. 59", 2),
        ("L13", "Contingent liabilities", "Notes", 14.80, 12.60, 10.90, "p. 84", 7),
        ("L14", "Net cash from operating activities", "Cash flow", cf["fy26"]["cfo"], cf["fy25"]["cfo"], 28.60, "p. 62", 5),
        ("L15", "Net cash from investing activities", "Cash flow", cf["fy26"]["cfi"], cf["fy25"]["cfi"], -14.20, "p. 62", 5),
        ("L16", "Net cash from financing activities", "Cash flow", cf["fy26"]["cff"], cf["fy25"]["cff"], -9.00, "p. 62", 5),
        ("L17", "Opening cash and cash equivalents", "Cash flow", 13.00, 8.50, 3.10, "p. 62", 5),
        ("L18", "Closing cash and cash equivalents", "Cash flow", cf["fy26"]["closing"], cf["fy25"]["closing"], 8.50, "p. 62", 5),
    ]
    assert close(125.40 + 79.00 + 15.00 + 185.00, 404.40) and close(58 + 112 + 15, 185.00)
    assert close(28.60 - 14.20 - 9.00, 5.40) and close(3.10 + 5.40, 8.50)
    return dict(pl=dict(items=pl, calc=calc), el=el, asset=asset, bs=bs, cf=cf, note14=note13, note31=note29, lines=lines)
