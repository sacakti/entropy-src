# Changelog

## 3.3.0 - 2026-11-03

### New

- Vision: a live activity bar for running plugins and workflows, with broadcast messages from Administration
- Download any run as an HTML or PDF report that looks like the run page
- Run again for plugin runs, with the earlier inputs filled in
- Task descriptions with headings, bold, italic, strikethrough, checklists and tables, and a preview
- Recurring due dates and reminders, with a calendar and time picker
- Task reports download as real PDF files, with images included
- Gallery view and custom icons for plugins and workflows
- Clash can compare two Oracle databases, both structure and data
- Consolidation of images, configuration and database scripts across releases, as one workflow
- Live OpenShift pod metrics, as an app plugin

### Improved

- Create release: search artifacts and see the latest first, five at a time
- Release Manager can delete releases, promotions and their history
- Select the current page or everything on paginated lists, with keyboard shortcuts
- The Modal backdrop setting now controls how solid all panels are; installs without wallpapers start fully solid
- Tasks update live, and followers are told about changes straight away
- Schedule names only need to be unique within a project
- Enable or disable plugins, and see the system tools each one needs
- What's new after an upgrade, and all release notes on the About page
- Lazy-loaded pages for faster starts
- The server runs on Python 3.13

### Fixed

- Text no longer shows through menus and panels with Liquid Glass on
- Creating a task no longer fails with a server error when it has no assignee
- People assigned or mentioned on a task are notified, and notifications open that task
- The due date field in the task panel is shown in full
- Switching project leaves a run from another project
- Image transfer no longer cleans Docker images; the Docker plugins do that
- Consistent last sign-in, CLI sign-ins and a working idle timeout

## Reworded

- Wallpapers as files, lazy-loaded pages, gzip assets, pause hidden videos => Lazy-loaded pages
