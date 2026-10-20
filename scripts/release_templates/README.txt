Entropy
=======

This package contains everything Entropy needs: a Python runtime, the
application, its web interface and all Python packages. No Python, pip,
virtual environment or npm is required on the server.

Install
-------

    Linux / macOS:   ./install.sh
    Windows:         install.cmd

The installer asks for the workflow workspace directory and the initial
(bootstrap) administrator, installs Entropy for the current user and
starts the web server (as a systemd user service when available).

Unattended:

    ENTROPY_ADMIN_PASSWORD='...' ./install.sh --yes --workspace /srv/entropy

Python packages:

    --deps bundled     offline, from the wheels in this package (default)
    --deps index       download from a package index (--index-url URL)
    --deps manual      you installed them yourself into the chosen Python;
                       ./install.sh --print-requirements lists them

Other options: --admin-user, --admin-name, --admin-password-file, --host,
--port, --service auto|systemd|none, --no-start, --python=PATH.
Run ./install.sh --help for details.

After installation
------------------

    ent web status | start | stop | restart     manage the web server
    ent web config --host 0.0.0.0 --port 8000   listen on the network (needed for remote nodes)
    ent upgrade --source entropy-<version>-<platform>.tar.gz [--check]
    ent upgrade --rollback                      back to the previous version
    ./install.sh uninstall                      remove Entropy and its data

Upgrades can also be applied from the web interface:
Administration -> System -> Upgrade. Upgrades back up the database,
migrate it and restart the web server; a failed upgrade restores the
previous version automatically.
