# VPN Setup and Troubleshooting Runbook

## Overview
This runbook covers installation, configuration, and troubleshooting of the corporate VPN client used for remote access to internal systems. All remote employees must connect via VPN when accessing internal resources. The approved client is Cisco AnyConnect; third-party VPN clients are not permitted.

## Installing Cisco AnyConnect
Download the Cisco AnyConnect installer from the IT Software Portal under Remote Access Tools. Run the installer with administrator privileges. When prompted for the server address, enter vpn.corp.internal. Use your Active Directory credentials (username and password) for authentication. Multi-factor authentication is required — approve the push notification on your registered MFA device before the session is established.

## Connecting and Disconnecting
Open Cisco AnyConnect from the system tray. Click Connect and select the profile matching your region (US-East, US-West, EU, or APAC). Enter your Active Directory username and password. After successful MFA approval the VPN tunnel is established. To disconnect, click the AnyConnect icon in the system tray and select Disconnect. Always disconnect before shutting down your machine to ensure session cleanup.

## Common Troubleshooting Steps
If the VPN fails to connect: verify your internet connection is active; confirm your MFA device has network access; restart the AnyConnect service via Services Manager; and retry. If authentication fails, check that your AD password has not expired — a forced password reset clears the VPN session token. If the tunnel connects but internal sites are unreachable, flush the DNS cache with ipconfig /flushdns on Windows or sudo dscacheutil -flushcache on macOS. Persistent issues should be escalated to the Network team via ITSM.

## Split Tunneling Policy
Corporate VPN uses full-tunnel mode by default: all traffic routes through the corporate gateway. Split tunneling is disabled to ensure endpoint security policy enforcement. Employees may not modify VPN routing tables or install alternate tunnel clients. Requests for VPN exceptions must be approved by the CISO and documented in the security register.
