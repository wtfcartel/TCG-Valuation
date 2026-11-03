"""Integrations page: systems this could connect to, each with its published API and any GitHub SDKs.

Every link points to the vendor's own developer documentation or GitHub organisation; community SDKs are labelled.
Nothing listed here is connected in the demo.
"""

from __future__ import annotations

from common.report import esc

# (system, what it is, API style and auth, docs URL, [(GitHub label, URL)], how it would fit)
CATEGORIES = [
    ("Accounting and finance", [
        ("Xero", "Cloud accounting", "REST, OAuth 2.0", "https://developer.xero.com",
         [("XeroAPI: official SDKs (Python, Node, .NET, Java, PHP, Ruby)", "https://github.com/XeroAPI")],
         "Post approved supplier bills and coded GL lines; pull invoices, payments and debtor ageing"),
        ("MYOB Business / AccountRight", "Cloud accounting", "REST, OAuth 2.0", "https://developer.myob.com",
         [("myob-oss: official AccountRight .NET SDK", "https://github.com/myob-oss"),
          ("pymyob: community Python SDK", "https://github.com/uptick/pymyob")],
         "Same as Xero for businesses on MYOB"),
        ("QuickBooks Online", "Cloud accounting", "REST, OAuth 2.0", "https://developer.intuit.com",
         [("intuit: official SDKs", "https://github.com/intuit")], "Same as Xero for businesses on QuickBooks"),
        ("Microsoft Dynamics 365 Business Central", "ERP and finance", "REST (OData), OAuth 2.0",
         "https://learn.microsoft.com/dynamics365/business-central/dev-itpro/api-reference/v2.0/",
         [("microsoft/AL: development tools", "https://github.com/microsoft/AL")], "Finance, purchasing and inventory in one ERP"),
    ]),
    ("Warehouse management (WMS)", [
        ("CartonCloud", "Australian WMS and TMS", "REST, OAuth 2.0", "https://api-docs.cartoncloud.com",
         [], "Stock on hand, sale and purchase orders, and consignments; public Postman collection"),
        ("Manhattan Active Warehouse Management", "Enterprise WMS", "REST microservices, OAuth 2.0",
         "https://developer.manh.com", [], "Orders, inventory and labour data for larger warehouse operations"),
        ("Odoo Inventory", "Open-source ERP module", "XML-RPC / JSON-RPC external API", "https://www.odoo.com/documentation",
         [("odoo/odoo: full source code", "https://github.com/odoo/odoo")], "Stock, transfers and purchasing for smaller operations"),
    ]),
    ("Transport management (TMS)", [
        ("MachShip", "Australian freight and carrier management", "REST, API token", "https://docs.machship.com/developers/",
         [], "Carrier rates, consignments, labels and tracking; Swagger reference at live.machship.com/swagger"),
        ("CartonCloud TMS", "Australian transport management", "REST, OAuth 2.0", "https://api-docs.cartoncloud.com",
         [], "Run sheets, proof of delivery and transport billing"),
        ("Manhattan Active Transportation Management", "Enterprise TMS", "REST microservices, OAuth 2.0",
         "https://developer.manh.com", [], "Load planning and freight cost for larger networks"),
    ]),
    ("Procurement", [
        ("Coupa", "Procure-to-pay", "REST (XML / JSON), OAuth 2.0", "https://docs.coupa.com/en/developer-documentation",
         [], "Purchase orders, approvals, receipts and supplier invoices"),
        ("SAP Ariba", "Procurement and supplier network", "REST, OAuth 2.0", "https://developer.ariba.com/api",
         [("SAP-samples: SAP sample code", "https://github.com/SAP-samples")], "Sourcing, contracts and purchase orders"),
    ]),
    ("Manufacturing and inventory", [
        ("Katana MRP", "Manufacturing ERP", "REST, API key", "https://developer.katanamrp.com",
         [("katana-openapi-client: community client", "https://github.com/dougborg/katana-openapi-client")],
         "Bills of materials, manufacturing orders and stock"),
        ("Unleashed", "Inventory and production", "REST, signed API key", "https://apidocs.unleashedsoftware.com",
         [], "Products, assemblies, purchase and sales orders"),
        ("SAP S/4HANA", "Enterprise ERP", "OData / REST, OAuth 2.0", "https://api.sap.com",
         [("SAP-samples: SAP sample code", "https://github.com/SAP-samples")], "Production, materials and finance for large manufacturers"),
    ]),
    ("Field operations and fleet", [
        ("simPRO", "Job management for trades and field service", "REST, OAuth 2.0", "https://developer.simprogroup.com",
         [], "Jobs, quotes, schedules, timesheets and job costing"),
        ("Procore", "Construction project management", "REST, OAuth 2.0", "https://procore.github.io/documentation/introduction",
         [("procore: official SDKs and samples", "https://github.com/procore")], "Projects, budgets, change events and daily logs"),
        ("Geotab", "Fleet telematics", "REST / JSON-RPC", "https://developers.geotab.com/myGeotab/introduction/",
         [("Geotab: official SDKs and samples", "https://github.com/Geotab")], "Vehicle and plant location, hours and utilisation"),
    ]),
    ("Reporting and workflow", [
        ("Power BI", "Reporting and dashboards", "REST, Azure AD (OAuth 2.0)", "https://learn.microsoft.com/rest/api/power-bi/",
         [("microsoft/PowerBI-JavaScript: embedding SDK", "https://github.com/microsoft/PowerBI-JavaScript")],
         "Embed reports; the review page's figures are already available as data feeds"),
        ("Microsoft 365 (Outlook, Teams, SharePoint)", "Email, chat and documents", "Microsoft Graph REST, OAuth 2.0",
         "https://learn.microsoft.com/graph/", [("microsoftgraph: official SDKs", "https://github.com/microsoftgraph")],
         "Read supplier invoices from a shared inbox, send approval emails, post alerts to Teams"),
    ]),
]


def section() -> str:
    blocks = ""
    for cat, systems in CATEGORIES:
        rows = ""
        for name, what, api, docs, gh, fit in systems:
            gh_html = "<br>".join(f"<a href='{u}' target='_blank' rel='noopener'>{esc(l)}</a>" for l, u in gh) or \
                "<span class='note'>No public SDK; use the API directly</span>"
            rows += (f"<tr><td><b>{esc(name)}</b><br><span class='note'>{esc(what)}</span></td><td>{esc(api)}</td>"
                     f"<td><a href='{docs}' target='_blank' rel='noopener'>API documentation</a></td><td>{gh_html}</td>"
                     f"<td>{esc(fit)}</td></tr>")
        blocks += (f"<h2>{esc(cat)}</h2><div class='tw'><table class='intg'><tr><th style='width:20%'>System</th>"
                   f"<th style='width:15%'>API</th><th style='width:12%'>Docs</th><th style='width:24%'>GitHub</th>"
                   f"<th>What it would connect</th></tr>{rows}</table></div>")
    return f"""<style>.tw{{overflow-x:auto}}.intg{{min-width:760px}}.intg td{{font-size:13px}}</style>
<p class="lede">The figures in the review come from job, invoice, payment, plant and supplier data. These are the systems that
data normally lives in, and each one has a published API, so it can be read automatically rather than re-keyed. Where the
vendor publishes code on GitHub, it's linked.</p>
<div class="say">Nothing here is connected in the demo. The invoice reader already produces Xero's bill-import format, so
Xero would be the first live connection, followed by whichever job, plant and stock systems are actually in use.</div>
{blocks}
<p class="note">Links go to each vendor's own developer documentation or GitHub account. Community-built SDKs are labelled
as such. Access to most of these APIs needs an account with the vendor, and some need partner approval.</p>"""
