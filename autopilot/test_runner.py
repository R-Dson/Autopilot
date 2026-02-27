import subprocess
import re
from pathlib import Path
from typing import Dict, Any, Optional


class TestRunner:
    NOISE_PATTERNS = [
        r"^=+$",
        r"^-{2,}.*?$",
        r"^\s*passed in \d+\.\d+s\s*?$",
        r"^\s*\d+ passed.*?$",
        r"^\s*\d+ failed.*?$",
        r"^\s*\d+ error.*?$",
        r"^\s*\d+ warning.*?$",
        r"^\s*\d+ deselected.*?$",
        r"^\s*\d+ xfailed.*?$",
        r"^\s*\d+ xpassed.*?$",
        r"^\s*Test session starts.*?$",
        r"^\s*platform .*?$",
        r"^\s*rootdir: .*?$",
        r"^\s*collected \d+ items.*?$",
        r"^\s*cachedir: .*?$",
        r"^\s*collecting.*?$",
        r"^\s*collected.*?$",
        r"^\s*==== .*?$",
        r"^\s*PASS .*?$",
        r"^\s*FAIL .*?$",
        r"^\s*Tests:.*?$",
        r"^\s*Time:.*?$",
        r"^\s*PASS.*?$",
        r"^\s*FAIL.*?$",
        r"^\s*\.\s*?$",
        r"^Test Files.*?$",
        r"^  \d+ passed.*?$",
        r"^  \d+ failed.*?$",
        r"^  \d+ ignored.*?$",
    ]

    @staticmethod
    def _filter_noise(output: str) -> str:
        """
        Removes boilerplate noise from test output using regex patterns.
        """
        lines = output.split("\n")
        filtered = []

        for line in lines:
            is_noise = False
            for pattern in TestRunner.NOISE_PATTERNS:
                if re.match(pattern, line):
                    is_noise = True
                    break
            if not is_noise:
                filtered.append(line)

        result = "\n".join(filtered)
        return "\n".join([line for line in result.split("\n") if line.strip()])

    @staticmethod
    def _detect_framework(workdir: str) -> Optional[str]:
        """
        Auto-detects the test framework based on config files.
        Returns 'pytest', 'vitest', or None.
        """
        workdir_path = Path(workdir)

        # Check for pytest
        pytest_files = ["pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"]
        for filename in pytest_files:
            if (workdir_path / filename).exists():
                content = (workdir_path / filename).read_text()
                if re.search(
                    r"\[tool\.pytest\]|\[pytest\]|py.test", content, re.IGNORECASE
                ):
                    return "pytest"

        # Check for Python test files
        if any(workdir_path.glob("test_*.py")) or any(workdir_path.glob("*_test.py")):
            return "pytest"

        # Check for vitest
        vitest_files = ["vitest.config.ts", "vitest.config.js", "vitest.config.mjs"]
        for filename in vitest_files:
            if (workdir_path / filename).exists():
                return "vitest"

        # Check for package.json with vitest config
        pkg_json = workdir_path / "package.json"
        if pkg_json.exists():
            content = pkg_json.read_text()
            if '"vitest"' in content or "vitest" in content:
                return "vitest"

        # Check for test files
        if any(workdir_path.glob("**/*.test.{ts,tsx,js,jsx}")) or any(
            workdir_path.glob("**/*.spec.{ts,tsx,js,jsx}")
        ):
            return "vitest"

        return None

    @staticmethod
    def run_pytest(workdir: str) -> Dict[str, Any]:
        """
        Runs pytest in the specified directory and returns a sanitized summary.
        """
        try:
            result = subprocess.run(
                ["pytest", "--tb=short", "-q"],
                cwd=workdir,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                return {"success": True, "message": "SUCCESS: All tests passed."}

            failures = result.stdout + result.stderr
            filtered_failures = TestRunner._filter_noise(failures)

            return {
                "success": False,
                "message": "FAILURES detected. See summary below:",
                "details": filtered_failures.strip() or failures.strip(),
            }
        except FileNotFoundError:
            return {
                "success": False,
                "message": "Error: 'pytest' not found in environment.",
            }
        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    @staticmethod
    def run_vitest(workdir: str) -> Dict[str, Any]:
        """
        Runs vitest in the specified directory and returns a sanitized summary.
        """
        try:
            result = subprocess.run(
                ["npx", "vitest", "run", "--reporter=verbose"],
                cwd=workdir,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                return {"success": True, "message": "SUCCESS: All tests passed."}

            failures = result.stdout + result.stderr
            filtered_failures = TestRunner._filter_noise(failures)

            return {
                "success": False,
                "message": "FAILURES detected. See summary below:",
                "details": filtered_failures.strip() or failures.strip(),
            }
        except FileNotFoundError:
            return {
                "success": False,
                "message": "Error: 'vitest' not found in environment.",
            }
        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    @staticmethod
    def run(workdir: str, framework: Optional[str] = None) -> Dict[str, Any]:
        """
        Auto-detects and runs the appropriate test framework.
        Pass 'pytest' or 'vitest' to force a specific framework.
        """
        if framework:
            if framework == "pytest":
                return TestRunner.run_pytest(workdir)
            elif framework == "vitest":
                return TestRunner.run_vitest(workdir)
            else:
                return {
                    "success": False,
                    "message": f"Error: Unknown framework '{framework}'. Use 'pytest' or 'vitest'.",
                }

        detected = TestRunner._detect_framework(workdir)
        if detected == "pytest":
            return TestRunner.run_pytest(workdir)
        elif detected == "vitest":
            return TestRunner.run_vitest(workdir)
        else:
            return {
                "success": False,
                "message": "Error: Could not detect test framework. No pytest or vitest configuration found.",
            }
