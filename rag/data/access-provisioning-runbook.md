# Access Provisioning Runbook

## Overview
This runbook covers the end-to-end process for granting, modifying, and revoking user access to corporate systems, applications, and data resources. Access follows the principle of least privilege: employees receive only the permissions required for their current role. All access changes are logged and subject to quarterly access reviews.

## Requesting Access to a System or Resource
Submit an access request ticket in the ITSM portal with the following details: the resource or system name, the specific role or permission level required, the business justification, and your manager's name for approval. For production systems and databases, a secondary approval from the resource owner or data steward is also required. Requests without complete justification are automatically returned to the requestor.

## Provisioning Access in Active Directory
After all approvals are recorded in ITSM, the IT administrator adds the user to the appropriate Active Directory security group. Access to file shares and internal web applications is controlled through group membership. For cloud resources on AWS or GCP, the IAM administrator assigns the appropriate IAM role to the user's federated identity. Provisioning is completed within one business day of final approval; urgent requests can be expedited with VP-level sign-off.

## Provisioning Database and Application Access
Database access is granted at the schema or table level following the principle of least privilege. The DBA team creates a role-specific database account and records the credential in the corporate secrets vault. Application-level access is configured by the application owner. Users receive access confirmation and credential retrieval instructions via encrypted email. Direct database access for non-DBA employees requires a time-boxed approval that expires after 30 days.

## Access Revocation and Offboarding
Access must be revoked immediately when an employee changes roles or departs. The HR system triggers an automated offboarding workflow that disables the Active Directory account, removes all group memberships, and revokes cloud IAM roles within one hour of the offboarding event. Contractors and temporary staff have time-boxed accounts that expire automatically on their contract end date. Access revocation is a destructive operation: it requires confirmation from the employee's manager and is logged with a non-repudiation audit record.
