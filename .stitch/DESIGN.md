---
name: Ally Voice AI Builder
colors:
  background: '#0a0a0a'
  surface: '#18181b'
  border: '#27272a'
  accent: '#4f46e5'
  accent-hover: '#6366f1'
  accent-light: '#818cf8'
  text-primary: '#f4f4f5'
  text-secondary: '#a1a1aa'
  text-muted: '#71717a'
  scrollbar-track: '#111111'
  scrollbar-thumb: '#333333'
typography:
  font-family: 'Geist, system-ui, -apple-system, sans-serif'
  antialiasing: true
radius:
  buttons: 8px
  cards: 12px
  chat-bubbles: 16px
mode: dark-only
---

# Ally Voice AI Builder — Design System

Extracted from the implemented React + Vite + Tailwind + shadcn/ui codebase
(`frontend/src`) for comparison against the Stitch reference screens.

## Brand

- Product name: **Ally**
- Wordmark: bold "Ally" text next to an indigo rounded-square avatar mark ("A")
- Dark mode only, no light theme toggle

## Color Tokens

| Token | Value | Usage |
|---|---|---|
| Background | `#0a0a0a` | Page background |
| Surface | `#18181b` | Cards, panels, inputs |
| Border | `#27272a` | Card/input borders, dividers |
| Accent (default) | `#4f46e5` | Primary buttons, active nav underline |
| Accent (hover) | `#6366f1` | Button hover state |
| Accent (light) | `#818cf8` | Icon accents, subtle highlights |
| Text primary | `#f4f4f5` | Headings, primary content |
| Text secondary | `#a1a1aa` | Descriptions, subtitles |
| Text muted | `#71717a` | Placeholders, empty-state captions |

## Layout

- Persistent top nav bar: logo/wordmark (left) · tab links "Agents / Logs / Builder" (center-left) · "Publish Agent" primary button + avatar (right)
- Active nav tab indicated by an indigo underline
- Content area is full-bleed below the nav, no left sidebar
- Empty states are centered vertically and horizontally: icon in a rounded dark circle, bold heading, muted subtext, primary CTA button below

## Components

### Buttons
- Primary: indigo fill (`#4f46e5`→hover `#6366f1`), white text, 8px radius, icon + label
- Nav "Publish Agent" always visible top-right

### Cards / Panels
- 12px radius, `#18181b` surface, `#27272a` 1px border

### Chat / Builder input
- Bottom-docked pill-shaped input bar, 16px radius, muted placeholder text, indigo circular send button, "Attach context" affordance below the input

### Empty states (shared pattern across Dashboard, Builder, Logs)
- Centered dark circular icon badge (~64px)
- Bold headline (`text-primary`)
- One muted subheadline sentence
- Optional primary CTA button

### Search / filter bar (Logs)
- Full-width pill input with leading search icon, `#18181b` fill, muted placeholder

## Screens (as implemented)

1. **Dashboard** (`/`) — "Your Agents" header + "New Agent" button top-right; empty state: mic icon, "Build your first voice agent", CTA
2. **Builder** (`/builder`) — "Builder Chat" panel header; empty state: sparkle icon, "Describe your voice agent"; bottom-docked chat input bar
3. **Call Logs** (`/logs`) — "Call Logs" header + subtitle; search bar; empty state: list icon, "No calls yet"

## Notes for Reconciliation

- No right-hand agent-preview/call panel is visible on Builder yet — CLAUDE.md specifies this should slide in once the agent is configured (two-panel view), currently only the empty single-panel chat state is implemented.
- Colors and radii match `frontend/src/index.css` `@theme` tokens and CLAUDE.md's documented design tokens exactly — no drift found there.
