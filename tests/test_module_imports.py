"""
Unit test to verify that every Python module in the repository imports cleanly
without any missing module-level dependencies or annotations.
"""

import importlib
import pkgutil
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestModuleImports(unittest.TestCase):
    def test_all_repository_modules_import_cleanly(self):
        packages_to_test = [
            "agent",
            "code_analysis",
            "binary_analysis",
            "memory",
            "config",
            "benchmarks",
        ]
        
        failed_imports = []
        for pkg_name in packages_to_test:
            pkg_dir = PROJECT_ROOT / pkg_name
            if not pkg_dir.exists():
                continue
            
            # Import the package itself
            try:
                importlib.import_module(pkg_name)
            except Exception as e:
                failed_imports.append((pkg_name, str(e)))
                continue

            # Walk all submodules
            for _, mod_name, is_pkg in pkgutil.walk_packages([str(pkg_dir)], prefix=f"{pkg_name}."):
                # Skip repo clones in benchmarks/repos
                if "benchmarks.repos" in mod_name:
                    continue
                try:
                    importlib.import_module(mod_name)
                except Exception as e:
                    failed_imports.append((mod_name, str(e)))

        self.assertEqual(
            failed_imports,
            [],
            f"The following modules failed to import:\n" + "\n".join(f"  - {m}: {err}" for m, err in failed_imports),
        )


if __name__ == "__main__":
    unittest.main()
