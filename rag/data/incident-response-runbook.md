# Incident Response Runbook

## Overview
This runbook defines the procedures for detecting, classifying, responding to, and resolving IT incidents. An incident is any unplanned interruption to a service or reduction in service quality. All incidents are tracked in the ITSM system and assigned a severity level that governs response times and escalation paths.

## Incident Severity Classification
P1 (Critical): Complete service outage affecting all users or a mission-critical system; response begins within 15 minutes. P2 (High): Major functionality degraded affecting a significant user population; response within 1 hour. P3 (Medium): Partial service degradation affecting a subset of users with a workaround available; response within 4 hours. P4 (Low): Minor issue with minimal business impact and a known workaround; response within 1 business day.

## Reporting a New Incident
Report incidents via the ITSM portal, the #it-incidents Slack channel, or by calling the IT hotline at ext. 5000 for P1/P2 situations. Provide a clear description of the issue, the affected systems, the number of users impacted, and the time the incident began. A P1 or P2 incident automatically pages the on-call SRE team and opens a dedicated incident bridge call. All communication during an active incident must go through the designated incident commander.

## Incident Response Procedure
Upon receiving an incident report, the assigned engineer acknowledges the ticket and confirms severity within 15 minutes. The engineer diagnoses the root cause, applies a temporary fix or workaround to restore service, and updates the incident ticket with status every 30 minutes. For P1 incidents, the SRE team lead acts as incident commander and coordinates across engineering, infrastructure, and communications. Once service is restored, the ticket moves to "Resolved" and a post-mortem is scheduled within 48 hours.

## Post-Mortem and Root Cause Analysis
Every P1 and P2 incident requires a written post-mortem within five business days. The post-mortem document must include a timeline of events, root cause analysis, contributing factors, and action items with owners and due dates. Post-mortems are blameless — the goal is systemic improvement, not individual fault. Completed post-mortems are published to the engineering wiki and reviewed in the monthly reliability review.
