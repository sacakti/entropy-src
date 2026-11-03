# Pod metrics (oc.pod_metrics)

A live page of the pods in an OpenShift namespace: CPU and memory compared with their
limits, status, readiness, restarts, node and age. It only reads.

Log in first with `oc.generic`, then run this plugin in **interactive** mode and open the run
screen's **App** tab. **Stop app** ends it. Automated runs make one pass and put the result in
the step's outputs. See [MAN.md](MAN.md).
