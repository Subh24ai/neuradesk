# Software Installation Runbook

## Overview
This runbook describes the process for requesting, approving, and deploying software on corporate endpoints. All software installations must go through the IT procurement and approval workflow. Employees may not install unapproved software on corporate devices; violations trigger an automated security alert.

## Requesting New Software
Submit a software installation request through the IT Self-Service Portal under Software Requests. Include the application name, version, vendor, business justification, and the names of employees who require it. The request is routed to your manager for budget approval and then to IT Security for license and vulnerability review. Approved requests are fulfilled within three business days for standard software and five business days for enterprise applications requiring custom configuration.

## Approved Software Catalog
The IT-approved software catalog is available in the Self-Service Portal. Common applications including Microsoft 365, Slack, Zoom, and Chrome are pre-approved and can be self-installed via the Software Center without opening a ticket. Development tools such as VS Code, Docker, and Python runtimes are available in the Developer Tools section. All catalog software is pre-licensed and patched to the latest stable version.

## Deployment via SCCM / Endpoint Management
IT deploys approved applications through Microsoft SCCM for Windows endpoints and Jamf for macOS. After approval, the software package appears in the Company Portal or Managed Software Center on the employee's device within four hours. Click Install to start the deployment. Installations that require a reboot will prompt the user before applying. Remote deployments run overnight to avoid disrupting working hours.

## License Compliance
Every installed application is tracked in the software asset register. Employees must not transfer licenses between devices or share login credentials for per-seat licensed tools. When an employee offboards, their software licenses are automatically reclaimed within 24 hours. Annual license audits are conducted by IT in Q4; discrepancies trigger an immediate review and potential cost-back to the relevant business unit.
