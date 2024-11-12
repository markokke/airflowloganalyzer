#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


class WindowsLintRunner:
    def __init__(self):
        self.exit_code = 0
        self.python_path = os.path.join(".venv", "Scripts", "python.exe")

        # Define directories to exclude
        self.exclude_dirs = {
            ".git",
            ".venv",
            "venv",
            "env",
            "__pycache__",
            "build",
            "dist",
            "*.egg-info",
        }

        # Find Python files to lint
        self.python_files = self.get_python_files()

    def get_python_files(self) -> List[str]:
        """Get list of Python files to lint, excluding certain directories."""
        python_files = []
        for root, dirs, files in os.walk("."):
            # Remove excluded directories
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]

            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    # Convert to relative path
                    rel_path = os.path.relpath(full_path)
                    # Skip files in excluded directories
                    if not any(excluded in rel_path for excluded in self.exclude_dirs):
                        python_files.append(rel_path)

        return python_files

    def run_command(self, command: List[str], description: str) -> Tuple[int, str]:
        """Run a lint command and return exit code and output."""
        print(f"\n{'='*20} Running {description} {'='*20}")
        try:
            # Use shell=True for Windows and capture output
            full_command = " ".join(command)
            result = subprocess.run(
                full_command, shell=True, capture_output=True, text=True, check=True
            )
            return 0, result.stdout + result.stderr
        except subprocess.CalledProcessError as e:
            return e.returncode, e.stdout + e.stderr

    def run_black(self) -> None:
        """Run black code formatter."""
        if not self.python_files:
            print("No Python files to format")
            return

        files = " ".join(self.python_files)
        exit_code, output = self.run_command(
            [f"{self.python_path} -m black --config .python-black {files}"],
            "Black Code Formatter",
        )
        print(output)
        self.exit_code = max(self.exit_code, exit_code)

    def run_isort(self) -> None:
        """Run isort import sorter."""
        if not self.python_files:
            print("No Python files to sort imports")
            return

        files = " ".join(self.python_files)
        exit_code, output = self.run_command(
            [f"{self.python_path} -m isort {files}"], "Import Sorter (isort)"
        )
        print(output)
        self.exit_code = max(self.exit_code, exit_code)

    def run_flake8(self) -> None:
        """Run flake8 linter."""
        if not self.python_files:
            print("No Python files to check with flake8")
            return

        files = " ".join(self.python_files)
        exit_code, output = self.run_command(
            [f"{self.python_path} -m flake8 --config .flake8 {files}"], "Flake8 Linter"
        )
        print(output)
        self.exit_code = max(self.exit_code, exit_code)

    def run_pylint(self) -> None:
        """Run pylint."""
        if not self.python_files:
            print("No Python files to check with pylint")
            return

        files = " ".join(self.python_files)
        exit_code, output = self.run_command(
            [f"{self.python_path} -m pylint --rcfile=.pylintrc {files}"], "Pylint"
        )
        print(output)
        self.exit_code = max(self.exit_code, exit_code)

    def run_all(self) -> int:
        """Run all linters and return highest exit code."""
        print("Starting linting process...")

        # Create .lint-cache if it doesn't exist
        Path(".lint-cache").mkdir(exist_ok=True)

        # Show which files will be linted
        print("\nFiles to be linted:")
        for file in self.python_files:
            print(f"  {file}")
        print()

        # Run all linters
        self.run_black()
        self.run_isort()
        self.run_flake8()
        self.run_pylint()

        if self.exit_code == 0:
            print("\n✅ All linters passed successfully!")
        else:
            print("\n❌ Some linters reported issues.")

        return self.exit_code


if __name__ == "__main__":
    runner = WindowsLintRunner()
    sys.exit(runner.run_all())
