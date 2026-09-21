# Al Dente Brain – Frontend Specification (Premium Executive Edition)

## Project Overview

**Product Name**: Al Dente Brain  
**Tagline**: Ask the company. Watch the evidence connect.

**Mission**: Build a sophisticated executive intelligence cockpit that makes agentic reasoning visible. Show how the system routes through company data (CRM, ERP, RAG, Calls) and connects evidence in a living knowledge graph.

---

## Visual Direction

**Aesthetic**: Premium Corporate Command Center  
**Vibe**: Professional, trustworthy, high-end (think modern ERP + Bloomberg Terminal + Apple design)

- Deep charcoal / near-black background
- Elegant glassmorphism panels with subtle borders and depth
- Primary accent: Teal / Emerald
- Secondary: Warm amber for alerts
- Typography: Inter + Satoshi (or system fonts)
- Animations: Purposeful and restrained (Framer Motion)

---

## Main Layout

┌──────────────────────────────────────────────────────────────────────────────┐
│ Al Dente Brain                          Source-Locked Mode: Active     X-Ray │
├─────────────────┬──────────────────────────────────┬───────────────────────┤
│                 │                                  │                       │
│ Orchestration   │       Living Knowledge Graph     │   Executive Memo      │
│ Hub             │         (Hero Visual)            │                       │
│                 │                                  │   • Answer            │
│ • CRM           │  Supplier → Material → Product   │   • Confidence        │
│ • ERP           │          → Lot → Customer        │   • Evidence          │
│ • RAG           │                                  │   • Sources           │
│ • Calls         │                                  │   • Next Actions      │
├─────────────────┴──────────────────────────────────┴───────────────────────┤
│                     ⌘ Ask the company brain...                               │
└──────────────────────────────────────────────────────────────────────────────┘



---

## Core Components

### 1. Header
- Logo + "Al Dente Brain"
- Source-Locked Mode badge (green)
- X-Ray Mode toggle
- User / Company info

### 2. Orchestration Hub (Left Panel)
**Title**: Intelligence Orchestration

Displays 4 tools:
- CRM, ERP, RAG, Call Logs

Each tool card includes:
- Icon (Lucide)
- Status (Idle / Active / Used)
- Record count / Evidence strength
- Subtle pulse when active

### 3. Knowledge Graph (Center – Most Important)
**Library**: React Flow

**Node Types**: Customer, Supplier, Product, Material, Order, Lot, Document, Call

**Behavior**:
- **Idle**: Gentle breathing glow + very slow subtle edge flow
- **On Question**: Soft scan animation
- **On Answer**:
  - Non-relevant nodes fade (60% opacity)
  - Relevant nodes get clean highlight ring + soft pulse
  - Animated flowing path traces the reasoning chain
  - Mini-map in top-right corner
- Hover: Highlight connected nodes

### 4. Executive Memo (Right Panel)
Professional briefing style:
- Clean answer with elegant reveal
- Confidence meter (visual bar + label)
- Evidence chips (clickable → highlights graph nodes)
- Sources list
- Recommended Next Actions
- Artifact Card (if `artifact_url` exists)

### 5. Command Bar (Bottom)
- Large elegant input field
- Voice input button (mic icon)
- Submit with loading state

---

## Backend Contract

**POST** `/ask`

```json
{
  "question": "Which customers are affected by lot L-221?"
}