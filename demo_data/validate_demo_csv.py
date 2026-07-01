#!/usr/bin/env python3
"""
validate_demo_csv.py — Kiểm tra bộ CSV demo SAFE trước khi import Odoo UI.

Usage:
    python3 demo_data/validate_demo_csv.py

Exit codes:
    0 = PASS (mọi check OK)
    1 = FAIL (có ít nhất 1 check fail)

KHÔNG ghi vào database, KHÔNG gọi Odoo. Chỉ parse CSV và check logic.
"""

import csv
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

FILES = {
    "partners": "01_res_partner_clients_SAFE.csv",
    "products": "02_product_template_services_SAFE.csv",
    "leads":    "03_crm_lead_opportunities_SAFE.csv",
    "quotes":   "04_sale_order_demo_quotes_FIXED_OPTIONAL.csv",
    "lines":    "05_sale_order_line_demo_quotes_FIXED_OPTIONAL.csv",
    "events":   "06_calendar_demo_events_REFERENCE_ONLY.csv",
}

ALLOWED_STAGES = {"Lead Qualified", "Onboarding Docs", "Quoted", "Won", "Lost"}
PROBABILITY_RANGES = {
    "Won": (100, 100),
    "Lost": (0, 0),
    "Quoted": (50, 80),
    "Onboarding Docs": (25, 50),
    "Lead Qualified": (10, 30),
}


class Report:
    def __init__(self):
        self.checks = []   # list of (name, status, detail)

    def add(self, name, status, detail=""):
        self.checks.append((name, status, detail))

    def passed(self):
        return [c for c in self.checks if c[1] == "PASS"]

    def failed(self):
        return [c for c in self.checks if c[1] == "FAIL"]


def read_csv(path):
    with open(path, "r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def check_parse(report):
    """Check all files parse correctly."""
    data = {}
    for key, fname in FILES.items():
        full = os.path.join(HERE, fname)
        try:
            rows = read_csv(full)
            data[key] = rows
            report.add(f"parse:{fname}", "PASS", f"{len(rows)} rows")
        except Exception as e:
            data[key] = []
            report.add(f"parse:{fname}", "FAIL", str(e))
    return data


def check_external_ids(report, data):
    """No duplicate External IDs across all files."""
    seen = {}
    duplicates = []
    for key, rows in data.items():
        for row in rows:
            ext_id = (row.get("id") or "").strip()
            if not ext_id:
                continue
            if ext_id in seen:
                duplicates.append((ext_id, seen[ext_id], key))
            else:
                seen[ext_id] = key
    if duplicates:
        report.add("external_ids:no_duplicates", "FAIL",
                   f"{len(duplicates)} duplicates e.g. {duplicates[0]}")
    else:
        report.add("external_ids:no_duplicates", "PASS",
                   f"{len(seen)} unique IDs")


def check_default_codes(report, data):
    """No duplicate product default_code."""
    codes = Counter()
    for row in data["products"]:
        code = (row.get("default_code") or "").strip()
        if code:
            codes[code] += 1
    dupes = [c for c, n in codes.items() if n > 1]
    if dupes:
        report.add("products:default_code_unique", "FAIL", f"dupes: {dupes}")
    else:
        report.add("products:default_code_unique", "PASS",
                   f"{len(codes)} unique codes")


def check_crm_partners_exist(report, data):
    """Every CRM partner_id/name exists in contacts."""
    partner_names = {(r.get("name") or "").strip() for r in data["partners"]}
    missing = []
    for row in data["leads"]:
        pn = (row.get("partner_id/name") or "").strip()
        if pn and pn not in partner_names:
            missing.append(pn)
    if missing:
        report.add("crm:partner_exists_in_contacts", "FAIL",
                   f"missing: {missing}")
    else:
        report.add("crm:partner_exists_in_contacts", "PASS",
                   f"{len(data['leads'])} leads, all partners match")


def check_crm_stages(report, data):
    """All CRM leads use allowed stage names."""
    bad = []
    for row in data["leads"]:
        stage = (row.get("stage_id/name") or "").strip()
        if stage not in ALLOWED_STAGES:
            bad.append((row.get("name"), stage))
    if bad:
        report.add("crm:stage_allowed", "FAIL", f"bad stages: {bad}")
    else:
        report.add("crm:stage_allowed", "PASS",
                   f"all {len(data['leads'])} leads in allowed stages")


def check_crm_mandatory_pacific(report, data):
    """Pacific lead exists at Quoted or Onboarding Docs."""
    for row in data["leads"]:
        if "Pacific Cargo PNG Ltd - 20ft Lae to Port Moresby" in (row.get("name") or ""):
            stage = (row.get("stage_id/name") or "").strip()
            if stage in ("Quoted", "Onboarding Docs"):
                report.add("crm:pacific_mandatory_lead", "PASS",
                           f"name ok, stage={stage}, prob={row.get('probability')}")
            else:
                report.add("crm:pacific_mandatory_lead", "FAIL",
                           f"Pacific lead stage={stage}, expected Quoted or Onboarding Docs")
            return
    report.add("crm:pacific_mandatory_lead", "FAIL",
               "Pacific Cargo PNG Ltd - 20ft Lae to Port Moresby not found")


def check_crm_probability(report, data):
    """Probability matches stage range."""
    bad = []
    for row in data["leads"]:
        stage = (row.get("stage_id/name") or "").strip()
        try:
            prob = int(row.get("probability") or 0)
        except ValueError:
            bad.append((row.get("name"), "non-numeric probability"))
            continue
        lo, hi = PROBABILITY_RANGES.get(stage, (0, 100))
        if not (lo <= prob <= hi):
            bad.append((row.get("name"), f"stage={stage} prob={prob} not in [{lo},{hi}]"))
    if bad:
        report.add("crm:probability_in_range", "FAIL",
                   f"bad: {bad[:3]}{'...' if len(bad) > 3 else ''}")
    else:
        report.add("crm:probability_in_range", "PASS",
                   f"{len(data['leads'])} leads probability OK")


def check_quote_order_ids(report, data):
    """Every order_id/id in lines exists in quotes."""
    quote_ids = {(r.get("id") or "").strip() for r in data["quotes"]}
    missing = []
    for row in data["lines"]:
        oid = (row.get("order_id/id") or "").strip()
        if oid and oid not in quote_ids:
            missing.append(oid)
    if missing:
        report.add("lines:order_id_in_quotes", "FAIL",
                   f"missing orders: {missing}")
    else:
        report.add("lines:order_id_in_quotes", "PASS",
                   f"{len(data['lines'])} lines all reference existing quotes")


def check_line_products(report, data):
    """Every line product_id/name exists in products."""
    product_names = {(r.get("name") or "").strip() for r in data["products"]}
    missing = []
    for row in data["lines"]:
        pn = (row.get("product_id/name") or "").strip()
        if pn and pn not in product_names:
            missing.append(pn)
    if missing:
        report.add("lines:product_in_products", "FAIL",
                   f"missing products: {missing}")
    else:
        report.add("lines:product_in_products", "PASS",
                   f"{len(data['lines'])} lines all reference existing products")


def check_line_subtotals(report, data):
    """price_subtotal == product_uom_qty * price_unit."""
    bad = []
    for row in data["lines"]:
        try:
            qty = float(row.get("product_uom_qty") or 0)
            unit = float(row.get("price_unit") or 0)
            sub = float(row.get("price_subtotal") or 0)
        except ValueError:
            bad.append((row.get("id"), "non-numeric"))
            continue
        expected = round(qty * unit, 2)
        if abs(sub - expected) > 0.01:
            bad.append((row.get("id"), f"{qty}*{unit}={expected} != {sub}"))
    if bad:
        report.add("lines:subtotal_correct", "FAIL",
                   f"bad: {bad[:3]}{'...' if len(bad) > 3 else ''}")
    else:
        report.add("lines:subtotal_correct", "PASS",
                   f"{len(data['lines'])} lines subtotal OK")


def check_quote_totals(report, data):
    """Each quote amount_untaxed equals sum of its lines subtotals."""
    by_order = defaultdict(float)
    for row in data["lines"]:
        oid = (row.get("order_id/id") or "").strip()
        try:
            sub = float(row.get("price_subtotal") or 0)
        except ValueError:
            continue
        by_order[oid] += sub
    bad = []
    for row in data["quotes"]:
        oid = (row.get("id") or "").strip()
        try:
            au = float(row.get("amount_untaxed") or 0)
        except ValueError:
            bad.append((oid, "non-numeric amount_untaxed"))
            continue
        sum_lines = round(by_order.get(oid, 0), 2)
        if abs(au - sum_lines) > 0.01:
            bad.append((oid, f"amount_untaxed={au} != sum_lines={sum_lines}"))
    if bad:
        report.add("quotes:amount_untaxed_matches_lines", "FAIL",
                   f"bad: {bad}")
    else:
        report.add("quotes:amount_untaxed_matches_lines", "PASS",
                   f"{len(data['quotes'])} quotes totals OK")


def check_contacts_no_website(report, data):
    """Contact SAFE file should NOT have a website column."""
    if not data["partners"]:
        report.add("contacts:no_website_column", "FAIL", "no partner rows")
        return
    headers = list(data["partners"][0].keys())
    has_website = any(h.lower() == "website" for h in headers)
    if has_website:
        report.add("contacts:no_website_column", "FAIL",
                   f"website column present: {headers}")
    else:
        report.add("contacts:no_website_column", "PASS",
                   f"columns: {headers}")


def check_contacts_company_type(report, data):
    """company_type must be lowercase 'company'."""
    bad = []
    for row in data["partners"]:
        ct = (row.get("company_type") or "").strip()
        if ct != "company":
            bad.append((row.get("name"), ct))
    if bad:
        report.add("contacts:company_type_lowercase", "FAIL",
                   f"bad: {bad[:3]}")
    else:
        report.add("contacts:company_type_lowercase", "PASS",
                   f"all {len(data['partners'])} partners use 'company'")


def check_products_uom(report, data):
    """Products should only use 'Units' for uom_id/name and uom_po_id/name."""
    bad = []
    for row in data["products"]:
        uom = (row.get("uom_id/name") or "").strip()
        po_uom = (row.get("uom_po_id/name") or "").strip()
        if uom != "Units" or po_uom != "Units":
            bad.append((row.get("name"), uom, po_uom))
    if bad:
        report.add("products:uom_units_only", "FAIL", f"bad: {bad[:3]}")
    else:
        report.add("products:uom_units_only", "PASS",
                   f"all {len(data['products'])} products use Units")


def check_no_real_emails(report, data):
    """No gmail/yahoo/hotmail/outlook in contacts or leads."""
    banned = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
              "aol.com", "live.com", "icloud.com"}
    bad = []
    for row in data["partners"]:
        em = (row.get("email") or "").lower()
        for b in banned:
            if em.endswith("@" + b):
                bad.append((row.get("name"), em))
    for row in data["leads"]:
        em = (row.get("email_from") or "").lower()
        for b in banned:
            if em.endswith("@" + b):
                bad.append((row.get("name"), em))
    if bad:
        report.add("emails:no_real_domains", "FAIL",
                   f"real-looking: {bad[:3]}")
    else:
        report.add("emails:no_real_domains", "PASS",
                   "no gmail/yahoo/hotmail/etc.")


def main():
    report = Report()
    data = check_parse(report)
    if any(c[1] == "FAIL" for c in report.checks if c[0].startswith("parse:")):
        print_results(report)
        return 1

    check_external_ids(report, data)
    check_default_codes(report, data)
    check_contacts_no_website(report, data)
    check_contacts_company_type(report, data)
    check_products_uom(report, data)
    check_crm_partners_exist(report, data)
    check_crm_stages(report, data)
    check_crm_mandatory_pacific(report, data)
    check_crm_probability(report, data)
    check_quote_order_ids(report, data)
    check_line_products(report, data)
    check_line_subtotals(report, data)
    check_quote_totals(report, data)
    check_no_real_emails(report, data)

    print_results(report)
    return 0 if not report.failed() else 1


def print_results(report):
    print("=" * 80)
    print("DEMO CSV VALIDATION REPORT")
    print("=" * 80)
    max_name = max(len(c[0]) for c in report.checks)
    for name, status, detail in report.checks:
        marker = "PASS" if status == "PASS" else "FAIL"
        print(f"  [{marker}] {name:<{max_name}}  {detail}")
    print("-" * 80)
    passed_n = len(report.passed())
    failed_n = len(report.failed())
    print(f"  TOTAL: {passed_n} PASS / {failed_n} FAIL")
    print("=" * 80)
    if failed_n:
        print("OVERALL: FAIL")
    else:
        print("OVERALL: PASS")


if __name__ == "__main__":
    sys.exit(main())