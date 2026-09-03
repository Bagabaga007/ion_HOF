"""测试分层门禁：每个用例必须且只能属于一个主测试层。"""

import pytest

PRIMARY_LAYERS = ("unit", "integration", "config", "system")


def pytest_collection_modifyitems(items):
    invalid = []
    for item in items:
        layers = [name for name in PRIMARY_LAYERS if item.get_closest_marker(name)]
        if len(layers) != 1:
            invalid.append(f"{item.nodeid}: {layers or 'missing'}")
    if invalid:
        raise pytest.UsageError(
            "每个测试必须且只能标记一个主测试层:\n" + "\n".join(invalid)
        )
