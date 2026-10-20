# Entropy Architecture Handbook

# Stage 7 — Execution Nodes

Version: 1.0

Status: Implemented (remote nodes over SSH + agent)

---

# Purpose

Workflows run on **nodes**. The server Entropy is installed on is always
the `local` node, also called the **main node**: it stores users, roles,
the Vault, workflows, plugins and run history, serves the web UI, and
fires schedules. Any number of **remote nodes** can be added; each runs
an Entropy agent that executes runs the main node hands it.

---

# Adding a node

Nodes → **+** opens *Add node*. Entropy needs:

| Field | Notes |
|---|---|
| Node name | Lowercase letters, digits, `.`, `_`, `-`. Cannot be `local`. |
| Host, SSH port, SSH user | The account the agent will run as. No root access is required. |
| Sign in with | A password, a private key (optional passphrase), or the SSH keys of the account running Entropy. |
| Main node URL | How **the node** reaches the main node, e.g. `https://entropy.example.com`. |
| Advanced | Python choice, concurrent runs, install directory (default `~/.entropy-agent`), a CA certificate, TLS verification. |

**Credentials are used for the setup only and never stored or logged.**
A password or passphrase reaches `ssh` through a private askpass helper;
a private key is written to a mode-0600 file in a private temporary
directory that is deleted when the setup ends. After setup the node is
authenticated by its own random token, stored on the main node only as
a SHA-256 hash.

Host keys are trusted on first use and pinned in
`~/.entropy/ssh/known_hosts` on the main node. A changed key fails the
connection; tick *Forget the saved host key* when setting a rebuilt
server up again.

---

# What setup does

Setup runs in the background and its progress is shown live (and kept
under *Last setup log*). Over one multiplexed SSH connection it:

1. Inspects the server: OS, architecture, home, free space, Python
   interpreters and whether systemd user services or cron are available.
2. Chooses Python. Entropy's vendored wheels are built for CPython 3.9,
   so a server Python **3.9 with pip** is used if present; otherwise a
   relocatable CPython 3.9 (python-build-standalone, checksum-verified)
   is shipped. Offline main nodes can place the archive in
   `~/.entropy/node-cache/`. *Always the server's Python* uses any
   Python ≥ 3.9 and installs packages from the package index.
3. Uploads the Entropy runtime (code + Linux wheels, about 8 MB; cached
   by content hash, so unchanged runtimes are not uploaded again).
4. Installs the Python packages (without the web server) into the
   agent's own site-packages.
5. Initialises the agent's own Entropy home (`<dir>/home`): config and a
   local job database. Re-running setup keeps its history.
6. Writes `agent.json` (mode 0600) with the node token, installs
   `bin/entropy-agent` and `bin/agent-ctl start|stop|status`, and
   registers the agent with a systemd user service (with lingering when
   allowed) or, failing that, cron `@reboot`.
7. Starts the agent and waits for its first heartbeat.

If setting an existing node up again fails, the previous agent is
restarted, so the node keeps running as before.

```
~/.entropy-agent/
    agent.json        node, main node URL, token (0600)
    bin/              entropy-agent, agent-ctl
    python/           bundled CPython (only when shipped)
    runtime/          Entropy code and wheels
    home/             the agent's Entropy home (config, job database)
    workspace/        run workspaces
    agent.log         agent log
```

---

# How remote runs work

```
Browser ──start run (node=edge-1)──▶ Main node ──queues──▶ node_jobs
                                         ▲                   │ claim (long poll)
                                         │ events, console,  ▼
                                         └── state, stop ◀── Agent on edge-1
                                                              │ runs the workflow with
                                                              ▼ Entropy's own engine
```

* The main node records the run as usual (Runs page, live screen) and
  queues it for the node with the definition, variables, the requesting
  user's identity and the digests of the plugins it needs.
* The agent claims it, acknowledges at once, fetches any plugin whose
  digest differs from its cached copy, and starts it with Entropy's
  workflow engine **as the requesting user** (a session issued for that
  run only).
* Every second it streams the run's events, console output and state
  back; the live run screen updates exactly as for local runs.
* **Stop** reaches the agent within seconds; it interrupts the worker's
  whole process group, so commands a step started stop too.
* An agent restart resumes forwarding runs that kept executing. A claim
  never acknowledged (e.g. answered to an agent that had just stopped)
  is handed out again after 15 seconds.
* Runs on a node not heard from for 5 minutes, or on a removed node,
  fail with an explanatory message.

Agents call the main node's `/api/agent/*` endpoints with
`Authorization: Bearer <token>`; the heartbeat (every 15 s) reports CPU,
memory, disk, load and uptime for the Nodes page and the Prometheus
endpoint.

---

# Operating nodes

| Action | Where | Effect |
|---|---|---|
| Disable / Enable | Node menu | A disabled node takes no new runs. |
| Set up again | Node menu | Asks for credentials, updates the runtime, issues a new token (revoking the old one). |
| Last setup log | Node menu | The most recent setup or removal, step by step. |
| Remove node | Node menu | Revokes the token at once (the agent exits); optionally signs in to uninstall it. |

On the node itself: `~/.entropy-agent/bin/agent-ctl status`, and
`kill -USR1 <agent pid>` writes every agent thread's stack to
`agent.out` for diagnosis.

---

# Security notes

* Use an `https://` main node URL. With plain HTTP the node token
  travels in clear text; the UI warns about this for non-local URLs.
* The agent runs as the SSH user given at setup, with that user's
  permissions; runs on the node can do what that user can.
* Plugins are shipped to nodes from the main node and verified by
  SHA-256 before installation.

---

# Run options: steps, tags and a node per step

The run dialog's **Advanced** section (collapsed by default) narrows and
spreads a workflow run:

| Option | Effect |
|---|---|
| Only steps tagged … | Runs only enabled steps carrying any of the chosen tags. |
| Step checkboxes | Leave steps out of this run. |
| Node per step | Runs that step on another node; unset steps use the run's node. |

Steps always run one after another in workflow order. The server checks the
selection before starting: a selected step that reads
`${steps.<step>.outputs.<key>}` from a step that is not selected is refused,
with the reason shown in the dialog (`POST /api/workflows/{name}/plan`
previews the plan; `POST /api/workflows/{name}/run` accepts `steps`,
`tags` and `step_nodes`).

## Runs across several nodes

Consecutive steps on the same node form a **segment**. A run with one
segment is an ordinary job (with a trimmed definition when steps were left
out). A run with several segments is coordinated by the main node
(`lib/runs/coordinator.py`):

1. The run is a job with no process of its own (`run_metadata.heartbeat_at`
   marks it); each segment is an ordinary job on its node, linked by
   `run_metadata.parent_job_id` and hidden from run lists and counts.
2. Each segment receives the workflow reduced to its steps. References to
   outputs of earlier segments are replaced by the values those steps
   produced (taken from their `plugin_result` events), so agents need no
   changes to take part.
3. A segment that fails or is stopped ends the run; stopping the run stops
   the running segment. If the main node stops following the run (no
   heartbeat for 60 s, e.g. after a restart), reconcile fails it.

The run screen merges the segments' events and logs, and records the plan
the run used (`run_metadata.options`: tags, selected and skipped steps,
node per step, dependencies, input names but never input values). It shows
the plan above the progress cards, tags on each card, and a **Diagram**
view: a draggable bubble per step, dashed arrows for execution order and
solid arrows for the step outputs each step reads.

# Permissions for workflows and plugins

| Action | Needs |
|---|---|
| View workflows and runs | `workflows.list` |
| Create, import, edit a workflow | `workflows.add` / `workflows.edit` **and** `plugins.list`; every step's plugin must be installed and enabled |
| Delete a workflow | `workflows.edit` |
| Run a workflow | `workflows.start` |
| Run a plugin directly (test run) | `plugins.run` |

A saved workflow is what grants its plugins: running it needs no plugin
permission, the way a CI job's runner does not need rights to every tool
the job uses. Choosing plugins is the privileged act, so authoring needs
`plugins.list`. The Workflows page disables what the user may not do and
says why on hover; the run dialog explains why **Start run** is unavailable.
