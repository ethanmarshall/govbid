# GovBid Pro

Find federal contract opportunities your business can bid on, see what each one requires, and track your bids.

Built for a service-disabled veteran-owned small business that is still finishing SBA VetCert: SDVOSB set-asides are tracked separately as "After certification" until you mark SDVOSB as certified on your profile.

## What it does

| Area | What you get |
|---|---|
| **SAM.gov sync** | Pulls solicitations, combined synopses, presolicitations and sources sought for each of your NAICS codes through the official SAM.gov Opportunities API. |
| **Eligibility check** | Every opportunity is labeled *Can bid now*, *After certification* or *Not eligible* from its set-aside code and your certifications, with warnings for SAM status, NAICS mismatch and size standard. |
| **DIBBS (DLA)** | Import DIBBS RFQ exports or the daily RFQ index file, filtered to your NSN/FSC watchlist. |
| **Agency forecasts** | Import forecast spreadsheets from Acquisition Gateway or agency OSDBU pages. Columns are matched automatically. |
| **Manual entry** | For state programs (for example NY OGS SDVOB), GSA eBuy and SBA SubNet, which need a login or have no API. |
| **Requirements breakdown** | Upload the RFP/RFQ, SOW/PWS and amendments (or pull SAM.gov attachments in one click). Get scope, evaluation method, factors, deadlines, page limits, key FAR/DFARS clauses, red flags and questions for the contracting officer. |
| **Compliance matrix** | Every shall/must requirement with section reference, category, proposal location and status. Edit in the app, export to Excel. |
| **Pipeline** | Track opportunities through tracking, evaluating, bidding, submitted, won, lost and no-bid. Win rate on the page. |
| **Competitor intel** | Past awards from USAspending.gov by NAICS, set-aside type, keyword or agency, with the top recipients. |
| **Packages** | Build proposal packages and technical data packages. Starts from a standard outline (cover letter, technical, management, past performance, price, reps and certs; or transmittal, drawings index, test results, quality records, markings for a TDP). Every compliance-matrix requirement is assigned to the section that should answer it; checking it off writes "where addressed" back to the matrix. Markdown editor with autosave, page-limit tracking, preview, AI drafting with bracketed placeholders for missing facts, and a reusable content library. Deliverables/attachments tab tracks CDRL lines, DIDs, status and uploaded files. Exports a formatted Word document (cover page, table of contents, headers and page numbers, attachment index, compliance cross-reference) and a zip with the Word file, compliance matrix and every uploaded file in a folder per CDRL. |
| **Target-market presets** | Recommended NAICS codes (335314 primary, plus instruments, test equipment, harnesses, fabrication, engineering, test and repair) and DLA supply classes, added to your profile in one click. Opportunities opens filtered to your NAICS codes, with quick filters for core manufacturing, services, veteran set-asides, sources sought, the DIBBS watchlist, and Navy nuclear power training buys (keyword match). SAM sync lets you pick a group and shows how many API requests it uses. Edit `backend/app/presets.py` to change the lists. |
| **Bid score** | Every opportunity gets a 0 to 100 score with the reason for each point: eligibility, fit (NAICS, keywords, past performance), time left, competition, size, your price against the last award, and risks such as export-controlled drawings or DFARS cyber clauses. Shown on the opportunity page and pipeline cards. |
| **Amendment watch** | Opportunities in the pipeline are re-checked on SAM.gov by solicitation number (button on the Dashboard or `python -m app.cli watch`). New deadlines, new attachments, amendments and award notices are logged and flagged on the Dashboard and the opportunity. |
| **Calendar feed** | `/api/calendar.ics` has response and question due dates, package deadlines, contact follow-ups, POA&M dates, and SAM.gov and JCP renewals. Subscribe in Apple Calendar or import into Google Calendar. |
| **Export control (JCP)** | Solicitations that mention ITAR, export-controlled data, Distribution Statements B to F, JCP or DD Form 2345 are flagged. Your JCP status lives on the profile, and the app warns when you need it. |
| **Standards library** | 600+ military and industry standards, specs and DIDs grouped by discipline, with lookup for any document ID, links to ASSIST and EverySpec, your own PDF copies, the revision you have on file, and a warning when a solicitation cites a different revision. Every standard an analyzed solicitation cites is added automatically. Import a full list from ASSIST or EverySpec as CSV/Excel. |
| **Contacts and teaming** | Primes, agencies, vendors and teaming partners with contacts, an interaction log and follow-up dates. A starter list of Navy primes and small business offices. A teaming finder that searches SAM.gov entity registrations by NAICS, state and SDVOSB/VOSB/WOSB/HUBZone/8(a). |
| **Past performance** | A log of completed work (including subcontract and personal projects), matched against each solicitation for the bid score, sent to the content library in one click, and exported as a past performance volume draft (.docx). |
| **CMMC compliance** | Level 1 (the 15 FAR 52.204-21 requirements) and Level 2 (all 110 NIST SP 800-171 requirements with the DoD Assessment Methodology weights). SPRS score, evidence notes, POA&M dates with the rules on what may be a POA&M item, and an Excel export. |
| **Instant quote (STEP)** | Drop a STEP file on Part Quotes and get a price in seconds, like an online machine shop. The model is measured automatically (size, volume, holes, turned diameters, sheet thickness, bends, cut length), shown in a 3D viewer, and routed to CNC milling, CNC turning or sheet metal. Pick material, thickness, tolerance, finish, threaded holes, PEM inserts, weld length, first article, material certs and MIL-STD-2073 packaging; the price and quantity breaks update as you click. 3D printing (FDM, SLA, SLS, MJF) is priced from the model volume, infill, supports and post-processing. Drop the PDF drawing too and the reader fills in material, finish, tolerance, threads and part number, and warns on export-controlled drawings. Enter the NSN to see award history (from DIBBS award exports, manual entries and your own won and lost quotes) and use the last award as the reference price. Saved quotes keep the model and reopen with every selection. |
| **Heat-set inserts (3D printing)** | For a printed part, pick the thread for each hole size (it guesses from tap drill and nominal sizes) and the STEP model is rebuilt with tapered holes sized for brass heat-set inserts per the PEM tapered insert hole table. Through holes stay open past the insert. The modified STEP downloads, and the inserts are priced from the shop rates. |
| **Quote from a PDF drawing** | No STEP file? Drop the drawing: envelope, hole and thread callouts, bends, material, finish and tolerance are read from the drawing text, shown with a confidence level and the lines they came from, and priced live. Correct any size and it reprices. Optional Claude read for drawings you may share. |
| **Extrusion builds** | Drop a drawing PDF with a BOM and cut list (or a BOM spreadsheet) for a T-slot aluminum frame. Profiles, lengths, machining (end taps, access holes, counterbores, miters), hardware and panels are matched to an editable catalog and priced per build with stock nesting, cut and machining charges and assembly labor. Download the cut list and purchase list. Catalog prices are placeholders until you enter your distributor's. |
| **Recompetes and buyers** | Contracts in your NAICS and FSC codes ending 6 to 18 months out (USAspending.gov), with a watch list, reminders and outreach logging; and buyer analytics: top buying commands, yearly spend, set-aside shares, top recipients. |
| **Evaluator review** | In a proposal package, a review against Section L and M the way an evaluator rates it (Claude, or rules without a key): ratings by factor, strengths, weaknesses, deficiencies, unanswered requirements, page-limit and placeholder problems, and a fix list linked to sections. |
| **Sources sought responses** | On Sources Sought and RFI notices, a draft response that answers the notice's questions with your accurate size and status, codes and matching past performance. Download as Word or save as a package. |
| **Capability statement** | A one-page PDF or Word capability statement built from your profile and past performance, with a live preview and optional tailoring to an opportunity. |
| **Make or buy** | Add outside shop quotes to any saved part quote. The app adds your markup, handling and receiving inspection, compares make and buy at every quantity, and checks the nonmanufacturer rule for the linked set-aside (including the exemption between the micro-purchase and simplified acquisition thresholds). |
| **Part quotes** | Should-cost estimates for parts you could CNC machine, laser or waterjet cut, form on a press brake, or weld: material from stock size, run and setup time per operation, hardware, outside finishing, inspection, MIL-STD-2073 packaging and freight, with price breaks per quantity, margin, lead time, and a comparison against a past award price. Saved quotes link to opportunities. Shop rates are editable and shared with the MCP server. |
| **MCP server for agents** | `backend/run_mcp.py` exposes the pricing engine and opportunity search to Claude and other MCP clients (see below). |
| **Resources** | Links to MIL-STDs and DIDs (free on ASSIST), ASME Y14 drawing standards, FAR/DFARS proposal clauses, quality and CM standards, and cyber requirements. Includes checklists for a technical proposal package and for a technical data package on completed work. |
| **Standards detection** | The requirements breakdown lists every MIL-STD, DID, ASME, ISO, SAE, IPC and NIST document the solicitation cites, and suggests related resources for the clauses it contains. |
| **Pricing workbook** | Indirect rates (fringe, overhead, G&A, profit, each with a selectable base) with a calculator for a new company, labor categories, and price builds by CLIN with labor, materials, subcontracts, ODCs and fixed-price part lines from Part quotes. Fully burdened rates, price to win with a target-price slider that back-solves profit, the FAR 52.219-14 limitations on subcontracting check, and an Excel export with live formulas. |
| **Source approvals (SAR)** | Track DLA Source Approval Requests by NSN: category (I to IV per the DLA SAR guide), status, the guide's document checklist with uploads, reverse-engineering notes, and which NSNs are worth approving (ranked by solicitations and award value). |
| **Jobs** | Turn a won opportunity into a job: CLINs, a traveler built from the quote's operations with sign-offs, vendor purchase orders and receipts, records (certs, inspection reports), shipping details, and a Certificate of Conformance document. On-time delivery metrics. |
| **Quality and suppliers** | Nonconformance reports and corrective actions, a calibration log with due dates, starter quality documents (quality manual, receiving inspection, nonconforming material, calibration, counterfeit parts prevention) you can edit and export, and supplier approvals with certificates and a scorecard from your POs. Approved Supplier List export. |
| **Clause flowdown** | Pick an opportunity or paste clause numbers, answer a few questions about the subcontract, and get the FAR/DFARS clauses that must flow down with the reason and source, plus a PO terms attachment (.docx). |
| **Invoices and finance** | Track invoices you submit in PIEE (WAWF) with Prompt Payment due dates and late interest (rate stored in settings), an aging report, invoice documents, CSV exports for QuickBooks Online and Wave, and an SBA and other loan tracker with draws, payments and amortization. |
| **Search everything** | One search across package sections, the content library, past performance, opportunities and analyses, part quotes, standards notes, contacts and SARs, with copy and insert-into-package. |
| **Daily digest** | `python -m app.cli digest --days 1 --watch --email` sends new matches with bid scores, due dates, amendments, follow-ups and alerts from every module. Preview it at `/api/search/digest-preview`. |

## Run it as a website (Render)

The repo includes a `Dockerfile` and a Render Blueprint (`render.yaml`). Render builds the app from GitHub and redeploys on every push.

1. Sign up at render.com with your GitHub account and allow it to read the `govbid` repo.
2. In the Render dashboard choose **New > Blueprint**, pick the repo, and confirm.
3. Fill in the values it asks for:
   - `APP_USERNAME` and `APP_PASSWORD`: your login. Use a long password; the site is on the public internet.
   - `SAM_API_KEY`, `ANTHROPIC_API_KEY`: your keys (leave blank to add later).
   - `APP_URL`: the site address Render gives you, for links in the digest email.
   `SESSION_SECRET` and `CALENDAR_TOKEN` are generated for you.
4. Wait for the first build (several minutes; the CAD library is large), then open the URL and sign in.

Notes:
- The database and uploads live on a 5 GB persistent disk mounted at `/var/data`. A disk needs a paid instance type, and the service runs as a single instance. Check Render's current pricing.
- The container refuses to start without `APP_PASSWORD`, so the site is never open by accident.
- Download a full backup any time at `/api/admin/backup` while signed in (database plus every uploaded file).
- The calendar subscription address on the Dashboard includes its own token, because calendar apps cannot sign in. Keep that link private.
- The MCP server for agents runs on your own computer against a local database; it does not talk to the hosted site.

## Setup

Requires Python 3.11+ and Node 18+. STEP reading uses `cadquery-ocp` (OpenCascade), which pip installs as a prebuilt wheel on Windows, macOS and Linux.

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add your keys

# Frontend
cd ../frontend
npm install
npm run build                      # backend serves the built app
```

Run it:

```bash
cd backend
uvicorn app.main:app --port 8000
```

Open http://localhost:8000. For frontend development with hot reload, run `npm run dev` in `frontend/` and use http://localhost:5173 (API calls proxy to port 8000).

### Keys

- **SAM_API_KEY** (needed for syncing): sign in at sam.gov, open *Account Details*, and request a Public API Key. Non-federal keys have a small daily request limit, so the app runs one query per NAICS code (up to 1,000 notices each) and loads notice descriptions only when you open an opportunity.
- **ANTHROPIC_API_KEY** (optional): turns on Claude-based analysis. Without it, a rule-based analyzer still extracts requirements, clauses, deadlines and page limits.

## First run

1. **Company profile**: enter your name, UEI, SAM status, NAICS codes, and set SDVOSB to *Applied, pending*. Mark SB as *Yes, small* if you are small under your codes.
2. **Opportunities**: click *Sync SAM.gov*. Filter *Can I bid?* to *Now or after certification*.
3. Open an opportunity, pull its attachments (or upload them), and click *Analyze requirements*.
4. *Track this opportunity* to add it to the pipeline.
5. When VetCert is approved, change SDVOSB to *Certified*. Every SDVOSB set-aside flips to *Can bid now*.

## Writing a package

1. Open an analyzed opportunity and click *Start proposal package*, or go to *Packages* and create one (choose *Technical data package* for completed work).
2. Work section by section. Each one shows what it should cover and the requirements assigned to it. Check a requirement once your text answers it.
3. Set page limits from Section L on each section; the outline flags sections that run over (about 500 words per single-spaced page).
4. Save reusable text to the *Content library* and insert it into later bids.
5. Upload forms, resumes, drawings and reports on the attachments/deliverables tab.
6. Export the Word document for final formatting, or the zip for the complete package. Open the Word file and accept the prompt to update fields so the table of contents fills in.

Markdown supported in sections: `###` headings, `-` bullets, `1.` numbered lists, `| pipe | tables |`, `**bold**`, `*italic*`.

## Part pricing MCP server

Agents can find part RFQs in your database, estimate custom parts, and save quotes that appear on the Part Quotes page. Nothing is ever submitted to the government; you review every quote.

**Tools:** `analyze_step_file`, `quote_step_file`, `convert_holes_for_inserts`, `quote_from_drawing`, `read_drawing_pdf`, `nsn_award_history`, `add_vendor_quote`, `opportunity_bid_score`, `pricing_reference`, `estimate_part`, `save_part_quote`, `list_part_quotes`, `get_part_quote`, `update_part_quote`, `search_opportunities`, `get_opportunity`, `get_shop_rates`, `update_shop_rates`. There is also a prompt, `quote_rfq_part`, that walks through quoting one opportunity.

**Set your shop rates first** (Part Quotes > Shop rates). The defaults are placeholders, and every estimate is only as good as those numbers.

**Claude Desktop**: add to `claude_desktop_config.json` (use your own paths; on Windows the Python path is `backend\\.venv\\Scripts\\python.exe`):

```json
{
  "mcpServers": {
    "govbid-pro": {
      "command": "/path/to/govbid-pro/backend/.venv/bin/python",
      "args": ["/path/to/govbid-pro/backend/run_mcp.py"]
    }
  }
}
```

**Claude Code**:

```bash
claude mcp add govbid-pro -- /path/to/govbid-pro/backend/.venv/bin/python /path/to/govbid-pro/backend/run_mcp.py
```

**Over HTTP** (for agents that connect by URL):

```bash
python backend/run_mcp.py --http --port 8765    # serves http://127.0.0.1:8765/mcp
```

The HTTP server has no login. Keep it on 127.0.0.1, or put it behind an authenticated reverse proxy or VPN before exposing it to another machine.

Example with a model: *"Quote ~/Downloads/bracket.step in 5052 aluminum with powder coat at 25 and 100 pieces, then save it as a draft."*

Example request to an agent: *"Find DIBBS RFQs in FSC 5340 and 3040, pick ones with drawings we could machine from 6061 or steel, estimate each at the RFQ quantity against the last award price, and save drafts with your assumptions."*

## How the instant quote prices a model

- **CNC milling**: stock is the part's bounding box plus 1/8 in per side. Cycle time comes from the volume removed, hole count and face count. Setups come from the directions holes and faces point.
- **CNC turning**: bar stock is the largest diameter plus 1/8 in. Time comes from the number of diameters, bores, cross holes and the threads you enter.
- **Sheet metal**: blank size comes from the flat area, laser cut length from the part outline and holes (waterjet over 1/2 in), plus press brake bends.
- Threads are rarely modeled, so enter tapped holes yourself from the drawing.
- Parts with 3D contoured surfaces, multiple bodies or very large sizes show a warning. Contoured parts are priced low; use your CAM time in the manual estimator for those.
- Prices are only as good as your shop rates and material prices. Check a few quotes against parts you know before relying on it.

## Scheduled sync and digest

### macOS: run it every morning with launchd

1. Create `~/Library/LaunchAgents/com.govbidpro.digest.plist` (replace `/Users/you/govbid-pro` with your path):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.govbidpro.digest</string>
  <key>WorkingDirectory</key><string>/Users/you/govbid-pro/backend</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string><string>-c</string>
    <string>/Users/you/govbid-pro/backend/.venv/bin/python -m app.cli sync --days 2; /Users/you/govbid-pro/backend/.venv/bin/python -m app.cli digest --days 1 --watch --email</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>45</integer></dict>
  <key>StandardOutPath</key><string>/Users/you/govbid-pro/backend/digest.log</string>
  <key>StandardErrorPath</key><string>/Users/you/govbid-pro/backend/digest.log</string>
</dict>
</plist>
```

2. Fill in `DIGEST_TO` and the SMTP settings in `backend/.env` (and `APP_URL`).
3. Load it: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.govbidpro.digest.plist`
4. Test it now: `launchctl kickstart -k gui/$(id -u)/com.govbidpro.digest`, then read `backend/digest.log`.
5. To change it: `launchctl bootout gui/$(id -u)/com.govbidpro.digest`, edit, and bootstrap again. If the Mac is asleep at 6:45 it runs on wake.

### Any system

```bash
cd backend
python -m app.cli sync --days 3
python -m app.cli digest --days 1            # prints to the console
python -m app.cli digest --days 1 --email    # sends via SMTP settings in .env
python -m app.cli watch                      # re-check pipeline opportunities for amendments
python -m app.cli backup                     # zip the database and uploads into backups/
```

Add those to cron (Linux/macOS) or Task Scheduler (Windows) to run each morning.

## Data source notes

- **SAM.gov**: the API docs describe `offset` as a page index, but it behaves as a record offset in practice. The connector advances by records and de-duplicates by notice ID, so either behavior works.
- **DIBBS**: blocks automated access, so it is file import only. The daily index text file has no published layout and is parsed by pattern (solicitation number, NSN, dates). CSV/Excel exports are more reliable. DLA buys over $25K also appear in the SAM.gov sync.
- **Eligibility**: SDVOSB set-asides require SBA VetCert certification. A pending application filed after the 2023 grace period does not make you eligible yet. Small business status is self-represented per NAICS code; check the SBA size standards table.
- **Analysis output** is a starting point. Always confirm against the solicitation and amendments before submitting.

## Project layout

```
backend/
  app/
    main.py               API routes; serves frontend/dist
    models.py             SQLite tables
    eligibility.py        set-aside rules
    analysis.py           text extraction, Claude and rule-based analysis, cited standards, Excel export
    services.py           upsert and SAM sync
    cli.py                sync and digest commands
    pricing.py            part cost model and default shop rates
    cad.py                STEP reading and geometry measurement (OpenCascade)
    cad_quote.py          turns geometry and selections into a priced spec
    cad_api.py            instant-quote REST endpoints
    drawing.py            PDF drawing reader (drawings_api.py)
    nsn_history.py        NSN award history (nsn_api.py, models_nsn.py)
    bidding.py            bid score, export-control detection, amendment watch, calendar feed
    make_or_buy.py        vendor quote comparison and nonmanufacturer rule check
    insights_api.py       score, watch, calendar and make-or-buy endpoints
    standards*.py         standards catalog, revision parsing and library API
    crm_api.py            contacts, follow-ups and SAM.gov teaming search (models_crm.py, connectors/sam_entity.py)
    cmmc_*.py             CMMC Level 1 and NIST SP 800-171 tracker (models_cmmc.py)
    past_performance_api.py  past performance log (models_pp.py)
    db.py                 creates tables and adds new columns to an older database automatically
    quotes.py             shop-rate storage and saved quotes (shared by web and MCP)
    pricing_api.py        Part Quotes REST endpoints
    mcp_server.py         MCP server (tools, prompt, stdio and HTTP)
    packages_api.py       package builder API, AI drafting, content library
    package_templates.py  proposal and TDP starting outlines
    package_export.py     Word and zip export
    connectors/
      sam_gov.py          SAM.gov Opportunities API
      usaspending.py      USAspending award search
      tabular_import.py   DIBBS and forecast file import
  tests/                  pytest suite with mocked APIs
frontend/
  src/resources.js        resource library and checklists (edit to add your own links)
  src/StepViewer.jsx      three.js viewer for uploaded models
  src/MakeOrBuy.jsx       vendor quote comparison panel
  src/markdown.js         preview renderer matching the Word export
  src/pages/              Dashboard, Opportunities, Detail, Pipeline, Packages, PackageBuilder, Competitors, Import, Resources, Profile
```

Run tests: `cd backend && pytest`
