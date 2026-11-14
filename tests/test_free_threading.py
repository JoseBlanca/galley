"""galley runs its per-page work in threads and needs the GIL to stay off."""

import importlib
import pkgutil
import subprocess
import sys

import galley


def test_importing_every_galley_module_leaves_the_gil_disabled() -> None:
    for module in pkgutil.walk_packages(galley.__path__, prefix="galley."):
        importlib.import_module(module.name)
    assert not sys._is_gil_enabled()


def test_importing_galley_installs_gilguard_without_pytest() -> None:
    # pytest loads gilguard itself (-p gilguard), so the check runs in a
    # fresh interpreter, as the galley2epub command would start.
    result = subprocess.run(
        [sys.executable, "-c", "import sys, galley; print('gilguard' in sys.modules)"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert result.stdout.strip() == "True"
