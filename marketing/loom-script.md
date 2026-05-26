# 90-second Loom — "Watch a board pack go out the door"

_The single demo asset. Embedded on `signkairos.com` in Section 3, linked from every cold email._

## Setup before recording

- **Sanitized example brains** loaded: `Acme SaaS Inc.` and `Beacon Logistics`. Both with realistic last-month financials, prior board updates, meeting notes, and one outstanding investor question each. (Scaffold lives at `vault/Acme SaaS Inc/` and `vault/Beacon Logistics/`.)
- **You** play yourself, the fractional CFO of both.
- **Voice over screen** only — no webcam.
- **Recording**: 1080p, no music, hard cuts only, real-time (no 2x).

---

## Beat sheet

### [0:00–0:08] Cold open, on the Approvals view

> _"This is what my Monday looks like. Two clients want their March board packs by Friday. I'm going to do both, in two minutes, on camera."_

### [0:08–0:22] Switch to chat in Acme's brain

Type:
> `Draft the March board update for Acme. Variance commentary on top three line items, ask about the new sales hire.`

Stream visibly runs. Tool calls appear (`search_brain`, `get_page`, `draft_board_pack`). Don't narrate the tool names — just let the viewer see them tick by.

> _"It's pulling last month's update, the variance notes I took on Thursday's call, and the runway model. None of that came from training data — it's all in Acme's vault."_

### [0:22–0:38] Result appears — a markdown board update

Don't read it aloud. Just scroll through.

> _"That's a draft. Not a sent email. Notice — bottom right."_

Camera zooms to the Approvals badge: **1 pending**.

### [0:38–0:55] Click into Approvals

> _"Here's the actual send. To: Acme's CEO. Subject, body, attachment. I can approve, edit, or deny. If I edit, it edits then sends. If I deny, it asks me what was wrong."_
>
> _"I'll approve."_

Click. Toast: _"Sent to ceo@acme.com."_

### [0:55–1:10] Switch brain to Beacon Logistics — visibly different sidebar

> _"Now Beacon. Same prompt. Watch what does **not** happen."_

Stream runs. The Beacon draft references Beacon's metrics, Beacon's people, Beacon's last conversation. No Acme leakage. The viewer can see the sidebar names changed.

> _"Different brain. Acme's data isn't visible here. Cross-contamination isn't a policy — it's a wall."_

### [1:10–1:25] Open the audit log timeline

(`logs/audit.jsonl` rendered as a timeline, or the cockpit's audit view.)

> _"And every step of both is here. Tool call, draft created, approval queued, approval resolved, send. Timestamped. Exportable. This is what I'd hand a malpractice carrier or an engagement-end review."_

### [1:25–1:30] Cut back to the homepage

> _"Two board packs in two minutes. Six clients, one brain, zero crossed wires. signkairos.com."_

---

## Production notes

- **No music.** Silence under voiceover reads serious. Music reads ad.
- **Hard cuts, no fades.** Every transition is a hard cut.
- **Mouse movements small and deliberate.** No zooming around.
- **Sanitized but realistic.** "Acme SaaS Inc," "Beacon Logistics" — not "Test Client 1."
- **Real-time only.** No 2x speed-up. Real-time is a trust signal.
- **No webcam overlay.** Your face distracts from the product.
- **Caption track:** auto-generate in Loom, then hand-fix the four key lines (the variance line, the "different brain" line, the audit line, the closer).

## What the viewer must believe by 1:30

1. The product remembers each client separately.
2. Nothing leaves until I approve it.
3. There's a paper trail when I need it.
4. Two real-looking board packs got drafted in real time, not in a stitched edit.

If any of those four feels weak on playback, re-record that beat.
