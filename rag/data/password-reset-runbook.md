# IT Password Reset Runbook

## Overview
This runbook covers procedures for resetting user account passwords, recovering from account lockouts, and managing temporary credentials. All password resets must be logged in the ITSM system for audit compliance. IT staff are required to verify user identity before initiating any admin-assisted reset.

## Self-Service Password Reset
Employees can reset their own password at any time via the IT Self-Service Portal. Navigate to Account Management and select Reset Password. Enter your registered work email address and complete the identity verification challenge. A one-time temporary password will be emailed to your personal address on file. Temporary passwords expire after 24 hours and must be changed on first successful login.

## Admin-Assisted Reset
When the self-service portal is unavailable or identity verification fails, open an ITSM ticket with category "Password Reset" and include the affected username. An IT agent will confirm identity via manager approval and a secondary credential. The temporary password is communicated through a separate secure channel — never over chat or unencrypted email. Every admin-assisted reset is recorded in the audit trail with the approving agent's ID.

## Account Lockout Recovery
User accounts are locked after five consecutive failed login attempts. To unlock an account: open Active Directory Users and Computers, locate the user account, right-click and select Unlock Account, then reset the password simultaneously to clear the bad-password counter. Notify the user through their manager's email to prevent repeat lockouts. If lockouts recur within 24 hours, escalate to the Security team to investigate potential credential compromise.

## Password Complexity and Compliance
All passwords must meet enterprise complexity requirements: minimum 12 characters, at least one uppercase letter, one lowercase letter, one digit, and one special character. Passwords cannot reuse any of the last 12 rotations. Multi-factor authentication must be re-enrolled within one business day of a forced password reset. Suspected credential compromise must be reported to the Security team immediately via the #security-incidents Slack channel.
