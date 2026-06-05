# Disease360 Atlas — Glossary & Domain Language

Use these terms consistently across code, docs, and UI copy.

## Platform

| Term | Definition |
|------|-----------|
| **Disease360 Atlas** | The competitive intelligence cockpit (this product) |
| **Vera** | The AI research assistant deployed on Databricks Model Serving (MLflow ResponsesAgent) |
| **Cockpit** | The React 19 SPA that users interact with |
| **Platinum Layer** | Pre-computed tables in Unity Catalog optimized for frontend consumption |
| **Context Layer** | Synonym for Platinum Layer (Gartner terminology) |

## Pharma domain

| Term | Definition |
|------|-----------|
| **AD** | Atopic Dermatitis — primary indication |
| **HS** | Hidradenitis Suppurativa — primary indication |
| **PSO** | Psoriasis — secondary indication |
| **KOL** | Key Opinion Leader — influential physician/researcher |
| **MoA** | Mechanism of Action — how a drug works at molecular level |
| **LOE** | Loss of Exclusivity — when patent protection expires |
| **PDUFA** | Prescription Drug User Fee Act — FDA regulatory deadline |
| **SmPC** | Summary of Product Characteristics (EMA equivalent of FDA label) |
| **Bullseye** | Radial competitive positioning chart (drugs/companies by proximity to Almirall) |
| **Pipeline drug** | Drug in development (Preclinical → Phase I → II → III → Approved) |
| **Marketed drug** | Drug that has regulatory approval and is commercially available |
| **Catalyst** | Upcoming event that could move a company's value (trial readout, approval, PDUFA date) |

## Data sources

| Source | What it provides |
|--------|-----------------|
| **GlobalData** | Commercial pharma intelligence (companies, drugs, deals, sales, catalysts, news) |
| **ClinicalTrials.gov** | Clinical trial registry (NCT IDs, sponsors, status, enrollment) |
| **PubMed / Entrez** | Biomedical literature (articles, abstracts, citations) |
| **BioMCP** | API layer over PubMed + ClinicalTrials.gov + gene/disease/drug ontologies |
| **EMA** | European Medicines Agency product information |
| **FDA / OpenFDA** | US drug approvals, labels, patents |
| **PharmaForce** | Additional commercial pharma data |

## Knowledge graph ontology

| Node type | Examples |
|-----------|---------|
| `company` | Almirall, Sanofi, Novartis, Eli Lilly |
| `drug` | Dupixent (dupilumab), Ebglyss (lebrikizumab), Cosentyx (secukinumab) |
| `indication` | Atopic Dermatitis, Hidradenitis Suppurativa, Psoriasis |
| `mechanism` | IL-4/IL-13 inhibitor, IL-17A inhibitor, JAK inhibitor |
| `trial` | NCT07297602, NCT05821478 |
| `kol` | Named researchers/physicians |
| `institution` | University hospitals, research centers |

| Relation type | Meaning |
|---------------|---------|
| `develops` | Company → Drug |
| `treats` | Drug → Indication |
| `targets` | Drug → Mechanism |
| `competes_with` | Company → Company (same therapeutic area) |
| `sponsors_trial` | Company → Trial |
| `evaluates` | Trial → Drug |
| `investigates` | KOL → Indication |
| `affiliated_with` | KOL → Institution |
| `approved_for` | Drug → Regulatory decision (by geography) |

## Architecture terms

| Term | Definition |
|------|-----------|
| **Memory service** | FastAPI module that queries Unity Catalog Platinum tables (graph, bullseye, search) |
| **Harness service** | FastAPI module for news RSS aggregation + Vera SSE proxy |
| **Unity Catalog** | Databricks governance layer for tables, views, and ML artifacts |
| **Vector Search** | Databricks semantic search service (used for KOL minutes, news, EMA docs) |
| **DABs** | Databricks Asset Bundles — deployment packaging format |
| **OBO** | On-Behalf-Of authentication — Databricks Apps injects user token |
| **Lakeflow Job** | Scheduled Databricks job that refreshes Platinum tables from Gold |
