"""SYNTHETIC test payloads shaped like each vendor's public API response.

These are not captured from live services (the build environment had no network access to them)
and they do not describe real vacancies. Employer names end in "(Fixture)" to make that obvious.
When live access is available, replace or supplement them with captured responses.
"""

ADZUNA_PAGE = {
    "count": 2,
    "results": [
        {
            "id": "4900000001",
            "title": "<strong>General Manager</strong> Supply Chain",
            "description": "Lead national warehousing and transport operations with full P&amp;L accountability...",
            "created": "2026-10-20T03:00:00Z",
            "redirect_url": "https://www.adzuna.com.au/land/ad/4900000001",
            "company": {"display_name": "Southern Freight (Fixture)"},
            "location": {
                "display_name": "Truganina, Melbourne",
                "area": ["Australia", "Victoria", "Melbourne", "Truganina"],
            },
            "salary_min": 230000,
            "salary_max": 260000,
            "salary_is_predicted": "0",
            "contract_time": "full_time",
            "category": {"label": "Logistics & Warehouse Jobs"},
        },
        {
            "id": "4900000002",
            "title": "Head of Strategy",
            "description": "Own the corporate strategy and strategic plan, reporting to the CEO...",
            "created": "2026-10-19T03:00:00Z",
            "redirect_url": "https://www.adzuna.com.au/land/ad/4900000002",
            "company": {"display_name": "Harbour Infrastructure (Fixture)"},
            "location": {"display_name": "Sydney, New South Wales", "area": ["Australia", "New South Wales", "Sydney"]},
            "salary_min": 180000.0,
            "salary_max": 180000.0,
            "salary_is_predicted": "1",
        },
    ],
}

WORKDAY_LIST = {
    "total": 2,
    "jobPostings": [
        {
            "title": "Executive General Manager, Operations",
            "externalPath": "/job/Melbourne/EGM-Operations_R10001",
            "locationsText": "Melbourne, VIC",
            "postedOn": "Posted 2 Days Ago",
            "bulletFields": ["R10001"],
        },
        {
            "title": "Warehouse Team Leader",
            "externalPath": "/job/Laverton/Warehouse-Team-Leader_R10002",
            "locationsText": "Laverton North, VIC",
            "postedOn": "Posted Today",
            "bulletFields": ["R10002"],
        },
    ],
}
WORKDAY_DETAIL = {
    "jobPostingInfo": {
        "id": "abc",
        "title": "Executive General Manager, Operations",
        "jobDescription": "<p>Reporting to the CEO, you will lead national operations across 14 sites with "
        "full P&amp;L accountability. Salary package $320,000 TRP plus STI.</p>",
        "location": "Melbourne, VIC",
        "startDate": "2026-10-20",
        "timeType": "Full time",
        "jobReqId": "R10001",
        "externalUrl": "https://example.wd3.myworkdayjobs.com/External/job/Melbourne/EGM-Operations_R10001",
        "remoteType": "Hybrid",
        "canApply": True,
    }
}

SMARTRECRUITERS_LIST = {
    "totalFound": 1,
    "content": [
        {
            "id": "744000012345678",
            "name": "Head of Commercial",
            "refNumber": "REF-77",
            "releasedDate": "2026-10-18T00:00:00.000Z",
            "location": {"city": "Melbourne", "region": "VIC", "country": "au", "remote": False},
            "company": {"name": "Coastal Distribution (Fixture)"},
            "typeOfEmployment": {"label": "Full-time"},
        }
    ],
}
SMARTRECRUITERS_DETAIL = {
    "postingUrl": "https://jobs.smartrecruiters.com/CoastalFixture/744000012345678",
    "applyUrl": "https://jobs.smartrecruiters.com/CoastalFixture/744000012345678/apply",
    "jobAd": {
        "sections": {
            "jobDescription": {"text": "<p>Lead commercial strategy, pricing and key accounts.</p>"},
            "qualifications": {"text": "<ul><li>Senior commercial leadership in logistics</li></ul>"},
            "additionalInformation": {"text": ""},
        }
    },
}

GREENHOUSE_JOBS = {
    "jobs": [
        {
            "id": 5550001,
            "title": "Director, Corporate Development & M&A",
            "updated_at": "2026-10-17T00:00:00Z",
            "location": {"name": "Sydney or Melbourne"},
            "absolute_url": "https://boards.greenhouse.io/fixture/jobs/5550001",
            "content": "&lt;p&gt;Lead acquisitions, due diligence and post-merger integration.&lt;/p&gt;",
            "company_name": "Network Holdings (Fixture)",
        }
    ]
}

LEVER_POSTINGS = [
    {
        "id": "aaaa-bbbb",
        "text": "Head of Transformation",
        "categories": {"location": "Melbourne", "commitment": "Full-time"},
        "descriptionPlain": "Lead the enterprise transformation program and operating model redesign.",
        "lists": [{"text": "You bring", "content": "<li>Turnaround experience</li>"}],
        "hostedUrl": "https://jobs.lever.co/fixture/aaaa-bbbb",
        "applyUrl": "https://jobs.lever.co/fixture/aaaa-bbbb/apply",
        "createdAt": 1792300000000,
        "workplaceType": "hybrid",
    }
]

PAGEUP_LIST = {
    "count": 1,
    "results": """
<table><tr class="job-row">
  <td><a class="job-link" href="/999/cw/en/job/600123/general-manager-fleet-services">General Manager Fleet Services</a>
  <span class="location">Dandenong, VIC</span><time datetime="2030-11-15">15 Nov 2030</time>
  <p class="job-summary">Lead fleet and transport operations.</p></td>
</tr></table>""",
}
PAGEUP_DETAIL_HTML = (
    "<html><body><div id='job-details'><p>Full accountability for a national fleet.</p></div></body></html>"
)


def bullhorn_page(job_id: int = 31092) -> dict:
    return {
        "total": 1,
        "start": 0,
        "count": 1,
        "data": [
            {
                "id": job_id,
                "title": "General Manager Supply Chain",
                "publicDescription": "<p>Our client, a private equity backed distributor, seeks a General Manager "
                "Supply Chain to lead warehousing, transport and procurement nationally. Melbourne based.</p>",
                "address": {"city": "Melbourne", "state": "VIC", "countryName": "Australia"},
                "dateAdded": 1792200000000,
                "dateLastPublished": 1792300000000,
                "employmentType": "Permanent",
            }
        ],
    }


RSS_FEED = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Fixture jobs</title>
<item><title>Chief Executive Officer - Community Mental Health</title><link>https://jobs.example.org/ceo-123?utm_source=rss</link>
<guid>ceo-123</guid><pubDate>Mon, 19 Oct 2026 09:00:00 +1100</pubDate>
<description>Lead a not-for-profit registered with the ACNC.</description></item>
</channel></rss>"""


def assessment_json(**overrides: object) -> dict:
    base = {
        "capability_fit": {"score": 9.0, "rationale": "Direct national operations and P&L leadership (E4, E5)."},
        "evidence_fit": {"score": 8.8, "rationale": "Evidence items E2, E5 and E7 support the key competencies."},
        "archetype_fit": {"score": 8.6, "rationale": "Former COO profile matches the likely shortlist."},
        "ats_lexical_fit": {"score": 8.5, "rationale": "Most key concepts appear in the evidence."},
        "recruiter_read_fit": {"score": 8.9, "rationale": "Logistics COO background reads as directly relevant."},
        "requirements": [
            {
                "requirement": "National operations leadership",
                "importance": "ESSENTIAL",
                "support": "STRONG",
                "evidence_ids": ["E4"],
                "note": "",
            }
        ],
        "missing_keywords": ["safety leadership"],
        "knockouts": [],
        "conversion": {
            "assessment": "STRONG",
            "rationale": "Directly comparable scale and scope.",
            "screening_risks": [],
        },
        "seniority": {"is_executive_scope": True, "rationale": "Reports to the CEO with P&L."},
        "specialist_role": False,
        "summary": "Strong match: national operations EGM in Melbourne with P&L accountability.",
    }
    base.update(overrides)
    return base
