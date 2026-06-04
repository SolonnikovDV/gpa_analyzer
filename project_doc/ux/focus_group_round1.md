# UX Focus Group Round 1 (Simulated)

## Participants

- Persona A: analytics engineer (daily SQL edits, high density workflow).
- Persona B: SQL developer (syntax validation, risk triage, result inspection).
- Persona C: product user (navigation clarity, action confidence, readability).

## Scenarios

- Open `home`, scan entry points, move to prepare.
- Fill stack/scenario, edit SQL/prompt, trigger generate/discovery.
- Inspect result risk blocks and detail cards.
- Re-check core flows in light theme.

## Positives

- Navigation and progress structure are predictable across pages.
- SQL lint and feedback blocks are useful for troubleshooting.
- Agent trace stream is informative and now visually grouped.
- Light theme became cleaner after token unification.

## Negatives

| ID | Persona | Finding | Severity | Decision |
|---|---|---|---|---|
| FG1-01 | A | SQL editor still needs stronger frame separation from card body in light theme. | medium | accepted |
| FG1-02 | B | Selection state in CodeMirror is better, but active selection should be stronger. | medium | accepted |
| FG1-03 | C | Home helper text is readable, but step cards need stronger hover feedback in light theme. | low | accepted |
| FG1-04 | B | Risk SQL block highlight must remain visible in both themes. | medium | accepted |

## Round 1 Actions

- Increased visual separation for editor shells and CodeMirror borders/shadows.
- Strengthened selected text colors for default and focused CodeMirror states.
- Added light-theme hover and border improvements for home cards.
- Replaced hardcoded result SQL snippet styling with theme-aware classes.

## Gate

- Result: `pass_with_risk`
- Residual risk:
  - verify perception of new light-state contrasts in repeated real sessions,
  - monitor if stronger selection colors remain comfortable for long SQL reading.
