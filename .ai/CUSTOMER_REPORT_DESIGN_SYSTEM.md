# VERIDRA Customer Report Design System

Status: Phase D shadow/customer-report acceptance candidate  
Purpose: turn VERIDRA evidence into a concise, visual, client-ready decision document.

## External benchmark principles

Professional client-ready audit examples consistently emphasize:
- one-page executive summary / fast decision layer;
- a small number of ranked findings rather than raw scanner output;
- evidence attached to every important finding;
- plain-language business impact;
- a concrete next action and re-test;
- technical detail moved to supporting evidence rather than the opening pages.

VERIDRA adopts those principles while avoiding synthetic grades or unsupported impact claims.

## Customer-facing report contract

### 1. Length
- Target: **1 page** for the main report.
- Maximum: **2 pages** if 3 visual findings plus evidence cannot fit cleanly.
- Technical evidence belongs in an appendix/export, not the customer front page.

### 2. Finding limit
- Maximum **3 priority findings**.
- If more issues exist, show only the ones that most clearly change trust, conversion, local presence, customer experience or business accuracy.
- Everything else stays in VERIDRA evidence or monitoring backlog.

### 3. Opening
Start with one short business-level takeaway:
- what is working;
- what needs attention;
- whether this looks like a focused cleanup, ongoing monitoring need, or no major corrective project.

Never open with a crawler count, severity table or technical warning list.

### 4. What is working
Include **2–4 verified strengths** when evidence supports them.
Purpose:
- reduce alarmism;
- show balanced judgment;
- make low-remediation cases credible.

### 5. Priority issue card

Each customer-visible issue uses exactly this structure:

**[Priority label] Plain-language issue title**

**Screenshot / evidence**
- show a tightly cropped screenshot of the visible problem whenever the issue is visual;
- add one red box/arrow only when needed;
- include page name or URL below the image;
- no decorative screenshots.

**Why it matters**
- maximum 1–2 sentences;
- connect to patient/customer trust, conversion, local accuracy or maintenance;
- do not invent revenue loss, traffic loss or conversion percentages.

**Recommended fix**
- maximum 1–2 sentences;
- concrete next action;
- include owner confirmation where facts such as canonical opening hours are uncertain.

**Priority**
- Fix now
- Improve
- Monitor

Do not expose internal severity labels such as high/medium/low unless necessary.

### 6. Screenshot rules
For every visible issue:
- capture desktop or mobile state where the problem is clearest;
- crop around the issue;
- preserve enough context to identify the page;
- add a red rectangle/arrow only if the issue is not immediately obvious;
- never alter the website content inside the capture;
- label the source URL/page;
- record capture date internally.

If no screenshot can prove the claim, use a compact evidence block instead of forcing an image.

### 7. Copy rules
- customer language, not analyzer language;
- short sentences;
- no acronyms without explanation;
- no raw IDs such as `crawl.description`;
- no “we detected X warnings” framing;
- no generic fear language;
- distinguish demonstrated condition from possible consequence;
- never claim business loss without evidence.

Preferred pattern:
**What we saw → why it matters → what to do next.**

### 8. Final section
End with:

**Recommended next step**
One clear action:
- focused cleanup;
- owner confirmation + reconciliation;
- monitoring baseline;
- or no major corrective work required.

Then, if appropriate:

**What we would monitor**
Maximum 3–5 items.

### 9. Scope note
One short line:
“Public website review only. No forms, private systems, patient data or transactions were accessed.”

### 10. Customer report vs technical evidence
Customer report:
- 1–3 issues;
- screenshots;
- business impact;
- action.

VERIDRA evidence appendix:
- full finding set;
- URLs;
- raw evidence;
- technical severity;
- validation state;
- re-test criteria.

The customer should not have to read the appendix to know what decision to make.

## Recommended visual hierarchy

1. Client/business name
2. “Digital Presence Review”
3. one-sentence takeaway
4. “What’s working”
5. up to 3 screenshot-backed issue cards
6. recommended next step
7. what we would monitor
8. one-line scope

## Report quality gate

A customer report is acceptable only if:
- a non-technical owner can understand the top issue in <30 seconds;
- every customer-visible problem is supported by evidence;
- the report contains no more than 3 priority issues;
- screenshots are used for visible issues;
- recommended actions are concrete;
- no major unsupported inference is presented as fact;
- the report does not manufacture work for a healthy site.


## Approved v6 master layout (2026-09-25)

Human visual acceptance: **APPROVED DIRECTION** after iterative review of Dublin City Dentist.

### Page 1 — Executive decision layer
- client/business name;
- short diagnosis headline;
- concise supporting sentence;
- verified “What is already working” block;
- service path: **FIX → VERIFY → MONITOR**;
- one restrained CTA:
  **Request cleanup + verification** (or equivalent service-specific wording);
- no synthetic score/KPI row unless the metric is genuinely decision-useful;
- use whitespace intentionally, but avoid empty-page feel.

### Page 2 — Evidence + action layer
For each priority issue:
- large screenshot/evidence crop;
- plain-language title;
- Why it matters;
- Recommended fix;
- Verification step.

Keep screenshots large enough to inspect without zooming.
Do not let monitoring/CTA blocks compete with or truncate finding content.

### Bottom section
- compact “After cleanup / What we would monitor” band;
- no second hard CTA;
- one-line scope note.

### Visual acceptance rule
Before a customer-facing PDF is accepted:
1. render every page to images;
2. visually inspect for clipping, overlap, weak hierarchy, unreadable screenshots and accidental whitespace;
3. if not acceptable, revise once before delivery;
4. do not claim acceptance from source/HTML alone.
