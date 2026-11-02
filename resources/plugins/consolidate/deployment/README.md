# Consolidate Deployments (consolidate.deployment)

`consolidate.deployment` merges the Deployment changes of several release
packages (image tag, env variables, mounts, volumes) into their **net result**:
one `DeploymentUpdate` per Deployment. An environment that skips releases
(say H010 to H015 at once) then applies each change once.

It only writes files. Apply them with `oc.deployment` (folder mode), as
`workflow.json` shows. The YAML repository is not touched.

```text
H010: app-1  update image=repo/app:1 ; add env MODE=a ; add mount logs
H011: app-1  update image=repo/app:2 ; update env MODE=b
H012: app-1  delete mount logs
=> deployment-app-1.yaml: update image=repo/app:2 ; add env MODE=b
```

Releases come from `release_directory` (natural name order: H9, H10, H101)
or `releases` (the order given). Each is a ZIP or an extracted folder, with
`App/openshift/yamls` or, for App-Published packages, `App/yamls`.

See [MAN.md](MAN.md) for the rules.
