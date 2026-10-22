# Entropy Architecture Handbook

# Stage 11 — Projects, Roles, Sign-in and Administration

Version: 1.0

Status: Implemented

---

# Purpose

Make it obvious who can do what, and where:

- **Projects** group workflows, schedules, runs and nodes. People get a
  role *in a project*; what they may do in one project says nothing about
  another.
- **Roles** are named bundles of permissions. Entropy ships sensible
  built-in roles; administrators add their own.
- **Sign-in** with Entropy's own passwords, LDAP / Active Directory, or
  single sign-on (OpenID Connect: Keycloak, Azure AD / Entra ID, Okta …).
- **Administration** is for running Entropy itself: projects, people,
  nodes, settings (e-mail, sign-in, retention) and upgrades.

---

# Projects

Every workflow, schedule, run and draft belongs to exactly one project.
Existing installations get a **Default** project that holds everything
that existed before projects did.

The project switcher in the top bar picks the *current project*. The web UI
sends it with every request (`X-Entropy-Project` header); lists show that
project's items, and new items are created in it. People see only the
projects they belong to (administrators see all).

A project's members are users or groups, each with one project role.

## Vault namespaces

Vault namespaces belong to a project too: the Vault page shows the current
project's namespaces, new ones are created in it, and another project's
namespace cannot be opened from here. A run reads secrets only from its own
project's namespaces (`${entv:namespace/key}` to another project's namespace
fails with "belongs to another project"). Namespaces made before projects
existed belong to Default. Namespace names stay unique across projects.

## Nodes

A node is either

- **shared** — any project may run on it (the default), or
- **assigned** — only the projects it is assigned to may run on it.

Node administrators set this in *Administration → Nodes → Access*. A run is
refused before it starts when its project may not use the chosen node.

---

# Roles

A role has a **scope**:

| Scope   | Given                          | Holds                                           |
|---------|--------------------------------|-------------------------------------------------|
| global  | to a user or group             | administration permissions, plugins, vault      |
| project | to a project member (in a project) | work inside the project: workflows, schedules, runs |

Built-in roles cannot be changed or removed:

| Role               | Scope   | Can                                                        |
|--------------------|---------|------------------------------------------------------------|
| Administrator      | global  | everything, in every project                               |
| User administrator | global  | users, groups, roles, projects and their members           |
| Node administrator | global  | add, set up and remove nodes; assign them to projects      |
| Plugin developer   | global  | create, install, change and remove plugins                 |
| Vault user         | global  | use the vault                                              |
| Viewer             | project | see workflows, schedules and runs                          |
| Operator           | project | Viewer, and run workflows and plugins                      |
| Developer          | project | Operator, and create and change workflows and schedules    |
| Maintainer         | project | Developer, and delete them and manage the project's members|

Custom roles pick any permissions their scope allows. A user's permissions
in a project are their global roles' plus the project roles given to them
or to their groups in that project.

## Upgrading from the earlier model

The first start after upgrading converts the old per-module type roles
(`workflows-read`, …) and directly granted privileges: unused generated
roles are removed, used ones become custom roles, and project-type grants
become memberships of the Default project, so nobody loses access.

---

# Sign-in

## Entropy passwords

Local accounts sign in with their Entropy password, as before. The
bootstrap `admin` is always a local account.

## LDAP / Active Directory

*Administration → Settings → LDAP / Active Directory.*

1. Entropy binds with the service account (bind DN and password; empty for
   an anonymous search) and finds the user under the base DN with the user
   filter — `(uid={username})` for OpenLDAP,
   `(sAMAccountName={username})` for Active Directory.
2. It then binds as the user's entry with the password they typed. Empty
   passwords are always refused.
3. First-time users get an Entropy account (unless *Create accounts* is
   off) with their name and e-mail from the directory.

Use `ldaps://` or STARTTLS outside trusted networks. **Test with an
account** shows what Entropy finds for a user, and which Entropy groups
they would join, before anyone relies on it.

## Single sign-on (OpenID Connect)

*Administration → Settings → Single sign-on.* Register Entropy at the
identity provider as a confidential web client with the redirect URI shown
on that page:

```
https://<entropy address>/api/auth/oidc/callback
```

Give Entropy the issuer URL, client ID and secret. The login page then
shows a **Sign in with …** button. Entropy uses the authorization code flow
with PKCE, and checks the ID token's signature (from the provider's
published keys), issuer, audience, expiry and nonce. The sign-in is tied to
the browser that started it.

Set *Address* (Administration → Settings → Address) to the URL people use
when Entropy is behind a proxy, so the redirect URI and e-mail links are
right.

## Groups from the directory or identity provider

Group mappings join users to Entropy groups when they sign in: an LDAP
group (by DN or CN, from `memberOf`) or an identity provider group (from
the `groups` claim). Give the Entropy groups their roles and project
memberships as usual. Only mapped groups are managed this way: memberships
given by hand in Entropy stay.

## Accounts and safety

- A directory or SSO account is linked to one Entropy user, by the entry's
  DN or the token's subject. Linked users sign in only at their provider;
  their Entropy password is random and unknown, and password changes are
  refused.
- An existing local account is never taken over by an outside identity
  with the same name (a directory `admin` cannot become Entropy's `admin`).
- Disabling a user in Entropy blocks them whatever the provider says.

---

# E-mail and run alerts

*Administration → Settings → E-mail* sets the SMTP server (STARTTLS, SSL or
none; optional sign-in). **Send test** checks it.

Each workflow and schedule has **E-mail alerts** (the bell on its row):
the addresses to write to, and for which outcomes — completed, failed,
cancelled. A workflow's alerts cover all its runs (UI, schedules, CLI); a
schedule's cover that schedule's runs. Failed runs include the last lines
of their output and a link to the run.

Every finished run also adds a notification for the person who started it.

---

# Data retention

*Administration → Settings → Data retention:*

- finished runs older than *Archive after* days are moved to the archive;
- archived runs older than *Delete archive after* days are deleted;
- notifications older than *Keep notifications* days are deleted
  (0 keeps them).

Housekeeping runs in the background; **Run now** applies the settings
immediately.

---

# Secrets

The SMTP password, LDAP bind password and OIDC client secret are encrypted
with the vault's master key and never sent back to the browser — the API
only says whether one is set.

---

# Moving work between projects

Select workflows (or schedules) and choose **Move or copy**:

- **Move** changes the project; names, history and alerts stay. The
  schedules that run moved workflows can come along.
- **Copy** creates new workflows with a free name (`deploy-2`), because
  workflow names are unique across Entropy. Copied schedules start paused.

Moving needs write and delete rights in the source project and write rights
in the target; copying needs read in the source and write in the target.

# Project dumps

*Administration → Projects*, on a project's row:

- **Dump** downloads a zip with the project's workflows, its schedules, the
  plugins its workflows use, and (optionally) vault namespaces encrypted
  with a passphrase.
- **Restore** reads a dump into a project — on this Entropy or another one.
  It first shows what is inside; nothing changes until you confirm. When a
  workflow name exists you choose: restore under a new name, keep the
  existing one, or replace it (its old version stays in History).
  Schedules come back paused. Plugins are installed only where missing;
  installed plugins are never replaced by a restore.

# Vault export and import

The Vault page's export button downloads chosen namespaces as an
`.entvault` file, encrypted with a passphrase (at least 12 characters;
scrypt and AES-256-GCM). Entropy's own key never leaves the server, so the
file can be imported into any Entropy that is given the passphrase.
Importing creates missing namespaces (owned by you) and keeps existing
secrets unless you ask to replace them.

# Plugins shipped with a release

Each Entropy release brings plugins in `resources/plugins`. The server
compares them with the installed plugins at start and every hour. People
who may install plugins (`plugins.write`) get one notification per new
plugin version, and the Plugins page shows what is new or newer. Nothing is
installed until someone picks it; an upgrade keeps the previous version in
the plugin's History. Installed plugins newer than the bundled ones are
left alone.

# Tools: EagleAPI

EagleAPI (Tools → EagleAPI) keeps everything per project: collections, TLS
profiles, the environment's vault namespace (`eagleapi-<project key>`) and
history. A project with EagleAPI collections cannot be deleted until they
are exported and deleted; its TLS profiles and history go with it.

- **Collection access.** A collection (top-level folder or request) is open
  to everyone in the project, whose project role decides what they may do.
  Its owner (who created it) can restrict it under *Access…*: then only the
  owner, administrators and the project members or groups chosen there see
  it, with *Can use* (read and send) or *Can change*.
- **History.** Each person's sent requests and responses are kept for them
  alone (the newest 500 per project), with secrets masked as on screen.
  They can turn it off, search it, delete chosen entries or all of it, and
  export it as EagleAPI JSON or HAR 1.2.
- **Export and import.** Collections export as EagleAPI, Postman v2.1 or
  SoapUI projects, and import from those and Insomnia v4. *Preserve
  settings* keeps auth, TLS, polling and options (and, in EagleAPI's own
  format, the TLS profiles). Vault values never leave the vault: references
  become the other tool's variables (`{{KEY}}`, `${#Project#KEY}`) and back,
  and paths use a `baseUrl` variable for the environment's base URL.

# Extensions (Python libraries for plugins)

*Extensions* (beside Plugins, and `ent extension`) installs the Python
libraries plugins need: from the package index (a version or range; the
default index pip is configured with, or one given), or your own file — a
wheel, a source archive, a `.py` module or a zipped package folder (the
last two get a name and version). Viewing needs `extensions.list`;
installing and removing need `extensions.install` (Plugin developer has
both).

- **Versions side by side.** Each version lives in its own folder,
  `extensions/libs/<name>/<version>/`, with the wheels it came from.
  Dependencies Entropy already has at the very same version are shared, not
  copied.
- **Entropy's own libraries** are listed under *In Entropy*. Installing one
  at the version Entropy has is refused ("already part of Entropy"); another
  version installs alongside.
- **Plugins** list what they need under `dependencies` in `plugin.json`:
  `{"name": "paramiko", "version": "3.0"}` (exactly 3.0), a range such as
  `">=2,<3"`, or no version. A requirement is met by Entropy's own library
  when its version fits, else by the newest fitting extension version.
  Installing a plugin whose libraries are missing fails, and says which;
  the web UI checks first and offers to install them. A reinstall checks
  before it removes anything.
- **At run time** the chosen versions go first on the plugin's import path.
  One run is one process: two plugins in it that need different versions of
  the same library are refused with a clear message. Libraries Entropy has
  already loaded (for example `cryptography`) stay Entropy's version in that
  process.
- **Nodes** fetch the versions their plugins need from the server, as
  wheels, and install them the same way.
- A version installed plugins still need cannot be removed.

# Database safety

Everything Entropy knows lives in `entropy.db` (SQLite). See
*Administration → Settings → Database* and `ent database`.

- **One server per database.** The web server holds an exclusive lock on
  `entropy.db.lock`; a second server on the same database refuses to start.
  Workflow workers and the command line still use the database.
- **Guard against deletion.** `.entropy.db.guard` is a hard link to the
  same data. If `entropy.db` is deleted, the server puts it back within
  seconds with nothing lost; if the guard was deleted too, it rebuilds the
  file from its open connection. Any process that finds the database
  missing puts it back before opening it, so an empty database never
  silently replaces the real one. (The guard sits in the same folder: it
  does not help against losing the whole folder or disk; backups do.)
- **Backups.** Every few hours (default 6; 28 kept) the server makes a
  consistent online copy with SQLite's backup API and keeps it only if it
  passes `PRAGMA integrity_check`. Put them on another disk: the backup
  folder, interval and count are set in the Database settings (stored in
  `database-safety.json` beside the database, as they must survive it) or
  with `ENTROPY_DB_BACKUP_DIR`.
- **Checks and recovery.** The server checks the database when it starts.
  A damaged one is moved aside (`entropy.db.damaged-<time>`) and the newest
  good backup takes its place; without a good backup the server does not
  start. Administrators are notified of every recovery.
- **Restore by hand.** With the server stopped: `ent database restore`
  (newest good backup) or `ent database restore <name>`; the replaced file
  is kept beside it. `ent database` works without signing in, as it must
  when the database is the problem; it needs access to the files.

