# Release scenarios

End-to-end check of `release.context_builder` → `custom.image_transfer` →
`oc.deployment` through the real Entropy runtime.

```bash
# 1. Build a sandbox (release ZIPs, Docker repo, YAML repos, workflow)
venv/bin/python tests/test-data/release_scenarios/build.py ~/entropy-release-scenarios

# 2. Run every scenario (or one: --tags S5)
ent workflow run -f ~/entropy-release-scenarios/release-scenarios.json

# 3. Check the results
venv/bin/python tests/test-data/release_scenarios/verify.py ~/entropy-release-scenarios
```

`build.py` only writes inside the sandbox and refuses to replace a
directory it did not create. Re-run it to reset the sandbox. Docker is
never called: image transfer steps use `skip_docker`.

| Tag | Release | Expected result |
| --- | --- | --- |
| S1 | `App/services/app-1/image` changed | app-1 image → `:2.0.0` |
| S2 | `DeploymentUpdate` (env add/update, volume, mount) | app-1 fields changed, image unchanged |
| S3 | S1 + S2 | app-1 fields changed and image → `:2.0.0` |
| S4 | Scripts-only package, `scripts/deploy/image_transfer.sh` | app1 image → `:1.5.0`; `apply_yaml.sh` prepared |
| S5 | App-Published: `App/yamls` `DeploymentUpdate` + `scripts/deploy/image_transfer.sh` | app1 env changed and image → `:1.6.0`; `apply_yaml.sh` prepared |
| S6 | New `app-3` Deployment + changed full `app-2` Deployment | app-3 created; app-2 skipped (whole-file update) |
| S7 | Folder mode with two `DeploymentUpdate` files | both Deployments updated |

Each scenario has its own YAML repository (`yamls/S1` ... `yamls/S6`), so
scenarios do not affect each other.
