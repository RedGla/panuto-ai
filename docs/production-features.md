# Offline product features

Panuto remains a single-user app bound to localhost. Personal organization is separate from AI-extracted instructions so completing or archiving a task never changes the announcement or its revision history.

## Implemented

- Task status: To do, In progress, and Done.
- Low, Normal, and High priorities; personal notes.
- Archive and unarchive without deleting source history.
- Search across subjects, activities, requirements, and notes.
- Subject, status, deadline, and archive filters; deadline and priority ordering.
- Open, overdue, and due-today summaries; pages of 20 activities.
- Edit all saved instruction fields with explicit confirmation and a new version.
- Manual activity entry without starting or calling Ollama.
- CSV export of the filtered list, with spreadsheet formula protection.
- Calendar export of open, dated activities; all-day events or local floating deadline times.
- Portable ZIP backup with confirmed versions, source text, available original images/PDFs, and organization.
- Validated, additive backup recovery. Existing activities are preserved; recovering twice adds duplicate copies.
- On-demand checks for storage, Python, local model, and OCR languages.
- In-app onboarding, recovery explanations, and source/AI limitations.

No new packages are required. The task_state SQLite table is created additively when the app starts. Existing activities default to To do, Normal priority, and active. The original extraction contract is unchanged.

## Data recovery

Prepare and download a backup from Backup & setup. The ZIP is a snapshot at the time Prepare backup is clicked. Prepare another after editing data.

Recovering a ZIP shows its activity count and requires explicit confirmation. Recovery validates the manifest, task schema, dates, version order, attachment paths, ZIP CRCs, entry sizes, and total expanded size before writing. It creates new IDs and preserves confirmed history. Failed database writes roll back and newly copied files are removed.

Backup limits are 50 MB compressed and 100 MB expanded; original files are limited to 20 MB each. Missing originals are reported in source warnings and their text is retained. For larger collections, stop the app and back up the entire data directory.

Calendar events use the importing calendar's local timezone. Calendar reminders depend on that calendar's settings. Panuto's due indicators update while the app is open; they are not background OS notifications.

## Inspiration

- [Vikunja on GitHub](https://github.com/go-vikunja/vikunja), with [documented priorities, filters, due dates, and task organization](https://vikunja.io/features/).
- [Tasks.org on GitHub](https://github.com/tasks/tasks), an established personal task manager.

These projects informed feature selection. No source code or assets were copied.

## Remaining production work

This is an improved offline prototype, not a claim of complete production readiness. Background notifications, recurring tasks, per-requirement checklists, signed desktop installers/automatic updates, encrypted storage/backups, independent evaluation on real announcements, and accessibility testing remain future work.

Accounts, team sharing, remote hosting, and cloud synchronization are outside the chosen single-user offline scope. Physical Wi-Fi-off verification and timed presentation rehearsals remain outstanding.
