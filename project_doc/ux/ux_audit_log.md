# UX Audit Log

## Scope

- Flow: `home -> prepare -> result` + modals (`agent_context`, runtime profile, helper modals).
- Themes: dark and light.
- Layers: typography, contrast, surface separation, button hierarchy, text selection, SQL/prompt readability.

## Baseline Matrix

| ID | Area | Theme | Severity | Finding | Fix Status |
|---|---|---|---|---|---|
| UX-001 | Global tokens | light | high | Light palette had weak contrast on secondary text and borders. | closed |
| UX-002 | Inputs/forms | light | high | Textareas and input fields visually merged with parent surfaces. | closed |
| UX-003 | Buttons | light | medium | Primary/outline buttons diverged from palette and hierarchy was unclear. | closed |
| UX-004 | Selection | dark/light | high | Selection/readability in SQL/prompt editors was inconsistent. | closed |
| UX-005 | Code blocks in results | dark/light | high | Risk SQL snippets used hardcoded `bg-light/text-dark`, breaking dark theme. | closed |
| UX-006 | Prepare tabs/workflow | light | medium | Active/hover states looked low-emphasis and hard to scan. | closed |
| UX-007 | Home cards/surfaces | light | medium | Home cards lacked clear elevation and readable helper copy. | closed |
| UX-008 | Waiting/trace cards | light | low | Trace blocks were too pale and had weak separation. | closed |

## Implemented Remediation

- Unified theme tokens in `styles.css` for light/dark symmetry:
  - text levels, border/focus colors, input backgrounds, selection colors, and primary button palette.
- Added global interaction improvements:
  - `::selection`, `*:focus-visible`, button disabled/focus behavior, stronger outline-button hover.
- Improved input/readability stack in `detailed.css`:
  - dedicated editor shell surface, stronger CodeMirror borders/shadows, caret/selection colors, textarea selection.
- Fixed result SQL risk presentation:
  - replaced hardcoded bootstrap color classes with theme-aware classes (`analysis-sql-snippet`, `sql-risk-highlight`).
- Improved visual hierarchy in `ux.css` and `home.css`:
  - clearer active/hover states for prepare tabs and workflow dots,
  - stronger light-theme surface separation for home cards/dock and trace panels.

## Coverage Check

- Home page: pass
- Prepare page: pass
- Result page: pass
- Agent context + runtime modals: pass (via shared token updates and form controls)
- Dark/light parity for SQL/prompt editing: pass
