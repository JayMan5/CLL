# CourtLOG UI Upgrade Task List

**Created:** 2 October 2026

**Status:** active — the first shell, dashboard, case-intake, and install-guidance slice is implemented; the automated viewport/browser regression (UI-17) passed. Cross-role review, accessibility/zoom review, and physical-device acceptance remain open.

**Evidence:** the supplied desktop screenshots of the Chief Registrar dashboard and browser install prompt, plus committed fictional-data Chromium screenshots and measurements in [`docs/viewport-evidence/`](docs/viewport-evidence/). Fresh test outputs are recreated under ignored `.local/viewport-pass/`.

**Goal:** make the next action, current role, and case state obvious without hiding important information or changing permissions/legal workflow.

## What looks confusing in the supplied screenshots

| Area | Observed issue | Planned response |
|---|---|---|
| Top bar | The page has an access-level selector, a separate user/profile card, a registry clock, a summary export button, an install button, and a refresh/sweep action. Role and identity are repeated; the selector looks interactive even though authorization comes from the signed-in account. | Establish one compact identity/role display and show only the page's relevant actions. Keep workflow sweep/export secondary and clearly labelled. |
| Sidebar | Several long labels compete for attention, and administrative, operational, and analytical views are in one flat list. | Group navigation by task, shorten labels without losing meaning, keep the active page obvious, and collapse it into a drawer on small screens. Preserve server-side authorization. |
| Dashboard | Three attention cards are followed by five metric cards; the same alert concepts appear in both places. The chart and case-registration form compete side by side, pushing the form below the initial viewport. | Put actionable work first, avoid duplicate counts, make the case list/work queue primary, and move registration and lower-priority analytics into clearer destinations. |
| Status language | Experimental risk, idle-custody prompts, missing-file reports, and the execution review prompt sit close together and use similarly urgent colors. | Improve grouping and labels so prototype prompts are not mistaken for legal findings or proof that a file is missing. Give each action one clear destination. |
| Install prompt | The second screenshot is the browser/OS's native PWA install dialog, not an in-page modal. It uses the current local origin (`127.0.0.1:8000`) and the manifest name currently includes “Sheriff Custody Check-In,” although the same shell shows all roles. | Decide whether the installable product is the whole registry shell or a Sheriff-focused app; make the manifest and in-app help consistent. The browser controls the native dialog's styling and origin/publisher text; do not try to style it with page CSS. |

## Recommended page hierarchy

1. **Header:** page title, one read-only role/scope indicator, one account menu, and at most one primary action relevant to the current page.
2. **Needs attention:** a short, prioritized list of actual open tasks with counts and direct links. Keep idle-custody prompts, explicit missing-file reports, DCR review, and execution review distinct.
3. **At-a-glance metrics:** a compact row with non-duplicated counts; explain prototype/experimental measures in their labels.
4. **Primary work area:** a searchable, filterable case/work queue with useful empty/loading/error states.
5. **Secondary analysis:** charts and experimental risk explanation below the work queue or in the existing analysis view.
6. **Case creation:** a clearly named, dedicated form view/modal/drawer instead of a competing dashboard card. Preserve the authenticated Clerk court default already added.

This is a starting layout recommendation, not a final design mockup. Confirm it with a short role-by-role walkthrough before implementation.

## P0 — Clarify roles, navigation, and the application shell

- [ ] **UI-01 — Map the top tasks for each role.** Document the first three tasks and permitted views for Sheriff, Clerk, Judge, DCR, and Chief Registrar. Use this map to decide what belongs in the sidebar and what belongs in page actions.
- [x] **UI-02 — Simplify the global header.** Show the authenticated role/scope once as non-editable information; keep account/profile and sign-out together; move Registry Clock and secondary actions out of the primary action cluster. Do not display a role control that implies staff can switch identity.
- [x] **UI-03 — Reorganize navigation.** Group work queues (custody, hearings, review, execution), insights, and administration. Shorten labels, retain accessible names, mark the current destination, and use a keyboard-accessible mobile drawer. Do not rely on hidden UI as an authorization boundary; keep API permission checks unchanged.
- [x] **UI-04 — Establish page layout and spacing rules.** Use a consistent content max-width, spacing scale, heading hierarchy, card padding, button sizes, and responsive grid. Reduce excess visual effects where they compete with text or controls.

## P1 — Make the dashboard scannable and task-oriented

- [x] **UI-05 — Prioritize one attention area.** Replace the duplicated alert-card/KPI presentation with a concise “Needs attention” area whose actions navigate to the relevant filtered list. Keep each count tied to a defined status.
- [x] **UI-06 — Reduce and clarify dashboard metrics.** Limit the first metric row to a small set of non-duplicated values. Give experimental risk and configured workflow prompts explicit prototype wording; never present them as approved legal conclusions.
- [x] **UI-07 — Give the case worklist priority.** Put search, filters, and the case table/work queue before secondary analytics. At narrow widths, reflow rows into readable cards or a controlled horizontal table region rather than shrinking text.
- [x] **UI-08 — Separate case registration from analytics.** Move “Register a Case File” to a dedicated view or an accessible drawer/modal with a clear open/close path. Keep the authenticated Clerk's court default and API validation. Do not change phone-field requiredness, consent policy, hearing rules, or execution rules as part of a visual redesign without the relevant review.
- [x] **UI-09 — Normalize alert presentation.** Use a consistent icon, label, explanation, and action for each alert. Do not use color alone to communicate severity. Preserve the distinction between an idle-custody prompt and an explicitly reported missing file.

## P1 — Make the installable PWA easier to understand

- [x] **UI-10 — Confirm the installed-app identity.** Decide whether the PWA represents all of CourtLOG or a Sheriff-only custody workflow; then align `frontend/manifest.webmanifest`, app title, icon, and installation instructions. Do not claim the install dialog is customizable—the browser owns that dialog.
- [x] **UI-11 — Keep install invitation deliberate.** Show an in-app install action only when the browser supports it; explain the iPhone/iPad “Add to Home Screen” path separately. Never auto-open the native prompt on page load. Explain that `127.0.0.1:8000` is expected for a local demo; a hosted origin depends on a separately selected/approved host.
- [x] **UI-12 — Clarify install and offline status.** Add clear success/dismissed/help states near the install action. Preserve the existing truthful rule: the PWA shell may be available offline, but custody scans are not stored or queued offline.

## P2 — Improve forms, tables, and accessibility

- [ ] **UI-13 — Standardize form feedback.** Use consistent inline validation, loading, success, and recoverable error states. Replace disruptive `alert()`/`prompt()` flows with accessible app dialogs/toasts where appropriate; do not report success before the server confirms it.
- [ ] **UI-14 — Standardize tables and empty states.** Align column labels, row actions, status badges, search/filter placement, pagination or large-list behavior, and empty/error/loading messages across views.
- [ ] **UI-15 — Complete keyboard and screen-reader pass.** Add/verify visible focus, meaningful labels, logical tab order, dialog focus management, announcements for asynchronous status, minimum touch targets, and text contrast. Do not use color as the only indicator.
- [ ] **UI-16 — Check zoom and text resilience.** Verify 200% browser zoom, long case identifiers, translated/longer role labels, and browser text-size changes without clipping or overlap.

## P2 — Responsive and visual acceptance

- [x] **UI-17 — Add viewport regression coverage.** `npm run test:viewport` passed in headless Chromium at 1600×900, 1366×768, 1024×768, 768×1024, and 390×844 using fictional API fixtures. The dashboard, attention cards, case table, mobile drawer, and case-registration form were checked; there was no page-wide horizontal overflow, and the table overflow stayed inside its scroll wrapper. Screenshots/measurements are committed in `docs/viewport-evidence/` and reproducible under ignored `.local/viewport-pass/`. This is not real-device or full accessibility acceptance.
- [ ] **UI-18 — Test role-specific screens.** Review Clerk, Sheriff, Judge, DCR, and Chief Registrar using fictional records. Confirm each sees the right controls, correct status copy, and useful empty/error states; UI changes must not widen API access.
- [ ] **UI-19 — Test the real PWA install path.** On the approved HTTPS test origin, test install/dismiss/reopen behavior on supported desktop and mobile browsers. Keep this separate from the native install-dialog styling and from final phone/printer acceptance.
- [ ] **UI-20 — Capture design review and sign-off.** Compare before/after screenshots with the team, resolve confusing labels, and record any deferred changes. Do not treat this review as legal or device acceptance.

## Acceptance checklist — keep open until demonstrated

- [ ] At 1600×900, the role, page purpose, primary action, and most important open work are immediately identifiable without duplicate status cards.
- [ ] At 390px wide and 200% zoom, navigation and primary tasks remain usable without clipped controls or accidental horizontal page scrolling.
- [ ] A user can tell the difference between an idle-custody prompt, a missing-file report, experimental risk, a DCR review, and a prototype execution prompt.
- [ ] The signed-in user's identity and permissions are clear; no control implies an unauthorized role switch.
- [ ] The native PWA prompt appears only after an intentional install action and is described as browser-controlled.
- [ ] Keyboard, focus, touch-target, contrast, loading/error/empty, and server-confirmed-success checks pass.
- [ ] Existing backend permissions, audit attribution, PWA privacy, and no-offline-scan-queue behavior still pass regression tests.
- [ ] Manual browser review is completed on the intended devices before UI acceptance is reported.

## Guardrails

- This is a UI/UX backlog only. No redesign is implemented by adding this document.
- Do not change legal thresholds, case lifecycle rules, forms, role scopes, consent requirements, or audit behavior in a visual-only change.
- Use only fictional/demo records during UI testing unless specific real-record permission is documented.
- Keep experimental/model labels truthful; keep simulations distinct from real delivery or acceptance.
- Preserve the approved PWA approach and explicitly disclose that camera/printer acceptance is a separate physical-device gate.
- Link implementation and acceptance work back to [`COURTLOG_COMPLETION_PLAN.md`](COURTLOG_COMPLETION_PLAN.md) and current code status in [`STATUS.md`](STATUS.md).
