# oc.audit

Audits an OpenShift YAML repository (a folder, or a Tools → Git repositories repository) after `oc.sync_yamls`: an HTML report of every ConfigMap key,
Secret key (values hidden) and Deployment field that changed since the previous audit, then a
git commit so the next audit starts from here. Reports rotate (10 days by default) and are
registered as generated artifacts.

```json
{"name": "AuditYamls", "plugin": "oc.audit",
 "arguments": {"repository": "${steps.SyncYamls.outputs.repository}"}}
```

See [MAN.md](MAN.md) for arguments, outputs and behaviour.
