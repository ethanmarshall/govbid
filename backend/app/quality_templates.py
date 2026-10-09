"""Starter quality documents for a one-person manufacturing and supply shop (markdown, editable in the app).

They follow the general structure of ISO 9001:2015 without claiming certification. Regulatory references
were checked on 2026-10-08:
- FAR 52.246-15 Certificate of Conformance: https://www.acquisition.gov/far/52.246-15
- FAR 52.246-11 Higher-Level Contract Quality Requirement (Dec 2014): https://www.acquisition.gov/far/52.246-11
- FAR 52.246-26 Reporting Nonconforming Items (Aug 2024), GIDEP report within 60 days: https://www.acquisition.gov/far/52.246-26
- FAR 4.703(a)(1) records kept 3 years after final payment unless another period applies: https://www.acquisition.gov/far/4.703
- DFARS 252.246-7007 Contractor Counterfeit Electronic Part Detection and Avoidance System (JAN 2023), twelve system criteria:
  https://www.acquisition.gov/dfars/252.246-7007-contractor-counterfeit-electronic-part-detection-and-avoidance-system.
- DFARS 252.246-7008 Sources of Electronic Parts (JAN 2023): https://www.acquisition.gov/dfars/252.246-7008-sources-electronic-parts.
"""

COMPANY = "[Company name]"

QUALITY_MANUAL = """# Quality Manual

## 1. Purpose and scope
This manual describes how [Company name] controls the quality of the parts, cable assemblies and training equipment it makes or buys for its customers, including the Department of the Navy and the Defense Logistics Agency.

The business is run by one person who acts as owner, buyer, machinist or assembler, inspector and quality manager. Because one person does all of these jobs, this system relies on written checklists, travelers and records so that every step can be checked later by a customer or auditor.

This manual follows the general structure of ISO 9001:2015. [Company name] is not certified to ISO 9001, AS9100 or any other quality standard unless a current certificate is on file. When a contract includes FAR 52.246-11 (Higher-Level Contract Quality Requirement), the standard named in that contract governs and this manual will be updated to meet it.

## 2. Quality policy
We deliver what the contract and drawing require, on time, with records that prove it. When something goes wrong we stop, contain it, tell the customer when the contract requires it, and fix the cause.

## 3. Responsibilities
The owner is responsible for every element of this manual. When work is subcontracted, the owner remains responsible for the result and flows down the applicable requirements.

## 4. Contract review
Before quoting and again at award, review and record:
- Drawing number and revision, specifications and standards called out
- Quantity, unit of issue, delivery date and ship-to address
- Inspection and acceptance point (origin or destination) and FOB terms
- Quality clauses (for example FAR 52.246-2, 52.246-11, 52.246-15, DFARS 252.246-7007 and 252.246-7008 when present)
- Packaging and marking requirements (MIL-STD-129, MIL-STD-2073 codes), IUID marking and first article requirements
- Approved source or source control requirements

Questions go to the contracting officer in writing before acceptance. The review is recorded as the first step on the job traveler.

## 5. Purchasing and supplier control
- Buy only from suppliers on the Approved Supplier List, or record why an unlisted supplier was used.
- Approve suppliers on a stated basis: a survey, a current quality certificate (such as ISO 9001 or AS9100), or acceptable past performance.
- Purchase orders state the part or material, revision, quantity, required certifications and any flowed down contract requirements.
- Supplier performance is reviewed from purchase order history: on-time delivery and the share of material accepted at receiving.
- Suppliers with poor performance are placed on conditional status or disapproved.

## 6. Receiving inspection
Incoming material and purchased parts are inspected under the Receiving Inspection procedure before use. Material that fails is tagged, segregated and handled under the Nonconforming Material procedure.

## 7. Production control with travelers
Every job has a traveler listing each operation in order, the work center or outside vendor, planned dates, status, quantities good and rejected, and sign-off initials and date. Work does not move to the next operation until the current one is signed off. The drawing revision used is recorded on the traveler.

## 8. Inspection and test
- First article inspection is performed when the contract requires it and on any new part or new drawing revision.
- In-process checks are made at the operations noted on the traveler.
- Final inspection verifies dimensions, finish, marking and quantity against the drawing and contract before packaging.
- Inspection results are recorded and filed with the job.
- Only calibrated instruments are used for acceptance.

## 9. Control of nonconforming product
Nonconforming material is identified, segregated and recorded on a Nonconformance Report (NCR) under the Nonconforming Material procedure. Use-as-is or repair dispositions on government contract items are not made without customer approval when the contract requires it.

## 10. Corrective action
Significant or repeated nonconformances, customer complaints and audit findings get a Corrective Action Request (CAR) with a root cause, an action, a due date and a later check that the action worked.

## 11. Calibration
Measuring and test equipment is listed on the calibration log with an interval, last calibration date and next due date, and is controlled under the Calibration procedure. Overdue instruments are not used for acceptance.

## 12. Certificate of Conformance and shipping
When a contract allows a Certificate of Conformance (for example under FAR 52.246-15, which requires written authorization from the Contract Administration Office), the certificate is completed and signed only after final inspection and records review are complete. Packaging and marking follow the contract.

## 13. Records retention
Quality records (contract review, travelers, purchase orders, material certifications, inspection reports, NCRs, CARs, calibration certificates and certificates of conformance) are kept for at least 3 years after final payment, as FAR 4.703(a)(1) sets out generally, or longer when a contract or other rule requires it. Records are kept electronically with a backup.

## 14. Counterfeit parts prevention
Electronic parts and other parts at risk of counterfeiting are controlled under the Counterfeit Parts Prevention Plan.

## 15. Foreign object damage (FOD) prevention
- Keep work areas clean and clear tools, chips and hardware at the end of each operation.
- Account for small hardware and tools before closing assemblies, connectors or enclosures.
- Inspect cavities, connectors and openings for debris before final assembly and packaging.
- Cap or bag open connectors and ports.

## 16. Training and competence
The owner keeps a record of training, certifications (for example welding or IPC workmanship certifications) and the procedures read and understood. Any helper or subcontractor is trained on the procedures that apply to their work before starting.

## 17. Management review
At least once a year, and after any significant quality problem, the owner reviews on-time delivery, supplier performance, NCRs, CARs, customer feedback and calibration status, and records decisions and changes to this manual.

## Revision history
Kept in the GovBid Pro quality documents log.
"""

RECEIVING_INSPECTION = """# Receiving Inspection Procedure

## 1. Purpose
Make sure purchased material, parts and outside services meet the purchase order before they are used.

## 2. Scope
All material, hardware, purchased parts, cable and connectors, and parts returned from outside processing (finishing, heat treat, plating).

## 3. Procedure
1. Compare the packing slip with the purchase order: part number, revision, quantity and supplier.
2. Check packaging for damage. Note damage before signing for the shipment when possible.
3. Check required documents are present: material test reports or mill certs, certificates of conformance, finish or process certs, and traceability to the manufacturer for electronic parts.
4. Compare cert data with the purchase order and drawing: material grade, temper, specification, heat or lot number.
5. Inspect a sample or all pieces as appropriate: dimensions, finish, marking and visible defects. Record the instrument used.
6. For electronic parts, follow the Counterfeit Parts Prevention Plan.
7. Accept: record the received date, quantity accepted and certs received on the purchase order in GovBid Pro, file the certs under the job's records, and identify the material with the job number.
8. Reject: tag the material "REJECTED", move it to the hold area, record the quantity rejected on the purchase order and open an NCR.

## 4. Records
Purchase order receipt entries, certificates and any NCRs, kept with the job.
"""

NONCONFORMING = """# Nonconforming Material Procedure

## 1. Purpose
Prevent the use or shipment of material or product that does not meet requirements.

## 2. Procedure
1. **Identify.** Tag the item "HOLD" or "REJECTED" as soon as the problem is found.
2. **Segregate.** Move it to the marked hold area so it cannot be used by mistake.
3. **Record.** Open a Nonconformance Report (NCR) with the job, part, quantity and a description of what is wrong compared with the requirement.
4. **Contain.** Check other material from the same lot, setup or supplier, including product already shipped, and record what was checked.
5. **Disposition.** Choose one:
   - Use as is (only when the requirement is still met in function and, for government contract items, with customer approval when the contract requires it)
   - Rework (bring the item fully into conformance to the drawing)
   - Repair (make it usable but still not fully to the drawing; requires customer approval on government items when the contract requires it)
   - Scrap (mark and dispose so it cannot be reused)
   - Return to vendor (record on the purchase order and notify the supplier)
6. **Re-inspect** reworked or repaired items before release.
7. **Root cause and corrective action.** Record the root cause. Open a Corrective Action Request (CAR) for repeated, costly or customer-found problems.
8. **Close** the NCR when the disposition is complete.

## 3. Reporting
When FAR 52.246-26 (Reporting Nonconforming Items) is in the contract, report counterfeit or suspect counterfeit items, and common items with a major or critical nonconformance, to GIDEP within 60 days of becoming aware, and notify the contracting officer in writing of counterfeit or suspect counterfeit items. Check the clause in your contract for exact terms and exemptions.

## 4. Records
NCRs, dispositions, approvals and related CARs, kept with the job.
"""

CALIBRATION = """# Calibration Procedure

## 1. Purpose
Make sure instruments used to accept product give accurate results.

## 2. Scope
All instruments used for acceptance, for example calipers, micrometers, height gauges, gauge blocks, pin gauges, thread gauges, torque wrenches, multimeters, megohmmeters, hipot testers and crimp tools with crimp height or pull test checks.

## 3. Procedure
1. Give each instrument a unique ID and list it on the calibration log with its interval, last calibration date and calibration source.
2. Set the starting interval from the manufacturer's recommendation or the customer's requirement. Shorten it when an instrument is found out of tolerance; lengthen it only with a history of passing results.
3. Calibrate against standards traceable to national standards (NIST in the United States). Use a calibration lab accredited to ISO/IEC 17025 when one is practical, and keep each certificate.
4. Label each instrument with its ID and next due date.
5. Check instruments before use for damage and zero. Do not use an overdue or damaged instrument for acceptance.
6. If an instrument is found out of tolerance, record it, take it out of service, and review product accepted with it since its last good calibration. Open an NCR if product may be affected.
7. Store and handle instruments to protect their accuracy.

## 4. Records
Calibration log and certificates, kept for the life of the instrument plus the records retention period.
"""

COUNTERFEIT = """# Counterfeit Parts Prevention Plan

## 1. Purpose
Prevent counterfeit and suspect counterfeit parts, especially electronic parts, from entering products delivered to customers.

## 2. Applicability
This plan applies to all purchased electronic parts (connectors, contacts, wire and cable, ICs, passive components, relays, circuit protection) and to other parts at risk of counterfeiting. When DFARS 252.246-7007 (Contractor Counterfeit Electronic Part Detection and Avoidance System) or 252.246-7008 (Sources of Electronic Parts) is in a contract or flowed down, its terms govern.

## 3. Sources of supply
Buy in this order of preference, in line with DFARS 252.246-7008:
1. The original manufacturer, its authorized suppliers (franchised distributors), or suppliers that buy only from those sources.
2. If parts are not available from those sources, a supplier that this business has approved using established counterfeit prevention standards and processes, with the part risk recorded.
3. Any other source only as a last resort, with prompt written notice to the contracting officer when the contract requires it, and with inspection, testing and authentication recorded and available to the government.

## 4. Controls
- **Training.** The owner reviews this plan and counterfeit awareness material at least once a year and records it.
- **Purchasing.** Purchase orders for electronic parts require a manufacturer's certificate of conformance and traceability back to the original manufacturer.
- **Receiving inspection.** Check packaging, labels, lot and date codes, marking quality and paperwork for consistency. Compare with known good parts or manufacturer data when available.
- **Traceability.** Record manufacturer, part number, lot or date code and supplier for parts used on each job.
- **Suspect parts.** Quarantine suspect parts, do not return them to the supplier, record an NCR and investigate.
- **Reporting.** When FAR 52.246-26 is in the contract, report counterfeit or suspect counterfeit items to GIDEP within 60 days of becoming aware and notify the contracting officer in writing.
- **Flow-down.** Flow the applicable counterfeit prevention clauses to suppliers of electronic parts.
- **Obsolete parts.** Identify obsolete parts early in contract review and plan an authorized source or approved alternate.
- **Staying current.** Check GIDEP and other credible sources for counterfeit alerts on parts you buy.

## 5. Records
Supplier approvals, purchase orders, manufacturer certificates, receiving inspection results, NCRs and any GIDEP reports.
"""

STARTER_DOCUMENTS = [
    {"key": "quality_manual", "doc_number": "QM-001", "title": "Quality Manual", "content": QUALITY_MANUAL},
    {"key": "receiving_inspection", "doc_number": "QP-001", "title": "Receiving Inspection Procedure", "content": RECEIVING_INSPECTION},
    {"key": "nonconforming_material", "doc_number": "QP-002", "title": "Nonconforming Material Procedure", "content": NONCONFORMING},
    {"key": "calibration", "doc_number": "QP-003", "title": "Calibration Procedure", "content": CALIBRATION},
    {"key": "counterfeit_prevention", "doc_number": "QP-004", "title": "Counterfeit Parts Prevention Plan", "content": COUNTERFEIT},
]
