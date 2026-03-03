# Technical Specification: Agentic Fact-Checking RAG (AF-RAG)

## 1. Project Overview
**AF-RAG** is a multi-agent system designed for law enforcement and investigative environments. Its purpose is to verify specific claims (e.g., alibis) against a disparate set of evidence—including witness statements, body-cam transcripts, and digital logs—using weighted credibility and outlier detection.

## 2. System Architecture
The system utilizes a **Plan-Execute-Verify** loop to ensure that queries are specialized and evidence is cross-referenced rather than just retrieved.

### Workflow Phases:
1. **Claim Extraction (Input):** Accepts raw text (e.g., "I was at the store with David at 11:00 PM on Sunday").
2. **Planner Agent (Specializer):** - Uses a fast, efficient model (e.g., Gemini Flash).
   - Decomposes claims into entities (David), times (11:00 PM), and locations (Store).
   - Generates targeted sub-queries.
3. **Researcher Agent (Hybrid RAG):** - Executes semantic and keyword searches against a Vector Database (Pinecone/ChromaDB).
   - Retrieves specific data "chunks" relevant to the specialized queries.
4. **Judge Agent (Synthesis & Reasoning):** - Uses a high-reasoning model (e.g., Gemini Pro).
   - Compares retrieved evidence against the claim using Natural Language Inference (NLI).



## 3. Logical Flow (Mermaid)

```mermaid
graph TD
    A[Raw Alibi/Fact] --> B[Planner Agent: Specializer]
    B --> C{Entity Extraction}
    C -->|Name: David| D[Query: David's Timeline]
    C -->|Time: 11pm| E[Query: Digital Logs]
    C -->|Loc: Store| F[Query: CCTV/Receipts]
    
    D & E & F --> G[Vector Database / RAG]
    G --> H[The Judge Agent: Synthesis]
    
    H --> I{Outlier Detection}
    I -->|Consistent| J[Verification: High Confidence]
    I -->|Minor Outlier| K[Verification: Flag Anomalies]
    I -->|Major Conflict| L[Verification: Contradiction Found]

    ## 3. Evidence Weighting & Outlier Logic
To handle conflicting testimonies without losing critical data, the system applies a reliability weight to different evidence types.

| Evidence Source | Weight | Description |
| :--- | :--- | :--- |
| **Digital Evidence** | 0.95 | GPS, Body Cam, CAD Logs, Metadata. |
| **Physical Evidence** | 0.90 | Receipts, Badge Swipes, Forensic Data. |
| **Human Testimony** | 0.60 | Witness statements (Flagged for memory drift). |

---

## 4. Implementation Details
* **Orchestration Framework:** LangGraph (for stateful agent loops).
* **Database:** Pinecone, Weaviate, or ChromaDB.
* **Language:** Python 3.10+.
* **Key Logic:** Temporal reasoning (handling "approximate" times like "around 11 PM").

---

## 5. Development Roadmap
- [ ] **Phase 1:** Build "Mock Investigation" folder with conflicting text files.
- [ ] **Phase 2:** Implement Planner Agent for claim decomposition.
- [ ] **Phase 3:** Create "The Judge" prompt with weighted scoring logic.
- [ ] **Phase 4:** UI/UX for displaying the "Conflict Map."

---
### Outlier Handling Policy
Outliers are **never discarded**. If a contradiction exists (e.g., the "99% vs 1%" scenario), the system:
1.  **Calculates a total Confidence Score** based on weighted inputs.
2.  **Appends an Anomaly Flag** to the report describing the minority statement.
3.  **Categorizes the outlier** (e.g., "Potential Memory Drift" or "Contradictory Eye-Witness").
