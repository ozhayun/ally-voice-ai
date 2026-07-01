---
name: Ally Voice AI Builder
colors:
  background: "#0a0a0a"
  surface: "#18181b"
  surface-elevated: "#09090b"
  border: "#27272a"
  border-subtle: "#3f3f46"
  accent-primary: "#4f46e5"
  accent-mid: "#6366f1"
  accent-light: "#818cf8"
  text-primary: "#f4f4f5"
  text-secondary: "#a1a1aa"
  text-muted: "#71717a"
  text-disabled: "#52525b"
  success: "#34d399"
  warning: "#facc15"
  danger: "#dc2626"
---

# Design System: Ally Voice AI Builder
**Project ID:** 2198012430480795953

## 1. Visual Theme & Atmosphere

Ally is a dark, focused tool — the UI disappears so the user can think. The background is a near-absolute black (#0a0a0a), not a softened dark gray, which gives every element that appears on top of it a sense of weight and purpose. Surfaces are layered in increments of zinc (zinc-900 for panels, zinc-950 for inset inputs), so depth is communicated through barely-perceptible tonal shifts rather than shadows or elevation.

The indigo accent (#4f46e5-#818cf8) is used sparingly and deliberately — only on interactive elements that deserve attention: the send button, active nav tabs, call-to-action buttons, typing indicators. Everything else recedes into the dark. The result is a high-focus interface that feels like a professional command center rather than a consumer product.

## 2. Color Palette & Roles

### Primary Foundation
- **Void Black** `#0a0a0a` — Page background, nav bar. The darkest layer.
- **Obsidian** `#09090b` — Inset inputs, elevated-dark surfaces (zinc-950).
- **Charcoal** `#18181b` — Card surfaces, chat bubbles, panel backgrounds (zinc-900).
- **Graphite** `#27272a` — Borders, dividers, separators (zinc-800).
- **Steel** `#3f3f46` — Hover borders, focus rings before accent (zinc-700).

### Accent & Interactive
- **Indigo Core** `#4f46e5` — Primary buttons, user chat bubbles, active nav underline, logo icon bg.
- **Indigo Mid** `#6366f1` — Hover state for primary buttons.
- **Indigo Glow** `#818cf8` — Typing indicator dots, subtle accents, icons at rest.
- **Indigo Ghost** `rgba(79,70,229,0.2)` — Empty state icon background ring.

### Typography & Text Hierarchy
- **Bright White** `#f4f4f5` — Primary text, headings, active labels (zinc-100).
- **Stone** `#a1a1aa` — Secondary text, descriptions (zinc-400).
- **Slate** `#71717a` — Muted labels, placeholder hints (zinc-500).
- **Fog** `#52525b` — Disabled text, placeholder text in inputs (zinc-600).

### Functional States
- **Emerald Live** `#34d399` — Active call pulse dot, positive sentiment (emerald-400).
- **Emerald Strong** `#10b981` — Live call indicator dot (emerald-500).
- **Amber Neutral** `#facc15` — Neutral sentiment label (yellow-400).
- **Red Danger** `#dc2626` — End call button, error states (red-600).
- **Red Soft** `#f87171` — Negative sentiment label (red-400).

## 3. Typography Rules

### Hierarchy & Weights
- **Font family**: system-ui, -apple-system, sans-serif (Geist where loaded). Antialiased rendering always on.
- **Labels / section headers**: 10-11px, `font-semibold`, `tracking-widest`, `uppercase` — used for role labels like "✦ Ally AI" and "LIVE".
- **Body / messages**: 14px (`text-sm`), `leading-relaxed`, normal weight. Chat messages, descriptions, input text.
- **Panel headings**: 14px, `font-semibold`, zinc-100.
- **Micro labels**: 9-10px, `uppercase`, `tracking-wider`, zinc-600 — used for metric sub-labels like "Duration".
- **Monospace**: used for call timer / numeric readouts (`font-mono`, zinc-200).
- **Brand wordmark**: 16px, `font-bold`, `tracking-tight`, zinc-100.

### Spacing Principles
- Base unit: 4px. Spacing uses Tailwind's 4px grid throughout.
- Panels: `px-4 py-3` for most internal sections. Nav: `px-6`.
- Generous letter-spacing on uppercase labels creates visual breathing room at small sizes.
- Line height on chat messages is relaxed (`leading-relaxed`) to aid readability in conversation flow.

## 4. Component Stylings

### Buttons
- **Primary (CTA)**: `bg-indigo-600 text-white rounded-lg px-4 py-2.5 text-sm font-semibold hover:bg-indigo-500 transition-colors`. Subtle indigo shadow on active call state (`shadow-lg shadow-indigo-600/20`).
- **Secondary / ghost**: `bg-zinc-800 text-zinc-300 rounded-lg hover:bg-zinc-700`. Same sizing, different surface.
- **Disabled**: `bg-zinc-800 text-zinc-500 cursor-not-allowed opacity-40`.
- **Danger**: `bg-red-600 hover:bg-red-500 text-white rounded-lg px-3 py-1.5 text-xs font-semibold`.
- Corner radius: `rounded-lg` (8px) consistently across all button types.
- No border on primary buttons. Transition: `transition-colors` only.

### Cards & Panels
- Corner radius: `rounded-xl` (12px) for cards, `rounded-2xl` (16px) for chat bubbles.
- Background: zinc-900 (`#18181b`). No drop shadow — depth from border only.
- Border: `border border-zinc-800` — hairline, graphite.
- Internal padding: `px-4 py-3` standard. Metrics / stat cells use `divide-x divide-zinc-800` for internal separation.
- Chat bubble asymmetry: user messages `rounded-tr-sm` (flattened top-right), AI messages `rounded-tl-sm` (flattened top-left) — a messaging convention that signals directionality.

### Navigation
- Horizontal tab bar. Height: `h-14` (56px). Sticky top, `z-10`.
- Active tab: `text-zinc-100 border-b-2 border-indigo-500 -mb-px`. Underline sits flush with the nav bottom border.
- Inactive tab: `text-zinc-500 border-transparent hover:text-zinc-300`. No background on hover.
- Logo: `w-7 h-7 rounded-lg bg-indigo-600` with white "A" lettermark.
- Right side: primary CTA button + avatar circle separated by `border-l border-zinc-800`.

### Inputs & Forms
- Surface: `bg-zinc-950 border border-zinc-700 rounded-lg`.
- Focus: `focus-within:border-indigo-500 transition-colors` — border shifts to indigo on focus, no glow ring.
- Text: `text-sm text-zinc-100 placeholder-zinc-600`.
- Textarea (chat input): `bg-transparent outline-none resize-none` inside a styled wrapper div — the wrapper provides the visible border and focus state.
- Icon prefix slots: left-aligned inside inputs with `px-3` prefix zone.

### Domain-Specific Components
- **Chat bubbles**: max-width 85%, `rounded-2xl`, asymmetric corner per sender. User = indigo-600 bg. AI = zinc-900 bg with zinc-800 border.
- **Typing indicator**: Three indigo-400 dots with staggered `animate-bounce` (`[animation-delay: 0ms / 150ms / 300ms]`).
- **Live call status bar**: `bg-zinc-950 border border-zinc-800 rounded-xl px-4 py-3` with pulsing emerald dot, uppercase tracking-widest "LIVE" label, mono duration counter, and red end-call button.
- **Metric cells**: 3-column grid, `divide-x divide-zinc-800 border-t border-zinc-800`. Each cell: 9px uppercase label in zinc-600, value in zinc-100 or sentiment color.
- **Empty state**: centered `w-10 h-10 rounded-full bg-indigo-600/20 border border-indigo-600/30` ring with indigo-400 `✦` glyph.

## 5. Layout Principles

### Grid & Structure
- Single-page app with top sticky nav (`h-14`) and full-height content below (`h-[calc(100vh-3.5rem)]`).
- **Builder**: Two-panel side-by-side. Left chat: `w-[45%]`. Right preview+call: `flex-1`. Panels separated by `border-r border-zinc-800`.
- **Builder empty state**: Left panel expands to full width (`w-full`) via CSS transition. Right panel hidden.
- **Dashboard**: Agent card grid (2-3 col responsive).
- **Logs**: Table + right-side transcript drawer.
- No max-width container — panels fill the viewport.

### Whitespace Strategy
- 4px base unit throughout.
- Section padding: `px-4 py-3` (standard), `px-5 py-3` (slightly looser for preview panels), `px-6` (nav).
- Dividers (`border-zinc-800`) do the heavy lifting for visual separation rather than margin/padding gaps.
- Tight density inside panels — this is a tool, not a marketing page.

### Alignment & Visual Balance
- Text left-aligned throughout. No centered body content.
- Icons always paired with labels; icon size 12-18px matched to text size.
- Right panel header uses flexbox space-between for title + action buttons.

### Responsive Behavior
- Desktop-first. No mobile breakpoints defined — designed for 1280px+ screen.
- Two-panel layout is fixed ratio; no collapse breakpoint needed (demo-only tool).

## 6. Design System Notes for Stitch Generation

### Language to Use
- "Dark command center", "focused tool interface", "near-black canvas with indigo precision accents"
- "Hairline zinc borders on obsidian surfaces", "no shadows — depth through tone"
- "Indigo reserved for action only", "everything else recedes"

### Color References
- Page background: Void Black `#0a0a0a`
- Panel surface: Charcoal `#18181b`
- Inset inputs: Obsidian `#09090b`
- Primary accent: Indigo Core `#4f46e5`
- Border: Graphite `#27272a`
- Primary text: Bright White `#f4f4f5`
- Muted text: Slate `#71717a`

### Component Prompts
- "A dark chat interface on a near-black background. AI messages in dark zinc-900 bubbles with hairline borders. User messages in indigo-600 bubbles. Three indigo dots animate as a typing indicator. Input at the bottom with indigo send button."
- "An agent preview card on a dark surface showing name, voice, qualifying questions as a list, and a collapsible system prompt section. Hairline zinc-800 borders separate each section."
- "A live call panel with phone input, lead name and email fields on zinc-950 background, an indigo Start Call button, and a status bar showing a pulsing emerald dot, uppercase LIVE label, monospaced duration counter, and red End Call button."

### Incremental Iteration
- Always start screens with background `#0a0a0a` and zinc-800 borders.
- Add indigo accent only on interactive targets — resist using it decoratively.
- Use uppercase + tracking-widest for all micro-labels and status indicators.
- Chat bubbles need asymmetric corner radius to feel like a real messenger.
