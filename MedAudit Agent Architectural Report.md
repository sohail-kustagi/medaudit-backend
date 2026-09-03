# **MedAudit Agent: System Architecture & Technical Specification**

## **Project Overview**

MedAudit is an autonomous agent designed for the "Everyday Agents" track of the Agents for Humans Hackathon. It operates silently in the background, utilizing the Strands Agents SDK to process medical bills, cross-reference CPT (Current Procedural Terminology) codes, detect upcoding errors, and draft regulatory-compliant dispute letters.

This report details the core architecture, divided into three primary domains: Frontend (User Interface/Interaction), Backend (Data Processing & Infrastructure), and LLM (Agentic Logic & Orchestration).

## **1\. Frontend Architecture (The "Zero-Noise" Interface)**

**Philosophy:** Following the hackathon's "zero-noise" mandate, the frontend is not a traditional dashboard where users spend time. It is an ambient interface designed solely for notification, document ingestion, and final approval.

### **Tech Stack**

* **Framework:** Next.js (React)  
* **Styling:** Tailwind CSS \+ shadcn/ui (for minimal, clean components)  
* **State Management:** Zustand (lightweight local state)  
* **Authentication:** AWS Cognito (secure patient data access)  
* **Deployment:** Vercel or AWS Amplify

### **Core Components**

1. **The Dropzone (Ingestion):** A secure, drag-and-drop file upload component allowing users to manually upload PDFs of medical bills or Explanation of Benefits (EOBs).  
2. **The Inbox (Notification Center):** A minimalist feed showing the status of processed documents (e.g., "Scanning," "Cleared," "Discrepancy Found").  
3. **The Action Modal (Human-in-the-Loop):** When the agent drafts a dispute, this modal surfaces. It displays:  
   * A side-by-side view of the original bill (highlighting the disputed CPT code).  
   * The agent's reasoning for the dispute.  
   * The generated markdown/PDF of the dispute letter.  
   * "Approve & Send" vs. "Dismiss" buttons.

### **User Flow (Frontend)**

1. User securely logs in via AWS Cognito.  
2. User drags and drops a PDF bill.  
3. The frontend requests a pre-signed S3 URL from the backend and uploads the file directly to AWS S3.  
4. The frontend returns to an idle state.  
5. When the backend agent flags a discrepancy, it sends a webhook/notification.  
6. The frontend displays the Action Modal for user review and final approval.

## **2\. Backend Architecture (Infrastructure & Data Processing)**

**Philosophy:** The backend handles the heavy lifting of document processing, secure storage, and event-driven orchestration, ensuring the LLM has clean, structured data to analyze.

### **Tech Stack**

* **API Framework:** FastAPI (Python) \- *chosen for speed and native async support.*  
* **Cloud Infrastructure:** AWS (to leverage the hackathon credits and requirements).  
* **Database:** PostgreSQL (via AWS RDS) for user metadata, CPT code reference tables, and document statuses.  
* **Document Processing:** Amazon Textract.  
* **Object Storage:** AWS S3 (for PDFs and generated dispute letters).

### **Core Pipelines**

1. **Ingestion & OCR Pipeline:**  
   * Triggered when a file lands in S3.  
   * FastAPI backend calls **Amazon Textract** via Boto3 to run OCR on the PDF.  
   * Textract outputs raw text, tables, and key-value pairs.  
2. **Structuring Pipeline:**  
   * The backend runs a preliminary script to extract the most relevant entities (Patient Name, Date of Service, Provider, Total Billed, and potential CPT/Diagnosis codes) from the Textract output, formatting it into a clean JSON payload.  
3. **Database References:**  
   * The backend maintains a localized, relational database of standard CPT codes and general Medicare pricing baselines. When the JSON payload is created, the backend enriches the payload with the standard descriptions of the detected CPT codes.

### **Event Flow (Backend)**

1. S3 ObjectCreated event triggers the FastAPI OCR route.  
2. FastAPI calls Amazon Textract \-\> Receives raw text.  
3. FastAPI structures the data into JSON.  
4. FastAPI passes the structured JSON to the LLM Agent Orchestrator.  
5. FastAPI listens for the Agent's output (Cleared vs. Disputed).  
6. Updates PostgreSQL database with the status and triggers a notification to the frontend if disputed.

## **3\. LLM & Agentic Architecture (Strands SDK Implementation)**

**Philosophy:** This is the core intelligence of MedAudit. It uses the Strands Agents SDK to reason through the structured bill data, utilizing specific tools to validate claims and generate outputs.

### **Tech Stack**

* **Agent Framework:** Strands Agents SDK (Python)  
* **LLM Provider:** Amazon Bedrock (e.g., Claude 3.5 Sonnet or Haiku, depending on cost/speed needs).  
* **Deployment Target (Crucial for Hackathon):** Amazon Bedrock AgentCore Runtime (provides secure, sandboxed execution).

### **The Agentic Workflow**

The MedAudit agent operates on a specific execution loop, utilizing several custom tools (defined via @tool decorators in the Strands SDK).

#### **1\. The Prompt Persona**

The agent is primed with a strict system prompt: *"You are MedAudit, a highly analytical medical billing auditor. Your goal is to review structured billing data, cross-reference it with standard medical coding logic, and identify upcoding, unbundling, or out-of-network pricing errors. You must detail your reasoning before generating a dispute."*

#### **2\. Custom Tools (@tool)**

The Strands SDK allows the agent to call these Python functions:

* query\_policy\_rules(patient\_id, cpt\_code): Allows the agent to query a simulated database of the user's specific insurance policy rules (e.g., "Is lab work at this facility covered?").  
* check\_unbundling(cpt\_code\_list): A tool that checks if a group of submitted codes should actually be billed as a single, comprehensive code.  
* draft\_appeal\_letter(patient\_info, provider\_info, disputed\_code, reasoning): Takes the agent's findings and generates a formal, formatted markdown letter.

#### **3\. The Execution Loop (The "Thinking" Phase)**

1. **Input:** The agent receives the structured JSON from the backend.  
2. **Reasoning (Using Strands Thinking Tool):** The agent is forced to outline its logic. It evaluates the billed codes against the diagnosis.  
3. **Tool Execution:** The agent decides it needs to call query\_policy\_rules and check\_unbundling based on its initial reasoning.  
4. **Synthesis:** The agent evaluates the results from the tools.  
   * *If no errors found:* The agent returns a simple {"status": "cleared"} payload.  
   * *If error found:* The agent calls draft\_appeal\_letter and returns a payload containing {"status": "disputed", "reasoning": "...", "letter\_markdown": "..."}.

### **Why this fits the Hackathon Criteria**

* **Everyday Agents Track:** It targets a painful, everyday problem (medical debt/billing confusion) and operates silently.  
* **Technical Implementation:** Demonstrates deep use of the Strands SDK (custom tools, thinking process) and utilizes AWS services (Textract, S3, Cognito).  
* **Design/Impact:** The "zero-noise" frontend combined with the complex backend processing delivers a complete product experience, not just a chatbot.