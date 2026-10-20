# Entropy on Red Hat UBI 9 (Python 3.9), for OpenShift.
#
#   podman build -t entropy:latest .
#   podman build -t entropy:latest --build-arg INSTALL_SQLPLUS=0 .
#
# The image holds the application only. The database, configuration,
# sessions, plugins, logs and workflow workspace live on a volume at
# /var/lib/entropy (an ODF PersistentVolumeClaim on OpenShift; see
# deploy/openshift/entropy.yaml). The first start initializes it.
#
# Optional tools (build arguments, 1 = include):
#   INSTALL_OC=1       oc and kubectl          (OC_VERSION, default stable)
#   INSTALL_SQLPLUS=1  Oracle Instant Client + sqlplus (ORACLE_IC_VERSION)
#   INSTALL_DOCKER=1   docker CLI only, no daemon (DOCKER_VERSION); point it at
#                      a daemon with DOCKER_HOST, see docs/architecture/10-container.md

ARG UBI_REGISTRY=registry.access.redhat.com/ubi9

# ----------------------------------------------------------------------
# Web UI
# ----------------------------------------------------------------------
FROM ${UBI_REGISTRY}/nodejs-22 AS ui
USER 0
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ----------------------------------------------------------------------
# Python packages (a virtual environment copied into the final image)
# ----------------------------------------------------------------------
FROM ${UBI_REGISTRY}/ubi AS python
RUN dnf -y install python3 python3-pip && dnf clean all
COPY resources/wheels/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/entropy/venv \
 && /opt/entropy/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/entropy/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# ----------------------------------------------------------------------
# Runtime
# ----------------------------------------------------------------------
FROM ${UBI_REGISTRY}/ubi

ARG INSTALL_OC=1
ARG OC_VERSION=stable
ARG INSTALL_SQLPLUS=1
ARG ORACLE_IC_VERSION=23.9.0.25.07
ARG INSTALL_DOCKER=1
ARG DOCKER_VERSION=29.9.2

LABEL name="entropy" \
      summary="Entropy deployment platform" \
      io.openshift.expose-services="8000:http" \
      io.k8s.display-name="Entropy"

# Runtime needs: Python 3.9, git (git plugin), ssh (node setup), tar/gzip.
RUN dnf -y install python3 git-core openssh-clients tar gzip procps-ng findutils \
 && dnf clean all && rm -rf /var/cache/dnf

# oc + kubectl from the OpenShift mirror.
RUN if [ "$INSTALL_OC" = 1 ]; then \
      arch=$(uname -m); \
      curl -fsSL "https://mirror.openshift.com/pub/openshift-v4/${arch}/clients/ocp/${OC_VERSION}/openshift-client-linux.tar.gz" \
        | tar -xz -C /usr/local/bin oc kubectl \
      && oc version --client; \
    fi

# Oracle Instant Client (basic + sqlplus) RPMs; libaio comes from the UBI repositories.
RUN if [ "$INSTALL_SQLPLUS" = 1 ]; then \
      arch=$(uname -m); \
      base="https://yum.oracle.com/repo/OracleLinux/OL9/oracle/instantclient23/${arch}/getPackage"; \
      dnf -y install \
        "${base}/oracle-instantclient-basic-${ORACLE_IC_VERSION}-1.el9.${arch}.rpm" \
        "${base}/oracle-instantclient-sqlplus-${ORACLE_IC_VERSION}-1.el9.${arch}.rpm" \
      && dnf clean all && rm -rf /var/cache/dnf \
      && sqlplus -V; \
    fi

# Docker CLI (static binary). There is no Docker daemon in an OpenShift pod.
RUN if [ "$INSTALL_DOCKER" = 1 ]; then \
      arch=$(uname -m); \
      curl -fsSL "https://download.docker.com/linux/static/stable/${arch}/docker-${DOCKER_VERSION}.tgz" \
        | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
      && docker --version; \
    fi

COPY --from=python /opt/entropy/venv /opt/entropy/venv
COPY core/ /opt/entropy/app/core/
COPY lib/ /opt/entropy/app/lib/
COPY resources/ /opt/entropy/app/resources/
COPY entropy.py pyproject.toml /opt/entropy/app/
COPY --from=ui /src/frontend/dist/ /opt/entropy/app/frontend/dist/
COPY deploy/container/entrypoint.sh deploy/container/ent /usr/local/bin/

# OpenShift runs the container with an arbitrary UID in group 0: the
# application is read-only for it, /etc/passwd group-writable so the
# entrypoint can name that UID (ssh and git need a passwd entry).
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/ent \
 && mkdir -p /var/lib/entropy \
 && chgrp -R 0 /var/lib/entropy && chmod -R g=u /var/lib/entropy \
 && chmod g=u /etc/passwd

ENV PATH=/opt/entropy/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/var/lib/entropy \
    ENTROPY_HOME=/var/lib/entropy/home \
    ENTROPY_WORKSPACE=/var/lib/entropy/workspace \
    ENTROPY_TMP=/var/lib/entropy/home/tmp \
    ENTROPY_CONTAINER=1 \
    ENTROPY_WEB_HOST=0.0.0.0 \
    ENTROPY_WEB_PORT=8000 \
    ENTROPY_THEME_ENABLE=0

WORKDIR /opt/entropy/app
VOLUME ["/var/lib/entropy"]
EXPOSE 8000
USER 1001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["serve"]
