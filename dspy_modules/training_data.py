"""Synthetic training examples for the DSPy triage classifier.

60 labelled examples — exactly 10 per category — used for BootstrapFewShot
compilation.  Each dict maps to a dspy.Example with fields:
    ticket_text (input), category, confidence, reasoning (outputs).
"""

from __future__ import annotations

TRAINING_EXAMPLES: list[dict[str, str | float]] = [
    # ── password_reset (10) ───────────────────────────────────────────────────
    {
        "ticket_text": "I forgot my password and can't log in to my corporate email account.",
        "category": "password_reset",
        "confidence": 0.97,
        "reasoning": "User explicitly states they forgot their password and cannot log in.",
    },
    {
        "ticket_text": "My Active Directory password expired overnight and I'm locked out of all systems.",
        "category": "password_reset",
        "confidence": 0.96,
        "reasoning": "Expired AD password causes system lockout, requiring a password reset.",
    },
    {
        "ticket_text": "I entered my password wrong too many times and my account is now locked.",
        "category": "password_reset",
        "confidence": 0.95,
        "reasoning": "Account lockout after failed attempts is resolved via password reset.",
    },
    {
        "ticket_text": "Can someone reset my Windows login password? I can't remember what it is.",
        "category": "password_reset",
        "confidence": 0.97,
        "reasoning": "Direct request to reset a forgotten Windows login password.",
    },
    {
        "ticket_text": "I need a temporary password to get back into my laptop after returning from parental leave.",
        "category": "password_reset",
        "confidence": 0.94,
        "reasoning": "Employee returning from leave needs account password restored.",
    },
    {
        "ticket_text": "My email password stopped working this morning. I keep getting 'authentication failed'.",
        "category": "password_reset",
        "confidence": 0.93,
        "reasoning": "Authentication failure on email typically indicates an expired or corrupted password.",
    },
    {
        "ticket_text": "Please help me reset my SSO password — every tool is showing login errors.",
        "category": "password_reset",
        "confidence": 0.96,
        "reasoning": "SSO password reset will restore access to all linked applications.",
    },
    {
        "ticket_text": "My VPN client says my credentials are wrong but my password hasn't changed. Please reset it.",
        "category": "password_reset",
        "confidence": 0.91,
        "reasoning": "Credential rejection on VPN suggests password synchronisation issue requiring reset.",
    },
    {
        "ticket_text": "I got a security alert asking me to change my password immediately — please guide me.",
        "category": "password_reset",
        "confidence": 0.92,
        "reasoning": "Security-triggered password change is a forced password reset workflow.",
    },
    {
        "ticket_text": "My account is showing 'password expired' and the self-service portal isn't working.",
        "category": "password_reset",
        "confidence": 0.95,
        "reasoning": "Expired password with self-service unavailable requires IT-assisted reset.",
    },
    # ── access_request (10) ───────────────────────────────────────────────────
    {
        "ticket_text": "I need read access to the production PostgreSQL database for my analytics work.",
        "category": "access_request",
        "confidence": 0.96,
        "reasoning": "Explicit request for database access permissions for a defined business purpose.",
    },
    {
        "ticket_text": "Please add me to the Finance AD group so I can open the monthly reporting portal.",
        "category": "access_request",
        "confidence": 0.95,
        "reasoning": "Request to join a security group to gain access to a specific application.",
    },
    {
        "ticket_text": "I've joined the DevOps team and need access to the AWS production account.",
        "category": "access_request",
        "confidence": 0.96,
        "reasoning": "New team assignment requires provisioning cloud infrastructure access.",
    },
    {
        "ticket_text": "Can you grant me edit permissions to the shared Engineering Confluence space?",
        "category": "access_request",
        "confidence": 0.94,
        "reasoning": "Permission change request for a collaboration tool's shared workspace.",
    },
    {
        "ticket_text": "I need contributor access to the mobile-app GitHub repository for the upcoming sprint.",
        "category": "access_request",
        "confidence": 0.95,
        "reasoning": "Code repository access is a standard access provisioning request.",
    },
    {
        "ticket_text": "Please provision Salesforce access for me — I'm starting in the sales role next Monday.",
        "category": "access_request",
        "confidence": 0.97,
        "reasoning": "Role-change triggers a Salesforce access provisioning request.",
    },
    {
        "ticket_text": "I require temporary access to the client VPN environment for the next 30 days.",
        "category": "access_request",
        "confidence": 0.93,
        "reasoning": "Time-boxed access to a client VPN is a scoped access provisioning request.",
    },
    {
        "ticket_text": "Can you add my account to the data-warehouse reader role for the Q4 analysis project?",
        "category": "access_request",
        "confidence": 0.95,
        "reasoning": "Request for a specific IAM role on the data warehouse for a project.",
    },
    {
        "ticket_text": "I need access to the HR SharePoint site to review the headcount planning documents.",
        "category": "access_request",
        "confidence": 0.94,
        "reasoning": "SharePoint site access grant is an access provisioning workflow.",
    },
    {
        "ticket_text": "Please give me admin rights on my local machine so I can install development tools.",
        "category": "access_request",
        "confidence": 0.91,
        "reasoning": "Request for elevated local administrator permissions on an endpoint.",
    },
    # ── software_install (10) ─────────────────────────────────────────────────
    {
        "ticket_text": "I need Python 3.11 and pip installed on my work MacBook.",
        "category": "software_install",
        "confidence": 0.97,
        "reasoning": "Direct request to install a specific software runtime on a corporate device.",
    },
    {
        "ticket_text": "Can you deploy Docker Desktop on my Windows laptop? I need it for the containerisation project.",
        "category": "software_install",
        "confidence": 0.96,
        "reasoning": "Software installation request with a clear business justification.",
    },
    {
        "ticket_text": "I need Adobe Acrobat Pro to edit and sign contracts — can you get it approved and installed?",
        "category": "software_install",
        "confidence": 0.95,
        "reasoning": "Licensed software procurement and installation request.",
    },
    {
        "ticket_text": "Please install VS Code with the Python, GitLens, and Docker extensions on my machine.",
        "category": "software_install",
        "confidence": 0.96,
        "reasoning": "IDE installation and configuration request for a developer.",
    },
    {
        "ticket_text": "The Zoom web client keeps crashing during large meetings. Can you install the desktop app?",
        "category": "software_install",
        "confidence": 0.93,
        "reasoning": "Request to install desktop client as a workaround for web client issues.",
    },
    {
        "ticket_text": "I need Tableau Desktop for the data visualisation initiative. Can you push it to my laptop?",
        "category": "software_install",
        "confidence": 0.96,
        "reasoning": "Licensed BI tool installation request for a specific project.",
    },
    {
        "ticket_text": "Please install the JIRA desktop client — the web version is too slow for my workflow.",
        "category": "software_install",
        "confidence": 0.94,
        "reasoning": "Preference-driven request to install a desktop alternative to a web tool.",
    },
    {
        "ticket_text": "Can you set up Postman on my machine for API testing?",
        "category": "software_install",
        "confidence": 0.95,
        "reasoning": "Developer tool installation request for API testing purposes.",
    },
    {
        "ticket_text": "I need Microsoft Project installed to manage the product roadmap Gantt chart.",
        "category": "software_install",
        "confidence": 0.95,
        "reasoning": "Licensed project management software installation request.",
    },
    {
        "ticket_text": "My new laptop doesn't have the VPN client installed. Can IT push it remotely?",
        "category": "software_install",
        "confidence": 0.94,
        "reasoning": "Missing standard corporate software on a new device — deployment request.",
    },
    # ── leave_approval (10) ───────────────────────────────────────────────────
    {
        "ticket_text": "I'd like to take annual leave from June 10 to June 14. Please approve.",
        "category": "leave_approval",
        "confidence": 0.98,
        "reasoning": "Explicit annual leave request with specific dates.",
    },
    {
        "ticket_text": "I'm not feeling well today and need to take a sick day.",
        "category": "leave_approval",
        "confidence": 0.97,
        "reasoning": "Same-day sick leave notification.",
    },
    {
        "ticket_text": "Can you approve my PTO for the week of July 4th? I'll be travelling.",
        "category": "leave_approval",
        "confidence": 0.98,
        "reasoning": "Advance PTO request for a full week.",
    },
    {
        "ticket_text": "I need to take a personal day on Friday for a medical appointment.",
        "category": "leave_approval",
        "confidence": 0.96,
        "reasoning": "Single-day personal leave request for a health-related appointment.",
    },
    {
        "ticket_text": "Requesting 3 days of bereavement leave following the passing of my grandfather.",
        "category": "leave_approval",
        "confidence": 0.98,
        "reasoning": "Bereavement leave request, a specific and sensitive leave type.",
    },
    {
        "ticket_text": "I'm planning to take parental leave starting September 1st for 16 weeks.",
        "category": "leave_approval",
        "confidence": 0.98,
        "reasoning": "Formal parental leave request with a start date.",
    },
    {
        "ticket_text": "Can I take a half-day on Thursday afternoon? I have a school event for my child.",
        "category": "leave_approval",
        "confidence": 0.95,
        "reasoning": "Short-duration personal leave request for a family commitment.",
    },
    {
        "ticket_text": "I'd like to use my remaining 5 PTO days before December 31st. Please confirm approval.",
        "category": "leave_approval",
        "confidence": 0.97,
        "reasoning": "Year-end PTO balance usage request.",
    },
    {
        "ticket_text": "Please approve my two-week vacation to Japan from August 5 to August 16.",
        "category": "leave_approval",
        "confidence": 0.98,
        "reasoning": "Advance vacation leave request spanning two weeks.",
    },
    {
        "ticket_text": "I need emergency leave today — there's a family emergency I have to attend to.",
        "category": "leave_approval",
        "confidence": 0.96,
        "reasoning": "Urgent same-day emergency leave request.",
    },
    # ── incident_report (10) ──────────────────────────────────────────────────
    {
        "ticket_text": "URGENT: The production payment service is completely down. Customers cannot check out.",
        "category": "incident_report",
        "confidence": 0.99,
        "reasoning": "Production service outage with direct customer impact — P1 incident.",
    },
    {
        "ticket_text": "Our corporate email system has been unavailable for 2 hours. No one can send or receive.",
        "category": "incident_report",
        "confidence": 0.98,
        "reasoning": "Company-wide email outage is a high-severity IT incident.",
    },
    {
        "ticket_text": "The VPN is dropping connections for all remote staff. We've had 50 disconnections in an hour.",
        "category": "incident_report",
        "confidence": 0.97,
        "reasoning": "Widespread VPN failures affecting remote workforce is an active incident.",
    },
    {
        "ticket_text": "CRITICAL: database cluster disk usage at 98% — queries are timing out and writes are failing.",
        "category": "incident_report",
        "confidence": 0.99,
        "reasoning": "Disk-full condition causing query failures is a critical infrastructure incident.",
    },
    {
        "ticket_text": "The CI/CD pipeline is broken — all builds are failing and no deployments can go out.",
        "category": "incident_report",
        "confidence": 0.96,
        "reasoning": "CI/CD outage blocking all releases is a high-severity engineering incident.",
    },
    {
        "ticket_text": "Multiple users are getting 500 errors on the login page. Roughly 200 users impacted.",
        "category": "incident_report",
        "confidence": 0.97,
        "reasoning": "Login page failures affecting hundreds of users is an active P2 incident.",
    },
    {
        "ticket_text": "The API gateway is timing out on all requests. Every downstream service is impacted.",
        "category": "incident_report",
        "confidence": 0.98,
        "reasoning": "API gateway failure causing cascading outage is a P1 incident.",
    },
    {
        "ticket_text": "Our monitoring is firing alerts for CPU usage above 95% across all app servers.",
        "category": "incident_report",
        "confidence": 0.95,
        "reasoning": "System-wide high CPU alert indicates an active performance incident.",
    },
    {
        "ticket_text": "The shared file server is inaccessible — the entire engineering floor cannot access project files.",
        "category": "incident_report",
        "confidence": 0.97,
        "reasoning": "File server outage blocking an entire team is a high-severity incident.",
    },
    {
        "ticket_text": "Security alert: we are seeing failed admin login attempts from an unknown IP. Possible breach.",
        "category": "incident_report",
        "confidence": 0.98,
        "reasoning": "Suspected unauthorised admin access is a critical security incident requiring immediate response.",
    },
    # ── unknown (10) ──────────────────────────────────────────────────────────
    {
        "ticket_text": "Can you help me understand the company's public holiday calendar for next year?",
        "category": "unknown",
        "confidence": 0.65,
        "reasoning": "Holiday calendar enquiry does not fit any defined service category.",
    },
    {
        "ticket_text": "Where is the closest parking garage to the main office building?",
        "category": "unknown",
        "confidence": 0.72,
        "reasoning": "Parking logistics question is outside the scope of IT and HR service categories.",
    },
    {
        "ticket_text": "What is the process for submitting expense reports through the finance portal?",
        "category": "unknown",
        "confidence": 0.61,
        "reasoning": "Expense process guidance is finance-related and does not match defined categories.",
    },
    {
        "ticket_text": "How do I find a mentor or career coach within the company?",
        "category": "unknown",
        "confidence": 0.68,
        "reasoning": "Mentorship enquiry is not directly addressed by any defined IT or HR service category.",
    },
    {
        "ticket_text": "I want to update my preferred name and pronouns in the HR profile system.",
        "category": "unknown",
        "confidence": 0.58,
        "reasoning": "Profile update request does not map to password reset, access, or leave categories.",
    },
    {
        "ticket_text": "Can someone explain the organisational chart for the product management department?",
        "category": "unknown",
        "confidence": 0.71,
        "reasoning": "Org chart enquiry is informational and falls outside defined service categories.",
    },
    {
        "ticket_text": "Where can I find the official template for business travel reimbursement claims?",
        "category": "unknown",
        "confidence": 0.63,
        "reasoning": "Document template location request is not covered by defined IT or HR service categories.",
    },
    {
        "ticket_text": "I'd like feedback on my slide deck before the all-hands presentation next Friday.",
        "category": "unknown",
        "confidence": 0.75,
        "reasoning": "Peer feedback request on presentation materials is outside service management scope.",
    },
    {
        "ticket_text": "What is the company's policy on freelance side projects and intellectual property ownership?",
        "category": "unknown",
        "confidence": 0.62,
        "reasoning": "IP and side-project policy enquiry is legal/HR advisory and not a standard service request.",
    },
    {
        "ticket_text": "How do I arrange a visitor badge for a client visiting the office on Thursday?",
        "category": "unknown",
        "confidence": 0.69,
        "reasoning": "Visitor badge request is a facilities/reception workflow outside defined service categories.",
    },
]

# Sanity check: exactly 60 examples, 10 per category.
assert len(TRAINING_EXAMPLES) == 60, f"Expected 60 examples, got {len(TRAINING_EXAMPLES)}"
_category_counts: dict[str, int] = {}
for _ex in TRAINING_EXAMPLES:
    _cat = str(_ex["category"])
    _category_counts[_cat] = _category_counts.get(_cat, 0) + 1
for _cat, _count in _category_counts.items():
    assert _count == 10, f"Category '{_cat}' has {_count} examples, expected 10"
