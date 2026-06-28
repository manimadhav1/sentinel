# ⚡ Sentinel — Touchless Invoice Automation Platform

Developed by **Team Nexus** for the **24 Hrs HackArena 2.0 Grand Finale** hosted by **Ignite Room**.

**Sentinel** is an intelligent, end-to-end operational automation gateway designed to eliminate manual data entry, cross-checking bottlenecks, and human billing discrepancies. The platform acts as a secure processing bridge between messy, unstructured operational records (such as digital timesheet PDFs, handwritten log sheets, multi-nested contract JSON layouts, or spreadsheets) and financial accounts payable architectures. By leveraging Generative AI alongside a deterministic multi-stage Python validation engine, Sentinel parses, verifies, audits, and transforms operational hours into finalized database records and compliant corporate invoices in seconds.

---

## 🚀 Key Core Features

* **Multi-Format Ingestion Node:** Native parsing support for standard digital PDFs, messy handwritten log sheets (`.png`/`.jpg`), multi-tab transaction spreadsheets (`.xlsx`/`.xls`/`.csv`), and structured contract schemas.
* **One-Pass AI Context Extraction:** Utilizes `gemini-2.5-flash` to efficiently interpret raw human document structures and dump them into tightly mapped, validated JSON models.
* **14-Point Business Validation Engine:** A robust backend system that automatically cross-checks extracted parameters against live reference master directories (`employees.json`, `clients.json`, and client protocols).
* **Deterministic Routing Authority:** Employs a secure exception handler to isolate parsing errors, grade risk weights, apply context patches, and dictate routing states (`AUTO_PROCEED`, `HUMAN_REVIEW`, `HARD_REJECT`, or `DUPLICATE_RETURN`).
* **Compliant Financial Asset Generation:** Automatically processes pre-negotiated exchange rates for global accounts and outputs pixel-perfect PDF corporate invoices along with SAP-compatible Excel ledger datasets.
* **Human-in-the-Loop Triage Board:** A dedicated review screen allowing operators to inspect low-confidence processes, address data exceptions, and oversee audit flags before finalizing billing data.
* **🎙️ Voice-Activated Multimodal Intelligence (Smallest.ai Integration):** Integrates dual audio layers into the tracking view, offering instant conversational voice queries via Speech-to-Text (STT) and automated high-quality summary overviews using Text-to-Speech (TTS).

---

## 🏗️ Core Architecture & The 5-Stage Pipeline

Sentinel utilizes a modular, decoupled domain structure driven by an atomic execution flow managed by `pipeline.py`:


```

[ Upload / Ingest ] ──> 📄 Stage 1: DocumentEngine (AI Extraction)
│
⚙️ Stage 2: ProcessingEngine (Billing Calculations)
│
🔍 Stage 3: ValidationEngine (14 Corporate Rules)
│
⚠️ Stage 4: ExceptionEngine (Routing Authority)
├─── [Below Threshold / Fails] ──> [ 🔍 Human Review Queue ]
└─── [Pass / Auto-Corrected]
│
📄 Stage 5: InvoiceEngine (PDF & SAP Excel Gen)
│
💾 Stage 6: Persist (SQLite Ledger & Log Events)
│
🎙️ [ 📄 Invoice Preview Page with Audio Control ]

```

1. **Stage 1 — DocumentEngine:** Ingests raw files and coordinates with the Google Gemini client to run structural extractions, mapping granular confidence vectors for every field.
2. **Stage 2 — ProcessingEngine:** Executes absolute calculation laws based on enterprise configurations, separating core limits (8h daily / 40h weekly) from active 1.5x overtime billing brackets.
3. **Stage 3 — ValidationEngine:** Evaluates contract boundaries, credentials, and live system logs to catch duplicate billing events before they clear accounts payable.
4. **Stage 4 — ExceptionEngine:** Acts as the central pipeline gatekeeper. It assigns human review priorities and uses soft-matching parameters to resolve text anomalies automatically.
5. **Stage 5 — InvoiceEngine:** Compiles the parsed data into finalized financial PDF representations based on corporate sequence patterns and packages down-stream transactional records.
6. **Stage 6 — Persist:** Commits invoice objects to an internal SQLite database layer and prints chronological events to the application's audit history.

---

## 🎙️ Smallest.ai Voice Pipeline Specifications

The `03_invoice_preview.py` module integrates native browser audio nodes to deliver interactive human audits:
* **Voice Query Assistant (STT & LLM Context):** Captures microphone buffers via `streamlit_mic_recorder`, fires the raw audio stream to the Smallest.ai Pulse API (`/waves/v1/pulse/get_text`), and feeds the resulting text into a context-locked Gemini loop loaded with the invoice's JSON profile to answer natural language operator inquiries.
* **Voice Invoice Narrator (TTS Generation):** Compiles financial stats into an explicit descriptive script and passes it to the Smallest.ai Waves API (`/waves/v1/tts`) using the lightning-fast `"lightning_v3.1_pro"` model and the custom `"meher"` voice profile at `24000Hz` to generate clear audio recaps.

---

## 💻 Tech Stack & Core Dependencies

* **Frontend & Interaction Layer:** * **Streamlit:** Powers the multi-page lifecycle (custom views, structural sidebar routing overrides, reactive metric nodes, and status sync elements).
    * **Streamlit Mic Recorder (`streamlit_mic_recorder`):** Captures local client audio directly inside the web interface without complex web-audio wrappers.
* **Intelligence & Generation Core:** * **Google Gemini API (`gemini-2.5-flash`):** Utilized for one-pass structured record extraction and real-time contextual analysis for voice-driven invoice inquiries.
* **🎙️ Audio AI Ecosystem (Smallest.ai APIs):** * **Smallest.ai Pulse Endpoint:** Delivers fast Speech-to-Text (STT) transcription over raw audio binary streams.
    * **Smallest.ai Waves Endpoint:** Provides text-to-speech rendering utilizing advanced multi-lingual voice structures.
* **Data Core & Compute Backend:** * **Pure Python (3.10+):** Manages the underlying domain framework using type-hinted Dataclasses and isolated logic engines.
    * **Pandas:** Transforms deep-nested line item data objects into fast tabular matrices for rendering granular invoice metrics.
    * **Requests & JSON Engine:** Executes low-level REST networking passing authorization bearer keys securely across audio nodes.
* **Durable Persistence Layer:** * **SQLite Storage Engine (`database.db`):** Governs transactional saves, consecutive sequence generations, state mutations, and immutable multi-event audit tracks.

---

## 📁 Repository Blueprint

```text
├── app.py                     # Primary Application Gateway & Dashboard Entry
├── pipeline.py                # Core 5-Stage Workflow Pipeline Controller
├── config.py                  # Global Business Constraints, Folders, & Threshold Rules
├── requirements.txt           # Declared System Architecture Dependencies
├── engines/                   # Decontextualized Functional Compute Units
│   ├── document_engine.py     # AI Context Parsing Engine
│   ├── processing_engine.py   # Pure Python Billing Core
│   ├── validation_engine.py   # 14-Point Rule Evaluation Layer
│   ├── exception_engine.py    # Routing Controller & Priority Grading
│   └── invoice_engine.py      # Artifact Generator Core (PDF/Excel)
├── pages/                     # Declarative Web Interfaces
│   ├── 01_upload.py           # Multi-Format File Ingestion Node
│   ├── 02_review_queue.py     # Human-in-the-Loop Triage Board
│   ├── 03_invoice_preview.py  # Financial Artifact Viewer with Smallest.ai STT/TTS Nodes
│   └── 04_dashboard.py        # Management Analytical View
├── services/                  # Persistent System Infrastructure APIs
│   ├── database_service.py    # SQLite Storage Core
│   ├── gemini_service.py      # LLM API Interface Client
│   └── export_service.py      # Downstream Transaction Handlers
├── data/                      # Active Static Reference Datasets
│   ├── contracts/             # Contract JSON definitions
│   └── master_data/           # Reference master directories (`employees.json`, etc.)
└── runtime/                   # Directory Context for Local Transactions

```

---

## 🛠️ Installation & Getting Started

### 1. Pre-requisites

Ensure you have `Python 3.10` or higher installed on your local system.

### 2. Clone the Repository

```bash
git clone [https://github.com/manimadhav1/sentinel.git](https://github.com/manimadhav1/sentinel.git)
cd sentinel

```

### 3. Setup Virtual Environment & Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt

```

### 4. Configure Environment Secrets

Create a `.env` file within the root folder of the project:

```env
GEMINI_API_KEY=your_actual_google_gemini_api_key_here

```

*(Note: Smallest.ai authorization values are mapped to `config.SMALLEST_API_KEY` for runtime queries).*

### 5. Initialize & Boot the Platform

Fire up the global Streamlit process wrapper to spin up the local server context:

```bash
streamlit run app.py

```

Open `http://localhost:8501` in your browser to view the automation suite dashboard.

---

## ⚖️ Embedded Business Policy Reference

The automation engines evaluate invoices against predefined constraints configured in `config.py`:

* **Confidence Floor:** Processes carrying an aggregate AI verification rate below `75.0%` are systematically locked and rerouted to the manual triage board.
* **Shift Parameters:** Standard human tracking caps are set to a maximum regular threshold of `8 hours per day` or `40 hours per week`.
* **Overtime Coefficient:** Verified overtime records are credited with a `1.5x` billable premium multiplier.
* **Taxation Ledger:** Every invoice calculates standard operational line items against an explicit `18% GST rate`.

---

## 👥 Team Nexus — HackArena 2.0

* **Project Showcase:** Sentinel Touchless Billing Automation Core
* **Event Context:** 24 Hrs HackArena 2.0 Grand Finale by Ignite Room
* **Development Focus:** Pure Python Logic Engines, Generative Document Extraction, Smallest.ai Voice Overlays, and Enterprise Human-in-the-Loop Orchestration Systems.

