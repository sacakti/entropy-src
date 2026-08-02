from lib.database.objects.plugin_registry import PluginRegistryTable


def test_create_users_table(connection):

    PluginRegistryTable().create(
        connection,
    )

    assert connection.table_exists(
        "plugin_registry"
    )
