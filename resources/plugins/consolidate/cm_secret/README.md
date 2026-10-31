# Consolidate ConfigMaps and Secrets (consolidate.cm_secret)

`consolidate.cm_secret` merges the ConfigMap and Secret changes of several
release packages into their **net result**: one YAML per ConfigMap/Secret.
An environment that skips releases (say H010 to H015 at once) then applies
each key once, with the value of the last release that changed it.

It only writes files. Apply them with `oc.cm_secret_update` (folder mode),
as `workflow.json` shows. The YAML repository is not touched.

```text
H010: cm-app  update db.url=A
H011: cm-app  update db.url=B, add feature.x=on
H012: cm-app  delete feature.x
=> configmap-cm-app.yaml: update db.url=B ; delete feature.x
```

Releases come from `release_directory` (natural name order: H9, H10, H101)
or `releases` (the order given). Each is a ZIP or an extracted folder, with
`App/openshift/yamls` or, for App-Published packages, `App/yamls`.

See [MAN.md](MAN.md) for the rules. Sibling plugins (deployments, services
and routes, database scripts) follow the same pattern.
