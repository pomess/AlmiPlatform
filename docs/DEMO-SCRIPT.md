# Disease360 Platform Demo Script
**Recording format:** Loom screen recording with narration
**Duration target:** 3–4 minutes
**Tone:** Confident, fast-paced, minimal filler — show, don't tell.

---

## OPENING (10 seconds)

**[Screen: Landing page at localhost:5173]**

> "This is Disease360 — a competitive intelligence platform built for Almirall's dermatology franchise. One workspace. Every competitor. Every drug. Every trial. Let me show you what it does."

**Click "Open platform" → navigates into the cockpit.**

---

## ACT 1: THE DASHBOARD (60–70 seconds)

**[Screen: Dashboard — global map view, 16 competitor pins visible]**

> "The dashboard is the live command center. Sixteen competitor sites tracked across Spain — Barcelona, Madrid, Tres Cantos. Each one is a pharma company running dermatology programs on Spanish soil."

**Click the Roche pin (Sant Cugat).**

> "Click any pin and you get three things at once: a 3D hologram of their actual headquarters, a photo card with their therapy focus areas, and a live news feed pulled from pharma press this morning."

**[Hologram renders, photo card slides in, news panel shows]**

> "The hologram is built from real OpenStreetMap building data — these are the actual structures at Roche's Sant Cugat campus."

**Now demonstrate voice (hold Space):**

> "And it responds to voice. Watch."

**Hold Space, say:** "Fly to Sanofi"

> *(Camera flies to Sanofi's Barcelona pin, hologram + news appear)*

> "Ask about any competitor and the map moves to them. The agent understands pharma context — companies, locations, indications."

**Hold Space, say:** "What's the latest on AstraZeneca?"

> *(Map flies to AstraZeneca, news panel shows relevant headlines)*

---

## ACT 2: THE BULLSEYE (50–60 seconds)

**Click "Bullseye" in the top nav.**

**[Screen: Bullseye visualization — concentric rings with drug dots]**

> "This is the competitive landscape as a radar. Five concentric rings — from Approved in the center, out through Phase III, Phase II, Phase I, to Preclinical at the edge."

> "Every dot is a drug. Companies fan around the perimeter. You can see at a glance who's where — Sanofi and Lilly dominating late-stage, Almirall's Ebglyss sitting in the Approved ring with that navy highlight."

**Click a dot (e.g., dupilumab or an Almirall asset).**

> "Click any asset and you get the full dossier — target, modality, route of administration, development timeline, highest phase. All curated from primary sources."

**Pan across indications if multiple tabs exist:**

> "Three indications wired in today: atopic dermatitis, hidradenitis suppurativa, and psoriasis. Same shell, same drill-down. Adding a new indication is adding a dataset — not a new tool."

---

## ACT 3: THE CHAT + KNOWLEDGE GRAPH (50–60 seconds)

**Click "Chat" in the top nav.**

**[Screen: Chat interface with brain selector]**

> "The chat is backed by a knowledge graph — not just an LLM. There's a curated vault of clinical trials, PubMed evidence, and competitive intelligence underneath."

**Type or say:** "What clinical trials are recruiting for hidradenitis suppurativa right now?"

> *(Agent responds with structured data from the BioMCP Brain — trial IDs, statuses, drugs involved)*

> "That answer didn't come from a generic model. It came from 33 ClinicalTrials.gov records and 3 PubMed papers that we ingested, structured, and linked. The agent cites its sources — every fact is traceable."

**Click "Graph" in the top nav.**

**[Screen: Knowledge graph visualization — nodes and edges]**

> "And here's the graph those answers are built on. Drugs, targets, mechanisms, companies, indications — all wired together. Click a node and you see every connection."

> "This is the context layer. When the agent says 'secukinumab is being studied in 3 HS trials,' it's because it can traverse this graph — not because it memorized a training set."

---

## CLOSING (15 seconds)

**Navigate back to Dashboard (or Landing).**

> "One platform. Real-time news, live maps, structured evidence, a knowledge graph, and an AI that can navigate all of it by voice or text. Built for the franchise team that needs answers now — not next quarter."

> "This is Disease360."

---

## TIPS FOR RECORDING

- **Resolution:** 1920x1080, browser fullscreen (F11)
- **Clear localStorage** before recording if you want the hologram to show the "instant load from static" flow
- **Pre-warm:** Open the dashboard once before recording so all assets are cached
- **Voice:** Speak clearly into the mic when doing push-to-talk. The STT picks up best with short, direct phrases like "Fly to Roche" or "Show me Pfizer"
- **Pace:** Don't rush transitions — let the flyTo animations and hologram renders complete before talking over them (they take ~2s)
- **If voice fails:** Use the text box at the bottom ("ASK DISEASE360") as backup — same agent, typed input
