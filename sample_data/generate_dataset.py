"""
K4Y Invoice Dataset Generator
==============================
Generates 100 payable invoices + 150 receivable invoices with realistic
correlated data for the AI-Driven Invoice Analysis FinTech System.

Output: dataset.json — all structured data ready for DB seeding + PDF rendering.

COMPLIANCE TEST CONVENTION:
  - All NORMAL invoices have invoice_number ending in a 2-digit suffix that is NOT "67".
  - All FLAGGED invoices (deliberately injected to trigger compliance checks) end in "67".
  - This makes flagged invoices visually identifiable in the DB and UI.
  - The compliance engine itself does not look at the suffix — it's purely a marker for humans.
"""

import json
import random
import uuid
from datetime import date, timedelta, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

random.seed(67)  # Reproducible

OUTPUT = Path(__file__).parent / "dataset.json"

# ─── Company ────────────────────────────────────────────────────────────────

COMPANY_ID = "7bf697fc-7220-40c7-9678-542d624d22ad"

COMPANY = {
    "id": COMPANY_ID,
    "name": "K4Y",
    "domain": "k4y.io",
    "country": "US",
    "address": "1200 Tech Park Drive, Suite 400, Austin, TX 78701",
    "phone": "+1 (512) 555-0147",
    "email": "finance@k4y.io",
    "tax_id": "84-2957301",
    "default_tax_rate": 0,
    "logo_url": None,
}

# ─── Vendors (10 + 1 test = 11 total after injection) ──────────────────────

VENDORS = [
    # Template 1 vendors
    {
        "name": "NexaCloud Solutions",
        "email": "billing@nexacloud.com",
        "phone": "+1 (415) 555-0231",
        "tax_id": "94-3218765",
        "address": {
            "street": "2500 Mission Street, Suite 300",
            "city": "San Francisco",
            "state": "CA",
            "postal_code": "94110",
            "country": "USA",
        },
        "template": 1,
        "category": "cloud_hosting",
        "frequency": "monthly",
        "amount_range": (1800, 2200),
        "tax_rate": 0,
        "currency": "USD",
        "payment_terms": 30,
        "iban": None,
    },
    {
        "name": "Apex Office Supply Co",
        "email": "accounts@apexoffice.com",
        "phone": "+1 (214) 555-0189",
        "tax_id": "75-4129087",
        "address": {
            "street": "890 Commerce Boulevard",
            "city": "Dallas",
            "state": "TX",
            "postal_code": "75201",
            "country": "USA",
        },
        "template": 1,
        "category": "office_supplies",
        "frequency": "irregular",
        "amount_range": (75, 450),
        "tax_rate": 8.25,
        "currency": "USD",
        "payment_terms": 15,
        "iban": None,
    },
    # Template 2 vendors
    {
        "name": "Prisma Software Inc",
        "email": "invoices@prismasoftware.io",
        "phone": "+1 (206) 555-0342",
        "tax_id": "91-5623487",
        "address": {
            "street": "44 Federal Street",
            "city": "Seattle",
            "state": "WA",
            "postal_code": "98101",
            "country": "USA",
        },
        "template": 2,
        "category": "software_licenses",
        "frequency": "quarterly",
        "amount_range": (3500, 4200),
        "tax_rate": 0,
        "currency": "USD",
        "payment_terms": 30,
        "iban": None,
    },
    {
        "name": "CodeForge Contractors",
        "email": "payments@codeforge.dev",
        "phone": "+1 (503) 555-0478",
        "tax_id": "93-7821456",
        "address": {
            "street": "1120 NW Couch Street, Unit 5",
            "city": "Portland",
            "state": "OR",
            "postal_code": "97209",
            "country": "USA",
        },
        "template": 2,
        "category": "freelance_contractors",
        "frequency": "project",
        "amount_range": (2000, 8500),
        "tax_rate": 0,
        "currency": "USD",
        "payment_terms": 30,
        "iban": None,
    },
    # Template 3 vendors
    {
        "name": "Summit Legal Partners",
        "email": "billing@summitlegal.com",
        "phone": "+1 (312) 555-0567",
        "tax_id": "36-9012345",
        "address": {
            "street": "225 West Wacker Drive, Floor 18",
            "city": "Chicago",
            "state": "IL",
            "postal_code": "60606",
            "country": "USA",
        },
        "template": 3,
        "category": "legal_accounting",
        "frequency": "quarterly",
        "amount_range": (1500, 4000),
        "tax_rate": 0,
        "currency": "USD",
        "payment_terms": 45,
        "iban": None,
    },
    {
        "name": "Ironside Hardware Corp",
        "email": "sales@ironsidehw.com",
        "phone": "+1 (512) 555-0698",
        "tax_id": "74-5647382",
        "address": {
            "street": "4400 Metric Boulevard",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78744",
            "country": "USA",
        },
        "template": 3,
        "category": "hardware",
        "frequency": "occasional",
        "amount_range": (5000, 18000),
        "tax_rate": 7.5,
        "currency": "USD",
        "payment_terms": 30,
        "iban": None,
    },
    # Template 4 vendors
    {
        "name": "Meridian Workspace LLC",
        "email": "leasing@meridianws.com",
        "phone": "+1 (512) 555-0823",
        "tax_id": "74-8901234",
        "address": {
            "street": "3100 South Lamar Boulevard",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78704",
            "country": "USA",
        },
        "template": 4,
        "category": "office_rent",
        "frequency": "monthly",
        "amount_range": (4500, 4500),  # fixed
        "tax_rate": 0,
        "currency": "USD",
        "payment_terms": 30,
        "iban": None,
    },
    {
        "name": "Broadleaf Marketing Group",
        "email": "finance@broadleafmktg.com",
        "phone": "+1 (737) 555-0912",
        "tax_id": "74-2345678",
        "address": {
            "street": "800 West 5th Street, Suite 200",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78703",
            "country": "USA",
        },
        "template": 4,
        "category": "marketing",
        "frequency": "bimonthly",
        "amount_range": (1200, 3000),
        "tax_rate": 0,
        "currency": "USD",
        "payment_terms": 30,
        "iban": None,
    },
    # Template 5 vendors
    {
        "name": "DataVault Security Inc",
        "email": "ap@datavaultsec.com",
        "phone": "+1 (571) 555-1045",
        "tax_id": "54-6789012",
        "address": {
            "street": "1750 Tysons Boulevard, Suite 1100",
            "city": "McLean",
            "state": "VA",
            "postal_code": "22102",
            "country": "USA",
        },
        "template": 5,
        "category": "cybersecurity",
        "frequency": "quarterly",
        "amount_range": (2800, 3500),
        "tax_rate": 0,
        "currency": "USD",
        "payment_terms": 30,
        "iban": "US42DVLT00192837465501",
    },
    {
        "name": "Greenline Facilities Mgmt",
        "email": "invoicing@greenlinefm.com",
        "phone": "+1 (512) 555-1167",
        "tax_id": "74-3456789",
        "address": {
            "street": "5520 Burnet Road",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78756",
            "country": "USA",
        },
        "template": 5,
        "category": "facilities",
        "frequency": "monthly",
        "amount_range": (600, 800),
        "tax_rate": 6.0,
        "currency": "USD",
        "payment_terms": 15,
        "iban": "US78GLFM00293847561002",
    },
]

# ─── Clients (8 + 1 test = 9 total after injection) ─────────────────────────

CLIENTS = [
    {
        "name": "Orion Dynamics Corp",
        "email": "ap@oriondynamics.com",
        "phone": "+1 (650) 555-2001",
        "tax_id": "94-1112233",
        "address": {
            "street": "500 Terry A Francois Blvd",
            "city": "San Francisco",
            "state": "CA",
            "postal_code": "94158",
            "country": "USA",
        },
        "category": "software_dev",
        "payment_behavior": "reliable",
        "avg_days_to_pay": 12,
        "amount_range": (8000, 35000),
        "frequency": "2-3/month",
    },
    {
        "name": "Halcyon Media Inc",
        "email": "accounting@halcyonmedia.com",
        "phone": "+1 (310) 555-2102",
        "tax_id": "95-2223344",
        "address": {
            "street": "8500 Sunset Blvd",
            "city": "Los Angeles",
            "state": "CA",
            "postal_code": "90069",
            "country": "USA",
        },
        "category": "uiux_design",
        "payment_behavior": "slow",  # PROBLEM CLIENT
        "avg_days_to_pay": 55,
        "amount_range": (3000, 12000),
        "frequency": "1-2/month",
    },
    {
        "name": "Steelbridge Capital Group",
        "email": "finance@steelbridgecap.com",
        "phone": "+1 (212) 555-2203",
        "tax_id": "13-3334455",
        "address": {
            "street": "200 Park Avenue, Floor 32",
            "city": "New York",
            "state": "NY",
            "postal_code": "10166",
            "country": "USA",
        },
        "category": "strategy_consulting",
        "payment_behavior": "reliable",
        "avg_days_to_pay": 8,
        "amount_range": (5000, 5000),  # fixed retainer
        "frequency": "monthly",
    },
    {
        "name": "Vertex Health Systems",
        "email": "payables@vertexhealth.org",
        "phone": "+1 (713) 555-2304",
        "tax_id": "76-4445566",
        "address": {
            "street": "6550 Fannin Street, Suite 1800",
            "city": "Houston",
            "state": "TX",
            "postal_code": "77030",
            "country": "USA",
        },
        "category": "software_dev",
        "payment_behavior": "fast",
        "avg_days_to_pay": 7,
        "amount_range": (4000, 20000),
        "frequency": "1-2/month",
    },
    {
        "name": "Cascade Logistics Ltd",
        "email": "finance@cascadelogistics.com",
        "phone": "+1 (206) 555-2405",
        "tax_id": "91-5556677",
        "address": {
            "street": "1201 Third Avenue, Suite 4200",
            "city": "Seattle",
            "state": "WA",
            "postal_code": "98101",
            "country": "USA",
        },
        "category": "training",
        "payment_behavior": "inconsistent",
        "avg_days_to_pay": 30,
        "amount_range": (2000, 6000),
        "frequency": "quarterly",
    },
    {
        "name": "Redwood Analytics Inc",
        "email": "ap@redwoodanalytics.com",
        "phone": "+1 (408) 555-2506",
        "tax_id": "94-6667788",
        "address": {
            "street": "2025 Gateway Place, Suite 300",
            "city": "San Jose",
            "state": "CA",
            "postal_code": "95110",
            "country": "USA",
        },
        "category": "maintenance_retainer",
        "payment_behavior": "reliable",
        "avg_days_to_pay": 15,
        "amount_range": (3500, 3500),  # fixed retainer
        "frequency": "monthly",
    },
    {
        "name": "BlueStar Education Group",
        "email": "procurement@bluestaredu.org",
        "phone": "+1 (617) 555-2607",
        "tax_id": "04-7778899",
        "address": {
            "street": "75 Federal Street",
            "city": "Boston",
            "state": "MA",
            "postal_code": "02110",
            "country": "USA",
        },
        "category": "software_dev",
        "payment_behavior": "reliable",
        "avg_days_to_pay": 20,
        "amount_range": (10000, 25000),
        "frequency": "occasional",  # new client, appears month 8+
    },
    {
        "name": "Pinnacle Real Estate Holdings",
        "email": "finance@pinnaclere.com",
        "phone": "+1 (305) 555-2708",
        "tax_id": "65-8889900",
        "address": {
            "street": "1395 Brickell Avenue, Suite 800",
            "city": "Miami",
            "state": "FL",
            "postal_code": "33131",
            "country": "USA",
        },
        "category": "strategy_consulting",
        "payment_behavior": "exact_on_due",
        "avg_days_to_pay": 0,  # pays exactly on due date
        "amount_range": (6000, 15000),
        "frequency": "monthly",
    },
]

# ─── Line item pools ────────────────────────────────────────────────────────

VENDOR_LINE_ITEMS = {
    "cloud_hosting": [
        "Cloud Compute Instances (Standard)",
        "Managed Kubernetes Cluster",
        "Object Storage (500GB tier)",
        "CDN Bandwidth Overage",
        "SSL Certificate Management",
        "DDoS Protection Service",
        "Database Hosting (PostgreSQL)",
        "Load Balancer Service",
    ],
    "office_supplies": [
        "A4 Copy Paper (10 reams)",
        "Ink Cartridge Set (CMYK)",
        "Ergonomic Desk Chair",
        "Standing Desk Converter",
        "Whiteboard Markers (24-pack)",
        "USB-C Docking Station",
        "Monitor Stand Riser",
        "Cable Management Kit",
        "Desk Organizer Set",
        "Wireless Mouse and Keyboard",
    ],
    "software_licenses": [
        "Enterprise IDE License (Annual)",
        "Project Management Suite (Quarterly)",
        "CI/CD Pipeline License",
        "Code Review Platform Subscription",
        "Cloud Monitoring Dashboard License",
        "API Gateway Management License",
    ],
    "freelance_contractors": [
        "Frontend Development (React)",
        "Backend API Development (Python)",
        "Database Migration Services",
        "Code Audit and Review",
        "Technical Documentation Writing",
        "DevOps Pipeline Setup",
        "Performance Optimization Sprint",
        "Security Penetration Testing",
    ],
    "legal_accounting": [
        "Corporate Legal Consultation",
        "Contract Review and Drafting",
        "Tax Filing Preparation (Quarterly)",
        "Compliance Audit Services",
        "Intellectual Property Review",
        "Employment Law Advisory",
    ],
    "hardware": [
        "Dell PowerEdge R750 Server",
        "Cisco Catalyst 9300 Switch",
        "APC Smart-UPS 3000VA",
        "Samsung 980 PRO NVMe SSD (2TB)",
        "Ubiquiti UniFi AP Pro",
        "Rack Mount Kit (42U)",
        "Cat6a Ethernet Cable (50-pack)",
        "KVM Switch (8-port)",
    ],
    "office_rent": [
        "Monthly Office Lease — Suite 400",
        "Parking Allocation (10 spots)",
        "Common Area Maintenance Fee",
    ],
    "marketing": [
        "Social Media Campaign Management",
        "Content Creation Package",
        "SEO Optimization Sprint",
        "PPC Ad Campaign Setup",
        "Brand Identity Refresh",
        "Email Marketing Automation",
        "Analytics Dashboard Setup",
    ],
    "cybersecurity": [
        "Endpoint Protection License (Quarterly)",
        "Vulnerability Assessment Scan",
        "Security Information & Event Management",
        "Incident Response Retainer",
        "Phishing Simulation Training",
        "Firewall Rule Audit",
    ],
    "facilities": [
        "Office Cleaning Service (Monthly)",
        "HVAC Maintenance Inspection",
        "Pest Control Service",
        "Landscaping Maintenance",
        "Fire Safety Inspection",
    ],
}

CLIENT_LINE_ITEMS = {
    "software_dev": [
        "Backend API Development (Sprint {n})",
        "Frontend Dashboard Development",
        "Database Architecture Design",
        "System Integration Module",
        "Automated Testing Suite",
        "Deployment Pipeline Setup",
        "Performance Optimization",
        "Security Hardening Module",
        "Data Migration Service",
        "API Documentation Package",
    ],
    "uiux_design": [
        "User Research & Persona Development",
        "Wireframe Design Package",
        "High-Fidelity Mockup Design",
        "Interactive Prototype Development",
        "Design System Creation",
        "Usability Testing Sessions",
        "Brand Style Guide Update",
        "Icon Set Design (Custom)",
    ],
    "strategy_consulting": [
        "Strategic Advisory Session",
        "Market Analysis Report",
        "Competitive Landscape Assessment",
        "Technology Roadmap Planning",
        "Digital Transformation Advisory",
        "Process Optimization Review",
    ],
    "maintenance_retainer": [
        "Monthly Maintenance Retainer",
        "Bug Fix and Patch Deployment",
        "Performance Monitoring",
        "Uptime SLA Guarantee",
        "Priority Support Hours (20h)",
    ],
    "training": [
        "Technical Training Workshop (Full Day)",
        "Hands-on Lab Session (Half Day)",
        "Executive Briefing Session",
        "Team Onboarding Program",
        "Certification Prep Course",
    ],
}

# ─── Helpers ────────────────────────────────────────────────────────────────

def uid():
    return str(uuid.uuid4())

def d(val):
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def rand_amount(low, high):
    return d(random.uniform(low, high))

def rand_date(start, end):
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))

# ─── Invoice numbering (67 = flagged, anything else = normal) ───────────────

def _non_67_suffix(idx):
    """
    Return a 4-digit suffix derived from idx where the last two digits are NEVER 67.
    """
    suffix = idx % 10000
    last_two = suffix % 100
    if last_two == 67:
        # Shift to 68 to avoid collision with the flagged marker
        suffix = (suffix - last_two) + 68
    return f"{suffix:04d}"

def inv_number_vendor(vendor_name, idx, issue_date_str):
    prefix = "".join(w[0] for w in vendor_name.split()[:2]).upper()
    year = issue_date_str[:4]
    return f"{prefix}-{year}-{_non_67_suffix(idx)}"

def inv_number_client(client_name, idx):
    prefix = "K4Y"
    return f"{prefix}-INV-{_non_67_suffix(1000 + idx)}"

def force_67(invoice_number, discriminator=None):
    """
    Rewrite the trailing 4-digit suffix so the last two digits are '67'.
    The two digits BEFORE the '67' can be set via `discriminator` (0-99) to
    avoid accidental collisions when two non-related flagged invoices share
    the same prefix and year (e.g. two different CodeForge tests both
    producing 'CC-2025-XX67'). Without a discriminator, the original two
    middle digits are preserved.

    Examples:
      force_67("CC-2025-0034")               -> "CC-2025-0067"
      force_67("CC-2025-0034", discriminator=12) -> "CC-2025-1267"
    """
    if len(invoice_number) < 4:
        return invoice_number + "67"
    head = invoice_number[:-4]
    if discriminator is None:
        middle = invoice_number[-4:-2]
    else:
        middle = f"{discriminator % 100:02d}"
    return f"{head}{middle}67"

START_DATE = date(2025, 6, 1)
END_DATE = date(2026, 7, 15)

# ─── Generate vendor invoices (payables) ────────────────────────────────────

def generate_payables():
    invoices = []
    
    # Per-vendor invoice schedules — tuned to hit ~100 total payables
    schedules = {
        "NexaCloud Solutions": {
            "months": list(range(13)),  # monthly = 13
            "count_per": 1,
        },
        "Apex Office Supply Co": {
            "months": [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 12],  # frequent = 11
            "count_per": 1,
        },
        "Prisma Software Inc": {
            "months": [0, 2, 3, 5, 6, 8, 9, 11, 12],  # near-monthly = 9
            "count_per": 1,
        },
        "CodeForge Contractors": {
            "months": [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12],  # frequent projects = 12
            "count_per": 1,
        },
        "Summit Legal Partners": {
            "months": [0, 2, 3, 5, 6, 8, 9, 11, 12],  # ~monthly = 9
            "count_per": 1,
        },
        "Ironside Hardware Corp": {
            "months": [0, 3, 4, 8, 10],  # occasional, spike in Oct (month 4) = 5
            "count_per": 1,
        },
        "Meridian Workspace LLC": {
            "months": list(range(13)),  # monthly fixed = 13
            "count_per": 1,
        },
        "Broadleaf Marketing Group": {
            "months": [0, 1, 3, 4, 6, 7, 9, 10, 12],  # bimonthly+ = 9
            "count_per": 1,
        },
        "DataVault Security Inc": {
            "months": [0, 2, 3, 5, 6, 8, 9, 11, 12],  # near-monthly = 9
            "count_per": 1,
        },
        "Greenline Facilities Mgmt": {
            "months": list(range(13)),  # monthly = 13
            "count_per": 1,
        },
    }
    
    global_idx = 0
    for vendor in VENDORS:
        vname = vendor["name"]
        sched = schedules[vname]
        cat = vendor["category"]
        
        for mi, month_offset in enumerate(sched["months"]):
            inv_date = START_DATE + timedelta(days=month_offset * 30 + random.randint(0, 5))
            if inv_date > END_DATE:
                continue
            due_date = inv_date + timedelta(days=vendor["payment_terms"])
            
            # Amount — seasonal spike for specific vendors
            low, high = vendor["amount_range"]
            if vname == "NexaCloud Solutions" and month_offset in [7]:  # Jan 2026 annual renewal
                subtotal = rand_amount(4500, 5200)  # spike
            elif vname == "Ironside Hardware Corp" and month_offset == 4:  # Oct 2025 server purchase
                subtotal = rand_amount(15000, 18000)  # big spike
            elif vname == "Prisma Software Inc" and month_offset == 7:  # Jan 2026 annual
                subtotal = rand_amount(12000, 14000)
            else:
                subtotal = rand_amount(low, high)
            
            # Line items
            pool = VENDOR_LINE_ITEMS[cat]
            n_items = random.randint(1, min(4, len(pool)))
            items = random.sample(pool, n_items)
            line_items = []
            remaining = subtotal
            for j, desc in enumerate(items):
                if j == len(items) - 1:
                    item_total = d(remaining)
                else:
                    item_total = d(remaining * random.uniform(0.15, 0.5))
                    remaining -= item_total
                qty = random.choice([1, 2, 3, 5, 10]) if cat in ["office_supplies", "hardware"] else random.choice([1, 1, 1, 2])
                up = d(item_total / qty)
                line_items.append({
                    "description": desc,
                    "quantity": qty,
                    "unit_price": up,
                    "line_subtotal": d(up * qty),
                    "discount": 0,
                })
            
            # Recalculate subtotal from line items
            subtotal = d(sum(li["line_subtotal"] for li in line_items))
            tax_pct = vendor["tax_rate"]
            total_tax = d(subtotal * tax_pct / 100)
            grand_total = d(subtotal + total_tax)
            
            # Status — forced distribution, overridden after generation
            today = date(2026, 5, 25)
            days_old = (today - inv_date).days
            
            if vname == "Meridian Workspace LLC":
                if days_old > vendor["payment_terms"] + 5:
                    status = "paid"
                else:
                    status = "unpaid"
            elif days_old < 20:
                status = "unpaid"
            else:
                status = "_pending"
            
            # Payment data for paid/partially_paid
            amount_paid = 0.0
            payments = []
            if status == "paid":
                amount_paid = grand_total
                pay_date = inv_date + timedelta(days=random.randint(5, vendor["payment_terms"] + 10))
                payments.append({
                    "payment_date": str(pay_date),
                    "amount": grand_total,
                    "method": random.choice(["bank_transfer", "check", "ach"]),
                    "reference": f"PAY-{random.randint(100000, 999999)}",
                })
            elif status == "partially_paid":
                amount_paid = d(grand_total * random.uniform(0.3, 0.7))
                pay_date = inv_date + timedelta(days=random.randint(10, 30))
                payments.append({
                    "payment_date": str(pay_date),
                    "amount": amount_paid,
                    "method": random.choice(["bank_transfer", "ach"]),
                    "reference": f"PAY-{random.randint(100000, 999999)}",
                })
            
            inv = {
                "id": uid(),
                "company_id": COMPANY_ID,
                "invoice_number": inv_number_vendor(vname, global_idx, str(inv_date)),
                "invoice_type": "payable",
                "issue_date": str(inv_date),
                "due_date": str(due_date),
                "currency": vendor["currency"],
                "tax_percent": tax_pct,
                "subtotal": subtotal,
                "total_tax": total_tax,
                "grand_total": grand_total,
                "discount": 0,
                "status": status,
                "amount_paid_so_far": amount_paid,
                # NOTE: confidence_score removed from JSON.
                # It will be computed by extraction_service.py during re-ingestion.
                "payment_method": random.choice(["bank_transfer", "check", "ach", None]),
                "description": None,
                "vendor_name": vname,
                "vendor_idx": VENDORS.index(vendor),
                "template": vendor["template"],
                "line_items": line_items,
                "payments": payments,
            }
            invoices.append(inv)
            global_idx += 1
    
    # Post-process: redistribute statuses to hit targets
    pending = [inv for inv in invoices if inv["status"] == "_pending"]
    random.shuffle(pending)
    n = len(pending)
    targets = {
        "paid": int(n * 0.45),
        "unpaid": int(n * 0.25),
        "overdue": int(n * 0.15),
        "partially_paid": n - int(n * 0.45) - int(n * 0.25) - int(n * 0.15),
    }
    
    idx = 0
    today = date(2026, 5, 25)
    for status_val, count in targets.items():
        for _ in range(count):
            if idx >= len(pending):
                break
            inv = pending[idx]
            inv["status"] = status_val
            inv_date = date.fromisoformat(inv["issue_date"])
            due_dt = date.fromisoformat(inv["due_date"]) if inv["due_date"] else inv_date + timedelta(days=30)
            
            if status_val == "paid":
                inv["amount_paid_so_far"] = inv["grand_total"]
                pay_date = inv_date + timedelta(days=random.randint(5, 25))
                inv["payments"] = [{
                    "payment_date": str(min(pay_date, today)),
                    "amount": inv["grand_total"],
                    "method": random.choice(["bank_transfer", "check", "ach"]),
                    "reference": f"PAY-{random.randint(100000, 999999)}",
                }]
            elif status_val == "partially_paid":
                paid_amt = d(inv["grand_total"] * random.uniform(0.25, 0.65))
                inv["amount_paid_so_far"] = paid_amt
                pay_date = inv_date + timedelta(days=random.randint(10, 30))
                inv["payments"] = [{
                    "payment_date": str(min(pay_date, today)),
                    "amount": paid_amt,
                    "method": random.choice(["bank_transfer", "ach"]),
                    "reference": f"PAY-{random.randint(100000, 999999)}",
                }]
            elif status_val == "overdue":
                inv["amount_paid_so_far"] = 0
                inv["payments"] = []
                if due_dt > today:
                    inv["due_date"] = str(today - timedelta(days=random.randint(5, 30)))
            else:  # unpaid
                inv["amount_paid_so_far"] = 0
                inv["payments"] = []
            idx += 1
    
    return invoices

def generate_receivables():
    invoices = []
    global_idx = 0
    
    for client in CLIENTS:
        cname = client["name"]
        cat = client["category"]
        behavior = client["payment_behavior"]
        
        if client["frequency"] == "2-3/month":
            months_active = list(range(13))
            invs_per_month = lambda m: random.choice([2, 3, 3])
        elif client["frequency"] == "1-2/month":
            months_active = list(range(13))
            invs_per_month = lambda m: random.choice([1, 2, 2])
        elif client["frequency"] == "monthly":
            months_active = list(range(13))
            invs_per_month = lambda m: random.choice([1, 1, 2])
        elif client["frequency"] == "quarterly":
            months_active = [0, 2, 3, 5, 6, 8, 9, 11, 12]
            invs_per_month = lambda m: 1
        elif client["frequency"] == "occasional":
            months_active = [8, 9, 10, 11, 12]
            invs_per_month = lambda m: random.choice([1, 2, 2])
        else:
            months_active = list(range(13))
            invs_per_month = lambda m: 1
        
        for month_offset in months_active:
            n_inv = invs_per_month(month_offset)
            for _ in range(n_inv):
                inv_date = START_DATE + timedelta(days=month_offset * 30 + random.randint(0, 25))
                if inv_date > END_DATE:
                    continue
                due_date = inv_date + timedelta(days=30)
                
                low, high = client["amount_range"]
                growth = 1 + (month_offset * 0.02)
                subtotal = rand_amount(low * growth, high * growth)
                
                pool = CLIENT_LINE_ITEMS[cat]
                n_items = random.randint(1, min(4, len(pool)))
                items = random.sample(pool, n_items)
                line_items = []
                remaining = subtotal
                for j, desc in enumerate(items):
                    desc_filled = desc.replace("{n}", str(random.randint(1, 20)))
                    if j == len(items) - 1:
                        item_total = d(remaining)
                    else:
                        item_total = d(remaining * random.uniform(0.2, 0.5))
                        remaining -= item_total
                    qty = random.choice([1, 1, 2])
                    up = d(item_total / qty)
                    line_items.append({
                        "description": desc_filled,
                        "quantity": qty,
                        "unit_price": up,
                        "line_subtotal": d(up * qty),
                        "discount": 0,
                    })
                
                subtotal = d(sum(li["line_subtotal"] for li in line_items))
                tax_pct = 0
                total_tax = 0
                grand_total = subtotal
                
                today = date(2026, 5, 25)
                days_old = (today - inv_date).days
                days_past_due = (today - due_date).days
                
                if behavior == "slow":
                    if days_old > 120:
                        status = random.choices(["paid", "overdue"], weights=[40, 60])[0]
                    elif days_old > 60:
                        status = random.choices(["overdue", "partially_paid", "sent"], weights=[50, 30, 20])[0]
                    elif days_old > 30:
                        status = random.choices(["sent", "overdue", "partially_paid"], weights=[30, 40, 30])[0]
                    else:
                        status = random.choices(["draft", "sent"], weights=[40, 60])[0]
                elif behavior == "fast":
                    if days_old > 15:
                        status = "paid"
                    elif days_old > 5:
                        status = "sent"
                    else:
                        status = "draft"
                elif behavior == "reliable":
                    if days_past_due > 0:
                        status = "paid"
                    elif days_old > 5:
                        status = "sent"
                    else:
                        status = "draft"
                elif behavior == "exact_on_due":
                    if days_past_due > 0:
                        status = "paid"
                    elif days_old > 3:
                        status = "sent"
                    else:
                        status = "draft"
                elif behavior == "inconsistent":
                    if days_old > 90:
                        status = random.choices(["paid", "overdue"], weights=[60, 40])[0]
                    elif days_old > 30:
                        status = random.choices(["paid", "sent", "overdue", "partially_paid"], weights=[30, 25, 25, 20])[0]
                    else:
                        status = random.choices(["draft", "sent"], weights=[50, 50])[0]
                else:
                    status = "draft"
                
                amount_paid = 0.0
                payments = []
                if status == "paid":
                    amount_paid = grand_total
                    if behavior == "exact_on_due":
                        pay_date = due_date
                    elif behavior == "fast":
                        pay_date = inv_date + timedelta(days=random.randint(3, 10))
                    elif behavior == "slow":
                        pay_date = due_date + timedelta(days=random.randint(15, 45))
                    else:
                        pay_date = inv_date + timedelta(days=client["avg_days_to_pay"] + random.randint(-3, 5))
                    payments.append({
                        "payment_date": str(min(pay_date, today)),
                        "amount": grand_total,
                        "method": random.choice(["bank_transfer", "ach", "credit_card", "check"]),
                        "reference": f"REC-{random.randint(100000, 999999)}",
                    })
                elif status == "partially_paid":
                    amount_paid = d(grand_total * random.uniform(0.2, 0.6))
                    pay_date = inv_date + timedelta(days=random.randint(15, 40))
                    payments.append({
                        "payment_date": str(min(pay_date, today)),
                        "amount": amount_paid,
                        "method": random.choice(["bank_transfer", "ach"]),
                        "reference": f"REC-{random.randint(100000, 999999)}",
                    })
                
                inv = {
                    "id": uid(),
                    "company_id": COMPANY_ID,
                    "invoice_number": inv_number_client(cname, global_idx),
                    "invoice_type": "receivable",
                    "issue_date": str(inv_date),
                    "due_date": str(due_date),
                    "currency": "USD",
                    "tax_percent": tax_pct,
                    "subtotal": subtotal,
                    "total_tax": total_tax,
                    "grand_total": grand_total,
                    "discount": 0,
                    "status": status,
                    "amount_paid_so_far": amount_paid,
                    # NOTE: confidence_score removed; populated by extraction during re-ingestion.
                    "payment_method": None,
                    "description": None,
                    "client_name": cname,
                    "client_idx": CLIENTS.index(client),
                    "line_items": line_items,
                    "payments": payments,
                }
                invoices.append(inv)
                global_idx += 1
    
    # Post-process: redistribute excess "paid" to other statuses
    today = date(2026, 5, 25)
    n = len(invoices)
    target_paid = int(n * 0.35)
    
    paid_invs = [inv for inv in invoices if inv["status"] == "paid"]
    excess_paid = len(paid_invs) - target_paid
    
    if excess_paid > 0:
        random.shuffle(paid_invs)
        to_convert = paid_invs[:excess_paid]
        
        redistribute = {
            "draft": int(excess_paid * 0.20),
            "sent": int(excess_paid * 0.25),
            "overdue": int(excess_paid * 0.25),
            "partially_paid": int(excess_paid * 0.15),
            "unpaid": excess_paid - int(excess_paid * 0.20) - int(excess_paid * 0.25) - int(excess_paid * 0.25) - int(excess_paid * 0.15),
        }
        
        ci = 0
        for new_status, cnt in redistribute.items():
            for _ in range(cnt):
                if ci >= len(to_convert):
                    break
                inv = to_convert[ci]
                inv["status"] = new_status
                inv_date = date.fromisoformat(inv["issue_date"])
                due_dt = date.fromisoformat(inv["due_date"]) if inv["due_date"] else inv_date + timedelta(days=30)
                
                if new_status in ("draft", "sent", "unpaid"):
                    inv["amount_paid_so_far"] = 0
                    inv["payments"] = []
                elif new_status == "overdue":
                    inv["amount_paid_so_far"] = 0
                    inv["payments"] = []
                    if due_dt > today:
                        inv["due_date"] = str(today - timedelta(days=random.randint(5, 45)))
                elif new_status == "partially_paid":
                    paid_amt = d(inv["grand_total"] * random.uniform(0.2, 0.55))
                    inv["amount_paid_so_far"] = paid_amt
                    pay_date = inv_date + timedelta(days=random.randint(15, 40))
                    inv["payments"] = [{
                        "payment_date": str(min(pay_date, today)),
                        "amount": paid_amt,
                        "method": random.choice(["bank_transfer", "ach"]),
                        "reference": f"REC-{random.randint(100000, 999999)}",
                    }]
                ci += 1
    
    return invoices


# ─── Compliance injection (re-engineered) ───────────────────────────────────

# Test-row identities. Both flagged invoices for missing-field tests
# (#4 missing_client_email and #8 missing_vendor_tax_id) are routed to these
# dedicated rows so the canonical 8 clients and 10 vendors stay untouched.
#
# Fourth-wall joke: the testing rows are themselves named after testing — a
# vendor literally called "Jones and Jordan" (a fake firm) and a client called
# "William Testria" (the test client used by the test client).

TEST_VENDOR = {
    "name": "Jones and Jordan",                # used for test #8 (vendor tax_id null)
    "email": "ap@jonesjordan.example",
    "phone": "+1 (000) 555-0000",
    "tax_id": None,                            # the test
    "address": {
        "street": "1 Testing Way",
        "city": "Testville",
        "state": "TX",
        "postal_code": "00000",
        "country": "USA",
    },
    "template": 2,
    "category": "freelance_contractors",
    "frequency": "occasional",
    "amount_range": (1000, 2000),
    "tax_rate": 0,
    "currency": "USD",
    "payment_terms": 30,
    "iban": None,
}

TEST_CLIENT = {
    "name": "William Testria",                 # used for test #4 (client email null)
    "email": None,                             # the test
    "phone": "+1 (000) 555-0001",
    "tax_id": "00-0000001",
    "address": {
        "street": "1 Testing Way",
        "city": "Testville",
        "state": "TX",
        "postal_code": "00000",
        "country": "USA",
    },
    "category": "software_dev",
    "payment_behavior": "reliable",
    "avg_days_to_pay": 15,
    "amount_range": (1000, 2000),
    "frequency": "occasional",
}


def _make_test_payable_for_jones_jordan(vendor_idx):
    """Build a single payable invoice routed to the Jones and Jordan test vendor."""
    inv_date = date(2026, 3, 15)
    due_date = inv_date + timedelta(days=30)
    line_items = [{
        "description": "Backend API Development (Python)",
        "quantity": 1,
        "unit_price": 1500.00,
        "line_subtotal": 1500.00,
        "discount": 0,
    }]
    subtotal = 1500.00
    return {
        "id": uid(),
        "company_id": COMPANY_ID,
        "invoice_number": f"JJ-2026-{_non_67_suffix(0)}",   # will be forced to 67 by caller
        "invoice_type": "payable",
        "issue_date": str(inv_date),
        "due_date": str(due_date),
        "currency": "USD",
        "tax_percent": 0,
        "subtotal": subtotal,
        "total_tax": 0,
        "grand_total": subtotal,
        "discount": 0,
        "status": "unpaid",
        "amount_paid_so_far": 0,
        "payment_method": "bank_transfer",
        "description": None,
        "vendor_name": TEST_VENDOR["name"],
        "vendor_idx": vendor_idx,
        "template": TEST_VENDOR["template"],
        "line_items": line_items,
        "payments": [],
    }


def _make_test_receivable_for_william_testria(client_idx):
    """Build a single receivable invoice routed to the William Testria test client."""
    inv_date = date(2026, 3, 10)
    due_date = inv_date + timedelta(days=30)
    line_items = [{
        "description": "Backend API Development (Sprint 1)",
        "quantity": 1,
        "unit_price": 1500.00,
        "line_subtotal": 1500.00,
        "discount": 0,
    }]
    subtotal = 1500.00
    return {
        "id": uid(),
        "company_id": COMPANY_ID,
        "invoice_number": f"K4Y-INV-{_non_67_suffix(9000)}",  # will be forced to 67 by caller
        "invoice_type": "receivable",
        "issue_date": str(inv_date),
        "due_date": str(due_date),
        "currency": "USD",
        "tax_percent": 0,
        "subtotal": subtotal,
        "total_tax": 0,
        "grand_total": subtotal,
        "discount": 0,
        "status": "sent",
        "amount_paid_so_far": 0,
        "payment_method": None,
        "description": None,
        "client_name": TEST_CLIENT["name"],
        "client_idx": client_idx,
        "line_items": line_items,
        "payments": [],
    }


def inject_compliance_issues(payables, receivables):
    """
    Mutates payables/receivables in place to inject deliberate compliance issues.
    Appends TEST_VENDOR and TEST_CLIENT to the VENDORS/CLIENTS module-level lists
    and creates dedicated invoices routed to them for tests #4 and #8.

    Every flagged invoice has invoice_number ending in '67'.
    Returns a list of issue descriptors for the metadata block in dataset.json.
    """
    issues = []

    # Append test rows. Indexes:
    #   TEST_VENDOR_IDX = 10  (after the existing 10 vendors at 0–9)
    #   TEST_CLIENT_IDX = 8   (after the existing 8 clients at 0–7)
    VENDORS.append(TEST_VENDOR)
    test_vendor_idx = len(VENDORS) - 1
    CLIENTS.append(TEST_CLIENT)
    test_client_idx = len(CLIENTS) - 1

    # ── Test #1: arithmetic mismatch on Apex Office Supply (payable) ──
    apex_invs = [p for p in payables if p["vendor_name"] == "Apex Office Supply Co"]
    if len(apex_invs) > 3:
        target = apex_invs[3]
        target["invoice_number"] = force_67(target["invoice_number"], discriminator=1)
        target["total_tax"] = d(target["total_tax"] + 12.50)
        # grand_total intentionally NOT recomputed — that's the mismatch
        issues.append({
            "invoice_id": target["id"],
            "invoice_number": target["invoice_number"],
            "type": "arithmetic_mismatch",
            "detail": "subtotal + tax - discount ≠ grand_total (off by $12.50)",
        })

    # ── Test #2: missing due_date on CodeForge (payable) ──
    cf_invs = [p for p in payables if p["vendor_name"] == "CodeForge Contractors"]
    if len(cf_invs) > 4:
        target = cf_invs[4]
        target["invoice_number"] = force_67(target["invoice_number"], discriminator=2)
        target["due_date"] = None
        issues.append({
            "invoice_id": target["id"],
            "invoice_number": target["invoice_number"],
            "type": "missing_due_date",
            "detail": "due_date is null",
        })

    # ── Test #3: line item sum mismatch on Halcyon Media (receivable) ──
    halcyon_invs = [r for r in receivables if r["client_name"] == "Halcyon Media Inc"]
    if len(halcyon_invs) > 5:
        target = halcyon_invs[5]
        target["invoice_number"] = force_67(target["invoice_number"], discriminator=3)
        if target["line_items"]:
            target["line_items"][0]["line_subtotal"] = d(
                target["line_items"][0]["line_subtotal"] + 200
            )
            # sum of line items now exceeds invoice.subtotal by $200
        issues.append({
            "invoice_id": target["id"],
            "invoice_number": target["invoice_number"],
            "type": "line_item_sum_mismatch",
            "detail": "Sum of line items exceeds invoice.subtotal by $200",
        })

    # ── Test #4: missing client email — route a receivable to William Testria ──
    test_receivable = _make_test_receivable_for_william_testria(test_client_idx)
    test_receivable["invoice_number"] = force_67(test_receivable["invoice_number"], discriminator=4)
    receivables.append(test_receivable)
    issues.append({
        "invoice_id": test_receivable["id"],
        "invoice_number": test_receivable["invoice_number"],
        "type": "missing_client_email",
        "detail": "William Testria has no email on file",
    })

    # ── Test #5: duplicate invoice number on Ironside Hardware (payable) ──
    # Only the second invoice gets a flag at ingestion time (the first one is
    # normal at the moment of its own insert). Both still end in -67 for
    # visual identification, and they SHARE the same discriminator so they
    # genuinely collide.
    iron_invs = [p for p in payables if p["vendor_name"] == "Ironside Hardware Corp"]
    if len(iron_invs) >= 2:
        iron_invs[0]["invoice_number"] = force_67(iron_invs[0]["invoice_number"], discriminator=5)
        iron_invs[1]["invoice_number"] = iron_invs[0]["invoice_number"]   # duplicate
        issues.append({
            "invoice_id": iron_invs[1]["id"],
            "invoice_number": iron_invs[1]["invoice_number"],
            "type": "duplicate_invoice_number",
            "detail": (
                f"Same (company_id, vendor_id, invoice_number) as invoice "
                f"{iron_invs[0]['id']}"
            ),
        })

    # ── Test #6: low_confidence — stack multiple issues on a Broadleaf payable ──
    # No longer a hand-set confidence score. Instead, the invoice carries
    # multiple genuine defects; the compliance engine will raise enough flags
    # that the meta-rule (>2 flags ⇒ low_confidence) fires automatically.
    bl_invs = [p for p in payables if p["vendor_name"] == "Broadleaf Marketing Group"]
    if len(bl_invs) > 3:
        target = bl_invs[3]
        target["invoice_number"] = force_67(target["invoice_number"], discriminator=6)

        # Defect 1: arithmetic mismatch
        target["total_tax"] = d(target["total_tax"] + 25.00)
        # grand_total unchanged

        # Defect 2: missing due_date
        target["due_date"] = None

        # Defect 3: line item sum mismatch
        if target["line_items"]:
            target["line_items"][0]["line_subtotal"] = d(
                target["line_items"][0]["line_subtotal"] + 30
            )

        # Expected flag count on ingestion:
        #   arithmetic_mismatch + missing_due_date + line_item_sum_mismatch
        #   = 3 flags ⇒ low_confidence fires as the 4th
        issues.append({
            "invoice_id": target["id"],
            "invoice_number": target["invoice_number"],
            "type": "low_confidence_via_multiple_defects",
            "detail": (
                "3 stacked defects (arithmetic + missing_due_date + "
                "line_item_sum) should trigger low_confidence meta-flag"
            ),
        })

    # ── Test #7: wrong tax applied on Apex (payable) ──
    # Apex's expected tax rate is 8.25%. We zero it out so the wrong_tax_applied
    # check fires against the vendor→expected-tax map maintained in the
    # backend compliance service.
    if len(apex_invs) > 6:
        target = apex_invs[6]
        target["invoice_number"] = force_67(target["invoice_number"], discriminator=7)
        target["tax_percent"] = 0.0
        # Recompute totals so the invoice is internally consistent — the test
        # is "wrong tax", not "broken arithmetic"
        subtotal = d(sum(li["line_subtotal"] for li in target["line_items"]))
        target["subtotal"] = subtotal
        target["total_tax"] = 0.0
        target["grand_total"] = subtotal
        issues.append({
            "invoice_id": target["id"],
            "invoice_number": target["invoice_number"],
            "type": "wrong_tax_applied",
            "detail": "0% tax applied to Apex invoice (expected 8.25%)",
        })

    # ── Test #8: missing vendor tax_id — route a payable to Jones and Jordan ──
    test_payable = _make_test_payable_for_jones_jordan(test_vendor_idx)
    test_payable["invoice_number"] = force_67(test_payable["invoice_number"], discriminator=8)
    payables.append(test_payable)
    issues.append({
        "invoice_id": test_payable["id"],
        "invoice_number": test_payable["invoice_number"],
        "type": "missing_vendor_tax_id",
        "detail": "Jones and Jordan has no tax_id on file",
    })

    # ── Test #9: negative line item on Prisma Software (payable) ──
    # WARNING: extraction may normalize the sign. If after re-ingestion the
    # line item has positive quantity, the test failed silently — fall back to
    # backend/scripts/inject_post_ingestion_anomalies.py.
    prisma_invs = [p for p in payables if p["vendor_name"] == "Prisma Software Inc"]
    if prisma_invs:
        target = prisma_invs[0]
        target["invoice_number"] = force_67(target["invoice_number"], discriminator=9)
        if target["line_items"]:
            target["line_items"][0]["quantity"] = -1
            # line_subtotal would normally go negative too; mirror that so the
            # PDF renders consistently
            up = target["line_items"][0]["unit_price"]
            target["line_items"][0]["line_subtotal"] = d(up * -1)
        issues.append({
            "invoice_id": target["id"],
            "invoice_number": target["invoice_number"],
            "type": "negative_line_item",
            "detail": "First line item has quantity = -1",
        })

    # ── Test #10: future issue_date on Summit Legal (payable) ──
    # "Today" in this dataset is 2026-05-25. issue_date set 90 days ahead.
    summit_invs = [p for p in payables if p["vendor_name"] == "Summit Legal Partners"]
    if summit_invs:
        target = summit_invs[0]
        target["invoice_number"] = force_67(target["invoice_number"], discriminator=10)
        future_issue = date(2026, 5, 25) + timedelta(days=90)
        future_due = future_issue + timedelta(days=45)  # Summit's payment terms
        target["issue_date"] = str(future_issue)
        target["due_date"] = str(future_due)
        # Force status back to unpaid; the original status may have been based
        # on the now-superseded issue date
        target["status"] = "unpaid"
        target["amount_paid_so_far"] = 0
        target["payments"] = []
        issues.append({
            "invoice_id": target["id"],
            "invoice_number": target["invoice_number"],
            "type": "future_issue_date",
            "detail": "issue_date is 90 days in the future",
        })

    # ── Test #11: due_date before issue_date on Meridian (payable) ──
    meridian_invs = [p for p in payables if p["vendor_name"] == "Meridian Workspace LLC"]
    if meridian_invs:
        # Pick an invoice that isn't already mutated by another test
        target = meridian_invs[2] if len(meridian_invs) > 2 else meridian_invs[0]
        target["invoice_number"] = force_67(target["invoice_number"], discriminator=11)
        issue_dt = date.fromisoformat(target["issue_date"])
        target["due_date"] = str(issue_dt - timedelta(days=5))
        issues.append({
            "invoice_id": target["id"],
            "invoice_number": target["invoice_number"],
            "type": "due_before_issue",
            "detail": "due_date is 5 days before issue_date",
        })

    # ── Test #12: overpayment on a paid CodeForge invoice (payable) ──
    # Find a paid CodeForge invoice (not the one already mutated by test #2).
    cf_paid = [p for p in cf_invs if p["status"] == "paid" and p["payments"]]
    if cf_paid:
        target = cf_paid[0]
        target["invoice_number"] = force_67(target["invoice_number"], discriminator=12)
        # Add an excess payment of $200 over grand_total
        overpay_amount = d(target["grand_total"] + 200)
        issue_dt = date.fromisoformat(target["issue_date"])
        target["payments"].append({
            "payment_date": str(issue_dt + timedelta(days=40)),
            "amount": overpay_amount,
            "method": "bank_transfer",
            "reference": f"PAY-{random.randint(100000, 999999)}",
        })
        # Total paid now exceeds grand_total
        target["amount_paid_so_far"] = d(
            sum(p["amount"] for p in target["payments"])
        )
        issues.append({
            "invoice_id": target["id"],
            "invoice_number": target["invoice_number"],
            "type": "overpayment",
            "detail": f"Total payments exceed grand_total by ~$200",
        })

    return issues


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    print("Generating payables...")
    payables = generate_payables()
    print(f"  Generated {len(payables)} payable invoices")
    
    print("Generating receivables...")
    receivables = generate_receivables()
    print(f"  Generated {len(receivables)} receivable invoices")
    
    print("Injecting compliance issues...")
    issues = inject_compliance_issues(payables, receivables)
    print(f"  Injected {len(issues)} deliberate compliance issues")
    print(f"  Test vendor 'Jones and Jordan' appended at index {len(VENDORS) - 1}")
    print(f"  Test client 'William Testria' appended at index {len(CLIENTS) - 1}")
    
    # Stats
    pay_statuses = {}
    for p in payables:
        pay_statuses[p["status"]] = pay_statuses.get(p["status"], 0) + 1
    rec_statuses = {}
    for r in receivables:
        rec_statuses[r["status"]] = rec_statuses.get(r["status"], 0) + 1
    
    print(f"\nPayable status distribution: {pay_statuses}")
    print(f"Receivable status distribution: {rec_statuses}")
    print(f"Total: {len(payables) + len(receivables)} invoices")
    
    # Vendor invoice counts
    print("\nVendor invoice counts:")
    for v in VENDORS:
        count = sum(1 for p in payables if p["vendor_name"] == v["name"])
        print(f"  {v['name']}: {count}")
    
    print("\nClient invoice counts:")
    for c in CLIENTS:
        count = sum(1 for r in receivables if r["client_name"] == c["name"])
        print(f"  {c['name']}: {count}")
    
    # Show all flagged (67-suffix) invoices for human verification
    print("\nFlagged invoices (suffix '67'):")
    flagged = [p for p in payables if p["invoice_number"].endswith("67")]
    flagged += [r for r in receivables if r["invoice_number"].endswith("67")]
    for inv in flagged:
        print(f"  {inv['invoice_number']}  ({inv['invoice_type']})")
    
    dataset = {
        "company": COMPANY,
        "vendors": [
            {k: v for k, v in ven.items()
             if k not in ("template", "category", "frequency", "amount_range", "payment_terms")}
            for ven in VENDORS
        ],
        "clients": [
            {k: v for k, v in cli.items()
             if k not in ("category", "payment_behavior", "avg_days_to_pay", "amount_range", "frequency")}
            for cli in CLIENTS
        ],
        "payables": payables,
        "receivables": receivables,
        "compliance_issues": issues,
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_payables": len(payables),
            "total_receivables": len(receivables),
            "total_invoices": len(payables) + len(receivables),
            "payable_statuses": pay_statuses,
            "receivable_statuses": rec_statuses,
            "compliance_issue_count": len(issues),
            "test_vendor_name": TEST_VENDOR["name"],
            "test_client_name": TEST_CLIENT["name"],
        },
    }
    
    with open(OUTPUT, "w") as f:
        json.dump(dataset, f, indent=2, default=str)
    
    print(f"\nDataset written to {OUTPUT}")
    print(f"File size: {OUTPUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()