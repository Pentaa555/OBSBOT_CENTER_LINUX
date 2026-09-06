import sys

import pytest

from tests.fake_bridge import FakeBridgeModule


def pytest_configure(config):
    # Installed once, before any `app.*` module is imported, so every
    # `import obsbot_bridge as bridge` inside the app package binds to this
    # exact instance for the whole test session.
    sys.modules["obsbot_bridge"] = FakeBridgeModule()


@pytest.fixture(autouse=True)
def reset_fake_bridge():
    # Reset the SAME instance's state before each test (not replace it —
    # see the docstring on FakeBridgeModule.reset for why replacing it
    # would silently not work).
    sys.modules["obsbot_bridge"].reset()
    yield
