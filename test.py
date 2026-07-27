from pathlib import Path
from time import sleep

from lib.output.output import OutputManager
from version import APP_NAME, VERSION


def test_console():

    output = OutputManager()
    
    output.initialize(Path("logs"))

    output.banner(APP_NAME, VERSION)

    output.system.info("Application started")
    output.system.success("Environment initialized")

    output.rule("Workflow Validation")

    task = output.progress("Loading workflow.json")
    sleep(1)
    output.workflow.success(
        "Workflow loaded",
        task=task,
    )

    task = output.progress("Validating workflow")
    sleep(2)
    output.workflow.success(
        "Workflow validated",
        task=task,
    )

    output.workflow.info("12 workflow steps found")

    output.step(
        1,
        "Database Deployment",
    )

    task = output.progress("Loading master_calling.sql")
    sleep(1)
    output.database.success(
        "Master script loaded",
        task=task,
    )

    task = output.progress("Validating master script")
    sleep(2)
    output.database.success(
        "Validation successful",
        task=task,
    )

    output.database.info("Found 4 child scripts")

    output.sub("app_tables.sql")
    output.sub("app_packages.sql")
    output.sub("app_views.sql")
    output.sub("app_grants.sql")

    task = output.progress("Executing app_tables.sql")
    sleep(2)
    output.database.success(
        "app_tables.sql executed successfully",
        task=task,
    )

    task = output.progress("Executing app_packages.sql")
    sleep(2)
    output.database.warning(
        "app_packages.sql completed with warnings",
        task=task,
    )

    output.sub("Package APP_UTIL already exists")

    task = output.progress("Executing app_views.sql")
    sleep(2)
    output.database.error(
        "app_views.sql execution failed",
        task=task,
    )

    output.sub("ORA-00942: table or view does not exist")
    output.sub("Line : 142")
    output.sub("Object : APP_CUSTOMER_V")

    output.step(
        2,
        "OpenShift Deployment",
    )

    task = output.progress("Updating ConfigMap")
    sleep(2)
    output.oc.success(
        "ConfigMap updated",
        task=task,
    )

    task = output.progress("Replacing Deployment")
    sleep(2)
    output.oc.success(
        "Deployment replaced",
        task=task,
    )

    output.step(
        3,
        "Generate Report",
    )

    task = output.progress("Generating HTML report")
    sleep(2)
    output.report.success(
        "HTML report generated",
        task=task,
    )

    output.system.success("Deployment completed successfully")

    output.shutdown()


if __name__ == "__main__":
    test_console()