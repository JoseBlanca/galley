"""galley runs its per-page work in threads and needs the GIL to stay off."""

import importlib
import pkgutil
import sys

import galley


def test_importing_every_galley_module_leaves_the_gil_disabled() -> None:
    for module in pkgutil.walk_packages(galley.__path__, prefix="galley."):
        importlib.import_module(module.name)
    assert not sys._is_gil_enabled()
