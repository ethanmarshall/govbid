// Reference library for proposal packages and technical data packages.
// "free" marks documents you can download at no cost. Paid standards link to the publisher.
// "clauses" ties a resource to FAR/DFARS clauses so the opportunity page can suggest it.

export const ASSIST = 'https://quicksearch.dla.mil/qsSearch.aspx'

export const CATEGORIES = [
  {
    id: 'proposal',
    title: 'Writing the proposal',
    blurb: 'How solicitations are structured, how offers are evaluated, and where to get free help.',
    items: [
      { name: 'FAR 15.204-1 Uniform contract format (Sections A to M)', desc: 'Explains what goes in each section of a negotiated solicitation. Section L tells you how to write it; Section M tells you how it will be scored.', url: 'https://www.acquisition.gov/far/15.204-1', free: true },
      { name: 'FAR Part 15 Contracting by negotiation', desc: 'Source selection rules: tradeoff vs. LPTA, discussions, competitive range, debriefings.', url: 'https://www.acquisition.gov/far/part-15', free: true },
      { name: 'FAR 52.212-1 Instructions to offerors (commercial)', desc: 'Default submission rules for commercial RFQs and combined synopsis/solicitations.', url: 'https://www.acquisition.gov/far/52.212-1', free: true, clauses: ['52.212-1'] },
      { name: 'FAR 52.212-2 Evaluation (commercial)', desc: 'Template for how commercial offers are evaluated. The solicitation fills in the actual factors.', url: 'https://www.acquisition.gov/far/52.212-2', free: true, clauses: ['52.212-2'] },
      { name: 'FAR 52.212-3 Offeror representations and certifications', desc: 'Reps and certs, mostly completed through your SAM registration.', url: 'https://www.acquisition.gov/far/52.212-3', free: true, clauses: ['52.212-3'] },
      { name: 'FAR 52.219-14 Limitations on subcontracting', desc: 'How much of a set-aside contract you must self-perform. Plan teaming around this.', url: 'https://www.acquisition.gov/far/52.219-14', free: true, clauses: ['52.219-14'] },
      { name: 'DFARS (full text)', desc: 'DoD supplement. Clauses starting with 252. are here.', url: 'https://www.acquisition.gov/dfars', free: true },
      { name: 'APEX Accelerators (find your local office)', desc: 'Free, government-funded counseling on proposals, registrations and compliance. The best first call for a new contractor.', url: 'https://www.napex.us/locations/', free: true },
      { name: 'Defense Acquisition University', desc: 'Free acquisition training, glossary and guidebooks. Useful for understanding how the buyer thinks.', url: 'https://www.dau.edu/', free: true },
      { name: 'SBA federal contracting guide', desc: 'Set-aside programs, certifications and the basics of selling to the government.', url: 'https://www.sba.gov/federal-contracting', free: true },
      { name: 'VA Office of Small and Disadvantaged Business Utilization', desc: 'Vets First program, VA forecasts and SDVOSB outreach events.', url: 'https://www.va.gov/osdbu/', free: true },
    ],
  },
  {
    id: 'pricing',
    title: 'Pricing and past performance',
    blurb: 'Supporting data for the price volume and past performance volume.',
    items: [
      { name: 'SBA table of size standards', desc: 'Confirm you are small under the solicitation NAICS before you bid.', url: 'https://www.sba.gov/document/support-table-size-standards', free: true, clauses: ['52.219-1'] },
      { name: 'Wage determinations (SCA and Davis-Bacon)', desc: 'Minimum wages and fringe for service and construction labor. Price against the one attached to the solicitation.', url: 'https://sam.gov/content/wage-determinations', free: true, clauses: ['52.222-41', '52.222-6'] },
      { name: 'GSA CALC+ labor pricing', desc: 'Awarded GSA schedule labor rates by category. Good for sanity-checking your rates.', url: 'https://buy.gsa.gov/pricing/', free: true },
      { name: 'CPARS', desc: 'Where agencies record your performance. Review your evaluations here and cite them as past performance.', url: 'https://www.cpars.gov/', free: true },
      { name: 'USAspending.gov', desc: 'Past award amounts by agency, NAICS and competitor (also built into Competitor intel).', url: 'https://www.usaspending.gov/search', free: true },
    ],
  },
  {
    id: 'asme',
    title: 'Engineering drawings (ASME Y14)',
    blurb: 'The drawing standards DoD has adopted. These are paid documents from ASME. Check which edition your contract or MIL-STD-100 calls out.',
    items: [
      { name: 'ASME Y14.5 Dimensioning and tolerancing (GD&T)', desc: 'The core GD&T standard. Current edition is 2018, reaffirmed 2024.', url: 'https://www.asme.org/codes-standards/find-codes-standards/y14-5-dimensioning-tolerancing', free: false },
      { name: 'ASME Y14.100 Engineering drawing practices', desc: 'Drawing content, numbering, notes and data management. Basis of MIL-STD-100.', url: 'https://www.asme.org/codes-standards/find-codes-standards', free: false },
      { name: 'ASME Y14.24 Types and applications of engineering drawings', desc: 'Detail, assembly, altered item, source control and specification control drawings.', url: 'https://www.asme.org/codes-standards/find-codes-standards', free: false },
      { name: 'ASME Y14.34 Associated lists', desc: 'Parts lists, data lists and index lists that accompany drawings.', url: 'https://www.asme.org/codes-standards/find-codes-standards', free: false },
      { name: 'ASME Y14.35 Revision of engineering drawings', desc: 'Revision letters, revision blocks and change records.', url: 'https://www.asme.org/codes-standards/find-codes-standards', free: false },
      { name: 'ASME Y14.41 Digital product definition data practices', desc: 'Model-based definition (3D models with PMI) in place of 2D drawings.', url: 'https://www.asme.org/codes-standards/find-codes-standards', free: false },
      { name: 'ASME Y14.38 Abbreviations and acronyms', desc: 'Approved abbreviations for drawings and related documents.', url: 'https://www.asme.org/codes-standards/find-codes-standards', free: false },
      { name: 'ANSI/ISA-5.1 Instrumentation symbols and identification', desc: 'P&ID symbols and tag numbering for process and instrumentation drawings.', url: 'https://www.isa.org/standards-and-publications/isa-standards', free: false },
    ],
  },
  {
    id: 'deliverables',
    title: 'Data deliverables (CDRLs and DIDs)',
    blurb: 'Contract data requirements are listed on DD Form 1423 (CDRL). Each line points to a Data Item Description (DID) that defines the format. DIDs are free on ASSIST.',
    items: [
      { name: 'DoD forms (DD 1423, DD 250, DD 1149, DD 254)', desc: 'Official DoD form library. DD 1423 lists required data deliverables.', url: 'https://www.esd.whs.mil/Directives/forms/', free: true },
      { name: 'DI-SESS-81000', id: 'DI-SESS-81000', desc: 'Product drawings/models and associated lists. The usual DID for drawing deliverables in a TDP.', url: ASSIST, free: true },
      { name: 'DI-NDTI-80603', id: 'DI-NDTI-80603', desc: 'Test procedure.', url: ASSIST, free: true },
      { name: 'DI-NDTI-80809', id: 'DI-NDTI-80809', desc: 'Test/inspection report.', url: ASSIST, free: true },
      { name: 'DI-MISC-80508', id: 'DI-MISC-80508', desc: 'Technical report, study/services. A common catch-all report format.', url: ASSIST, free: true },
      { name: 'DI-CMAN-80639', id: 'DI-CMAN-80639', desc: 'Engineering change proposal (ECP).', url: ASSIST, free: true },
      { name: 'MIL-STD-130 IUID marking', id: 'MIL-STD-130', desc: 'Identification marking of U.S. military property, including IUID 2D data matrix marks. The full standards list is on the Standards library page.', url: ASSIST, free: true, clauses: ['252.211-7003'] },
      { name: 'PIEE / Wide Area WorkFlow', desc: 'Where DoD invoices, receiving reports (the electronic DD 250) and some deliverables are submitted.', url: 'https://piee.eb.mil/', free: true, clauses: ['252.232-7006'] },
      { name: 'FAR 52.246-15 Certificate of conformance', desc: 'When allowed, ship with a signed CoC instead of government inspection.', url: 'https://www.acquisition.gov/far/52.246-15', free: true },
      { name: 'FAR Subpart 9.3 First article testing', desc: 'Rules for first article approval before production.', url: 'https://www.acquisition.gov/far/subpart-9.3', free: true },
    ],
  },
  {
    id: 'quality',
    title: 'Quality and configuration management',
    blurb: 'Standards commonly cited for quality systems and change control.',
    items: [
      { name: 'ISO 9001 Quality management systems', desc: 'General quality system standard. Often cited in Section C or as an evaluation strength.', url: 'https://www.iso.org/standard/62085.html', free: false },
      { name: 'SAE AS9100 Aerospace quality management', desc: 'ISO 9001 plus aerospace and defense requirements.', url: 'https://www.sae.org/standards/content/as9100d/', free: false },
      { name: 'SAE EIA-649 Configuration management standard', desc: 'Industry CM standard DoD uses with MIL-HDBK-61.', url: 'https://www.sae.org/standards/content/eia649c/', free: false },
      { name: 'IPC standards (J-STD-001, IPC-A-610, IPC/WHMA-A-620)', desc: 'Soldering, electronic assembly acceptability, and cable and harness workmanship.', url: 'https://www.ipc.org/', free: false, clauses: ['252.246-7008'] },
    ],
  },
  {
    id: 'cyber',
    title: 'Cybersecurity and registrations',
    blurb: 'Requirements that can block an award if you are not ready.',
    items: [
      { name: 'NIST SP 800-171', desc: 'Security controls for Controlled Unclassified Information. Required by DFARS 252.204-7012.', url: 'https://csrc.nist.gov/pubs/sp/800/171/r3/final', free: true, clauses: ['252.204-7012', '252.204-7019'] },
      { name: 'CMMC program (DoD CIO)', desc: 'CMMC levels, assessment requirements and timeline.', url: 'https://dodcio.defense.gov/CMMC/', free: true, clauses: ['252.204-7021', '252.204-7025'] },
      { name: 'FAR 52.204-21 Basic safeguarding', desc: 'The 15 basic controls that map to CMMC Level 1.', url: 'https://www.acquisition.gov/far/52.204-21', free: true, clauses: ['52.204-21'] },
      { name: 'CAGE code lookup', desc: 'Look up or verify CAGE codes for your company and teaming partners.', url: 'https://cage.dla.mil/', free: true },
      { name: 'SBA VetCert', desc: 'SDVOSB and VOSB certification applications and status.', url: 'https://veterans.certify.sba.gov/', free: true, clauses: ['52.219-27'] },
    ],
  },
]

export const CHECKLISTS = [
  {
    id: 'proposal',
    title: 'Technical proposal package',
    items: [
      'Read Sections L and M (or 52.212-1 and 52.212-2 addenda) and every amendment',
      'Build the compliance matrix and map each requirement to a proposal section',
      'Confirm set-aside eligibility, size under the NAICS, and active SAM registration',
      'Check limitations on subcontracting against your teaming plan',
      'Submit questions to the contracting officer before the questions deadline',
      'Cover letter with solicitation number, UEI, CAGE, point of contact and validity period',
      'Technical volume organized in the same order as Section L, within page limits',
      'Management plan: staffing, key personnel resumes, schedule, quality control',
      'Past performance: recent, relevant references with contract numbers and POCs',
      'Price volume: CLIN pricing in the required format, wage determination applied',
      'Signed SF 1449 / SF 33 / SF 30 amendment acknowledgments',
      'Reps and certs complete (SAM, 52.204-24/-26, any solicitation-specific forms)',
      'Formatting: font, margins, file type, file naming and size limits',
      'Final compliance check against the matrix, then submit before the deadline and keep proof of submission',
    ],
  },
  {
    id: 'tdp',
    title: 'Technical data package for completed work',
    items: [
      'Pull the CDRL (DD 1423) and each DID the contract lists',
      'Confirm the TDP type and elements on the MIL-STD-31000 option selection worksheet',
      'Drawings to ASME Y14.100 / MIL-STD-100, with GD&T to the edition the contract cites',
      'Models and drawing native files plus neutral formats (STEP, PDF) as specified',
      'Associated lists: parts lists, data lists, index list (ASME Y14.34)',
      'Specifications and source or specification control drawings for purchased parts',
      'Revision history and approved ECPs; drawings match the as-built configuration',
      'Test procedures and test/inspection reports, signed and dated',
      'Certificates of conformance and material certifications',
      'IUID marking data and registry entries where 252.211-7003 applies',
      'Operation and maintenance manuals per the cited manual standard',
      'Distribution statements, export control markings and data rights legends on every document',
      'Transmittal letter listing each deliverable against its CDRL line',
      'Submit through the required system (often PIEE/WAWF) and keep the acceptance record',
    ],
  },
]

export function resourcesForClauses(clauses) {
  const set = new Set(clauses)
  const out = []
  for (const cat of CATEGORIES) {
    for (const item of cat.items) {
      if (item.clauses?.some((c) => set.has(c))) out.push(item)
    }
  }
  return out
}
