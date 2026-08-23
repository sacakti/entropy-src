# Deployment plugin

## Modes

### folder

Loads `DeploymentUpdate` YAML definitions from `source` and applies them to Deployment YAML files under `target`.

### deployments

Consumes `BuildReleaseContext.outputs.deployment.resources.deployments` through the `deployments` argument and uses `repository` as the YAML repository root.
