import distributed_storage


def test_package_imports_and_has_version() -> None:
    assert isinstance(distributed_storage.__version__, str)
    assert distributed_storage.__version__
