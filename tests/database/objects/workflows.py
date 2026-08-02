from lib.database.objects.workflows import WorkflowsTable


def test_create_users_table(connection):

    WorkflowsTable().create(
        connection,
    )

    assert connection.table_exists(
        "workflows"
    )
