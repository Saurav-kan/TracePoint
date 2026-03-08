# Forensic Investigation Report v2.0
**Case ID:** 2026-SS-01
**Subject:** High-Security Vault Intrusion

## Summary of Findings
Post-incident analysis of the server rack located in the High-Security Vault (Room 402) has identified a rouge device connection during the suspected breach window (22:10 - 22:20).

## Device Identification
- **Hardware:** MacBook Pro (v14.2)
- **Serial Number:** C02XP193JGVD
- **MAC Address:** 3C:06:30:4F:A1:D2
- **Assigned User:** Elena Vance (Director of Engineering)

## Connection Logs
The server rack's internal monitoring system recorded an automated script execution at 22:15, which initiated a full copy of the "Aegis" encryption key directory (`/opt/secure/keys/aegis`). The data was transferred via USB 3.0 to a locally connected drive.

## Physical Evidence
The laptop was found physically present behind the server rack, partially obscured by a cooling cable bundle. Fingerprints were found on the laptop's chassis, though initial results were smudged and inconclusive.
