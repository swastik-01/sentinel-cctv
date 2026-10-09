# Official Problem Statement — Gujarat Police Innovation Challenge 2026 (SENTINEL)

> **Provenance.** Scraped verbatim from <https://sentinel.gujarat.gov.in/problems>
> ("Problem Statement & Solution Flow") on **23 September 2026**. Public portal page,
> no login required. Content below is the portal's wording, reorganised only for
> readability — nothing added, nothing invented.
>
> **For parallel sessions:** this file is the single source of truth for *what the
> judges asked for*. Do not re-scrape; read this. Anything not in this file (the ~50
> government camera feeds, credentials, FAQ page, prize money page) lives behind
> login on the portal's **Resources** page and is **not** captured here.

---

## 0. Fast facts

| Item | Value |
|---|---|
| Challenge name | Gujarat Police Innovation Challenge / Hackathon 2026 ("SENTINEL", "Gujarat CCTV Hackathon 2026") |
| Theme | Integrated Video Management & Analytics Platform |
| Organiser | Government of Gujarat, Home Department — State Crime Records Bureau (SCRB); partner: i-Hub Gujarat |
| Registration opened | 4 August 2026 |
| **Submission deadline** | **28 September 2026** (extended "by popular demand"; banner reads "One last time") |
| Shortlisting | 28 September 2026 |
| Event / finale | 12–13 October 2026 |
| Results | 13 October 2026 |
| Target scale | ~80,000 cameras statewide |
| Test-case scale | ~50 heterogeneous government cameras (via portal Resources page) |
| Contact | SCRB, Next to Police Bhawan, Sector 18, Gandhinagar, Gujarat 382009 · +91 95370 89982 · sentinel.hackathon@gujarat.gov.in · https://gujhome.gujarat.gov.in |

Portal navigation: About · Prize Money · Resources · Problem Statements & Step by Step Guide · Schedule & Venue · FAQs · Contact Us · Sign In / Register.

The participant journey is structured as 7 steps: (1) Understand the Background, (2) Choose Integration Model, (3) Build the Platform, (4) Test on CCTV Feeds, (5) Prepare & Submit, (6) Plan for Scale, (7) Evaluation & Recognition.

---

## Step 1 — Understand the Challenge

### Background

At present, **26 different Government Departments** operate independent CCTV systems across the State. These systems include both **analog and IP-based cameras** deployed at geographically dispersed locations ranging from border districts to areas such as **Valsad, Dahod, Somnath, Jamnagar, and Dwarka**.

Each department currently operates a standalone camera ecosystem. Some departments use **cloud-based storage**, others rely on **local storage**. The video **retention period varies significantly** — some systems store footage for **7 days**, others for **15 days or more**.

Deployment patterns differ by department, e.g.:

- **Home Department** cameras — public domain: traffic monitoring, law & order management, crime detection.
- **Food & Civil Supplies Department** cameras — godowns, PDS shops and related facilities.
- **RTO** cameras — offices, testing tracks, checkpoints and other operational locations.

The Government intends to integrate these government cameras (primarily those deployed in the public domain) into a unified video management and analytics ecosystem. The proposed solution should **also support viewing of public-facing CCTV cameras installed by societies, malls, commercial establishments and other private entities**, wherever feasible and permitted.

Various Government departments already maintain critical databases — **VAHAN, SARTHI, eGujCop (Gujarat Police's CCTNS platform), AFIS and NAFIS** — containing records of arrested persons, stolen vehicles, wanted criminals, missing persons, unidentified dead bodies and fingerprint data. The proposed CCTV Integration System **should be integrated with these databases** to enable automated real-time alerts and proactive monitoring for law enforcement.

The system must therefore be **scalable, modular and future-ready**, supporting seamless integration while ensuring secure feed exchange, standardised integration mechanisms, scalability and compatibility.

### Core goal (verbatim)

> Propose a **secure, scalable, interoperable, technically feasible, and cost-effective** approach that uses **existing infrastructure to the maximum practical extent**.

### Key challenges

1. **Heterogeneous Infrastructure** — different vendors, VMS platforms, AMC periods, storage architectures, camera types, formats and feed-sharing protocols.
2. **Geographical Dispersion** — camera sites distributed across the State, distances extending to approximately **1,000 kilometres**.
3. **Unified Analytics** — analytics and event handling across all onboarded cameras through one unified framework.
4. **Scalability** — new cameras, departments, systems and future analytics onboarded **without major redesign**.

---

## Step 2 — Explore Integration Models

Five reference options. **Model 1 is flagged "Mandatory"** on the portal: *"Model 1 should be treated as the common CCTV registry and GIS foundation that may support Models 2, 3, and 4."* As the foundational model it must be combined with one or more of the others to deliver feed integration, unified viewing and analytics.

### Model 1 — Centralised CCTV Registry & GIS Mapping Model
*Metadata & Asset Visibility Layer*

**Introduction.** Multiple departments (Municipal Corporations, Transport Departments, Police, institutions) have deployed CCTV independently; there is no centralised mechanism to systematically identify, map and manage these assets. This model proposes a centralised CCTV registry and GIS-based mapping platform for onboarding and maintaining camera metadata — location, department, camera type, ownership, connectivity status, storage details and other infrastructure information. **This model does not involve centralised live video streaming or recording.** Objective: a unified inventory and visibility layer for planning future integration, identifying monitoring gaps, infrastructure assessment and decision support.

**Key functional features**
- Bulk import, manual entry, and API-based camera onboarding.
- Interactive GIS map with department, camera type, status and coverage layers.
- Camera health and maintenance-status monitoring.
- Gap-analysis reports for uncovered zones and ageing infrastructure.
- Role-based search, filtering, export, and metadata audit trails.

**Suggested technology stack**
- GIS: Leaflet / OpenLayers / PostGIS
- Backend: Node.js or Python (Django/FastAPI)
- Database: PostgreSQL + PostGIS
- Frontend: React.js
- Authentication: department-wise role-based access control

**Expected deliverables**
- Working registry portal with GIS map view.
- Bulk and manual camera-onboarding demonstration.
- Sample onboarded camera-metadata dataset.
- Registry API documentation.
- Sample gap-analysis report.

**Reference flow:** Department CCTV assets (location · ownership) → Onboarding & validation (bulk upload · manual entry · APIs) → Central registry (standardised CCTV metadata) → PostgreSQL + PostGIS (GIS and asset data store) → GIS dashboard & APIs (map · search · reports · integration).

### Model 2 — Unified Viewing & Metadata Analytics Model
*Centralised viewing with metadata-based analytics*

**Introduction.** Departments run independent CCTV through their own VMS; command centres must use multiple separate viewers, increasing operational complexity. This model proposes a unified viewing platform accessing departmental feeds through **a single interface without disturbing existing infrastructure** — departmental VMS/storage keep operating independently. The platform connects **directly** to each departmental CCTV/VMS through **RTSP, ONVIF, vendor SDKs or available APIs**, with **no intermediate middleware or federation layer**. Focus: centralised viewing, operational accessibility, and selective metadata/analytics from accessible streams. Subject to feasibility, ANPR-based metadata generation, event tagging, camera-wise indexing and searchable vehicle-movement records may be enabled **without centralised storage of all video feeds**.

**Key functional features**
- Feed aggregation through RTSP, ONVIF or vendor APIs.
- ANPR-based metadata generation.
- Event tagging and camera-wise indexing.
- Searchable vehicle-movement records.
- Configurable video walls and multi-camera grid views.
- Alerts for tagged events and vehicles of interest.

**Suggested technology stack**
- Streaming: WebRTC / HLS relay
- Integration: ONVIF / RTSP libraries / vendor SDKs
- AI/ML: ANPR using open-source or custom models
- Backend: Node.js or Python microservices
- Messaging/Search: Kafka, Elasticsearch, PostgreSQL

**Expected deliverables**
- Unified viewer connected to sample feeds from **at least two different systems**.
- ANPR demonstration on live or recorded feeds.
- Searchable metadata dashboard.
- Architecture note showing existing departmental systems remain unaffected.

**Reference flow:** Departmental VMS platforms (remain independent) → RTSP / ONVIF / vendor APIs (secure feed access layer) → Unified stream gateway (relay · transcode · session control) → Analytics & metadata (ANPR · tagging · indexing · alerts) → Unified control-room view (multi-camera viewing and search).

### Model 3 — VMS Federation & Middleware Integration Model
*Interoperability & cross-system integration layer*

**Introduction.** Heterogeneous multi-vendor CCTV systems cause fragmented monitoring and interoperability problems. This model proposes a **middleware/federation layer** integrating multiple departmental VMS platforms through APIs, SDKs, metadata exchange, event-sharing mechanisms or standard protocols — enabling interoperability, cross-platform communication, centralised event correlation and unified workflows **without replacing existing departmental systems**. Departments retain infrastructure and operational control. **Unlike Model 2**, the solution does *not* connect directly to each departmental system; the middleware acts as the common integration platform, talks to the existing VMS platforms, and exposes a single unified interface to downstream applications, dashboards and AI services.

**Key functional features**
- Adapter/plugin architecture for multiple VMS vendors.
- Metadata exchange bus for camera and event information.
- Cross-system event-correlation engine.
- Unified workflow and alert dashboard.
- Extensible connector framework for onboarding future vendors.

**Suggested technology stack**
- Middleware: Node.js / Java (Spring Boot)
- Messaging: Kafka / RabbitMQ
- API Gateway: Kong / NGINX
- Database: PostgreSQL and Redis
- Frontend: React.js

**Expected deliverables**
- Working middleware demo federating **at least two different systems**.
- Unified event-correlation dashboard.
- Adapter/plugin architecture documentation.
- Sample federated analytics report.

**Reference flow:** Multiple vendor VMS (department-controlled source systems) → Adapters / connectors (API · SDK · ONVIF · protocol translation) → Federation middleware (authentication · routing · orchestration) → Event & metadata bus (Kafka / RabbitMQ · correlation) → Unified dashboard (cross-system monitoring and workflows).

### Model 4 — Central VMS Model
*Fully centralised monitoring & analytics platform*

**Introduction.** A single consolidated **Central VMS** integrating CCTV cameras across departments onto one unified platform — centralised monitoring, management, recording, storage, playback and advanced analytics through a common interface. Aims at a fully integrated statewide platform supporting centralised analytics, AI-based processing, vehicle tracking, event detection and cross-departmental monitoring. Requires robust infrastructure: scalable storage, high-bandwidth connectivity, centralised compute, redundancy, cybersecurity controls, and architecture able to support large-scale video ingestion and real-time processing.

**Key functional features**
- Centralised feed ingestion.
- Tiered hot, warm and cold storage.
- ANPR, face recognition, crowd/vehicle counting, anomaly detection.
- Statewide vehicle tracking and route reconstruction.
- Integration readiness for **VAHAN, SARTHI, eGujCop, AFIS and NAFIS**.
- Redundancy, disaster recovery, encryption, network segmentation and RBAC.

**Suggested technology stack**
- VMS: custom or extended open-source platform
- Storage: S3-compatible distributed object storage / Ceph
- Streaming & inference: Kafka plus GPU-based analytics
- Database: PostgreSQL / TimescaleDB
- Orchestration: Kubernetes
- Networking: high-bandwidth backbone with regional edge support

**Expected deliverables**
- Working centralised VMS prototype using sample multi-department feeds.
- ANPR and multi-location vehicle-tracking demonstration.
- Scalability and load-test report for approximately **80,000 cameras**.
- Disaster-recovery and redundancy design.
- Security architecture document.

**Reference flow:** Statewide CCTV sources (government and eligible integrated feeds) → Central ingestion layer (streaming gateway · load balancing) → Central VMS platform (monitoring · recording · playback) → Storage & AI analytics (distributed storage · GPU inference) → Command centre & integrations (alerts · GIS · authorised databases).

### Model 5 — Hybrid / Innovative Architecture
*Customised or combined integration approach*

The four models above are **indicative reference models** to guide participants. Companies may propose a **hybrid** solution combining suitable elements from two or more models, or submit a **fully innovative and customised architecture**, provided it addresses the stated functional, interoperability, security, scalability, analytics and implementation requirements.

---

## Step 3 — Choose Your Challenge: Expected Solution Approach

Using the selected reference model, design and build a **deployment-ready** solution that **continuously processes the CCTV feeds provided through the hackathon portal**. The solution must demonstrate how live video streams are integrated with a **searchable database of watchlist records** (stolen vehicles, wanted persons, missing persons, blacklisted vehicles, suspect watchlists or other entities of interest), enabling continuous AI-powered analysis and **automated alert generation whenever a match is detected**.

Participants design the complete integration workflow, including **database structure, matching logic, alerting mechanism and user interface**. Teams should create and use **representative datasets**. During evaluation, teams **may be required to identify specified vehicles or other entities from the CCTV feeds and generate accurate, real-time alerts**.

Ten dimensions the submission must cover:

1. Overall Architecture
2. Integration Strategy
3. AI & Video Analytics
4. Cybersecurity Architecture
5. Deployment Architecture
6. Infrastructure Sizing
7. Cost-Benefit Analysis
8. Department-wise Information Requirements
9. Scalability Strategy
10. Future Roadmap

### Architecture principles (verbatim)

> The proposed solution shall adopt an **open, modular, scalable, secure, standards-based, and vendor-neutral** architecture. The solution shall **avoid vendor lock-in** and enable seamless integration, interoperability, replacement, upgrade, and future expansion of cameras, Video Management Systems (VMS), analytics engines, storage platforms, AI modules, and other technology components through **documented standard APIs, open protocols, SDKs, and modular adapter-based frameworks**. The architecture should be **technology-agnostic**, support heterogeneous multi-vendor environments, and facilitate future enhancements without requiring significant redesign of the overall system.

### Permitted approach

Any one of:
- Any one of the five reference solution models in the official Problem Statement.
- A hybrid architecture combining features from two or more reference models.
- A fully customised architecture meeting the challenge requirements.

…provided it addresses the objectives: integrating diverse CCTV systems, correlating live video feeds with watchlist databases, and generating AI-powered real-time alerts for law enforcement.

---

## Step 4 — Technical Evaluation / Test Case (the live challenge)

Headline: *"Integrate approximately 50 heterogeneous cameras, track a designated vehicle and deliver real-time insights, alerts and GIS visualisation."* Sub-tasks shown on the portal: onboard ~50 cameras · integrate live feeds · track vehicle · generate alerts & history · visualise on GIS · route, movement history & searchable events.

### Test scenario

- After registration, participants can access details, resources and **live camera feeds from approximately 50 geographically distributed cameras** through the **Resources page** of the website for the technical evaluation.
- The cameras are deployed across different departments and use **various technologies, formats, VMS platforms and storage mechanisms**.
- Teams must onboard the available cameras onto **one integrated platform**.
- The solution must enable **centralised monitoring and AI-powered video analytics**.
- During evaluation, participants are given a **designated vehicle registration number**. The solution must **identify, trace and present the movement** of that vehicle across the integrated CCTV network, as it appears at different camera locations and times.
- The solution must also demonstrate **continuous cross-referencing of live feeds with a representative watchlist database** and generate **automated real-time alerts** on a match. Participants may use their own representative watchlist database.

### Expected output

1. Identify and trace the designated vehicle across the integrated CCTV network using the registration number provided at evaluation time.
2. **Complete route traversed** by the designated vehicle, including **timestamped and location-wise movement history**.
3. A **working watchlist database** integrated with the solution, showing continuous cross-referencing between live feeds and representative watchlist records, with automated real-time alerts on match.
4. Evidence of successful CCTV integration, AI-powered video analytics, interoperability, scalability and end-to-end system performance.

---

## Step 5 — Prepare & Submit

Deliverable set: Solution Presentation · High-Level Design Document · Own-Feed Demonstration · Government-Feed Demonstration · Video & Output Report · Submission Links.

### 1. Solution Presentation (PPT/PDF)

- Proposed solution model (Reference Model 1–5, Hybrid, or Customised Architecture) **with justification**.
- Solution overview, objectives and key innovations.
- High-level system architecture and end-to-end workflow.
- AI-powered video analytics approach, including detection, recognition and event analytics.
- Methodology for correlating live CCTV feeds with watchlist databases and generating automated real-time alerts.
- Key technologies, frameworks and tools used.
- Scalability, interoperability, security and deployment considerations.
- Expected operational benefits and impact on policing and public safety.

### 2. Technical Proposal — High-Level Design (HLD)

- Overall solution architecture, with high-level architecture diagrams and component interactions.
- Approach for integrating heterogeneous CCTV cameras, **NVRs** and VMS into a unified platform.
- Architecture for ingesting, processing and managing live video streams from geographically dispersed camera locations.
- Approach for integrating live feeds with **watchlist databases** (stolen vehicles, wanted persons, missing persons, blacklisted vehicles, suspect watchlists) and continuously correlating analytics results to generate real-time alerts.
- AI-powered video analytics approach, including **ANPR, Facial Recognition Systems (FRS), object detection, person and vehicle tracking**, and other intelligent analytics proposed by the team.
- Alert generation and notification workflow, including **prioritisation, visualisation and user interaction**.
- Scalability, interoperability, security and performance considerations for statewide deployment and future expansion to **~80,000 cameras**.
- **Technical prerequisites, assumptions, and information required from participating departments** to assess camera integration feasibility and ensure seamless interoperability.

### 3. Demonstration on Participant's Own Feed

Screen-recorded demonstration, **maximum 2–3 minutes**, on CCTV cameras or video footage of your choice, clearly showing:

- Onboarding and processing of live or recorded CCTV feeds.
- AI-powered detection and analytics (ANPR, facial recognition, or other proposed capabilities).
- Correlation of detected entities with a representative watchlist database.
- Automatic generation of real-time alerts and visualisation on successful detection and database matching.

> **"The demonstration must showcase a fully functional working solution. Mock-ups, animations, simulated interfaces, or concept videos without an operational backend will not be considered."**

### 4. Live Demonstration on Government-Provided CCTV Feed

- Onboard the Government-provided feed(s) onto the proposed platform.
- Demonstrate successful onboarding and live or recorded viewing.
- Demonstrate available video-analytics output on the provided feed.
- Submit a screen-recorded video **plus an output report showing detected vehicles or number plates with corresponding timestamps**.

### How to submit

- Unlisted YouTube link (video visibility set to **Unlisted**).
- Google Drive or OneDrive link with access set to **"Anyone with the link — Viewer"**.
- Optionally, a URL to the hosted platform **with test login credentials** for the screening committee.
- Optionally, a **GitHub or GitLab repository link** containing the platform source code or relevant components.

---

## Step 6 — Plan for Scale

Requirement: present the strategy to scale the solution **securely and reliably to approximately 80,000 cameras across Gujarat**. Portal sub-headings: Hardware & Software Requirements · Network & Bandwidth Planning · Storage & Retention Strategy · AI Processing Capacity · Disaster Recovery Strategy · Statewide Rollout Plan.

Participants should explain:

- Central, regional and **edge-compute** requirements.
- **GPU or accelerator** requirements for video analytics.
- Expected network bandwidth and **low-bandwidth strategies**.
- **Hot, warm and cold storage** assumptions based on retention periods.
- Load balancing, horizontal scaling, monitoring, logging and health checks.
- High availability, backup, disaster recovery and cybersecurity controls.
- **Estimated implementation and operational costs**.

---

## Step 7 — Evaluation & Recognition

Solutions are evaluated **qualitatively across multiple dimensions**. All eligible submissions are first assessed against the common evaluation areas; bonus consideration may then be awarded for meaningful capabilities beyond the mandatory requirements.

### A. Common evaluation areas

| # | Area | What is assessed |
|---|---|---|
| 01 | **Successful Test Case** | Successful onboarding and operation of the solution on the Government-provided CCTV feed, including live or recorded viewing and the required analytics output. |
| 02 | **Solution Presentation** | Clarity and completeness of the PPT/PDF: problem understanding, proposed model, justification, solution overview, key features. |
| 03 | **Solution Architecture** | Technical soundness, feasibility, security, interoperability and clarity of the HLD and architecture diagrams. |
| 04 | **Working Platform and Demonstration** | Maturity of the actual working platform, shown on both the participant's own feed and the Government-provided feed. |
| 05 | **Video Analytics Output** | Quality and usefulness of ANPR, vehicle/person detection, intrusion detection, object detection, timestamps and output reports. |
| 06 | **Scalability and PoC Readiness** | Readiness to scale toward ~80,000 cameras and preparedness for the **on-site proof-of-concept**. |
| 07 | **Submission Completeness** | Completeness, accessibility and consistency of all required documents, videos, reports, links, credentials and supporting technical information. |

### B. Bonus consideration

Awarded for additional capabilities that are relevant, functional and demonstrated as part of the working solution. **Bonus features will not compensate for failure to meet any mandatory submission or test requirement.**

- Innovative hybrid or customised architecture with clear operational value.
- Advanced cross-camera vehicle movement tracking or multi-camera correlation.
- Additional reliable analytics **beyond the mandatory ANPR requirement**.
- Strong edge-processing, bandwidth-optimisation or low-connectivity operation.
- Enhanced cybersecurity, privacy protection, auditability or role-based access controls.
- Operational dashboards, automated alerts, health monitoring or integration-ready APIs.

---

## Notes for implementers (derived, not portal text)

- **ANPR is the only analytic the portal calls "mandatory"** (Step 7B: "beyond the mandatory ANPR requirement"). FRS, object detection and tracking are listed in the HLD requirements but are graded under analytics quality.
- **Model 1 (registry + GIS) is flagged mandatory as a foundation** and must be paired with Model 2/3/4 — a submission that only streams video without a GIS-backed camera registry misses a flagged requirement.
- Two feed demos are required and they are **separate deliverables**: own feed (2–3 min, screen-recorded) *and* the government-provided feed (video **plus** an output report with plates and timestamps).
- The evaluation-time vehicle number is **unknown in advance** — the watchlist must be editable at runtime, not compiled in.
- Movement history must be **timestamped and location-wise**, i.e. per-camera geo-coordinates are needed → the GIS registry feeds the tracking view.
- The portal page also carries an announcement modal ("Date Extended: 12–13 Oct", submission extended to 28 September 2026), an accessibility widget (font size, high contrast, dyslexia font, listen-to-page) and an "AI Hackathon Assistant" chatbot. None of these affect deliverables.

### Not captured here (behind login / other pages)

- **Resources page** — the ~50 government camera feeds, their URLs/protocols/credentials, and any provided datasets.
- **About** page. The public **FAQs**, **Prize Money (phases)**, **Schedule** and **Registration** pages were read on 24 September: see the appendix at the end of this file.
- Registration form and team/eligibility rules.

---

## Appendix — FAQs, Phases, Schedule and Registration pages (public, read 24 September 2026)

> **Provenance.** Fetched from <https://sentinel.gujarat.gov.in/faqs>, `/phases`, `/schedule` and
> `/register` on **24 September 2026** through a fetch-and-extract tool, so the quotes below are the
> tool's rendering of the page text, not a raw HTML extract like `official-problem-statement.raw.txt`.
> Only the items that add to, or sharpen, Steps 1–7 above are kept; the FAQ's restatements of the
> models and evaluation areas match the text above and are omitted.

### What the sandbox feeds are (FAQ 26, 39–41)

- Q26: "After registration, participants access **~50 geographically distributed live-simulated camera
  feeds** from different departments. Teams must onboard these cameras onto their integrated platform and
  enable centralized monitoring and analytics."
- Q39: "**Approximately 12 hours of CCTV footage from each of the 30+ cameras** deployed across **five
  Government departments: Health, Police, GSRTC, Panchayat, and Municipal Corporation**."
- Q40: "A dedicated **Python-based streaming middleware** ingests the recorded footage, **synchronizes it on
  a common timeline**, and serves it as simulated live video via a dedicated streaming endpoint (URL) for
  each camera."
- Q41: simulated streams are used "to ensure every team is tested against a consistent, repeatable dataset
  under identical, fair conditions."
- Q27: "A designated vehicle number is provided to participants **on the hackathon day**."

### What the two videos must show (FAQ 31, 33)

- Own feed: "2–3 min screen recording **showing onboarding, live/recorded viewing, and vehicle
  detection/ANPR**."
- Government feed: "showing onboarding, viewing, and analytics output (**ANPR, vehicle/person/intrusion/
  object detection**)", plus "an output report showing detected vehicles or number plates with corresponding
  timestamps."

### What the HLD must cover, as the FAQ phrases it (FAQ 24, 30)

- "approach for integrating heterogeneous cameras/VMS (**IP, analog, multi-vendor, varied protocols**);
  handling geographically dispersed locations (**bandwidth, connectivity, edge vs. centralized
  processing**); video analytics approach (ANPR, **cross-camera tracking**); scalability approach for
  ~80,000 cameras; and department-level technical details needed for integration feasibility."
- Design dimensions: "…cybersecurity/privacy/RBAC/audit controls, deployment architecture
  (central/regional/edge), infrastructure sizing, **cost-benefit analysis**, department-wise technical
  requirements, and a scalability roadmap."

### Format, categories and prizes (FAQ 44–50; Phases page)

- Two categories. **Category 1**: students, graduates, postgraduates, doctoral scholars, academic or research
  teams, DPIIT-recognised startups (certificate required). **Category 2**: companies, system integrators,
  LLPs and other enterprises. The registration page's "Register As" choices are *Student / Student Team /
  Researchers / Professionals*, *DPIIT Startup*, *Company / SI*. Registration is free, needs an e-mail OTP,
  and a team may apply to more than one problem statement.
- **Phase 1, Sandbox Round**: ranked **within category**; "the six highest-ranked participants across both
  categories qualify for Phase 2" (the Phases page: top 3 per category). Prizes: Category 1 ₹4 L / ₹2 L /
  ₹1 L; Category 2 ₹5 L / ₹3 L / ₹2 L; four consolation awards of ₹25,000. Phase 1 prize money "also serves
  as a grant toward building the final Phase 2 solution."
- **Phase 2, Production Round (Grand Finale)**, 12–13 October 2026 at i-Hub Gujarat: "the six qualifiers
  demonstrate their solutions using live camera feeds in a production-scale environment." Prizes ₹16 L /
  ₹8 L / ₹7 L, ₹50,000 to each other finalist, a ₹50,000 special jury award. Total pool ₹51 L.
- Knowledge partners who help evaluate: NFSU and DA-IICT (AI, computer vision, video analytics,
  cybersecurity, digital forensics).
- The schedule page gives no finale format, duration, hardware, network or judging details (still to ask
  by e-mail).
