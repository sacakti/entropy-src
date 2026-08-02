from lib.database.objects.schema_migrations import SchemaMigrationsTable


def test_create_users_table(connection):

    SchemaMigrationsTable().create(
        connection,
    )

    assert connection.table_exists(
        "schema_migrations"
    )
