# Frontend Component Specification

> **Source:** `/poc/static/index.html` — single-file HTML+CSS+JS (727 lines)
> **Domain:** Telecom Agentic Orchestration Engine — PoC Demo
> **Stack:** Vanilla JS, no frameworks. JetBrains Mono font. Dark theme (Slate palette).

---

## 1. Layout Structure

### Top-Level DOM
```
<body>
  .header                          ← fixed top bar (branding, badge)
  .main
    .panel.panel-left              ← LEFT PANEL (420px, flex-shrink:0)
      .left-section                → textarea#prompt
      .btn-row                     → btn-primary "Execute" + btn-secondary "Clear"
      .left-section                → .samples#samples (sample chips)
    .panel.panel-right             ← RIGHT PANEL (flex:1)
      .empty-state#empty-state     → shown until first submission
      #trace-content (hidden)      → shown after submission
        .trace-header              → h2, .trace-id, .trace-status
        #trace-steps               → array of .trace-step > .step-card.*
        #notification-timeline     → .notif-timeline
        #pattern-analysis          → .pattern-analysis
        #final-summary             → .final-summary
        #network-elements          → .network-elements
  .zoom-backdrop#zoom-backdrop     ← fixed overlay (hidden until zoom)
    .zoom-container#zoom-container
  .zoom-close-hint#zoom-hint       ← "Click anywhere outside to close · Esc"
```

### Left Panel (`.panel-left`)
| Section | Element | Purpose |
|---------|---------|---------|
| Service Request | `textarea#prompt` | User enters TMF640/641 JSON or unstructured text |
| Actions | `.btn-row` > `#btn-submit`, `btn-secondary` | Execute pipeline or clear all |
| Sample Requests | `.samples#samples` | Populated by `loadSamples()` — one `.sample-chip` per sample |

### Right Panel (`.panel-right`)
| Section | Element | Purpose |
|---------|---------|---------|
| Empty State | `#empty-state` | Shown when no request has been submitted |
| Trace Header | `.trace-header` | Title, trace ID, status badge |
| Trace Steps | `#trace-steps` | Flow lines — each `.trace-step` wraps a `.step-card` |
| Notifications | `#notification-timeline` | TMF lifecycle notification timeline (horizontal) |
| Pattern Analysis | `#pattern-analysis` | Confidence, pattern match, verification, suggestions |
| Final Summary | `#final-summary` | Orchestration totals, subscriber diff |
| Network Elements | `#network-elements` | Post-activation NE state grid |

---

## 2. CSS Class Reference

### 2.1 Global & Layout

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `body` | `font-family: 'JetBrains Mono'; background: #020617; color: #e2e8f0; height: 100vh; display: flex; flex-direction: column` | Full-viewport dark flex-column shell |
| `.header` | `bg: rgba(15,23,42,0.9); border-bottom: 1px solid #1e293b; padding: 0.75rem 1.5rem; display: flex; align-items: center; flex-shrink: 0` | Frosted-glass top bar, never shrinks |
| `.pulse` | `width: 10px; height: 10px; background: #22d3ee; border-radius: 50%; animation: pulse 2s infinite` | Cyan dot pulses opacity (1 → 0.5 → 1) |
| `@keyframes pulse` | `0%/100% { opacity: 1 } 50% { opacity: 0.5 }` | Breathing indicator |
| `.header h1` | `font-size: 1rem; font-weight: 600; letter-spacing: -0.02em` | Compact title |
| `.header .badge` | `font-size: 0.65rem; padding: 0.15rem 0.55rem; border-radius: 999px; background: rgba(34,211,238,0.15); color: #22d3ee; border: 1px solid rgba(34,211,238,0.3)` | Pill-shaped "PoC Demo" badge |
| `.main` | `display: flex; flex: 1; overflow: hidden` | Panel container — fills remaining vertical space |
| `.panel` | `padding: 1.25rem; overflow-y: auto` | Shared panel base — scrolls vertically |
| `.panel-left` | `width: 420px; flex-shrink: 0; border-right: 1px solid #1e293b; background: rgba(15,23,42,0.4)` | Fixed-width left column |
| `.panel-right` | `flex: 1; background: rgba(2,6,23,0.6)` | Fluid right column |
| `.left-section` | `margin-bottom: 1.25rem` | Vertical spacing between left-panel sections |
| `.left-section label` | `font-size: 0.7rem; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.08em` | ALL-CAPS muted label |
| `textarea` | `min-height: 160px; background: #0f172a; border: 1px solid #334155; border-radius: 8px; color: #e2e8f0; font-size: 0.72rem; padding: 0.75rem; resize: vertical; line-height: 1.5` | Dark input area |
| `textarea:focus` | `outline: none; border-color: #22d3ee; box-shadow: 0 0 0 2px rgba(34,211,238,0.15)` | Cyan glow on focus |

### 2.2 Buttons

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.btn-row` | `display: flex; gap: 0.5rem; margin-top: 0.6rem` | Horizontal button group |
| `button` | `font-family: 'JetBrains Mono'; font-size: 0.7rem; font-weight: 600; padding: 0.55rem 1rem; border-radius: 8px; border: none; cursor: pointer; transition: all 0.15s` | Base button reset |
| `.btn-primary` | `background: #22d3ee; color: #020617` | Cyan execute button |
| `.btn-primary:hover` | `background: #67e8f9` | Lightens on hover |
| `.btn-secondary` | `background: rgba(51,65,85,0.5); color: #94a3b8; border: 1px solid #334155` | Ghost clear button |
| `.btn-secondary:hover` | `background: rgba(51,65,85,0.8); color: #e2e8f0` | Fills on hover |
| `button:disabled` | `opacity: 0.4; cursor: not-allowed` | Dimmed during submission |

### 2.3 Samples

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.samples` | `margin-top: 0.5rem` | Container for sample chips |
| `.sample-chip` | `display: block; width: 100%; text-align: left; padding: 0.45rem 0.6rem; background: rgba(30,41,59,0.5); border: 1px solid #1e293b; border-radius: 6px; color: #94a3b8; font-size: 0.62rem; cursor: pointer; margin-bottom: 0.3rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis` | Truncated clickable sample row |
| `.sample-chip:hover` | `background: rgba(34,211,238,0.08); border-color: rgba(34,211,238,0.3); color: #22d3ee` | Cyan highlight on hover |

### 2.4 Trace Header

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.trace-header` | `display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid #1e293b` | Horizontal bar with bottom rule |
| `.trace-header h2` | `font-size: 0.85rem; font-weight: 600` | "Pipeline Trace" heading |
| `.trace-id` | `font-size: 0.6rem; color: #475569` | Muted trace/order ID |
| `.trace-status` | `font-size: 0.65rem; padding: 0.15rem 0.55rem; border-radius: 999px; font-weight: 600` | Status pill base |
| `.trace-status.blocked` | `background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3)` | Red "BLOCKED" / "TUNNEL ERROR" / "ERROR" pill |
| `.trace-status.running` | `background: rgba(251,191,36,0.15); color: #fbbf24; border: 1px solid rgba(251,191,36,0.3)` | Amber "PROCESSING" pill |
| `.trace-status.error` | `background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3)` | Red error pill |
| `.trace-status.completed` | `background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3)` | Green "COMPLETED" pill |

### 2.5 Notification Timeline

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.notif-timeline` | `margin: 0.4rem 0; padding: 0.6rem 0.8rem; background: rgba(6,182,212,0.05); border: 1px solid rgba(6,182,212,0.15); border-radius: 8px` | Cyan-tinged section box |
| `.notif-timeline h3` | `font-size: 0.7rem; color: #06b6d4; margin-bottom: 0.5rem; font-weight: 600` | "📬 TMF Lifecycle Notifications" |
| `.notif-track` | `display: flex; align-items: flex-start; gap: 0; overflow-x: auto; padding: 0.2rem 0` | Horizontally scrollable track of nodes + connectors |
| `.notif-node` | `display: flex; flex-direction: column; align-items: center; min-width: 80px; position: relative` | Single node — dot on top, state label below |
| `.notif-dot` | `width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; background: rgba(6,182,212,0.2); border: 2px solid #06b6d4; color: #06b6d4` | Cyan circle with icon inside |
| `.notif-dot.active` | `background: rgba(34,197,94,0.25); border-color: #22c55e; color: #22c55e` | Green circle for active/completed notifications |
| `.notif-state` | `font-size: 0.5rem; color: #64748b; margin-top: 0.25rem; text-align: center; word-break: break-all; max-width: 80px` | State label below dot |
| `.notif-connector` | `flex: 1; min-width: 20px; height: 2px; background: rgba(6,182,212,0.3); margin-top: 13px` | Horizontal line between dots |
| `.notif-connector.active` | `background: #22c55e` | Green connector line |

### 2.6 Trace Steps (Cards)

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.trace-step` | `opacity: 0; transform: translateX(20px); animation: slideIn 0.35s ease-out forwards; margin-bottom: 0.5rem` | Slide-in animation wrapper for each step |
| `@keyframes slideIn` | `to { opacity: 1; transform: translateX(0) }` | Slides in from right |
| `.step-card` | `border-radius: 10px; border: 1px solid; overflow: hidden; transition: all 0.2s; cursor: pointer` | Card container — border color set by theme class |
| `.step-card:hover` | `box-shadow: 0 0 20px rgba(0,0,0,0.3)` | Dark glow on hover |
| `.step-header` | `display: flex; align-items: center; gap: 0.5rem; padding: 0.55rem 0.8rem; cursor: pointer; user-select: none` | Clickable header row — icon, title, elapsed |
| `.step-icon` | `font-size: 1.1rem; flex-shrink: 0` | Emoji icon for step |
| `.step-title` | `font-size: 0.75rem; font-weight: 600; flex: 1` | Step description text |
| `.step-elapsed` | `font-size: 0.6rem; opacity: 0.6; white-space: nowrap` | Millisecond duration |
| `.step-body` | `padding: 0.6rem 0.8rem 0.8rem; font-size: 0.65rem; line-height: 1.55; border-top: 1px solid rgba(255,255,255,0.05)` | Expandable detail section |
| `.step-body.hidden` | `display: none` | Collapsed state (toggled by header click) |
| `.step-body .fl` | `color: #94a3b8; font-weight: 600` | Default field label color |
| `.step-body .fv` | `color: #cbd5e1` | Default field value color |
| `.step-body .fl-goal` | `color: #67e8f9` | "Goal:" label — light cyan |
| `.step-body .fl-in` | `color: #a78bfa` | "Input:" label — violet |
| `.step-body .fl-exp` | `color: #fbbf24` | "Expected:" label — amber |
| `.step-body .fl-act` | `color: #4ade80` | "Actual:" label — green |
| `.step-body .fl-out` | `color: #f472b6` | "Output:" label — pink |

### 2.7 Card Color Themes

Each `.step-card` carries exactly one theme class (`.card-green`, `.card-amber`, `.card-red`, `.card-blue`, `.card-violet`, `.card-cyan`). The theme class controls border, background, header background, title color, and body text color.

| Class | Border | Card BG | Header BG | Title Color | Body Color |
|-------|--------|---------|-----------|-------------|------------|
| `.card-green` | `rgba(34,197,94,0.3)` | `rgba(34,197,94,0.06)` | `rgba(34,197,94,0.1)` | `#4ade80` | `#bbf7d0` |
| `.card-amber` | `rgba(251,191,36,0.3)` | `rgba(251,191,36,0.06)` | `rgba(251,191,36,0.1)` | `#fbbf24` | `#fde68a` |
| `.card-red` | `rgba(239,68,68,0.3)` | `rgba(239,68,68,0.06)` | `rgba(239,68,68,0.1)` | `#f87171` | `#fecaca` |
| `.card-blue` | `rgba(59,130,246,0.3)` | `rgba(59,130,246,0.06)` | `rgba(59,130,246,0.1)` | `#60a5fa` | `#bfdbfe` |
| `.card-violet` | `rgba(167,139,250,0.3)` | `rgba(167,139,250,0.06)` | `rgba(167,139,250,0.1)` | `#a78bfa` | `#ddd6fe` |
| `.card-cyan` | `rgba(34,211,238,0.3)` | `rgba(34,211,238,0.06)` | `rgba(34,211,238,0.1)` | `#22d3ee` | `#a5f3fc` |

### 2.8 Running Animation

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.card-running` | `animation: pulseGlow 2s ease-in-out infinite` | Added by `pollUntilDone` to steps whose `status === 'running'` |
| `@keyframes pulseGlow` | `0%/100% { box-shadow: 0 0 8px rgba(34,211,238,0.15) } 50% { box-shadow: 0 0 20px rgba(34,211,238,0.35) }` | Cyan glow pulses around running step cards |

### 2.9 Pattern Analysis Section

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.pattern-analysis` | `margin-top: 1rem; padding: 1rem 1.25rem; border-radius: 12px; border: 1px solid rgba(167,139,250,0.25); background: rgba(167,139,250,0.04); opacity: 0; animation: slideIn 0.5s 0.1s ease-out forwards` | Violet-tinged section with staggered slide-in |
| `.pattern-analysis h3` | `font-size: 0.78rem; color: #a78bfa; margin-bottom: 0.75rem` | Violet heading |
| `.pa-grid` | `display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem` | Two-column grid |
| `.pa-card` | `background: rgba(15,23,42,0.6); border: 1px solid #1e293b; border-radius: 8px; padding: 0.7rem` | Grid cell card |
| `.pa-card-title` | `font-size: 0.6rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.5rem` | ALL-CAPS muted label |
| `.pa-card-value` | `font-size: 0.72rem; font-weight: 700` | Large value text (confidence %) |
| `.pa-card-value.hi` | `color: #4ade80` | High confidence (≥70%) |
| `.pa-card-value.mi` | `color: #fbbf24` | Medium confidence (40-69%) |
| `.pa-card-value.lo` | `color: #f87171` | Low confidence (<40%) |
| `.pa-bar-wrap` | `display: flex; align-items: center; gap: 0.5rem; margin-top: 0.35rem` | Bar + tag row |
| `.pa-bar` | `flex: 1; height: 8px; background: #1e293b; border-radius: 4px; overflow: hidden` | Progress bar track |
| `.pa-bar-fill` | `height: 100%; border-radius: 4px; transition: width 0.5s ease` | Filled portion — width set via inline `style="width:XX%"`. No explicit background color in CSS; colored by inline `class="mid"` etc. (though the CSS doesn't define `.pa-bar-fill.high/mid/low` — color is controlled by the parent `.pa-card-value` semantic class) |
| `.pa-tag` | `display: inline-block; padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.55rem; font-weight: 600` | Small tag pill |
| `.pa-tag.llm` | `background: rgba(59,130,246,0.15); color: #60a5fa` | Blue "LLM Learned" tag |
| `.pa-tag.taught` | `background: rgba(34,197,94,0.15); color: #4ade80` | Green "Taught" tag |
| `.pa-tag.cached` | `background: rgba(167,139,250,0.15); color: #a78bfa` | Violet "Cache Hit" tag |
| `.pa-suggestion` | `margin-top: 0.8rem; padding: 0.6rem 0.8rem; border-radius: 8px; border: 1px solid rgba(251,191,36,0.2); background: rgba(251,191,36,0.05); font-size: 0.6rem; color: #fcd34d` | Amber suggestion box with 💡 icon |
| `.pa-suggestion .sug-icon` | `margin-right: 0.4rem` | Spacing after 💡 icon |
| `.verification-list` | `margin-top: 0.6rem` | Verification items container |
| `.verification-list .v-item` | `display: flex; align-items: flex-start; gap: 0.4rem; padding: 0.2rem 0; font-size: 0.62rem` | Single verification row (icon + description) |
| `.v-item .v-icon` | `font-size: 0.7rem; flex-shrink: 0; margin-top: 1px` | Verification icon |

### 2.10 Final Summary

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.final-summary` | `margin-top: 1rem; padding: 1rem 1.25rem; border-radius: 12px; border: 2px solid rgba(34,197,94,0.4); background: rgba(34,197,94,0.08); opacity: 0; animation: slideIn 0.5s 0.2s ease-out forwards` | Green-tinged summary with staggered slide-in |
| `.final-summary h3` | `font-size: 0.78rem; color: #4ade80; margin-bottom: 0.5rem` | Green heading: "✅ Orchestration Complete — XXms" |
| `.kv` | `display: flex; gap: 2rem; flex-wrap: wrap` | Key-value row |
| `.kv-item` | `font-size: 0.65rem` | One KV pair |
| `.kv-label` | `color: #64748b` | Muted key |
| `.kv-value` | `color: #e2e8f0; font-weight: 600` | Bright value |

### 2.11 Network Elements

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.network-elements` | `margin-top: 1rem; padding: 1rem 1.25rem; border-radius: 12px; border: 1px solid rgba(59,130,246,0.3); background: rgba(59,130,246,0.05); opacity: 0; animation: slideIn 0.5s 0.3s ease-out forwards` | Blue-tinged section with staggered slide-in |
| `.network-elements h3` | `font-size: 0.78rem; color: #60a5fa; margin-bottom: 0.75rem` | Blue heading |
| `.ne-grid` | `display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 0.6rem` | Responsive auto-fill grid |
| `.ne-card` | `background: rgba(15,23,42,0.7); border: 1px solid #1e293b; border-radius: 8px; padding: 0.7rem; transition: border-color 0.2s; cursor: pointer` | NE card — hover border highlights |
| `.ne-card:hover` | `border-color: rgba(59,130,246,0.4)` | Blue border on hover |
| `.ne-card-header` | `display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.5rem; padding-bottom: 0.4rem; border-bottom: 1px solid #1e293b` | Header row with icon, name, workflow |
| `.ne-card-icon` | `font-size: 1rem` | Emoji icon for NE |
| `.ne-card-name` | `font-size: 0.7rem; font-weight: 600; color: #e2e8f0` | NE name |
| `.ne-card-wf` | `font-size: 0.55rem; color: #64748b; margin-left: auto` | Workflow label, right-aligned |
| `.ne-attr` | `display: flex; justify-content: space-between; padding: 0.18rem 0; font-size: 0.6rem` | Attribute row (key left, value right) |
| `.ne-attr-key` | `color: #64748b` | Muted attribute key |
| `.ne-attr-val` | `color: #94a3b8; font-weight: 500; max-width: 55%; text-align: right; overflow: hidden; text-overflow: ellipsis` | Attribute value, right-aligned, truncates |
| `.ne-attr-val.status-ok` | `color: #4ade80` | Green for status values matching active/OK patterns |

### 2.12 Empty State & Zoom

| Class | Styles / Purpose | Visual Behavior |
|-------|------------------|-----------------|
| `.empty-state` | `text-align: center; padding: 4rem 2rem; color: #475569` | Centered placeholder |
| `.empty-state .icon` | `font-size: 3rem; margin-bottom: 0.75rem` | Large ⚙️ icon |
| `.empty-state p` | `font-size: 0.75rem; line-height: 1.6` | Instructional text |
| `.zoom-backdrop` | `position: fixed; inset: 0; z-index: 1000; background: rgba(2,6,23,0.75); backdrop-filter: blur(8px); display: none; align-items: center; justify-content: center; animation: fadeIn 0.2s ease-out` | Full-screen blurred overlay — hidden by default |
| `.zoom-backdrop.active` | `display: flex` | Overlay shown — flex-centers the container |
| `@keyframes fadeIn` | `from { opacity: 0 } to { opacity: 1 }` | Fade-in for backdrop |
| `.zoom-container` | `width: 96vw; max-width: 1200px; max-height: 94vh; overflow-y: auto; border-radius: 12px; animation: zoomIn 0.25s ease-out; box-shadow: 0 0 60px rgba(0,0,0,0.6)` | Cloned card container — scrolls if content tall |
| `@keyframes zoomIn` | `from { transform: scale(0.92); opacity: 0 } to { transform: scale(1); opacity: 1 }` | Scale-up entrance |
| `.zoom-container .step-card` | `padding: 2rem 2.5rem; min-width: 600px; font-size: 1.05rem; border-width: 2px` | Enlarged step card in zoom |
| `.zoom-container .ne-card` | `padding: 1.5rem 1.75rem; min-width: 400px` | Enlarged NE card in zoom |
| `.zoom-container .step-header` | `padding: 0.8rem 1rem` | Larger header |
| `.zoom-container .step-icon` | `font-size: 1.6rem` | Larger icon |
| `.zoom-container .step-title` | `font-size: 1.2rem; font-weight: 700` | Larger bold title |
| `.zoom-container .step-elapsed` | `font-size: 0.85rem` | Larger elapsed |
| `.zoom-container .step-body` | `font-size: 0.95rem; line-height: 1.8; padding: 1rem 1rem 1rem 2.5rem` | Enlarged detail body |
| `.zoom-container .ne-card-name` | `font-size: 1.05rem` | Larger NE name |
| `.zoom-container .ne-card-wf` | `font-size: 0.75rem` | Larger workflow label |
| `.zoom-container .ne-attr` | `font-size: 0.85rem; padding: 0.35rem 0` | Larger attribute row |
| `.zoom-container .ne-grid` | `grid-template-columns: repeat(auto-fill, minmax(380px, 1fr))` | Wider grid cells |
| `.zoom-container .ne-card-icon` | `font-size: 1.4rem` | Larger NE icon |
| `.zoom-close-hint` | `position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%); font-size: 0.75rem; color: #64748b; pointer-events: none; animation: fadeIn 0.3s 1s ease-out forwards; opacity: 0` | Bottom-center hint text — appears after zoom is open |
| `::-webkit-scrollbar` | `width: 6px` | Thin scrollbar |
| `::-webkit-scrollbar-track` | `background: transparent` | Invisible track |
| `::-webkit-scrollbar-thumb` | `background: #1e293b; border-radius: 3px` | Dark thumb |

---

## 3. JavaScript Function Reference

### 3.1 `loadSamples()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 341–352 |
| **Signature** | `async function loadSamples()` |
| **Purpose** | Fetch available sample requests from `/api/samples` and render them as clickable `.sample-chip` buttons in the `#samples` container. |
| **Called by** | Invoked directly at line 693 (page load) |
| **Calls** | `fetch('/api/samples')`, DOM manipulation (`createElement`, `appendChild`) |
| **Flow** | `GET /api/samples` → `resp.json()` → for each sample, create `button.sample-chip`, set `textContent` to `s.label`, set `onclick` to populate `#prompt` textarea with `s.text` |

### 3.2 `clearAll()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 354–363 (original), overridden at lines 723–724 |
| **Signature** | `function clearAll()` |
| **Purpose** | Reset the entire UI to initial state: clear prompt, hide trace content, show empty state, clear all section innerHTML. The override also closes any open zoom. |
| **Called by** | `onclick="clearAll()"` on Clear button (line 307) |
| **Calls** | `closeZoom()` (via override), DOM manipulation |
| **Flow** | clear prompt.value → hide `#trace-content` → show `#empty-state` → clear `#trace-steps`, `#notification-timeline`, `#final-summary`, `#network-elements`, `#pattern-analysis` innerHTML → close zoom (override) |

### 3.3 `submitRequest()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 365–455 |
| **Signature** | `async function submitRequest()` |
| **Purpose** | Primary orchestrator: reads the prompt, POSTs to `/api/process`, handles all response states (processing/completed/blocked/error/tunnel-error/timeout), and delegates to `pollUntilDone` or `showFinalOutput`. |
| **Called by** | `onclick="submitRequest()"` on Execute button (line 306) |
| **Calls** | `fetch('/api/process', POST)`, `escapeHtml()`, `renderStep()`, `pollUntilDone()`, `showFinalOutput()` |
| **Flow** | 1. Validate prompt (return if empty) → 2. Disable button → 3. Hide empty state, show trace content → 4. Set status "PROCESSING" (running) → 5. Show loading step with animated dots (1s interval, cycles 0-3 dots) → 6. `POST /api/process` with 130s timeout via AbortController → 7. Parse response JSON: if `status === 'processing'` → render initial trace + start `pollUntilDone`; if `status === 'completed'` → render all steps + `showFinalOutput` (with staggered delay); if `status === 'blocked'` → render steps without final output → 8. Re-enable button in `finally` block |

### 3.4 `pollUntilDone()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 457–500 |
| **Signature** | `async function pollUntilDone(orderId, statusEl, btn, startedAt)` |
| **Parameters** | `orderId` (string) — the trace/order ID; `statusEl` — the `.trace-status` DOM element; `btn` — the submit button element; `startedAt` — ISO timestamp string for elapsed time display |
| **Purpose** | Poll `GET /api/process/{orderId}` every 2 seconds for up to 120 attempts (4 minutes). Re-renders trace steps on each poll, adds `card-running` animation to in-progress steps, and transitions to `showFinalOutput` on completion or to blocked state on failure. |
| **Called by** | `submitRequest()` (line 425) |
| **Calls** | `fetch('/api/process/{orderId}')`, `renderStep()`, `showFinalOutput()` |
| **Flow** | 1. Set "PROCESSING" status → 2. Start elapsed timer (1s interval updating `#trace-id`) → 3. Loop 120×: sleep 2s, `GET /api/process/{id}` → 4. Clear and re-render all steps → 5. For steps with `status === 'running'`, add `card-running` class → 6. If `status === 'completed'`: clear timer, set "COMPLETED", call `showFinalOutput`, re-enable button, return → 7. If `status === 'blocked'`: clear timer, set "BLOCKED", re-enable button, return → 8. On fetch error: silently retry → 9. After 120 attempts: set "TIMEOUT", re-enable button |

### 3.5 `formatDetail()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 503–516 |
| **Signature** | `function formatDetail(text)` |
| **Parameters** | `text` (string) — raw detail text from a step |
| **Returns** | HTML string with labeled spans and `<br>` line breaks |
| **Purpose** | Transform step detail text into rich HTML: converts newlines to `<br>`, wraps field labels (`Goal:`, `Input:`, `Expected:`, `Actual:`, `Output:`) in `<span class="fl fl-{type}">` for color-coding, and HTML-escapes everything else. |
| **Called by** | `renderStep()` (line 521) |
| **Calls** | `escapeHtml()` |

### 3.6 `renderStep()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 518–523 |
| **Signature** | `function renderStep(step, i)` |
| **Parameters** | `step` (object) — `{ color, icon, title, ms/elapsed_ms, detail }`; `i` (int) — index for staggered animation |
| **Purpose** | Create a `.trace-step` wrapper div with staggered `animationDelay` containing a `.step-card` with the appropriate color theme class, header, and body. |
| **Called by** | `submitRequest()` (line 424/438), `pollUntilDone()` (line 473) |
| **Calls** | `escapeHtml()`, `formatDetail()` |

### 3.7 `showFinalOutput()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 526–539 |
| **Signature** | `function showFinalOutput(data)` |
| **Parameters** | `data` (object) — full API response containing `final_state`, `total_ms`, etc. |
| **Purpose** | Orchestrate the rendering of all post-trace output sections: notification timeline, pattern analysis, final summary, and network elements. Introduces a 200ms delay for summary/NE rendering and scrolls the notification timeline into view. |
| **Called by** | `submitRequest()` (line 440), `pollUntilDone()` (line 484) |
| **Calls** | `renderNotificationTimeline()`, `buildPatternAnalysis()`, `buildSummaryHTML()`, `renderNetworkElements()`, `scrollIntoView()` |
| **Flow** | 1. Immediately: render notification timeline + pattern analysis → 2. After 200ms: render final summary + network elements → 3. Scroll notification timeline into view (smooth, start block) |

### 3.8 `renderNotificationTimeline()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 541–569 |
| **Signature** | `function renderNotificationTimeline(fs)` |
| **Parameters** | `fs` (object) — `final_state` containing `fs.notifications[]` |
| **Purpose** | Build a horizontal timeline of TMF lifecycle notifications. Each notification shows a dot (✅ for last, ● for earlier) and the milestone/state name extracted from the TMF641 event structure. |
| **Called by** | `showFinalOutput()` (line 529) |
| **Calls** | `escapeHtml()`, DOM `innerHTML` assignment |
| **Flow** | 1. Extract state from `event.serviceOrder.milestone[0].name` or `event.serviceOrder.state` → 2. Build `.notif-track` with alternating `.notif-node` + `.notif-connector` → 3. Assign to `#notification-timeline` innerHTML |

### 3.9 `buildPatternAnalysis()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 571–623 |
| **Signature** | `function buildPatternAnalysis(fs)` |
| **Parameters** | `fs` (object) — `final_state` with `patternMatch`, `patternConfidence`, `llmUsed`, `patternId`, etc. |
| **Purpose** | Build the complete pattern analysis block: confidence bar, pattern match details, five verification items, and a contextual suggestion. |
| **Called by** | `showFinalOutput()` (line 530) |
| **Calls** | DOM `innerHTML` assignment |
| **Flow** | 1. Compute confidence % → 2. Determine bar class (high/mid/low) → 3. Determine tag (llm/cached) → 4. Generate suggestion text based on HIT/MISS + confidence band → 5. Build verification list → 6. Assemble complete `.pattern-analysis` HTML |

### 3.10 `buildSummaryHTML()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 625–652 |
| **Signature** | `function buildSummaryHTML(total_ms, fs)` |
| **Parameters** | `total_ms` (number) — total orchestration time; `fs` (object) — `final_state` |
| **Returns** | HTML string for `.final-summary` |
| **Purpose** | Build the final summary section with service ID, state, workflow count, resource count, subscriber ID, and diff information (updated vs new provisioning). |
| **Called by** | `showFinalOutput()` (line 532) |
| **Calls** | `escapeHtml()` |

### 3.11 `renderNetworkElements()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 654–687 |
| **Signature** | `function renderNetworkElements(elements, diff)` |
| **Parameters** | `elements` (array) — NE objects with `name`, `workflow`, `attributes`; `diff` (object) — subscriber diff containing `networkElementDiffs` |
| **Purpose** | Render a grid of NE cards with icon, name, workflow, attributes, and visual diff indicators (amber left border, "⚡ MODIFIED" badge, strikethrough old values). |
| **Called by** | `showFinalOutput()` (line 533) |
| **Calls** | `escapeHtml()` |
| **Flow** | 1. Map NE names to icons → 2. For each NE: build card header (icon + name + optional modified badge + workflow) → 3. For each attribute: check for diff changes → 4. Apply `status-ok` class if value matches active patterns → 5. Render changed values with amber new value + red strikethrough old value |

### 3.12 `escapeHtml()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 689–691 |
| **Signature** | `function escapeHtml(str)` |
| **Parameters** | `str` (string) |
| **Returns** | HTML-escaped string |
| **Purpose** | Replace `&`, `<`, `>`, `"` with HTML entities to prevent XSS. |
| **Called by** | `formatDetail()`, `renderStep()`, `submitRequest()`, `buildSummaryHTML()`, `renderNetworkElements()`, `renderNotificationTimeline()` |

### 3.13 `openZoom()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 696–708 |
| **Signature** | `function openZoom(el)` |
| **Parameters** | `el` (HTMLElement) — the `.step-card` or `.ne-card` to clone and display |
| **Purpose** | Clone the clicked card, remove `hidden` from any `.step-body`, place the clone in the zoom container, show the backdrop, hide body scroll, and show the close hint. |
| **Called by** | Click event listener on `#trace-panel` (line 717–722) |
| **Calls** | `cloneNode()`, `classList.add()`, DOM manipulation |

### 3.14 `closeZoom()`
| Property | Detail |
|----------|--------|
| **Location** | Lines 709–715 |
| **Signature** | `function closeZoom(e)` |
| **Parameters** | `e` (Event) — must have the backdrop as target, or be simulated with `{target: backdropEl}` |
| **Purpose** | Hide the zoom backdrop, clear the container, hide the close hint, restore body scroll. |
| **Called by** | Click on `.zoom-backdrop` (line 335), Escape key listener (line 716), `clearAll()` override (line 724) |
| **Calls** | DOM manipulation |

### 3.15 Event Listeners (Anonymous)

| Location | Event | Handler Purpose |
|----------|-------|-----------------|
| Line 693 | (invocation) | Calls `loadSamples()` on page load |
| Line 716 | `keydown` on `document` | If Escape key: call `closeZoom({target: backdrop})` |
| Lines 717–722 | `click` on `#trace-panel` | Delegated click: if target is `.step-card` or `.ne-card` BUT NOT inside `.step-header`, call `openZoom(card)`. This is the **anti-scroll/anti-toggle guard** — header clicks toggle body visibility, not zoom. |
| Lines 723–724 | (definition) | Override `clearAll` to also call `closeZoom()` first, then original `clearAll` |

---

## 4. Data Flow

### 4.1 Complete Pipeline

```
User enters prompt → clicks "Execute"
          │
          ▼
  submitRequest() — POST /api/process { prompt }
          │
          ├─(JSON parse fails)─► "Tunnel Error" (red card, BLOCKED status)
          │
          ├─(resp.status === "processing")
          │     │
          │     ├─ render initial trace steps
          │     └─ pollUntilDone(orderId) ───────────────┐
          │           │                                    │
          │           ▼ (every 2s, up to 120×)             │
          │     GET /api/process/{orderId}                 │
          │           │                                    │
          │           ├─ Clear #trace-steps                │
          │           ├─ data.trace.forEach → renderStep() │
          │           ├─ Add .card-running to running steps│
          │           │                                    │
          │           ├─ status==="completed" ─────────────┤
          │           ├─ status==="blocked" → stop, BLOCKED│
          │           └─ fetch error → retry              │
          │                                                │
          ├─(resp.status === "completed")                  │
          │                                                │
          └────────────────────────────────────────────────┘
                              │
                              ▼
                     showFinalOutput(data)
                              │
               ┌──────────────┼──────────────────┐
               │              │                   │
          (immediate)    (after 200ms)      (after 200ms)
               │              │                   │
               ▼              ▼                   ▼
   renderNotificationTimeline  buildPatternAnalysis  buildSummaryHTML + renderNetworkElements
```
### 4.2 API Call Details

| Operation | Method | Endpoint | Input | Output |
|-----------|--------|----------|-------|--------|
| Load samples | `GET` | `/api/samples` | — | `{ samples: [{ label, text }] }` |
| Submit request | `POST` | `/api/process` | `{ prompt: string }` | `{ order_id, status, trace[], final_state?, total_ms? }` |
| Poll status | `GET` | `/api/process/{order_id}` | — | `{ status, trace[], final_state? }` |

### 4.3 DOM Rendering Sequence

1. **submitRequest** → hides `#empty-state`, shows `#trace-content`, sets `#trace-status` to "PROCESSING"
2. **Loading step** rendered as `.trace-step` with animated dots in `.step-title`
3. **First trace** rendered via `data.trace.forEach(renderStep)` — each step gets staggered `animationDelay`
4. **Poll loop** clears `#trace-steps` innerHTML and re-renders all steps on every poll
5. **On completion**: `showFinalOutput` called synchronously (or after stagger delay if initial request completed immediately)
6. **showFinalOutput** renders into four sections:
   - `#notification-timeline` — immediate
   - `#pattern-analysis` — immediate
   - `#final-summary` — after 200ms delay
   - `#network-elements` — after 200ms delay
7. After summary + NEs render, `#notification-timeline` is scrolled into view (smooth, start block)

### 4.4 Polling Loop Details

- **Interval:** 2 seconds between attempts (via `setTimeout` promise)
- **Max attempts:** 120 (4 minutes total)
- **Elapsed timer:** 1-second interval updating `#trace-id` text from `startedAt` timestamp
- **Re-rendering:** Entire `#trace-steps` is cleared and rebuilt on every poll
- **Running animation:** Steps with `status === 'running'` get `.card-running` class (pulsing glow)
- **Error handling:** Fetch failures in the poll loop are silently caught and retried
- **Stopping conditions:** `status === 'completed'` → show final output; `status === 'blocked'` → stop; 120 attempts → "TIMEOUT"

---

## 5. Color / Semantic Mapping Table

| Semantic Meaning | Color Value | CSS Context | Applied To |
|------------------|-------------|-------------|------------|
| **Success / Complete / OK** | `#22c55e` green-500 | `.trace-status.completed` | Trace status pill |
| | `#4ade80` green-400 | `.card-green .step-title` | Step title text |
| | `#4ade80` green-400 | `.pa-card-value.hi` | High confidence % |
| | `#4ade80` green-400 | `.ne-attr-val.status-ok` | OK status attribute |
| | `#bbf7d0` green-200 | `.card-green .step-body` | Step body text |
| | `rgba(34,197,94,0.3)` | `.card-green` border | Card border |
| | `rgba(34,197,94,0.06)` | `.card-green` background | Card background |
| | `rgba(34,197,94,0.4)` | `.final-summary` border (2px) | Summary border |
| | `#22c55e` green-500 | `.notif-dot.active` | Active notification dot |
| | `#22c55e` green-500 | `.notif-connector.active` | Active connector line |
| **Warning / Running / Amber** | `#fbbf24` amber-400 | `.trace-status.running` | Processing pill |
| | `#fbbf24` amber-400 | `.card-amber .step-title` | Step title text |
| | `#fbbf24` amber-400 | `.pa-card-value.mi` | Medium confidence % |
| | `#fde68a` amber-200 | `.card-amber .step-body` | Step body text |
| | `rgba(251,191,36,0.3)` | `.card-amber` border | Card border |
| | `#fcd34d` amber-300 | `.pa-suggestion` | Suggestion text |
| | `#fbbf24` amber-400 | NE diff highlights | Modified values, badges, left border |
| **Error / Blocked / Red** | `#ef4444` red-500 | `.trace-status.blocked` | Blocked/error pill |
| | `#f87171` red-400 | `.card-red .step-title` | Step title text |
| | `#f87171` red-400 | `.pa-card-value.lo` | Low confidence % |
| | `#fecaca` red-200 | `.card-red .step-body` | Step body text |
| | `rgba(239,68,68,0.3)` | `.card-red` border | Card border |
| | `#f87171` red-400 | Strikethrough old values | `text-decoration: line-through; opacity: 0.65` |
| **Info / Processing / Blue** | `#60a5fa` blue-400 | `.card-blue .step-title` | Step title text |
| | `#60a5fa` blue-400 | `.network-elements h3` | Section heading |
| | `#bfdbfe` blue-200 | `.card-blue .step-body` | Step body text |
| | `rgba(59,130,246,0.3)` | `.card-blue` border | Card border |
| | `rgba(59,130,246,0.05)` | `.network-elements` background | NE section BG |
| | `rgba(59,130,246,0.15)` | `.pa-tag.llm` | "LLM Learned" tag |
| **Intelligence / Pattern / Violet** | `#a78bfa` violet-400 | `.card-violet .step-title` | Step title text |
| | `#a78bfa` violet-400 | `.pattern-analysis h3` | Section heading |
| | `#ddd6fe` violet-200 | `.card-violet .step-body` | Step body text |
| | `rgba(167,139,250,0.3)` | `.card-violet` border | Card border |
| | `rgba(167,139,250,0.25)` | `.pattern-analysis` border | Pattern section border |
| | `rgba(167,139,250,0.15)` | `.pa-tag.cached` | "Cache Hit" tag |
| **Highlight / Primary / Cyan** | `#22d3ee` cyan-400 | `.card-cyan .step-title` | Step title text |
| | `#22d3ee` cyan-400 | `.header .badge` | PoC badge text |
| | `#22d3ee` cyan-400 | `.pulse` dot | Animated indicator |
| | `#22d3ee` cyan-400 | `textarea:focus` border | Input focus ring |
| | `#22d3ee` cyan-400 | `.btn-primary` bg | Execute button |
| | `#a5f3fc` cyan-200 | `.card-cyan .step-body` | Step body text |
| | `rgba(34,211,238,0.3)` | `.card-cyan` border | Card border |
| | `rgba(34,211,238,0.15)` | `textarea:focus` box-shadow | Focus glow |
| | `#06b6d4` cyan-500 | `.notif-timeline h3` | Notifications heading |
| | `#06b6d4` cyan-500 | `.notif-dot` | Notification dot |
| **Pink (Output label)** | `#f472b6` pink-400 | `.step-body .fl-out` | "Output:" field label |
| **Light Cyan (Goal label)** | `#67e8f9` cyan-300 | `.step-body .fl-goal` | "Goal:" field label |
| **Muted / Disabled** | `#64748b` slate-500 | `.kv-label`, `.ne-attr-key`, `.pa-card-title` | Muted labels |
| | `#475569` slate-600 | `.trace-id`, `.empty-state` | Trace ID, placeholder |
| | `#94a3b8` slate-400 | `.left-section label`, `.sample-chip` | UI labels |
| **Dark Backgrounds** | `#020617` slate-950 | `body` | Root background |
| | `#0f172a` slate-900 | `textarea` | Input background |
| | `#1e293b` slate-800 | borders, `.pa-bar` | Border lines, bar track |
| | `#334155` slate-700 | `textarea` border, `.btn-secondary` border | Input border |

---

## 6. Error / Tunnel Handling

### 6.1 Error Scenarios and UI Responses

| Scenario | Detection | Status Pill | UI Response |
|----------|-----------|-------------|-------------|
| **JSON Parse Failure** | `JSON.parse()` throws (line 416) | `TUNNEL ERROR` (`.blocked`) | Red card with "❌ Tunnel error" + raw response text (first 200 chars, HTML-escaped) |
| **Request Timeout** | `AbortError` after 130s (line 444–450) | `TIMEOUT` (`.blocked`) | Red card: "⏱ Request timed out after 130 seconds." + tunnel hint |
| **Connection/Fetch Error** | `catch(err)` not AbortError (line 448–450) | `ERROR` (`.blocked`) | Red card: "❌ Connection error: {escaped message}" |
| **Blocked Status (initial)** | `data.status === 'blocked'` (line 431) | `BLOCKED` (`.blocked`) | Trace steps rendered but no final output shown |
| **Blocked Status (poll)** | `data.status === 'blocked'` (line 488) | `BLOCKED` (`.blocked`) | Poll terminates, no final output, button re-enabled |
| **Poll Exhaustion** | 120 attempts without completion (line 498) | `TIMEOUT` (`.blocked`) | Stop polling, button re-enabled |
| **Generic Error Status** | `data.status` unknown (line 433) | `ERROR` (`.blocked`) | Trace steps rendered |

### 6.2 Resilience Mechanisms

- **AbortController** with 130-second timeout on the initial POST
- **Silent retry** on poll fetch errors (line 495: `catch(e) { /* retry */ }`)
- **`finally` block** always re-enables the Execute button (line 452–454)
- **Loading interval cleanup**: `clearInterval(loadingInterval)` is called on both success (line 410) and catch (line 443)
- **Timeout cleanup**: `clearTimeout(timeoutId)` on success (line 409)
- **HTML escaping** via `escapeHtml()` prevents XSS in error messages that display raw response text

---

## 7. Anti-Scroll Logic

### 7.1 Problem

When a user clicks a `.step-card`, two distinct actions compete:
1. **Toggle body**: The `.step-header` has an inline `onclick` that toggles `.step-body.hidden`
2. **Zoom**: The `.step-card` or `.ne-card` click should trigger `openZoom()`

### 7.2 Implementation (Lines 717–722)

```javascript
document.getElementById('trace-panel').addEventListener('click', (e) => {
  const card = e.target.closest('.step-card') || e.target.closest('.ne-card');
  if (!card) return;                          // (1) not a card click → ignore
  if (e.target.closest('.step-header')) return;  // (2) header click → toggle body only, NO zoom
  openZoom(card);                             // (3) body click → zoom the card
});
```

### 7.3 How It Works

The guard at line 720 — `e.target.closest('.step-header')` — checks whether the click target is inside the `.step-header` element. If so, the function returns early, allowing the inline `onclick` handler on `.step-header` to toggle the body visibility without triggering zoom.

This is NOT a scroll-prevention mechanism per se; it's a **click-target disambiguation guard** that prevents zoom from firing when the user intends only to expand/collapse a trace step body. The term "anti-scroll" in the task description refers to preventing unwanted zoom/layout shifts when toggling step bodies.

### 7.4 Click Target Resolution

| Click Location | Result |
|----------------|--------|
| `.step-header` (icon, title, elapsed) | Toggle `.step-body.hidden` — NO zoom |
| `.step-body` (detail text) | `openZoom(card)` — no toggle |
| `.ne-card` anywhere | `openZoom(card)` — NE cards have no toggle |

**Note:** `.ne-card` headers are NOT clickable for toggling; only `.step-card .step-header` has the inline `onclick` toggle handler. NE cards are zoom-only.

---

## 8. Zoom Interaction Flow

### 8.1 Trigger

Zoom is triggered by clicking on any `.step-card` (outside its header) or any `.ne-card` within the `#trace-panel`.

### 8.2 Entry Animation Sequence

```
1. User clicks .step-card or .ne-card
2. Event delegated to #trace-panel click listener
3. openZoom(cardElement) called
   ├─ cardElement.cloneNode(true)        ← deep clone of card
   ├─ Remove .hidden from .step-body     ← ensure body is visible in zoom
   ├─ Clear #zoom-container, append clone
   ├─ #zoom-backdrop.classList.add('active')   ← display: flex (was hidden)
   │   → @keyframes fadeIn (0.2s)              ←  backdrop fades in with blur
   ├─ #zoom-hint.style.opacity = '1'
   │   → @keyframes fadeIn (0.3s, 1s delay)    ←  hint text appears after 1s
   └─ document.body.style.overflow = 'hidden'  ←  prevent background scroll
       → .zoom-container scales up:
         @keyframes zoomIn (0.25s)
         from { scale(0.92), opacity: 0 }
         to   { scale(1),    opacity: 1 }
```

### 8.3 Zoomed Content Appearance

When a card is inside `.zoom-container`, CSS selectors override its text sizes and layout:

| Element | Normal | Zoomed |
|---------|--------|--------|
| `.step-card` | default padding, `min-width: auto` | `padding: 2rem 2.5rem; min-width: 600px; font-size: 1.05rem; border-width: 2px` |
| `.ne-card` | default padding | `padding: 1.5rem 1.75rem; min-width: 400px` |
| `.step-icon` | `1.1rem` | `1.6rem` |
| `.step-title` | `0.75rem, weight 600` | `1.2rem, weight 700` |
| `.step-elapsed` | `0.6rem` | `0.85rem` |
| `.step-body` | `0.65rem, line-height 1.55` | `0.95rem, line-height 1.8, padding: 1rem 1rem 1rem 2.5rem` |
| `.ne-card-name` | `0.7rem` | `1.05rem` |
| `.ne-card-wf` | `0.55rem` | `0.75rem` |
| `.ne-attr` | `0.6rem` | `0.85rem, padding: 0.35rem 0` |
| `.ne-grid` | `minmax(260px, 1fr)` | `minmax(380px, 1fr)` |
| `.ne-card-icon` | `1rem` | `1.4rem` |

### 8.4 Exit Methods

| Method | Handler | Notes |
|--------|---------|-------|
| Click on backdrop | `onclick="closeZoom(event)"` on `.zoom-backdrop` | `e.target` must be the backdrop itself; `stopPropagation()` on `.zoom-container` prevents container clicks from bubbling |
| Press Escape key | `document.addEventListener('keydown', ...)` | Fires `closeZoom({target: backdrop})` — simulates backdrop click |
| Click "Clear" button | `clearAll()` override | Calls `closeZoom()` before original `clearAll()` |

### 8.5 Exit Animation Sequence

```
1. closeZoom() called
   ├─ #zoom-backdrop.classList.remove('active')   ← display: none (immediate, no exit animation)
   ├─ #zoom-container.innerHTML = ''              ←   clear cloned content
   ├─ #zoom-hint.style.opacity = '0'              ←   hide hint
   └─ document.body.style.overflow = ''           ←   restore body scrolling
```

**Note:** The zoom **exit has no CSS animation** — backdrop disappears immediately when `.active` is removed. Only the **entry** has animations (fadeIn for backdrop, zoomIn for container, delayed fadeIn for hint).

### 8.6 Interaction Rules

- Clicks on `.step-header` toggle the body but **never** trigger zoom (anti-scroll guard)
- Clicks on `.step-body` or `.ne-card` trigger zoom (the whole card is cloned)
- `.step-body` is forced visible (`.hidden` removed) during cloning — so the zoom always shows full details
- `event.stopPropagation()` on `#zoom-container` prevents backdrop click handler from firing when clicking inside the zoomed card
- Multiple cards cannot be zoomed simultaneously — zoom is exclusive
- Scrolling within the zoom container is enabled (`overflow-y: auto`) for tall content

---

## Appendix A: Edge Cases & Notes

1. **Empty notifications**: `renderNotificationTimeline` returns early with empty innerHTML if `fs.notifications` is empty or missing.
2. **Missing NE diff**: `renderNetworkElements` gracefully handles missing `diff` or `diff.networkElementDiffs` by defaulting to `{}`.
3. **Missing started_at**: `pollUntilDone` defaults `startTime` to `Date.now()` if `startedAt` is falsy.
4. **Sample chips**: Each chip's `onclick` directly sets `#prompt.value` — no validation or trimming.
5. **Loading dots animation**: During submission, dots cycle 0-3 appended to "Submitting — dispatching pipeline..." with 1-second interval. The interval uses `.repeat(dots)`.
6. **Poll re-render**: The entire `#trace-steps` innerHTML is cleared and rebuilt on every poll. This means any user-expanded step bodies collapse back to their default state on each poll cycle.
7. **Window resize**: The zoom container uses `vw`/`vh` units and `max-width`/`max-height` constraints, making it responsive to viewport changes.
8. **Font**: JetBrains Mono is loaded from Google Fonts with weights 400, 500, 600, 700.
9. **No cache meta tags**: `Cache-Control: no-cache, no-store, must-revalidate` and `Pragma: no-cache` are set to prevent browser caching of stale responses.
10. **Subscriber diff detection**: In `buildSummaryHTML`, the presence of `diff.hasPrevious` determines whether the subscriber is "UPDATED" (amber) or "First provisioning" (green).
