def test_runtime_exposes_application_services(runtime):
    assert runtime.configuration is not None
    assert runtime.executor is not None
    assert runtime.template is not None
    assert runtime.database is not None
    assert runtime.ui is not None
    assert runtime.logger is not None


def test_runtime_exposes_authenticated_user(runtime):
    assert runtime.user == "tester"
