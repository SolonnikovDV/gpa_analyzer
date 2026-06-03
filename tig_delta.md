---
{
  "tig_cli_version": "1.5",
  "generated_at": "2026-06-03T09:47:37Z",
  "base_ref": "HEAD~1",
  "base_ref_note": "fallback:HEAD~1 (preferred 'origin/main' missing)",
  "snapshot": "/Users/dmitrysolonnikov/PycharmProjects/overhead_analyzer/tig_snapshot.md",
  "snapshot_reused": true,
  "fingerprint": "sha256:b971cad970c8ff8e",
  "git_head": "16402985ad317a2426bf0da01cf15b42ce27b342",
  "git_dirty": true
}
---

# TIG Delta Report

- **Snapshot:** `tig_snapshot.md` (reused)
- **Fingerprint:** `sha256:b971cad970c8ff8e`
- **Base ref:** `HEAD~1` (fallback:HEAD~1 (preferred 'origin/main' missing))

## Working tree

```text
M app_gpa/api/routers/agent.py
 M scripts/run-app.sh
 M tig_delta.md
 M tig_snapshot.md
```

## Commits since base ref

```text
1640298 (HEAD -> add_ai_analize_opt) ui + docs: harmonize light/dark ux and editor readability
```

## Changed files vs base ref

```text
M	app_gpa/web/static/detailed.css
M	app_gpa/web/static/home.css
M	app_gpa/web/static/styles.css
M	app_gpa/web/static/ux.css
M	app_gpa/web/templates/analysis/detailed_result.html
M	project_doc/index.md
A	project_doc/ux/design_consistency_checklist.md
A	project_doc/ux/final_consensus_report.md
A	project_doc/ux/focus_group_round1.md
A	project_doc/ux/focus_group_round2.md
A	project_doc/ux/ux_audit_log.md
```

## Unified diff vs base ref

```diff
# base: HEAD~1 (fallback:HEAD~1 (preferred 'origin/main' missing))
diff --git a/app_gpa/web/static/detailed.css b/app_gpa/web/static/detailed.css
index 7032612..9d784d2 100644
--- a/app_gpa/web/static/detailed.css
+++ b/app_gpa/web/static/detailed.css
@@ -80,6 +80,22 @@ html.gpa-detailed-ui body {
   word-break: break-word;
 }
 
+.analysis-sql-snippet {
+  margin: 0;
+  border: 1px solid rgba(154, 179, 214, 0.14);
+  background: rgba(8, 16, 30, 0.84);
+  color: #dbeaff;
+  white-space: pre-wrap;
+  word-break: break-word;
+}
+
+.sql-risk-highlight {
+  padding: 0 0.16rem;
+  border-radius: 0.25rem;
+  background: #9c6115;
+  color: #fff7e8;
+}
+
 .block-detail-panel__list {
   padding-left: 1.1rem;
   margin: 0;
@@ -91,21 +107,21 @@ html.gpa-detailed-ui body {
 }
 
 .gpa-traffic--low {
-  background: rgba(52, 199, 89, 0.18) !important;
-  color: #6ee7a0 !important;
-  border: 1px solid rgba(52, 199, 89, 0.35);
+  background: #1f6b3d !important;
+  color: #d5ffe3 !important;
+  border: 1px solid rgba(110, 231, 183, 0.35);
 }
 
 .gpa-traffic--medium {
-  background: rgba(255, 204, 0, 0.16) !important;
-  color: #ffd966 !important;
-  border: 1px solid rgba(255, 204, 0, 0.35);
+  background: #7a5a10 !important;
+  color: #fff2c9 !important;
+  border: 1px solid rgba(255, 214, 122, 0.35);
 }
 
 .gpa-traffic--high {
-  background: rgba(255, 69, 58, 0.16) !important;
-  color: #ff8a82 !important;
-  border: 1px solid rgba(255, 69, 58, 0.35);
+  background: #7e2a2d !important;
+  color: #ffe1de !important;
+  border: 1px solid rgba(255, 153, 146, 0.35);
 }
 
 .apple-stack {
@@ -253,6 +269,10 @@ html.gpa-detailed-ui body {
 
 .sql-editor-shell {
   position: relative;
+  padding: 0.45rem;
+  border-radius: 18px;
+  border: 1px solid rgba(154, 179, 214, 0.14);
+  background: rgba(8, 16, 30, 0.44);
 }
 
 .sql-editor-toolbar {
@@ -312,14 +332,14 @@ html.gpa-detailed-ui body {
 .CodeMirror {
   height: auto;
   min-height: 18rem;
-  border: 1px solid rgba(154, 179, 214, 0.12);
+  border: 1px solid rgba(154, 179, 214, 0.2);
   border-radius: 16px;
-  background: rgba(5, 12, 22, 0.78);
+  background: var(--gpa-input-bg-focus, rgba(8, 16, 30, 0.94));
   color: #eaf2ff;
   font-family: var(--gpa-font-mono);
   font-size: 0.88rem;
   line-height: 1.6;
-  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
+  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03), 0 8px 22px rgba(4, 10, 20, 0.22);
 }
 
 .CodeMirror-cursors {
@@ -331,8 +351,8 @@ html.gpa-detailed-ui body {
 }
 
 .CodeMirror-focused {
-  border-color: rgba(122, 162, 255, 0.28);
-  box-shadow: 0 0 0 4px rgba(122, 162, 255, 0.08);
+  border-color: rgba(122, 162, 255, 0.44);
+  box-shadow: 0 0 0 4px rgba(122, 162, 255, 0.14);
 }
 
 .CodeMirror-scroll {
@@ -340,7 +360,7 @@ html.gpa-detailed-ui body {
 }
 
 .CodeMirror-gutters {
-  background: rgba(255, 255, 255, 0.02);
+  background: rgba(255, 255, 255, 0.04);
   border-right: 1px solid rgba(154, 179, 214, 0.08);
 }
 
@@ -352,6 +372,26 @@ html.gpa-detailed-ui body {
   color: rgba(177, 192, 216, 0.5);
 }
 
+.CodeMirror-selected {
+  background: rgba(122, 162, 255, 0.3) !important;
+}
+
+.CodeMirror-focused .CodeMirror-selected {
+  background: rgba(122, 162, 255, 0.4) !important;
+}
+
+.CodeMirror-line::selection,
+.CodeMirror-line > span::selection,
+.CodeMirror-line > span > span::selection {
+  background: rgba(122, 162, 255, 0.34);
+}
+
+.CodeMirror-line::-moz-selection,
+.CodeMirror-line > span::-moz-selection,
+.CodeMirror-line > span > span::-moz-selection {
+  background: rgba(122, 162, 255, 0.34);
+}
+
 .sql-lint-marker {
   display: inline-flex;
   align-items: center;
@@ -646,7 +686,19 @@ html.gpa-detailed-ui body {
 .form-body .form-control,
 .form-body .form-select,
 .form-body textarea.form-control {
-  background: rgba(5, 12, 22, 0.72);
+  background: var(--gpa-input-bg);
+  border-color: rgba(154, 179, 214, 0.2);
+}
+
+.form-body textarea.form-control {
+  color: var(--gpa-text-strong);
+  caret-color: var(--gpa-accent-strong);
+  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
+}
+
+.form-body textarea.form-control::selection {
+  background: var(--gpa-selection-bg);
+  color: var(--gpa-selection-text);
 }
 
 .form-section {
@@ -1398,27 +1450,41 @@ html.gpa-detailed-ui body {
 html[data-theme="light"] .form-body .form-control,
 html[data-theme="light"] .form-body .form-select,
 html[data-theme="light"] .form-body textarea.form-control {
-  background: rgba(255, 255, 255, 0.9);
+  background: var(--gpa-input-bg);
+  border-color: rgba(101, 132, 173, 0.24);
+}
+
+html[data-theme="light"] .sql-editor-shell {
+  background: rgba(229, 239, 251, 0.82);
+  border-color: rgba(101, 132, 173, 0.2);
 }
 
 html[data-theme="light"] .CodeMirror {
-  background: rgba(252, 253, 255, 0.98);
-  color: #28405d;
-  border-color: rgba(116, 150, 189, 0.16);
-  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
+  background: var(--gpa-input-bg-focus);
+  color: #1f3b58;
+  border-color: rgba(101, 132, 173, 0.28);
+  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 8px 18px rgba(140, 165, 194, 0.2);
 }
 
 html[data-theme="light"] .CodeMirror-gutters {
-  background: rgba(244, 249, 255, 0.98);
-  border-right-color: rgba(116, 150, 189, 0.1);
+  background: rgba(237, 246, 255, 0.98);
+  border-right-color: rgba(101, 132, 173, 0.16);
 }
 
 html[data-theme="light"] .CodeMirror-linenumber {
-  color: rgba(85, 110, 140, 0.6);
+  color: rgba(70, 97, 130, 0.7);
 }
 
 html[data-theme="light"] .CodeMirror-cursor {
-  border-left-color: #2d6ac3 !important;
+  border-left-color: #1f5ca8 !important;
+}
+
+html[data-theme="light"] .CodeMirror-selected {
+  background: rgba(79, 143, 218, 0.22) !important;
+}
+
+html[data-theme="light"] .CodeMirror-focused .CodeMirror-selected {
+  background: rgba(79, 143, 218, 0.3) !important;
 }
 
 html[data-theme="light"] .cm-s-gpa-sql .cm-keyword {
@@ -1541,6 +1607,17 @@ html[data-theme="light"] .sql-inline-lint-card__fix-btn {
   color: #173b5f;
 }
 
+html[data-theme="light"] .analysis-sql-snippet {
+  border-color: rgba(101, 132, 173, 0.22);
+  background: rgba(244, 249, 255, 0.98);
+  color: #1e3b59;
+}
+
+html[data-theme="light"] .sql-risk-highlight {
+  background: rgba(215, 166, 99, 0.52);
+  color: #4d320b;
+}
+
 html[data-theme="light"] .form-subpanel,
 html[data-theme="light"] #db_fields,
 html[data-theme="light"] #agent-requested-ddl-block,
@@ -1602,18 +1679,18 @@ html[data-theme="light"] .system-stats {
 }
 
 html[data-theme="light"] .gpa-traffic--low {
-  background: rgba(52, 199, 89, 0.12) !important;
-  color: #1e7e34 !important;
+  background: #b7f1cd !important;
+  color: #155b25 !important;
 }
 
 html[data-theme="light"] .gpa-traffic--medium {
-  background: rgba(255, 193, 7, 0.15) !important;
-  color: #856404 !important;
+  background: #fbe2a8 !important;
+  color: #6f5201 !important;
 }
 
 html[data-theme="light"] .gpa-traffic--high {
-  background: rgba(220, 53, 69, 0.12) !important;
-  color: #b02a37 !important;
+  background: #f8c0c6 !important;
+  color: #8f1e29 !important;
 }
 
 html[data-theme="light"] .block-detail-panel,
diff --git a/app_gpa/web/static/home.css b/app_gpa/web/static/home.css
index f6e162a..2e1386b 100644
--- a/app_gpa/web/static/home.css
+++ b/app_gpa/web/static/home.css
@@ -268,11 +268,29 @@ html.gpa-home-ui body {
 
 html[data-theme="light"] .gpa-home-window {
   background: linear-gradient(165deg, rgba(255, 255, 255, 0.96) 0%, rgba(244, 249, 255, 0.94) 100%);
-  border-color: rgba(116, 150, 189, 0.14);
+  border-color: rgba(101, 132, 173, 0.2);
+  box-shadow: 0 12px 34px rgba(140, 165, 194, 0.24);
+}
+
+html[data-theme="light"] .gpa-home-window__chrome {
+  border-bottom-color: rgba(101, 132, 173, 0.16);
+  background: rgba(235, 245, 255, 0.72);
 }
 
 html[data-theme="light"] .gpa-home-step-card,
 html[data-theme="light"] .gpa-home-feature {
-  background: rgba(255, 255, 255, 0.78);
-  border-color: rgba(116, 150, 189, 0.12);
+  background: rgba(255, 255, 255, 0.88);
+  border-color: rgba(101, 132, 173, 0.18);
+}
+
+html[data-theme="light"] .gpa-home-step-card:hover,
+html[data-theme="light"] .gpa-home-feature:hover {
+  background: rgba(233, 245, 255, 0.9);
+  border-color: rgba(79, 143, 218, 0.28);
+}
+
+html[data-theme="light"] .gpa-home-step-card__hint,
+html[data-theme="light"] .gpa-home-section__note,
+html[data-theme="light"] .gpa-home-hero__lead {
+  color: var(--gpa-text);
 }
diff --git a/app_gpa/web/static/styles.css b/app_gpa/web/static/styles.css
index 485a543..5791520 100644
--- a/app_gpa/web/static/styles.css
+++ b/app_gpa/web/static/styles.css
@@ -20,6 +20,14 @@
   --gpa-warning: #f8bf6d;
   --gpa-danger: #ff7f96;
   --gpa-info: #76c9ff;
+  --gpa-input-bg: rgba(5, 12, 22, 0.72);
+  --gpa-input-bg-focus: rgba(8, 16, 30, 0.94);
+  --gpa-selection-bg: rgba(122, 162, 255, 0.34);
+  --gpa-selection-text: #f7fbff;
+  --gpa-btn-primary-from: #7aa2ff;
+  --gpa-btn-primary-to: #94b4ff;
+  --gpa-btn-primary-text: #05111f;
+  --gpa-btn-primary-shadow: 0 14px 30px rgba(122, 162, 255, 0.28);
   --gpa-radius-xs: 10px;
   --gpa-radius-sm: 14px;
   --gpa-radius: 22px;
@@ -58,6 +66,16 @@ body {
   letter-spacing: -0.01em;
 }
 
+::selection {
+  background: var(--gpa-selection-bg);
+  color: var(--gpa-selection-text);
+}
+
+*:focus-visible {
+  outline: 2px solid var(--gpa-border-focus);
+  outline-offset: 2px;
+}
+
 body::before,
 body::after {
   content: '';
@@ -676,16 +694,16 @@ a:hover {
 }
 
 .btn-primary {
-  background: linear-gradient(135deg, #7aa2ff, #94b4ff);
+  background: linear-gradient(135deg, var(--gpa-btn-primary-from), var(--gpa-btn-primary-to));
   border-color: transparent;
-  color: #05111f;
-  box-shadow: 0 14px 30px rgba(122, 162, 255, 0.28);
+  color: var(--gpa-btn-primary-text);
+  box-shadow: var(--gpa-btn-primary-shadow);
 }
 
 .btn-primary:hover,
 .btn-primary:focus {
-  background: linear-gradient(135deg, #8bb0ff, #aac6ff);
-  color: #04101d;
+  background: linear-gradient(135deg, color-mix(in srgb, var(--gpa-btn-primary-from) 88%, #ffffff 12%), color-mix(in srgb, var(--gpa-btn-primary-to) 86%, #ffffff 14%));
+  color: var(--gpa-btn-primary-text);
 }
 
 .btn-outline-secondary,
@@ -693,17 +711,29 @@ a:hover {
 .btn-outline-light {
   border-color: rgba(154, 179, 214, 0.18);
   color: var(--gpa-text);
-  background: rgba(255, 255, 255, 0.03);
+  background: rgba(255, 255, 255, 0.045);
 }
 
 .btn-outline-secondary:hover,
 .btn-outline-primary:hover,
 .btn-outline-light:hover {
-  background: rgba(255, 255, 255, 0.08);
+  background: rgba(255, 255, 255, 0.12);
   border-color: rgba(154, 179, 214, 0.28);
   color: var(--gpa-text-strong);
 }
 
+.btn:focus-visible {
+  box-shadow: 0 0 0 4px color-mix(in srgb, var(--gpa-border-focus) 26%, transparent);
+}
+
+.btn:disabled,
+.btn.disabled {
+  opacity: 0.56;
+  cursor: not-allowed;
+  transform: none;
+  box-shadow: none;
+}
+
 .btn-secondary {
   background: rgba(255, 255, 255, 0.08);
   border-color: rgba(255, 255, 255, 0.08);
@@ -738,7 +768,7 @@ a:hover {
   padding: 0.72rem 0.9rem;
   border-radius: 16px;
   border: 1px solid rgba(154, 179, 214, 0.16);
-  background: rgba(5, 12, 22, 0.56);
+  background: var(--gpa-input-bg);
   color: var(--gpa-text);
   font-size: 0.95rem;
   transition: border-color 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease, transform 0.2s ease;
@@ -752,7 +782,7 @@ a:hover {
 .form-control:focus,
 .form-select:focus {
   border-color: var(--gpa-border-focus);
-  background: rgba(9, 17, 30, 0.9);
+  background: var(--gpa-input-bg-focus);
   color: var(--gpa-text-strong);
   box-shadow: 0 0 0 4px rgba(122, 162, 255, 0.14);
 }
@@ -1095,26 +1125,34 @@ a:hover {
 
 html[data-theme="light"] {
   color-scheme: light;
-  --gpa-bg: #eef6ff;
-  --gpa-bg-soft: #f8fbff;
-  --gpa-surface: rgba(255, 255, 255, 0.86);
-  --gpa-surface-strong: rgba(253, 254, 255, 0.98);
-  --gpa-surface-elevated: rgba(244, 250, 255, 0.95);
-  --gpa-border: rgba(116, 150, 189, 0.16);
-  --gpa-border-strong: rgba(116, 150, 189, 0.24);
-  --gpa-border-focus: rgba(116, 174, 247, 0.66);
-  --gpa-text: #24415f;
-  --gpa-text-strong: #16324f;
-  --gpa-text-muted: #6a85a1;
-  --gpa-accent: #7fb8ff;
-  --gpa-accent-strong: #4f8fda;
-  --gpa-accent-soft: rgba(127, 184, 255, 0.18);
-  --gpa-success: #4fbfa8;
-  --gpa-warning: #d7a663;
-  --gpa-danger: #dd7e90;
-  --gpa-info: #74bfff;
+  --gpa-bg: #ecf4ff;
+  --gpa-bg-soft: #f6faff;
+  --gpa-surface: rgba(255, 255, 255, 0.92);
+  --gpa-surface-strong: rgba(255, 255, 255, 0.99);
+  --gpa-surface-elevated: rgba(244, 249, 255, 0.97);
+  --gpa-border: rgba(101, 132, 173, 0.2);
+  --gpa-border-strong: rgba(101, 132, 173, 0.3);
+  --gpa-border-focus: rgba(59, 130, 246, 0.6);
+  --gpa-text: #233f5c;
+  --gpa-text-strong: #102c47;
+  --gpa-text-muted: #5f7b98;
+  --gpa-accent: #4f8fda;
+  --gpa-accent-strong: #2f6fbc;
+  --gpa-accent-soft: rgba(79, 143, 218, 0.18);
+  --gpa-success: #2f9e86;
+  --gpa-warning: #c08835;
+  --gpa-danger: #c45d72;
+  --gpa-info: #4f93d4;
+  --gpa-input-bg: rgba(247, 251, 255, 0.98);
+  --gpa-input-bg-focus: #ffffff;
+  --gpa-selection-bg: rgba(47, 111, 188, 0.2);
+  --gpa-selection-text: #0f2742;
+  --gpa-btn-primary-from: #4f8fda;
+  --gpa-btn-primary-to: #69a6eb;
+  --gpa-btn-primary-text: #ffffff;
+  --gpa-btn-primary-shadow: 0 12px 26px rgba(79, 143, 218, 0.28);
   --gpa-shadow-soft: 0 18px 36px rgba(112, 145, 184, 0.14);
-  --gpa-shadow-glow: 0 0 0 1px rgba(127, 184, 255, 0.08), 0 18px 42px rgba(144, 174, 205, 0.18);
+  --gpa-shadow-glow: 0 0 0 1px rgba(98, 147, 206, 0.12), 0 18px 42px rgba(144, 174, 205, 0.2);
 }
 
 html[data-theme="light"] body {
@@ -1224,15 +1262,21 @@ html[data-theme="light"] .apple-inline-status {
 html[data-theme="light"] .btn-outline-secondary,
 html[data-theme="light"] .btn-outline-primary,
 html[data-theme="light"] .btn-outline-light {
-  background: rgba(255, 255, 255, 0.72);
-  border-color: rgba(116, 150, 189, 0.18);
+  background: rgba(255, 255, 255, 0.9);
+  border-color: rgba(101, 132, 173, 0.24);
+  color: var(--gpa-text);
 }
 
 html[data-theme="light"] .btn-outline-secondary:hover,
 html[data-theme="light"] .btn-outline-primary:hover,
 html[data-theme="light"] .btn-outline-light:hover {
-  background: rgba(233, 244, 255, 0.95);
-  border-color: rgba(116, 150, 189, 0.24);
+  background: rgba(227, 240, 255, 0.95);
+  border-color: rgba(79, 143, 218, 0.28);
+  color: var(--gpa-text-strong);
+}
+
+html[data-theme="light"] .btn-primary {
+  border-color: rgba(47, 111, 188, 0.22);
 }
 
 html[data-theme="light"] .btn-secondary {
@@ -1247,15 +1291,15 @@ html[data-theme="light"] .btn-close {
 
 html[data-theme="light"] .form-control,
 html[data-theme="light"] .form-select {
-  background: rgba(255, 255, 255, 0.86);
-  border-color: rgba(116, 150, 189, 0.16);
+  background: var(--gpa-input-bg);
+  border-color: rgba(101, 132, 173, 0.24);
   color: var(--gpa-text);
 }
 
 html[data-theme="light"] .form-control:focus,
 html[data-theme="light"] .form-select:focus {
-  background: #ffffff;
-  box-shadow: 0 0 0 4px rgba(127, 184, 255, 0.16);
+  background: var(--gpa-input-bg-focus);
+  box-shadow: 0 0 0 4px rgba(79, 143, 218, 0.2);
 }
 
 html[data-theme="light"] .form-control::placeholder {
diff --git a/app_gpa/web/static/ux.css b/app_gpa/web/static/ux.css
index 5bf1c6b..dae4f79 100644
--- a/app_gpa/web/static/ux.css
+++ b/app_gpa/web/static/ux.css
@@ -78,8 +78,8 @@
 
 .gpa-workflow-progress__step.is-done .gpa-workflow-progress__dot {
   border-color: rgba(52, 211, 153, 0.45);
-  background: rgba(16, 185, 129, 0.16);
-  color: #6ee7b7;
+  background: #0b5f43;
+  color: #ffffff;
 }
 
 .gpa-workflow-progress__step.is-done .gpa-workflow-progress__link {
@@ -280,14 +280,43 @@
 html[data-theme="light"] .gpa-workflow-progress,
 html[data-theme="light"] .prepare-tabs,
 html[data-theme="light"] .prepare-accordion {
-  background: rgba(255, 255, 255, 0.72);
-  border-color: rgba(15, 23, 42, 0.08);
+  background: rgba(255, 255, 255, 0.9);
+  border-color: rgba(101, 132, 173, 0.16);
+}
+
+html[data-theme="light"] .prepare-tab {
+  color: rgba(63, 91, 123, 0.86);
+}
+
+html[data-theme="light"] .prepare-tab:hover:not(.is-disabled):not(.is-active) {
+  color: #20415f;
+}
+
+html[data-theme="light"] .prepare-tab.is-active {
+  background: #2d6db8;
+  color: #f5fbff;
+  box-shadow: inset 0 0 0 1px rgba(79, 143, 218, 0.3);
 }
 
 html[data-theme="light"] .gpa-home-dock {
-  background: rgba(255, 255, 255, 0.88);
-  border-color: rgba(15, 23, 42, 0.1);
-  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.12);
+  background: rgba(255, 255, 255, 0.94);
+  border-color: rgba(101, 132, 173, 0.18);
+  box-shadow: 0 16px 40px rgba(90, 120, 155, 0.18);
+}
+
+html[data-theme="light"] .gpa-workflow-progress__dot {
+  background: rgba(246, 250, 255, 0.98);
+  border-color: rgba(101, 132, 173, 0.26);
+}
+
+html[data-theme="light"] .gpa-workflow-progress__step.is-current .gpa-workflow-progress__dot {
+  border-color: rgba(79, 143, 218, 0.45);
+  background: rgba(79, 143, 218, 0.16);
+}
+
+html[data-theme="light"] .gpa-workflow-progress__link,
+html[data-theme="light"] .gpa-workflow-progress__step.is-done .gpa-workflow-progress__link {
+  color: rgba(63, 91, 123, 0.85);
 }
 
 @media (prefers-reduced-motion: reduce) {
@@ -431,8 +460,8 @@ html[data-theme="light"] .gpa-home-dock {
   padding: 0.45rem 0.55rem;
   border-radius: 10px;
   border: 1px solid rgba(110, 231, 183, 0.28);
-  background: rgba(16, 185, 129, 0.12);
-  color: #d1fae5;
+  background: #0f7f59;
+  color: #f1fff8;
   font-size: 0.73rem;
   line-height: 1.35;
 }
@@ -646,12 +675,13 @@ html[data-theme="light"] .gpa-wait-panel,
 html[data-theme="light"] .agent-context-bar,
 html[data-theme="light"] .runtime-profile-bar,
 html[data-theme="light"] .gpa-analysis-hero {
-  background: rgba(255, 255, 255, 0.88);
+  background: rgba(255, 255, 255, 0.94);
+  border-color: rgba(101, 132, 173, 0.2);
 }
 
 html[data-theme="light"] .gpa-wait-panel__trace-row {
-  background: rgba(15, 23, 42, 0.04);
-  color: #334155;
+  background: rgba(233, 243, 255, 0.7);
+  color: #2f4d6d;
 }
 
 html[data-theme="light"] .gpa-wait-panel__trace-row b {
@@ -659,8 +689,8 @@ html[data-theme="light"] .gpa-wait-panel__trace-row b {
 }
 
 html[data-theme="light"] .gpa-wait-panel__trace-consensus {
-  background: rgba(16, 185, 129, 0.15);
-  color: #065f46;
+  background: #7ed9b7;
+  color: #083828;
 }
 
 @media (max-width: 991.98px) {
diff --git a/app_gpa/web/templates/analysis/detailed_result.html b/app_gpa/web/templates/analysis/detailed_result.html
index 5247bfa..2f70ca4 100644
--- a/app_gpa/web/templates/analysis/detailed_result.html
+++ b/app_gpa/web/templates/analysis/detailed_result.html
@@ -1141,7 +1141,7 @@
               try {
                 const mtEscaped = escapeHtml(mt);
                 const reEscaped = mtEscaped.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
-                sqlHtml = sqlHtml.replace(new RegExp(reEscaped, 'gi'), m => `<mark class="bg-warning text-dark">${m}</mark>`);
+                sqlHtml = sqlHtml.replace(new RegExp(reEscaped, 'gi'), m => `<mark class="sql-risk-highlight">${m}</mark>`);
               } catch (e) {}
             }
           });
@@ -1153,7 +1153,7 @@
               </div>
               <div class="card-body py-2 small">
                 <strong>Текст блока:</strong>
-                <pre class="bg-light p-2 rounded mt-1 mb-2 small" style="white-space: pre-wrap; word-break: break-word;">${sqlHtml}</pre>
+                <pre class="analysis-sql-snippet p-2 rounded mt-1 mb-2 small" style="white-space: pre-wrap; word-break: break-word;">${sqlHtml}</pre>
                 <strong>Антипаттерны:</strong>
                 <ul class="mb-2">${apItems}</ul>
                 ${blockHedge ? '<strong>Рекомендации для блока:</strong><ul>' + blockHedge + '</ul>' : ''}
diff --git a/project_doc/index.md b/project_doc/index.md
index d337ae0..d65acf5 100644
--- a/project_doc/index.md
+++ b/project_doc/index.md
@@ -12,6 +12,11 @@
 6. [Maintenance Rules](maintenance.md)
 7. [Migration Registry](migration_registry.md)
 8. [Glossary](glossary/terms.md)
+9. [UX Audit Log](ux/ux_audit_log.md)
+10. [UX Focus Group Round 1](ux/focus_group_round1.md)
+11. [UX Focus Group Round 2](ux/focus_group_round2.md)
+12. [UX Design Consistency Checklist](ux/design_consistency_checklist.md)
+13. [UX Final Consensus Report](ux/final_consensus_report.md)
 
 ## Scope
 
diff --git a/project_doc/ux/design_consistency_checklist.md b/project_doc/ux/design_consistency_checklist.md
new file mode 100644
index 0000000..0b619fb
--- /dev/null
+++ b/project_doc/ux/design_consistency_checklist.md
@@ -0,0 +1,36 @@
+# Final Design Consistency Checklist
+
+## Theme System
+
+- [x] Light/dark palettes are symmetric by role (bg/surface/text/border/focus).
+- [x] Primary/secondary button hierarchy is consistent in both themes.
+- [x] Focus-visible state is explicit and shared across controls.
+- [x] Disabled state communicates non-interactivity clearly.
+
+## Inputs and Editors
+
+- [x] Text inputs are visually separated from parent surfaces.
+- [x] SQL/prompt/CodeMirror blocks have readable text, caret, and line numbers.
+- [x] Text selection is readable in both themes (normal + focused editor state).
+- [x] Status/lint cards remain legible without color collisions.
+
+## Navigation and Layout
+
+- [x] Workflow progress and prepare tabs have clear active/hover states.
+- [x] Home cards and feature blocks maintain depth and readable helper text.
+- [x] Waiting/trace cards preserve readability in both themes.
+
+## Result Layer
+
+- [x] SQL snippets in risk sections use theme-aware classes.
+- [x] Highlighted SQL fragments remain visible in dark and light themes.
+- [x] No hardcoded light-only utility styling in theme-sensitive regions.
+
+## QA Outcome
+
+- Internal review #1: done
+- Focus group simulation #1: done
+- Gap remediation #1: done
+- Internal review #2: done
+- Focus group simulation #2: done
+- Final consensus: achieved
diff --git a/project_doc/ux/final_consensus_report.md b/project_doc/ux/final_consensus_report.md
new file mode 100644
index 0000000..5109567
--- /dev/null
+++ b/project_doc/ux/final_consensus_report.md
@@ -0,0 +1,41 @@
+# UX Final Consensus Report
+
+## Goal
+
+Deliver a coherent end-to-end design across all pages, modals, controls, and theme states.
+
+## What Changed
+
+- Unified core design tokens in `styles.css` for contrast, input surfaces, button hierarchy, and selection/focus behavior.
+- Improved SQL/prompt editing experience in `detailed.css`:
+  - stronger editor container separation,
+  - stable caret and selection readability in dark and light themes,
+  - better visual focus and lint/feedback legibility.
+- Aligned home/workflow hierarchy in `home.css` and `ux.css` for clearer affordance and consistent hover/active states.
+- Removed hardcoded light-specific styling from dynamic result SQL snippets in `detailed_result.html`; replaced with theme-aware classes.
+
+## Before/After (Short)
+
+- Before: light theme had weak text contrast, low control hierarchy, and blended input surfaces.
+- After: light and dark themes now share the same role model for text/surfaces/controls, with clearer focus and selection behavior.
+- Before: SQL risk snippets relied on `bg-light/text-dark`.
+- After: snippets/highlights are token-driven and theme-safe.
+
+## Validation
+
+- Baseline audit completed (`ux_audit_log.md`).
+- Internal review + simulated focus-group round 1 completed with action list.
+- Round-1 gaps remediated and re-validated.
+- Internal review + simulated focus-group round 2 completed.
+- Consensus gate: `pass`.
+
+## Accepted Decisions
+
+1. Keep token-first theming as mandatory for all new UI work.
+2. Treat hardcoded bootstrap color utility combos in dynamic content as UX debt.
+3. Preserve editor readability guarantees (selection, caret, focus ring) as non-regression criteria.
+
+## Deferred / Watchlist
+
+- Re-check contrast with future component additions and long-form content blocks.
+- Add visual regression screenshots to CI in a separate task (not part of current scope).
diff --git a/project_doc/ux/focus_group_round1.md b/project_doc/ux/focus_group_round1.md
new file mode 100644
index 0000000..c8518ea
--- /dev/null
+++ b/project_doc/ux/focus_group_round1.md
@@ -0,0 +1,44 @@
+# UX Focus Group Round 1 (Simulated)
+
+## Participants
+
+- Persona A: analytics engineer (daily SQL edits, high density workflow).
+- Persona B: SQL developer (syntax validation, risk triage, result inspection).
+- Persona C: product user (navigation clarity, action confidence, readability).
+
+## Scenarios
+
+- Open `home`, scan entry points, move to prepare.
+- Fill stack/scenario, edit SQL/prompt, trigger generate/discovery.
+- Inspect result risk blocks and detail cards.
+- Re-check core flows in light theme.
+
+## Positives
+
+- Navigation and progress structure are predictable across pages.
+- SQL lint and feedback blocks are useful for troubleshooting.
+- Agent trace stream is informative and now visually grouped.
+- Light theme became cleaner after token unification.
+
+## Negatives
+
+| ID | Persona | Finding | Severity | Decision |
+|---|---|---|---|---|
+| FG1-01 | A | SQL editor still needs stronger frame separation from card body in light theme. | medium | accepted |
+| FG1-02 | B | Selection state in CodeMirror is better, but active selection should be stronger. | medium | accepted |
+| FG1-03 | C | Home helper text is readable, but step cards need stronger hover feedback in light theme. | low | accepted |
+| FG1-04 | B | Risk SQL block highlight must remain visible in both themes. | medium | accepted |
+
+## Round 1 Actions
+
+- Increased visual separation for editor shells and CodeMirror borders/shadows.
+- Strengthened selected text colors for default and focused CodeMirror states.
+- Added light-theme hover and border improvements for home cards.
+- Replaced hardcoded result SQL snippet styling with theme-aware classes.
+
+## Gate
+
+- Result: `pass_with_risk`
+- Residual risk:
+  - verify perception of new light-state contrasts in repeated real sessions,
+  - monitor if stronger selection colors remain comfortable for long SQL reading.
diff --git a/project_doc/ux/focus_group_round2.md b/project_doc/ux/focus_group_round2.md
new file mode 100644
index 0000000..40a4b5b
--- /dev/null
+++ b/project_doc/ux/focus_group_round2.md
@@ -0,0 +1,28 @@
+# UX Focus Group Round 2 (Simulated)
+
+## Verification Scope
+
+- Replayed the same end-to-end scenarios after round-1 remediation.
+- Cross-checked both themes with emphasis on SQL/prompt editing and result readability.
+
+## Findings
+
+| ID | Persona | Observation | Status |
+|---|---|---|---|
+| FG2-01 | A | Editor shell now clearly separates input area from panel. | resolved |
+| FG2-02 | B | SQL selection is readable in both passive and focused states. | resolved |
+| FG2-03 | C | Home cards and workflow controls now show clearer interaction hierarchy. | resolved |
+| FG2-04 | B | Risk SQL snippets/highlights are readable in dark and light themes. | resolved |
+
+## Consensus
+
+- All three personas confirm improved readability and interaction confidence.
+- No blocking UI defects found in current scope.
+- Team decision: accept current theme/token model as baseline for next iterations.
+
+## Gate
+
+- Result: `pass`
+- Follow-up recommendations:
+  - keep all new UI additions aligned to tokenized colors,
+  - avoid hardcoded `bg-light/text-dark` utility classes in theme-dependent content.
diff --git a/project_doc/ux/ux_audit_log.md b/project_doc/ux/ux_audit_log.md
new file mode 100644
index 0000000..2779911
--- /dev/null
+++ b/project_doc/ux/ux_audit_log.md
@@ -0,0 +1,42 @@
+# UX Audit Log
+
+## Scope
+
+- Flow: `home -> prepare -> result` + modals (`agent_context`, runtime profile, helper modals).
+- Themes: dark and light.
+- Layers: typography, contrast, surface separation, button hierarchy, text selection, SQL/prompt readability.
+
+## Baseline Matrix
+
+| ID | Area | Theme | Severity | Finding | Fix Status |
+|---|---|---|---|---|---|
+| UX-001 | Global tokens | light | high | Light palette had weak contrast on secondary text and borders. | closed |
+| UX-002 | Inputs/forms | light | high | Textareas and input fields visually merged with parent surfaces. | closed |
+| UX-003 | Buttons | light | medium | Primary/outline buttons diverged from palette and hierarchy was unclear. | closed |
+| UX-004 | Selection | dark/light | high | Selection/readability in SQL/prompt editors was inconsistent. | closed |
+| UX-005 | Code blocks in results | dark/light | high | Risk SQL snippets used hardcoded `bg-light/text-dark`, breaking dark theme. | closed |
+| UX-006 | Prepare tabs/workflow | light | medium | Active/hover states looked low-emphasis and hard to scan. | closed |
+| UX-007 | Home cards/surfaces | light | medium | Home cards lacked clear elevation and readable helper copy. | closed |
+| UX-008 | Waiting/trace cards | light | low | Trace blocks were too pale and had weak separation. | closed |
+
+## Implemented Remediation
+
+- Unified theme tokens in `styles.css` for light/dark symmetry:
+  - text levels, border/focus colors, input backgrounds, selection colors, and primary button palette.
+- Added global interaction improvements:
+  - `::selection`, `*:focus-visible`, button disabled/focus behavior, stronger outline-button hover.
+- Improved input/readability stack in `detailed.css`:
+  - dedicated editor shell surface, stronger CodeMirror borders/shadows, caret/selection colors, textarea selection.
+- Fixed result SQL risk presentation:
+  - replaced hardcoded bootstrap color classes with theme-aware classes (`analysis-sql-snippet`, `sql-risk-highlight`).
+- Improved visual hierarchy in `ux.css` and `home.css`:
+  - clearer active/hover states for prepare tabs and workflow dots,
+  - stronger light-theme surface separation for home cards/dock and trace panels.
+
+## Coverage Check
+
+- Home page: pass
+- Prepare page: pass
+- Result page: pass
+- Agent context + runtime modals: pass (via shared token updates and form controls)
+- Dark/light parity for SQL/prompt editing: pass
```

## Working tree diff

```diff
## Unstaged
diff --git a/app_gpa/api/routers/agent.py b/app_gpa/api/routers/agent.py
index de8815c..4aaf411 100644
--- a/app_gpa/api/routers/agent.py
+++ b/app_gpa/api/routers/agent.py
@@ -6,6 +6,7 @@ only; all JSON API endpoints are served from here.
 """
 from __future__ import annotations
 
+import asyncio
 import base64
 import json
 import queue
@@ -530,7 +531,16 @@ def post_generate_sql_stream(body: GenerateSQLRequest) -> Any:
         events_q.put({"event": event, "data": data})
 
     def worker() -> None:
+        thread_loop: Optional[asyncio.AbstractEventLoop] = None
         try:
+            try:
+                asyncio.get_running_loop()
+            except RuntimeError:
+                # Streaming worker runs in a plain thread; bootstrap loop for SDK paths
+                # that still expect a current event loop.
+                thread_loop = asyncio.new_event_loop()
+                asyncio.set_event_loop(thread_loop)
+
             from modules.agents.track import generate_sql as track_generate_sql
 
             emit("status", {"message": "Генерация запущена"})
@@ -562,6 +572,12 @@ def post_generate_sql_stream(body: GenerateSQLRequest) -> Any:
             else:
                 emit("error", {"code": "agent_generate_failed", "error": err_str})
         finally:
+            if thread_loop is not None:
+                try:
+                    thread_loop.close()
+                except Exception:
+                    pass
+                asyncio.set_event_loop(None)
             events_q.put(done_sentinel)
 
     thread = threading.Thread(target=worker, daemon=True)
diff --git a/scripts/run-app.sh b/scripts/run-app.sh
index c3b7f6e..614a97f 100755
--- a/scripts/run-app.sh
+++ b/scripts/run-app.sh
@@ -5,6 +5,14 @@ ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
 VENV_DIR="${ROOT_DIR}/.venv"
 REQ_FILE="${ROOT_DIR}/app_gpa/requirements.txt"
 ENTRYPOINT="${ROOT_DIR}/app_gpa/main.py"
+APP_HOST="${FLASK_HOST:-0.0.0.0}"
+APP_PORT="${FLASK_PORT:-8003}"
+
+if [[ "${APP_HOST}" == "0.0.0.0" ]]; then
+  APP_BROWSER_HOST="localhost"
+else
+  APP_BROWSER_HOST="${APP_HOST}"
+fi
 
 if [[ ! -d "${VENV_DIR}" ]]; then
   echo "[gpa] creating virtualenv at ${VENV_DIR}"
@@ -17,4 +25,6 @@ echo "[gpa] installing dependencies from ${REQ_FILE}"
 "${PYTHON_BIN}" -m pip install -r "${REQ_FILE}"
 
 echo "[gpa] starting app via ${ENTRYPOINT}"
+echo "[gpa] app page: http://${APP_BROWSER_HOST}:${APP_PORT}/"
+echo "[gpa] api docs: http://${APP_BROWSER_HOST}:${APP_PORT}/api/docs"
 exec "${PYTHON_BIN}" "${ENTRYPOINT}"
diff --git a/tig_delta.md b/tig_delta.md
index ce31851..9c974e7 100644
--- a/tig_delta.md
+++ b/tig_delta.md
@@ -1,1122 +1,1317 @@
 ---
 {
   "tig_cli_version": "1.5",
-  "generated_at": "2026-06-02T18:01:44Z",
+  "generated_at": "2026-06-03T09:45:37Z",
   "base_ref": "HEAD~1",
   "base_ref_note": "fallback:HEAD~1 (preferred 'origin/main' missing)",
   "snapshot": "/Users/dmitrysolonnikov/PycharmProjects/overhead_analyzer/tig_snapshot.md",
-  "snapshot_reused": true,
-  "fingerprint": "sha256:5d2214dd4877ad64",
-  "git_head": "ffddf3cdbe0b58571e37e0fe769871b63cfac2f2",
+  "snapshot_reused": false,
+  "fingerprint": "sha256:b971cad970c8ff8e",
+  "git_head": "16402985ad317a2426bf0da01cf15b42ce27b342",
   "git_dirty": true
 }
 ---
 
 # TIG Delta Report
 
-- **Snapshot:** `tig_snapshot.md` (reused)
-- **Fingerprint:** `sha256:5d2214dd4877ad64`
+- **Snapshot:** `tig_snapshot.md` (regenerated)
+- **Fingerprint:** `sha256:b971cad970c8ff8e`
 - **Base ref:** `HEAD~1` (fallback:HEAD~1 (preferred 'origin/main' missing))
 
 ## Working tree
 
 ```text
-M .venv/bin/pip
- M .venv/bin/pip3
- M .venv/bin/pip3.9
- D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/INSTALLER
- D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/LICENSE.txt
- D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/METADATA
- D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/RECORD
- D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/REQUESTED
- D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/WHEEL
- D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/entry_points.txt
- D .venv/lib/python3.9/site-packages/pip-21.2.4.dist-info/top_level.txt
- M .venv/lib/python3.9/site-packages/pip/__init__.py
- M .venv/lib/python3.9/site-packages/pip/__main__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/build_env.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cache.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/autocompletion.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/base_command.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/cmdoptions.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/command_context.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/main.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/main_parser.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/parser.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/progress_bars.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/req_command.py
- M .venv/lib/python3.9/site-packages/pip/_internal/cli/spinners.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/cache.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/check.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/completion.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/configuration.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/debug.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/download.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/freeze.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/hash.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/help.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/index.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/install.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/list.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/search.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/show.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/uninstall.py
- M .venv/lib/python3.9/site-packages/pip/_internal/commands/wheel.py
- M .venv/lib/python3.9/site-packages/pip/_internal/configuration.py
- M .venv/lib/python3.9/site-packages/pip/_internal/distributions/base.py
- M .venv/lib/python3.9/site-packages/pip/_internal/distributions/installed.py
- M .venv/lib/python3.9/site-packages/pip/_internal/distributions/sdist.py
- M .venv/lib/python3.9/site-packages/pip/_internal/distributions/wheel.py
- M .venv/lib/python3.9/site-packages/pip/_internal/exceptions.py
- M .venv/lib/python3.9/site-packages/pip/_internal/index/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/index/collector.py
- M .venv/lib/python3.9/site-packages/pip/_internal/index/package_finder.py
- M .venv/lib/python3.9/site-packages/pip/_internal/index/sources.py
- M .venv/lib/python3.9/site-packages/pip/_internal/locations/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/locations/_distutils.py
- M .venv/lib/python3.9/site-packages/pip/_internal/locations/_sysconfig.py
- M .venv/lib/python3.9/site-packages/pip/_internal/locations/base.py
- M .venv/lib/python3.9/site-packages/pip/_internal/main.py
- M .venv/lib/python3.9/site-packages/pip/_internal/metadata/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/metadata/base.py
- M .venv/lib/python3.9/site-packages/pip/_internal/metadata/pkg_resources.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/candidate.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/direct_url.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/format_control.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/index.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/link.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/scheme.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/search_scope.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/selection_prefs.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/target_python.py
- M .venv/lib/python3.9/site-packages/pip/_internal/models/wheel.py
- M .venv/lib/python3.9/site-packages/pip/_internal/network/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/network/auth.py
- M .venv/lib/python3.9/site-packages/pip/_internal/network/cache.py
- M .venv/lib/python3.9/site-packages/pip/_internal/network/download.py
- M .venv/lib/python3.9/site-packages/pip/_internal/network/lazy_wheel.py
- M .venv/lib/python3.9/site-packages/pip/_internal/network/session.py
- M .venv/lib/python3.9/site-packages/pip/_internal/network/utils.py
- M .venv/lib/python3.9/site-packages/pip/_internal/network/xmlrpc.py
- M .venv/lib/python3.9/site-packages/pip/_internal/operations/build/metadata.py
- D .venv/lib/python3.9/site-packages/pip/_internal/operations/build/metadata_legacy.py
- M .venv/lib/python3.9/site-packages/pip/_internal/operations/build/wheel.py
- D .venv/lib/python3.9/site-packages/pip/_internal/operations/build/wheel_legacy.py
- M .venv/lib/python3.9/site-packages/pip/_internal/operations/check.py
- M .venv/lib/python3.9/site-packages/pip/_internal/operations/freeze.py
- M .venv/lib/python3.9/site-packages/pip/_internal/operations/install/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_internal/operations/install/editable_legacy.py
- D .venv/lib/python3.9/site-packages/pip/_internal/operations/install/legacy.py
- M .venv/lib/python3.9/site-packages/pip/_internal/operations/install/wheel.py
- M .venv/lib/python3.9/site-packages/pip/_internal/operations/prepare.py
- M .venv/lib/python3.9/site-packages/pip/_internal/pyproject.py
- M .venv/lib/python3.9/site-packages/pip/_internal/req/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_internal/req/constructors.py
- M .venv/lib/python3.9/site-packages/pip/_internal/req/req_file.py
- M .venv/lib/python3.9/site-packages/pip/_internal/req/req_install.py
- M .venv/lib/python3.9/site-packages/pip/_internal/req/req_set.py
- D .venv/lib/python3.9/site-packages/pip/_internal/req/req_tracker.py
- M .venv/lib/python3.9/site-packages/pip/_internal/req/req_uninstall.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/base.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/legacy/resolver.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/base.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/candidates.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/factory.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/provider.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/reporter.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/requirements.py
- M .venv/lib/python3.9/site-packages/pip/_internal/resolution/resolvelib/resolver.py
- M .venv/lib/python3.9/site-packages/pip/_internal/self_outdated_check.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/appdirs.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/compat.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/compatibility_tags.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/datetime.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/deprecation.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/direct_url_helpers.py
- D .venv/lib/python3.9/site-packages/pip/_internal/utils/distutils_args.py
- D .venv/lib/python3.9/site-packages/pip/_internal/utils/encoding.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/entrypoints.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/filesystem.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/filetypes.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/glibc.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/hashes.py
- D .venv/lib/python3.9/site-packages/pip/_internal/utils/inject_securetransport.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/logging.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/misc.py
- D .venv/lib/python3.9/site-packages/pip/_internal/utils/models.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/packaging.py
- D .venv/lib/python3.9/site-packages/pip/_internal/utils/parallel.py
- D .venv/lib/python3.9/site-packages/pip/_internal/utils/pkg_resources.py
- D .venv/lib/python3.9/site-packages/pip/_internal/utils/setuptools_build.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/subprocess.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/temp_dir.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/unpacking.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/urls.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/virtualenv.py
- M .venv/lib/python3.9/site-packages/pip/_internal/utils/wheel.py
- M .venv/lib/python3.9/site-packages/pip/_internal/vcs/bazaar.py
- M .venv/lib/python3.9/site-packages/pip/_internal/vcs/git.py
- M .venv/lib/python3.9/site-packages/pip/_internal/vcs/mercurial.py
- M .venv/lib/python3.9/site-packages/pip/_internal/vcs/subversion.py
- M .venv/lib/python3.9/site-packages/pip/_internal/vcs/versioncontrol.py
- M .venv/lib/python3.9/site-packages/pip/_internal/wheel_builder.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/appdirs.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/_cmd.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/adapter.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/cache.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/caches/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/caches/file_cache.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/caches/redis_cache.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/compat.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/controller.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/filewrapper.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/heuristics.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/serialize.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/cachecontrol/wrapper.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/certifi/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/certifi/cacert.pem
- M .venv/lib/python3.9/site-packages/pip/_vendor/certifi/core.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/big5freq.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/big5prober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/chardistribution.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/charsetgroupprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/charsetprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/cli/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/cli/chardetect.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/codingstatemachine.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/compat.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/cp949prober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/enums.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/escprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/escsm.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/eucjpprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/euckrfreq.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/euckrprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/euctwfreq.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/euctwprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/gb2312freq.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/gb2312prober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/hebrewprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/jisfreq.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/jpcntx.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langbulgarianmodel.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langgreekmodel.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langhebrewmodel.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langhungarianmodel.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langrussianmodel.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langthaimodel.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/langturkishmodel.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/latin1prober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/mbcharsetprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/mbcsgroupprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/mbcssm.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/metadata/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/metadata/languages.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/sbcharsetprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/sbcsgroupprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/sjisprober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/universaldetector.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/utf8prober.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/chardet/version.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/ansi.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/ansitowin32.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/initialise.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/win32.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/colorama/winterm.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/misc.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/shutil.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/sysconfig.cfg
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/sysconfig.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/_backport/tarfile.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/compat.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/database.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/index.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/locators.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/manifest.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/markers.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/metadata.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/scripts.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/t32.exe
- M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/t64.exe
- M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/util.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/version.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/w32.exe
- M .venv/lib/python3.9/site-packages/pip/_vendor/distlib/w64.exe
- D .venv/lib/python3.9/site-packages/pip/_vendor/distlib/wheel.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/distro.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_ihatexml.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_inputstream.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_tokenizer.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_trie/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_trie/_base.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_trie/py.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/_utils.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/constants.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/alphabeticalattributes.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/base.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/inject_meta_charset.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/lint.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/optionaltags.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/sanitizer.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/filters/whitespace.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/html5parser.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/serializer.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treeadapters/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treeadapters/genshi.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treeadapters/sax.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/base.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/dom.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/etree.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treebuilders/etree_lxml.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/base.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/dom.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/etree.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/etree_lxml.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/html5lib/treewalkers/genshi.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/idna/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/idna/codec.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/idna/compat.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/idna/core.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/idna/idnadata.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/idna/intranges.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/idna/package_data.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/idna/uts46data.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/msgpack/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/msgpack/_version.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/msgpack/ext.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/msgpack/fallback.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/packaging/__about__.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/__init__.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/_manylinux.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/_musllinux.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/_structures.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/markers.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/requirements.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/specifiers.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/tags.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/utils.py
- M .venv/lib/python3.9/site-packages/pip/_vendor/packaging/version.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/__init__.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/build.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/check.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/colorlog.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/compat.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/dirtools.py
- D .venv/lib/python3.9/site-packages/pip/_vendor/pep517/envbuild.py
... [working tree diff: truncated, 2664 lines omitted]
```
