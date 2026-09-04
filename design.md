# Ubichinon — Design Direction

## 1. Design goal

Ubichinon should feel like a **serious retail operations tool with a warm human layer**, not a generic “AI dashboard”.

The interface should be:

- calm
- compact
- easy to scan
- slightly warm, not playful
- operational rather than futuristic
- focused on the current task
- restrained in its use of borders, cards, badges, icons, and metrics

The product should visually say:

> “This is a dependable store operations workspace that happens to use AI.”

Not:

> “This is an AI chatbot demo.”

---

## 2. What currently makes the interface feel “AI slop”

The current UI has several patterns that are heavily associated with generic AI-generated admin dashboards:

1. Too many bordered rectangles.
2. Tiny uppercase section labels everywhere.
3. Monospace/technical styling used beyond places where it is useful.
4. Large empty chat canvas with a tiny centered assistant bubble.
5. A bright robot icon used repeatedly as the main identity.
6. Sidebars packed with implementation details such as provider, runtime, database, trace, token counts, and LLM calls.
7. “Command queue” presets permanently occupying prime screen space.
8. Every piece of metadata is given equal visual importance.
9. Orange accent appears as a generic AI highlight rather than part of a coherent brand system.
10. Login page is a centered card floating in a large empty dark background — a common generated SaaS pattern.

The redesign should remove visual noise before adding new visual elements.

---

# 3. Product personality

## Core attributes

**Warm**
- slightly warm neutral backgrounds
- soft contrast
- restrained amber accent
- natural language

**Operational**
- dense enough for daily work
- clear hierarchy
- fast keyboard interaction
- important system states remain visible

**Confident**
- no decorative gradients
- no glowing elements
- no fake “AI intelligence” visual effects
- no oversized chatbot branding

**Human**
- conversational copy
- readable typography
- comfortable spacing
- subtle texture through typography and spacing rather than ornament

---

# 4. Visual direction

## Reference mood

Think:

- modern POS / retail operations software
- Linear-level restraint
- Notion-level clarity
- Stripe Dashboard-level hierarchy

But with a warmer palette and less “developer tool” styling.

Do **not** imitate any of those products directly.

---

# 5. Color system

The interface should not be pure black.

Use slightly warm charcoal surfaces.

```css
:root {
  --bg: #11110f;
  --surface: #171714;
  --surface-raised: #1d1d19;
  --surface-hover: #24231f;

  --border: #2b2a25;
  --border-subtle: #23231f;

  --text-primary: #f3f0e8;
  --text-secondary: #aaa69a;
  --text-muted: #77746b;

  --accent: #d48a31;
  --accent-hover: #e49a3f;
  --accent-soft: #2b2115;

  --success: #65a67b;
  --warning: #d3a04d;
  --danger: #c96b62;
}
```

### Rules

- Accent is used sparingly.
- Most buttons should not be orange.
- Orange is reserved for:
  - primary action
  - active navigation state
  - selected important action
  - small brand mark
- Never use orange for large filled surfaces.

---

# 6. Typography

Avoid using a “tech-looking” font for the whole product.

Recommended:

```css
font-family:
  Inter,
  "Instrument Sans",
  "IBM Plex Sans",
  system-ui,
  sans-serif;
```

Use monospace only for:

- request IDs
- model names
- token counts
- trace IDs
- raw JSON
- logs

Recommended scale:

| Role | Size | Weight |
|---|---:|---:|
| Page title | 24px | 600 |
| Section title | 15–16px | 600 |
| Body | 14px | 400 |
| Secondary | 13px | 400 |
| Metadata | 12px | 500 |

Avoid excessive uppercase.

Instead of:

`DEVELOPMENT CLIENT`

use:

`Development`

or omit it entirely when context already makes it obvious.

---

# 7. Border radius

Use a smaller, more intentional radius.

```css
--radius-sm: 6px;
--radius-md: 8px;
--radius-lg: 12px;
```

Avoid 16–24px rounded cards everywhere.

Inputs and buttons:

`8px`

Panels:

`10–12px`

---

# 8. Border strategy

Do not put every group inside a card.

Prefer:

- spacing
- typography
- subtle separators
- surface changes

Use borders only when they clarify containment.

Bad:

```text
[ CARD ]
  [ CARD ]
    [ CARD ]
```

Preferred:

```text
Section title

Content
────────────────
Next section
```

---

# 9. Login page

## Current problem

The current login screen feels like a generated SaaS template:

- content floats in the exact center
- excessive empty space
- brand represented primarily by robot icon
- login form is a standalone dark card
- tiny uppercase “STORE OPS”
- visual hierarchy is weak

## New layout

Desktop:

```text
┌─────────────────────────────────────────────────────────────────┐
│ Ubichinon                                                        │
│                                                                  │
│                                                                  │
│          Store operations, without the busywork.                 │
│          Search products, answer policy questions,               │
│          and handle routine store tasks from one place.          │
│                                                                  │
│                                  Sign in                         │
│                                  Email                           │
│                                  [________________________]       │
│                                                                  │
│                                  Password                        │
│                                  [________________________]       │
│                                                                  │
│                                  [ Sign in ]                     │
│                                                                  │
│                                  Protected against repeated      │
│                                  failed sign-in attempts.        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Structure

Use a two-column composition.

Left:

- wordmark
- short positioning statement
- optional 2–3 compact capability examples

Right:

- login form
- no floating card if possible
- form width approximately 360–400px

### Brand mark

Replace the large orange robot with a quieter mark.

Possible direction:

- simple “U” monogram
- abstract inventory box mark
- small geometric store/shelf symbol

Do not make the visual identity explicitly “robot”.

### Login copy

Title:

**Welcome back**

Subtitle:

**Sign in to Ubichinon**

Fields:

- Email
- Password

Primary button:

**Sign in**

Security message:

**Repeated failed sign-in attempts are temporarily blocked.**

Do not put a shield icon unless it adds meaning.

---

# 10. Main application shell

The main application should have three levels:

```text
Navigation
Workspace
Context
```

But the third panel should only appear when useful.

## Recommended desktop structure

```text
┌──────────────┬──────────────────────────────────────┬─────────────┐
│ Sidebar      │ Conversation                         │ Context     │
│ 224px        │ flexible                             │ 300px       │
│              │                                      │ optional    │
└──────────────┴──────────────────────────────────────┴─────────────┘
```

The right panel should be **collapsible** and closed by default for normal users.

---

# 11. Left sidebar

The current sidebar exposes too much infrastructure.

## Default sidebar

```text
Ubichinon

New conversation

Conversations
  Recent
  Saved

Workspace
  Orders
  Products
  Policies

──────────────

Admin
Settings
```

At the bottom:

```text
NS
Nabilah
Administrator
```

The user should not constantly see:

- localhost URL
- database type
- LLM provider
- model alias
- runtime selector

Move those to:

`Settings → AI & Infrastructure`

or an admin-only developer panel.

---

# 12. Development indicators

Development information is useful, but it should not dominate the product.

Use one subtle environment pill in the header:

```text
Development
```

Clicking it opens:

```text
Environment
API
Model
Database
Trace tools
```

Do not permanently show all infrastructure fields in the sidebar.

---

# 13. Conversation header

Replace:

```text
DEVELOPMENT CLIENT
Agent workspace
FastAPI
alias:openrouter/free
```

with:

```text
Assistant

Store operations
```

Optional right-side controls:

```text
History    Details    •••
```

Developer metadata belongs inside `Details`.

---

# 14. Empty conversation state

The current screen has too much dead space.

Use a deliberate empty state.

```text
What can I help with?

Search inventory, check an order,
or ask about a store policy.

[ Search for a product ]
[ Check an order ]
[ Ask about a policy ]
```

The suggested tasks should sit in the conversation canvas, not in a permanent right sidebar.

Limit to 3 suggestions.

Do not call them “Command Queue”.

---

# 15. Message layout

Avoid chat bubbles for every message.

For a work application, use document-style conversation.

Example:

```text
You
Find running shoes under Rp 1,500,000

Ubichinon
I found 8 matching products.

[Product results]

The best value is ...
```

User messages may use a subtle tinted background.

Assistant responses should mostly sit directly on the canvas.

This creates a calmer, more professional workspace.

---

# 16. Composer

The message composer should be visually important but not oversized.

Desktop:

```text
┌────────────────────────────────────────────────────┐
│ Ask about products, orders, customers, or policies │
│                                                    │
│ Attach                                      Send ↵ │
└────────────────────────────────────────────────────┘
```

Width:

`min(760px, calc(100% - 48px))`

Place it centered relative to the conversation column.

### Behavior

- Enter = send
- Shift + Enter = newline
- `/` = commands
- `@` = reference entity
- optional attachment button

Do not use a large orange square send button.

Use a compact icon button or text button.

---

# 17. Right context panel

The right side should be task-dependent.

## Normal state

Hidden.

## When useful

Examples:

### Product search

Show:

- filters
- selected products
- comparison

### Order support

Show:

- order details
- customer
- fulfillment status

### Admin/debug mode

Show:

- latency
- token usage
- model
- workflow
- trace

This is where the current “Last Request” and “Trace” information belongs.

---

# 18. Metrics

Do not render six separate metric cards.

Use one compact diagnostics row:

```text
824 ms · 1,284 tokens · 2 LLM calls · $0.0014
```

Click:

`View trace`

Expanded state can contain full diagnostics.

This preserves observability without making the app look like an LLM benchmark dashboard.

---

# 19. AI terminology

Reduce explicit AI terminology in user-facing copy.

Avoid:

- AI Agent
- Agent Workspace
- LLM Calls
- Workflow
- Model Provider

Unless the user is in developer/admin mode.

Prefer:

- Assistant
- Conversation
- Activity
- Details
- Automation
- Source

The system can be agentic without constantly announcing that it is an agent.

---

# 20. Buttons

## Primary

Use one main filled action per view.

Example:

```text
Sign in
Send
Confirm
Create
```

## Secondary

Neutral dark surface.

## Tertiary

Text or ghost button.

Avoid giving every button a border.

---

# 21. Icons

Use icons to clarify actions, not decorate headings.

Good:

```text
Search
Settings
History
Send
Attach
```

Bad:

```text
robot icon + title
database icon + database
shield icon + text
clock icon + latency
coin icon + cost
```

The UI should still be understandable with most icons removed.

Recommended icon set:

- Lucide
- Radix Icons

Use 16px icons in most places.

---

# 22. Spacing

Use a consistent 4px grid.

Recommended spacing:

```text
4
8
12
16
24
32
48
64
```

Typical component spacing:

- field label → input: 6px
- input → next field: 16px
- section heading → content: 12px
- section → section: 28–32px
- sidebar item height: 36–40px

---

# 23. Responsive behavior

## ≥ 1280px

Sidebar + conversation + optional context panel.

## 768–1279px

Sidebar collapses to icon/navigation drawer.

Context panel becomes overlay/drawer.

## < 768px

Single column.

Header:

```text
☰  Ubichinon                •••
```

Composer stays fixed near the bottom.

Do not render desktop diagnostic panels on mobile.

---

# 24. Suggested information architecture

```text
Ubichinon
│
├── Assistant
│   ├── New conversation
│   ├── Recent conversations
│   └── Saved conversations
│
├── Operations
│   ├── Orders
│   ├── Products
│   └── Policies
│
├── Admin
│   ├── Users
│   ├── AI & Infrastructure
│   ├── Observability
│   └── Security
│
└── Settings
```

Do not add navigation items until a real workflow needs them.

---

# 25. Suggested component hierarchy

```text
AppShell
├── Sidebar
│   ├── Wordmark
│   ├── NewConversationButton
│   ├── PrimaryNavigation
│   ├── AdminNavigation
│   └── AccountMenu
│
├── ConversationWorkspace
│   ├── ConversationHeader
│   ├── MessageList
│   │   ├── EmptyState
│   │   ├── UserMessage
│   │   ├── AssistantMessage
│   │   ├── ToolResult
│   │   └── ConfirmationCard
│   └── Composer
│
└── ContextPanel
    ├── EntityDetails
    ├── TaskContext
    └── DeveloperDiagnostics
```

---

# 26. Important agent UX

Agentic behavior needs strong interaction design.

Never let the agent silently execute consequential actions.

Use three action categories.

## Read action

Example:

```text
Search products
Check order status
Read return policy
```

Execute immediately.

## Reversible action

Example:

```text
Add item to cart
Apply filter
Save note
```

Can execute directly but show clear feedback and undo when possible.

## Consequential action

Example:

```text
Issue refund
Cancel order
Submit payment dispute
Change inventory
```

Require confirmation.

Example confirmation:

```text
Refund Rp 749,000?

Order #UB-18492
Reason: duplicate charge

[Cancel] [Confirm refund]
```

Do not use generic:

`Are you sure?`

---

# 27. Tool activity

When the assistant performs multiple operations, show a compact activity disclosure.

Collapsed:

```text
Checked 3 sources
```

Expanded:

```text
✓ Searched product catalog
✓ Checked current inventory
✓ Applied price filter
```

Do not expose raw chain-of-thought or internal reasoning.

---

# 28. Loading states

Avoid:

```text
Thinking...
```

Prefer task-specific status:

```text
Searching products…
Checking your order…
Reviewing the return policy…
```

If the operation lasts more than a few seconds, expose progress through completed tool steps.

---

# 29. Error states

Errors should be plain and actionable.

Bad:

```text
Workflow execution failed.
```

Better:

```text
I couldn't reach the product catalog.

Try again, or check the catalog connection in Settings.
```

Technical details can be expandable:

```text
View technical details
```

---

# 30. Login wireframe

```text
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  Ubichinon                                                             │
│                                                                        │
│                                                                        │
│  Store operations,                                                     │
│  without the busywork.                        Welcome back             │
│                                               Sign in to continue      │
│  Find products, check orders,                                          │
│  and resolve routine store                    Email                    │
│  questions from one workspace.                [____________________]   │
│                                                                        │
│                                               Password                 │
│                                               [____________________]   │
│                                                                        │
│                                               [      Sign in       ]   │
│                                                                        │
│                                               Repeated failed login    │
│                                               attempts are blocked.    │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

# 31. Main workspace wireframe

```text
┌──────────────────┬─────────────────────────────────────────────────────┐
│ Ubichinon        │ Assistant                                  Details │
│                  ├─────────────────────────────────────────────────────┤
│ + New            │                                                     │
│                  │                                                     │
│ Recent           │              What can I help with?                  │
│ • Product search │                                                     │
│ • Return policy  │       Search inventory, check an order,             │
│                  │       or ask about a store policy.                  │
│ Operations       │                                                     │
│ Products         │       Search for a product                          │
│ Orders           │       Check an order                               │
│ Policies         │       Ask about a policy                            │
│                  │                                                     │
│                  │                                                     │
│                  ├─────────────────────────────────────────────────────┤
│                  │  Ask about products, orders, or policies…      ↑   │
├──────────────────┴─────────────────────────────────────────────────────┤
│ Nabilah · Administrator                                               │
└────────────────────────────────────────────────────────────────────────┘
```

---

# 32. When conversation is active

```text
You

Find Nike running shoes under Rp 1,500,000


Ubichinon

I found 8 options currently within your budget.

Nike Revolution 7
Rp 899,000
42 · In stock

Nike Downshifter 13
Rp 1,099,000
41 · 42 · 43 · In stock

Nike Winflo 11
Rp 1,449,000
42 · Low stock

[View all 8 products]


──────────────────────────────────────────────

Ask about these results…                           ↑
```

No speech bubbles are required for the assistant.

---

# 33. Anti-slop checklist

Before merging a new screen, check:

- [ ] Is there a card that could just be spacing?
- [ ] Is there a border that can be removed?
- [ ] Is an icon being used decoratively?
- [ ] Is a label unnecessarily uppercase?
- [ ] Is technical metadata visible to normal users?
- [ ] Are there more than two accent-colored objects on screen?
- [ ] Is the page centered only because it was easiest to implement?
- [ ] Does the empty state explain what the user can actually do?
- [ ] Is AI terminology being used where normal product language would work?
- [ ] Does every permanent panel deserve to remain visible?
- [ ] Does this feel like a retail operations product even if the word “AI” is removed?

If several answers are unfavorable, simplify before adding more UI.

---

# 34. First redesign priorities

Do not redesign everything at once.

## Phase 1 — highest impact

1. Remove infrastructure information from the main sidebar.
2. Remove the permanent Command Queue.
3. Remove the permanent Last Request metric cards.
4. Replace chat bubbles with document-style messages.
5. Build a proper empty state inside the conversation.
6. Reduce uppercase micro-labels.
7. Replace repeated robot branding with a restrained wordmark.
8. Redesign the login page into an asymmetric two-column composition.
9. Make diagnostics available through a collapsible Details panel.
10. Normalize typography, spacing, radius, and colors.

## Phase 2

1. Add conversation history.
2. Add task-specific context panels.
3. Improve agent confirmation UX.
4. Add tool activity disclosures.
5. Add responsive/mobile layouts.
6. Add keyboard navigation and command palette.

---

# 35. Final design rule

Whenever choosing between:

```text
more visual UI
```

and:

```text
less UI + clearer hierarchy
```

choose the second option.

Ubichinon should feel like a **quiet operating system for store work**, not a showcase of how many AI components the application contains.
