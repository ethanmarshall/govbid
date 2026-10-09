"""CMMC Level 1 and Level 2 (NIST SP 800-171 Rev 2) requirement data with DoD Assessment Methodology point values.

Sources (checked 2026-10-08):
- FAR 52.204-21(b)(1)(i)-(xv), Basic Safeguarding of Covered Contractor Information Systems:
  https://www.acquisition.gov/far/52.204-21 (requirement text below is quoted from it).
- CMMC Assessment Guide Level 1, Version 2.13, September 2024 (DoD CIO):
  https://dodcio.defense.gov/Portals/0/Documents/CMMC/AssessmentGuideL1.pdf
  (15 requirements, identifiers AC.L1-b.1.i through SI.L1-b.1.xv).
- NIST SP 800-171 DoD Assessment Methodology, Version 1.2.1, June 24, 2020, Annex A scoring template.
  Requirement text and point values below were parsed from a copy of that PDF (the acq.osd.mil copy could not be
  fetched from this environment because of a TLS error, so a university-hosted copy of the same document was used):
  https://cdn.prod.web.uta.edu/-/media/project/website/cross-timbers/documents/interim-rule-docs/nist-scoring-methodology.pdf
  The Annex A text reproduces the NIST SP 800-171 Rev 2 requirement statements. Weights sum to 313, so the lowest
  possible score is 110 - 313 = -203.
- NIST SP 800-171 Rev 2 (https://csrc.nist.gov/pubs/sp/800/171/r2/upd1/final). NIST withdrew Rev 2 on May 14, 2024
  in favor of Rev 3, but the CMMC program rule (32 CFR part 170) assesses Level 2 against Rev 2.
- 32 CFR 170.21 (POA&M rules): https://www.ecfr.gov/current/title-32/subtitle-A/chapter-I/subchapter-G/part-170/subpart-D/section-170.21
  Conditional Level 2 status needs a score of at least 0.8 x 110 (88). No requirement worth more than 1 point may be
  on a POA&M, except SC.L2-3.13.11 when encryption is used but is not FIPS-validated (3 points). Six requirements can
  never be POA&M items: 3.1.20, 3.1.22, 3.12.4, 3.10.3, 3.10.4, 3.10.5. POA&M items must be closed within 180 days.

Scoring notes from the methodology:
- 3.5.3 (MFA): subtract 5 if MFA is not implemented; subtract 3 if implemented for remote and privileged users but
  not for general users. In this app, status "partial" on 3.5.3 means that case.
- 3.13.11 (FIPS crypto): subtract 5 if no encryption; subtract 3 if encryption is used but not FIPS-validated.
  Status "partial" on 3.13.11 means that case.
- 3.12.4 (system security plan) has no point value ("NA"). Without an SSP the assessment cannot be completed at all,
  so the app treats a missing SSP as a blocking warning rather than a deduction.
- 3.1.12, 3.1.13, 3.1.16, 3.1.17, 3.1.18: no deduction if remote, wireless or mobile access is not permitted.
  Mark those "not_applicable" in that case.
- Partial implementation of any other requirement scores as not implemented (it earns no partial credit).
"""

LEVEL1_TOTAL = 15
SPRS_MAX = 110
CONDITIONAL_MIN_SCORE = 88  # 0.8 x 110, 32 CFR 170.21(a)(2)

# 800-171 requirement IDs whose point value is "3 to 5"
PARTIAL_CREDIT = {
    "3.5.3": {"full": 5, "partial": 3, "partial_meaning": "MFA in place for remote and privileged users, not yet for general users"},
    "3.13.11": {"full": 5, "partial": 3, "partial_meaning": "Encryption in place but not FIPS-validated"},
}

# Never allowed on a POA&M under 32 CFR 170.21(a)(2)(iii), regardless of point value
NO_POAM = {"3.1.20", "3.1.22", "3.12.4", "3.10.3", "3.10.4", "3.10.5"}

FAMILIES = {
    "AC": ("3.1", "Access Control"),
    "AT": ("3.2", "Awareness and Training"),
    "AU": ("3.3", "Audit and Accountability"),
    "CM": ("3.4", "Configuration Management"),
    "IA": ("3.5", "Identification and Authentication"),
    "IR": ("3.6", "Incident Response"),
    "MA": ("3.7", "Maintenance"),
    "MP": ("3.8", "Media Protection"),
    "PS": ("3.9", "Personnel Security"),
    "PE": ("3.10", "Physical Protection"),
    "RA": ("3.11", "Risk Assessment"),
    "CA": ("3.12", "Security Assessment"),
    "SC": ("3.13", "System and Communications Protection"),
    "SI": ("3.14", "System and Information Integrity"),
}

# FAR 52.204-21(b)(1) paragraph, CMMC L1 identifier, short name (L1 guide v2.13), FAR text, mapped 800-171 Rev 2 IDs
_LEVEL1 = [
    ("i", "AC.L1-b.1.i", "Authorized Access Control", "Limit information system access to authorized users, processes acting on behalf of authorized users, or devices (including other information systems).", ["3.1.1"]),
    ("ii", "AC.L1-b.1.ii", "Transaction & Function Control", "Limit information system access to the types of transactions and functions that authorized users are permitted to execute.", ["3.1.2"]),
    ("iii", "AC.L1-b.1.iii", "External Connections", "Verify and control/limit connections to and use of external information systems.", ["3.1.20"]),
    ("iv", "AC.L1-b.1.iv", "Control Public Information", "Control information posted or processed on publicly accessible information systems.", ["3.1.22"]),
    ("v", "IA.L1-b.1.v", "Identification", "Identify information system users, processes acting on behalf of users, or devices.", ["3.5.1"]),
    ("vi", "IA.L1-b.1.vi", "Authentication", "Authenticate (or verify) the identities of those users, processes, or devices, as a prerequisite to allowing access to organizational information systems.", ["3.5.2"]),
    ("vii", "MP.L1-b.1.vii", "Media Disposal", "Sanitize or destroy information system media containing Federal Contract Information before disposal or release for reuse.", ["3.8.3"]),
    ("viii", "PE.L1-b.1.viii", "Limit Physical Access", "Limit physical access to organizational information systems, equipment, and the respective operating environments to authorized individuals.", ["3.10.1"]),
    ("ix", "PE.L1-b.1.ix", "Manage Visitors & Physical Access", "Escort visitors and monitor visitor activity; maintain audit logs of physical access; and control and manage physical access devices.", ["3.10.3", "3.10.4", "3.10.5"]),
    ("x", "SC.L1-b.1.x", "Boundary Protection", "Monitor, control, and protect organizational communications (i.e., information transmitted or received by organizational information systems) at the external boundaries and key internal boundaries of the information systems.", ["3.13.1"]),
    ("xi", "SC.L1-b.1.xi", "Public-Access System Separation", "Implement subnetworks for publicly accessible system components that are physically or logically separated from internal networks.", ["3.13.5"]),
    ("xii", "SI.L1-b.1.xii", "Flaw Remediation", "Identify, report, and correct information and information system flaws in a timely manner.", ["3.14.1"]),
    ("xiii", "SI.L1-b.1.xiii", "Malicious Code Protection", "Provide protection from malicious code at appropriate locations within organizational information systems.", ["3.14.2"]),
    ("xiv", "SI.L1-b.1.xiv", "Update Malicious Code Protection", "Update malicious code protection mechanisms when new releases are available.", ["3.14.4"]),
    ("xv", "SI.L1-b.1.xv", "System & File Scanning", "Perform periodic scans of the information system and real-time scans of files from external sources as files are downloaded, opened, or executed.", ["3.14.5"]),
]

# 800-171 Rev 2 ID, CMMC family, DoD Assessment Methodology v1.2.1 value (max for 3-to-5 items; 0 for 3.12.4 "NA"),
# requirement text, methodology comment
_LEVEL2 = [
    ('3.1.1', 'AC', 5, 'Limit system access to authorized users, processes acting on behalf of authorized users, and devices (including other systems).', ''),
    ('3.1.2', 'AC', 5, 'Limit system access to the types of transactions and functions that authorized users are permitted to execute.', ''),
    ('3.1.3', 'AC', 1, 'Control the flow of CUI in accordance with approved authorizations.', ''),
    ('3.1.4', 'AC', 1, 'Separate the duties of individuals to reduce the risk of malevolent activity without collusion.', ''),
    ('3.1.5', 'AC', 3, 'Employ the principle of least privilege, including for specific security functions and privileged accounts.', ''),
    ('3.1.6', 'AC', 1, 'Use non-privileged accounts or roles when accessing non-security functions.', ''),
    ('3.1.7', 'AC', 1, 'Prevent non-privileged users from executing privileged functions and capture the execution of such functions in audit logs.', ''),
    ('3.1.8', 'AC', 1, 'Limit unsuccessful logon attempts.', ''),
    ('3.1.9', 'AC', 1, 'Provide privacy and security notices consistent with applicable CUI rules.', ''),
    ('3.1.10', 'AC', 1, 'Use session lock with pattern-hiding displays to prevent access and viewing of data after a period of inactivity.', ''),
    ('3.1.11', 'AC', 1, 'Terminate (automatically) a user session after a defined condition.', ''),
    ('3.1.12', 'AC', 5, 'Monitor and control remote access sessions.', 'Do not subtract points if remote access not permitted'),
    ('3.1.13', 'AC', 5, 'Employ cryptographic mechanisms to protect the confidentiality of remote access sessions.', 'Do not subtract points if remote access not permitted'),
    ('3.1.14', 'AC', 1, 'Route remote access via managed access control points.', ''),
    ('3.1.15', 'AC', 1, 'Authorize remote execution of privileged commands and remote access to security-relevant information.', ''),
    ('3.1.16', 'AC', 5, 'Authorize wireless access prior to allowing such connections.', 'Do not subtract points if wireless access not permitted'),
    ('3.1.17', 'AC', 5, 'Protect wireless access using authentication and encryption.', 'Do not subtract points if wireless access not permitted'),
    ('3.1.18', 'AC', 5, 'Control connection of mobile devices.', 'Do not subtract points if connection of mobile devices is not permitted'),
    ('3.1.19', 'AC', 3, 'Encrypt CUI on mobile devices and mobile computing platforms.', 'Exposure limited to CUI on mobile platform'),
    ('3.1.20', 'AC', 1, 'Verify and control/limit connections to and use of external systems.', ''),
    ('3.1.21', 'AC', 1, 'Limit use of portable storage devices on external systems.', ''),
    ('3.1.22', 'AC', 1, 'Control CUI posted or processed on publicly accessible systems.', ''),
    ('3.2.1', 'AT', 5, 'Ensure that managers, systems administrators, and users of organizational systems are made aware of the security risks associated with their activities and of the applicable policies, standards, and procedures related to the security of those systems.', ''),
    ('3.2.2', 'AT', 5, 'Ensure that personnel are trained to carry out their assigned information security-related duties and responsibilities.', ''),
    ('3.2.3', 'AT', 1, 'Provide security awareness training on recognizing and reporting potential indicators of insider threat.', ''),
    ('3.3.1', 'AU', 5, 'Create and retain system audit logs and records to the extent needed to enable the monitoring, analysis, investigation, and reporting of unlawful or unauthorized system activity.', ''),
    ('3.3.2', 'AU', 3, 'Ensure that the actions of individual system users can be uniquely traced to those users so they can be held accountable for their actions.', ''),
    ('3.3.3', 'AU', 1, 'Review and update logged events.', ''),
    ('3.3.4', 'AU', 1, 'Alert in the event of an audit logging process failure.', ''),
    ('3.3.5', 'AU', 5, 'Correlate audit record review, analysis, and reporting processes for investigation and response to indications of unlawful, unauthorized, suspicious, or unusual activity.', ''),
    ('3.3.6', 'AU', 1, 'Provide audit record reduction and report generation to support on-demand analysis and reporting.', ''),
    ('3.3.7', 'AU', 1, 'Provide a system capability that compares and synchronizes internal system clocks with an authoritative source to generate time stamps for audit records.', ''),
    ('3.3.8', 'AU', 1, 'Protect audit information and audit logging tools from unauthorized access, modification, and deletion.', ''),
    ('3.3.9', 'AU', 1, 'Limit management of audit logging functionality to a subset of privileged users.', ''),
    ('3.4.1', 'CM', 5, 'Establish and maintain baseline configurations and inventories of organizational systems (including hardware, software, firmware, and documentation) throughout the respective system development life cycles.', ''),
    ('3.4.2', 'CM', 5, 'Establish and enforce security configuration settings for information technology products employed in organizational systems.', ''),
    ('3.4.3', 'CM', 1, 'Track, review, approve or disapprove, and log changes to organizational systems.', ''),
    ('3.4.4', 'CM', 1, 'Analyze the security impact of changes prior to implementation.', ''),
    ('3.4.5', 'CM', 5, 'Define, document, approve, and enforce physical and logical access restrictions associated with changes to organizational systems.', ''),
    ('3.4.6', 'CM', 5, 'Employ the principle of least functionality by configuring organizational systems to provide only essential capabilities.', ''),
    ('3.4.7', 'CM', 5, 'Restrict, disable, or prevent the use of nonessential programs, functions, ports, protocols, and services.', ''),
    ('3.4.8', 'CM', 5, 'Apply deny-by-exception (blacklisting) policy to prevent the use of unauthorized software or deny-all, permit-by-exception (whitelisting) policy to allow the execution of authorized software.', ''),
    ('3.4.9', 'CM', 1, 'Control and monitor user-installed software.', ''),
    ('3.5.1', 'IA', 5, 'Identify system users, processes acting on behalf of users, and devices.', ''),
    ('3.5.2', 'IA', 5, 'Authenticate (or verify) the identities of users, processes, or devices, as a prerequisite to allowing access to organizational systems.', ''),
    ('3.5.3', 'IA', 5, 'Use multifactor authentication (MFA) for local and network access to privileged accounts and for network access to non-privileged accounts.', 'Subtract 5 points if MFA not implemented. Subtract 3 points if implemented for remote and privileged users, but not the general user'),
    ('3.5.4', 'IA', 1, 'Employ replay-resistant authentication mechanisms for network access to privileged and non-privileged accounts.', ''),
    ('3.5.5', 'IA', 1, 'Prevent reuse of identifiers for a defined period.', ''),
    ('3.5.6', 'IA', 1, 'Disable identifiers after a defined period of inactivity.', ''),
    ('3.5.7', 'IA', 1, 'Enforce a minimum password complexity and change of characters when new passwords are created.', ''),
    ('3.5.8', 'IA', 1, 'Prohibit password reuse for a specified number of generations.', ''),
    ('3.5.9', 'IA', 1, 'Allow temporary password use for system logons with an immediate change to a permanent password.', ''),
    ('3.5.10', 'IA', 5, 'Store and transmit only cryptographically-protected passwords.', 'Encrypted representations of passwords include, for example, encrypted versions of passwords and one-way cryptographic hashes of passwords'),
    ('3.5.11', 'IA', 1, 'Obscure feedback of authentication information.', ''),
    ('3.6.1', 'IR', 5, 'Establish an operational incident-handling capability for organizational systems that includes preparation, detection, analysis, containment, recovery, and user response activities.', ''),
    ('3.6.2', 'IR', 5, 'Track, document, and report incidents to designated officials and/or authorities both internal and external to the organization.', ''),
    ('3.6.3', 'IR', 1, 'Test the organizational incident response capability.', ''),
    ('3.7.1', 'MA', 3, 'Perform maintenance on organizational systems.', ''),
    ('3.7.2', 'MA', 5, 'Provide controls on the tools, techniques, mechanisms, and personnel used to conduct system maintenance.', ''),
    ('3.7.3', 'MA', 1, 'Ensure equipment removed for off-site maintenance is sanitized of any CUI.', ''),
    ('3.7.4', 'MA', 3, 'Check media containing diagnostic and test programs for malicious code before the media are used in organizational systems.', ''),
    ('3.7.5', 'MA', 5, 'Require multifactor authentication to establish nonlocal maintenance sessions via external network connections and terminate such connections when nonlocal maintenance is complete.', ''),
    ('3.7.6', 'MA', 1, 'Supervise the maintenance activities of maintenance personnel without required access authorization.', ''),
    ('3.8.1', 'MP', 3, 'Protect (i.e., physically control and securely store) system media containing CUI, both paper and digital.', 'Exposure limited to CUI on media'),
    ('3.8.2', 'MP', 3, 'Limit access to CUI on system media to authorized users.', 'Exposure limited to CUI on media'),
    ('3.8.3', 'MP', 5, 'Sanitize or destroy system media containing CUI before disposal or release for reuse.', 'While exposure limited to CUI on media, failure to sanitize can result in continual exposure of CUI'),
    ('3.8.4', 'MP', 1, 'Mark media with necessary CUI markings and distribution limitations.', ''),
    ('3.8.5', 'MP', 1, 'Control access to media containing CUI and maintain accountability for media during transport outside of controlled areas.', ''),
    ('3.8.6', 'MP', 1, 'Implement cryptographic mechanisms to protect the confidentiality of CUI stored on digital media during transport unless otherwise protected by alternative physical safeguards.', ''),
    ('3.8.7', 'MP', 5, 'Control the use of removable media on system components.', ''),
    ('3.8.8', 'MP', 3, 'Prohibit the use of portable storage devices when such devices have no identifiable owner.', ''),
    ('3.8.9', 'MP', 1, 'Protect the confidentiality of backup CUI at storage locations.', ''),
    ('3.9.1', 'PS', 3, 'Screen individuals prior to authorizing access to organizational systems containing CUI.', ''),
    ('3.9.2', 'PS', 5, 'Ensure that organizational systems containing CUI are protected during and after personnel actions such as terminations and transfers.', ''),
    ('3.10.1', 'PE', 5, 'Limit physical access to organizational systems, equipment, and the respective operating environments to authorized individuals.', ''),
    ('3.10.2', 'PE', 5, 'Protect and monitor the physical facility and support infrastructure for organizational systems.', ''),
    ('3.10.3', 'PE', 1, 'Escort visitors and monitor visitor activity.', ''),
    ('3.10.4', 'PE', 1, 'Maintain audit logs of physical access.', ''),
    ('3.10.5', 'PE', 1, 'Control and manage physical access devices.', ''),
    ('3.10.6', 'PE', 1, 'Enforce safeguarding measures for CUI at alternate work sites.', ''),
    ('3.11.1', 'RA', 3, 'Periodically assess the risk to organizational operations (including mission, functions, image, or reputation), organizational assets, and individuals, resulting from the operation of organizational systems and the associated processing, storage, or transmission of CUI.', ''),
    ('3.11.2', 'RA', 5, 'Scan for vulnerabilities in organizational systems and applications periodically and when new vulnerabilities affecting those systems and applications are identified.', ''),
    ('3.11.3', 'RA', 1, 'Remediate vulnerabilities in accordance with risk assessments.', ''),
    ('3.12.1', 'CA', 5, 'Periodically assess the security controls in organizational systems to determine if the controls are effective in their application.', ''),
    ('3.12.2', 'CA', 3, 'Develop and implement plans of action designed to correct deficiencies and reduce or eliminate vulnerabilities in organizational systems.', ''),
    ('3.12.3', 'CA', 5, 'Monitor security controls on an ongoing basis to ensure the continued effectiveness of the controls.', ''),
    ('3.12.4', 'CA', 0, 'Develop, document, and periodically update system security plans that describe system boundaries, system environments of operation, how security requirements are implemented, and the relationships with or connections to other systems.', 'The absence of a system security plan would result in a finding that ‘an assessment could not be completed due to incomplete information and noncompliance with DFARS clause 252.204-7012.’'),
    ('3.13.1', 'SC', 5, 'Monitor, control, and protect communications (i.e., information transmitted or received by organizational systems) at the external boundaries and key internal boundaries of organizational systems.', ''),
    ('3.13.2', 'SC', 5, 'Employ architectural designs, software development techniques, and systems engineering principles that promote effective information security within organizational systems.', ''),
    ('3.13.3', 'SC', 1, 'Separate user functionality from system management functionality.', ''),
    ('3.13.4', 'SC', 1, 'Prevent unauthorized and unintended information transfer via shared system resources.', ''),
    ('3.13.5', 'SC', 5, 'Implement subnetworks for publicly accessible system components that are physically or logically separated from internal networks.', ''),
    ('3.13.6', 'SC', 5, 'Deny network communications traffic by default and allow network communications traffic by exception (i.e., deny all, permit by exception).', ''),
    ('3.13.7', 'SC', 1, 'Prevent remote devices from simultaneously establishing non-remote connections with organizational systems and communicating via some other connection to resources in external networks (i.e., split tunneling).', ''),
    ('3.13.8', 'SC', 3, 'Implement cryptographic mechanisms to prevent unauthorized disclosure of CUI during transmission unless otherwise protected by alternative physical safeguards.', ''),
    ('3.13.9', 'SC', 1, 'Terminate network connections associated with communications sessions at the end of the sessions or after a defined period of inactivity.', ''),
    ('3.13.10', 'SC', 1, 'Establish and manage cryptographic keys for cryptography employed in organizational systems.', ''),
    ('3.13.11', 'SC', 5, 'Employ FIPS-validated cryptography when used to protect the confidentiality of CUI.', 'Subtract 5 points if no cryptography is employed; 3 points if mostly not FIPS validated'),
    ('3.13.12', 'SC', 1, 'Prohibit remote activation of collaborative computing devices and provide indication of devices in use to users present at the device.', ''),
    ('3.13.13', 'SC', 1, 'Control and monitor the use of mobile code.', ''),
    ('3.13.14', 'SC', 1, 'Control and monitor the use of Voice over Internet Protocol (VoIP) technologies.', ''),
    ('3.13.15', 'SC', 5, 'Protect the authenticity of communications sessions.', ''),
    ('3.13.16', 'SC', 1, 'Protect the confidentiality of CUI at rest.', ''),
    ('3.14.1', 'SI', 5, 'Identify, report, and correct system flaws in a timely manner.', ''),
    ('3.14.2', 'SI', 5, 'Provide protection from malicious code at designated locations within organizational systems.', ''),
    ('3.14.3', 'SI', 5, 'Monitor system security alerts and advisories and take action in response.', ''),
    ('3.14.4', 'SI', 5, 'Update malicious code protection mechanisms when new releases are available.', ''),
    ('3.14.5', 'SI', 3, 'Perform periodic scans of organizational systems and real-time scans of files from external sources as files are downloaded, opened, or executed.', ''),
    ('3.14.6', 'SI', 5, 'Monitor organizational systems, including inbound and outbound communications traffic, to detect attacks and indicators of potential attacks.', ''),
    ('3.14.7', 'SI', 3, 'Identify unauthorized use of organizational systems.', ''),]

LEVEL1_CONTROLS = [
    {
        "framework": "L1",
        "control_id": cid,
        "family": cid.split(".")[0],
        "family_name": FAMILIES[cid.split(".")[0]][1],
        "far_paragraph": f"52.204-21(b)(1)({para})",
        "title": name,
        "text": text,
        "nist_ids": nist,
        "weight": None,
        "scoring_note": "",
        "poam_allowed": False,  # 32 CFR 170.21(a)(1): POA&Ms are not permitted for Level 1
    }
    for para, cid, name, text, nist in _LEVEL1
]

LEVEL2_CONTROLS = [
    {
        "framework": "L2",
        "control_id": nid,
        "family": fam,
        "family_name": FAMILIES[fam][1],
        "cmmc_id": f"{fam}.L2-{nid}",
        "far_paragraph": "",
        "title": text,
        "text": text,
        "nist_ids": [nid],
        "weight": weight,
        "scoring_note": note,
        "poam_allowed": nid not in NO_POAM and (weight <= 1 or nid == "3.13.11"),
    }
    for nid, fam, weight, text, note in _LEVEL2
]

ALL_CONTROLS = LEVEL1_CONTROLS + LEVEL2_CONTROLS
CONTROL_INDEX = {(c["framework"], c["control_id"]): c for c in ALL_CONTROLS}
WEIGHTS = {c["control_id"]: c["weight"] for c in LEVEL2_CONTROLS}


def deduction(control_id: str, status: str) -> int:
    """Points subtracted from 110 for one Level 2 requirement in the given status."""
    if status in ("implemented", "not_applicable"):
        return 0
    if status == "partial" and control_id in PARTIAL_CREDIT:
        return PARTIAL_CREDIT[control_id]["partial"]
    return WEIGHTS.get(control_id, 0) or 0


def sprs_score(statuses: dict[str, str]) -> int:
    """110 minus the deductions for every Level 2 requirement. Missing IDs count as not implemented."""
    return SPRS_MAX - sum(deduction(c["control_id"], statuses.get(c["control_id"], "not_started")) for c in LEVEL2_CONTROLS)


assert len(LEVEL1_CONTROLS) == 15
assert len(LEVEL2_CONTROLS) == 110
assert sum(WEIGHTS.values()) == 313
