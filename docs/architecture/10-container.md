# Entropy Architecture Handbook

# Stage 10 — Container Image (UBI 9) and OpenShift

Version: 1.0

Status: Implemented (image layout and start-up verified; the UBI build itself
must be run where registry.access.redhat.com is reachable)

---

# The image

`Dockerfile` (repository root) builds on Red Hat UBI 9 with its Python 3.9:

| Stage | Base | Produces |
|---|---|---|
| `ui` | `ubi9/nodejs-22` | the web UI (`npm ci && npm run build`) |
| `python` | `ubi9/ubi` | a virtual environment with `resources/wheels/requirements.txt` |
| final | `ubi9/ubi` | application in `/opt/entropy/app` (read only), venv, tools |

```sh
podman build -t entropy:1.1.2 .
# without Oracle tools, or a pinned oc:
podman build -t entropy:1.1.2 --build-arg INSTALL_SQLPLUS=0 --build-arg OC_VERSION=stable-4.18 .
```

On OpenShift without a local container engine:

```sh
oc new-build --name entropy --strategy docker --binary
oc start-build entropy --from-dir . --follow
```

The image runs as any UID in group 0 (OpenShift's `restricted-v2` SCC);
nothing in the application directory is written at runtime.

## Included tools

| Build argument | Tool | Notes |
|---|---|---|
| `INSTALL_OC=1`, `OC_VERSION=stable` | `oc`, `kubectl` | From mirror.openshift.com. Pin `OC_VERSION` (e.g. `stable-4.18`) to your cluster version. Inside the cluster `oc` can use the pod's service account; give it a Role/RoleBinding for what workflows do. |
| `INSTALL_SQLPLUS=1`, `ORACLE_IC_VERSION=23.9.0.25.07` | `sqlplus` (Oracle Instant Client basic + sqlplus) | RPMs from yum.oracle.com; `libaio` comes from the UBI repositories. Instant Client is under Oracle's Free Use Terms, which allow redistribution in an image; check them against your policy. Mount `tnsnames.ora` and set `TNS_ADMIN` if you use aliases. |
| `INSTALL_DOCKER=1`, `DOCKER_VERSION=29.9.2` | `docker` CLI only | See below. |

### Docker in OpenShift

An OpenShift pod has no Docker daemon (nodes run CRI-O), and running one
needs a privileged pod. The image therefore ships only the `docker` client;
the Docker plugins work when it points at a daemon elsewhere:

- `DOCKER_HOST=ssh://user@docker-host` (mount an SSH key and `known_hosts`),
  or `DOCKER_HOST=tcp://docker-host:2376` with `DOCKER_TLS_VERIFY=1` and
  `DOCKER_CERT_PATH` (mount the client certificates).
- Or, usually simpler: add the Docker machine as an **execution node**
  (Nodes → Add node) and run Docker steps there (`--step-node`), where
  Docker is local.

`podman`, `buildah` and `skopeo` are not in the UBI repositories (they
need a RHEL subscription), so they are not included.

---

# Storage

Everything that changes lives on one volume mounted at `/var/lib/entropy`:

| Path | Contents |
|---|---|
| `home/database/entropy.db` | the SQLite database |
| `home/config/entropy.json` | configuration |
| `home/session`, `home/plugins`, `home/site-packages`, `home/logs` | sessions, installed plugins and their packages, logs |
| `home/tmp` | worker logs and run definitions (`ENTROPY_TMP`) |
| `home/node-cache`, `home/ssh` | node runtime bundles, node host keys |
| `workspace/` | the workflow workspace (`ENTROPY_WORKSPACE`) |

`deploy/openshift/entropy.yaml` claims it from ODF:

- Storage class **`ocs-storagecluster-ceph-rbd`** (Ceph block, RWO). SQLite
  wants a local-disk filesystem with working locks; RBD gives it one.
  CephFS (`ocs-storagecluster-cephfs`, RWX) works but is slower and gains
  nothing, since only one pod may write the database.
- **One replica, `Recreate` strategy**, so two pods never open the database
  at once.
- Back up with ODF volume snapshots (`VolumeSnapshot` of `entropy-data`), or
  take a consistent copy of the database from the running pod:

  ```sh
  oc exec deploy/entropy -- python3 -c "import sqlite3; s=sqlite3.connect('/var/lib/entropy/home/database/entropy.db'); d=sqlite3.connect('/var/lib/entropy/backup.db'); s.backup(d)"
  oc cp $(oc get pod -l app=entropy -o name | cut -d/ -f2):/var/lib/entropy/backup.db ./entropy-backup.db
  ```

# Start-up

The entrypoint (`deploy/container/entrypoint.sh`) adds a passwd entry for
the arbitrary UID (ssh and git need one), then runs
`python3 -m lib.install.container serve`:

1. First start on an empty volume: directories, configuration, database,
   the administrator (`ENTROPY_ADMIN_PASSWORD_FILE` → the `entropy-admin`
   secret, or `ENTROPY_ADMIN_PASSWORD`), default plugins and workflow.
2. Every later start (restarts and new images): database migrations only.
3. Then the web server on `0.0.0.0:8000`.

Other commands: `oc exec deploy/entropy -- ent <command>` (the local CLI),
`podman run … entropy init` (prepare a volume only), `… bash`.

# Deploying

```sh
oc new-project entropy
oc create secret generic entropy-admin --from-literal=password='<strong password>'
# set the image in deploy/openshift/entropy.yaml, then:
oc apply -f deploy/openshift/entropy.yaml
oc get route entropy
```

Execution nodes use the Route URL (`https://…`) as the main node URL; the
remote `ent` client logs in to it the same way.

| Variable | Default | |
|---|---|---|
| `ENTROPY_ADMIN_PASSWORD_FILE` / `ENTROPY_ADMIN_PASSWORD` | — | First start only. |
| `ENTROPY_ADMIN_USER`, `ENTROPY_ADMIN_NAME` | `admin`, `Administrator` | First start only. |
| `ENTROPY_THEME_ENABLE` | `0` | Wallpaper customization. |
| `ENTROPY_WEB_PORT` | `8000` | |
| `ENTROPY_HOME`, `ENTROPY_WORKSPACE`, `ENTROPY_TMP` | under `/var/lib/entropy` | Keep them on the volume. |
| `DOCKER_HOST` | — | Daemon for the `docker` CLI. |

# Upgrades

Deploy a newer image (`oc set image deploy/entropy entropy=…:1.2.0` or a new
build). The new pod migrates the database on the volume when it starts.
Upgrading from Administration → System is disabled in the container
(`ENTROPY_CONTAINER=1`); the page says so.
