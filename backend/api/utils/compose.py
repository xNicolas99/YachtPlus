import os
import fnmatch
from fastapi import HTTPException
import re
from pathlib import Path



def validate_app_name(name):
    """
    Validates that the app name is safe to use in subprocess commands.
    Only allows alphanumeric characters, underscores, and hyphens.
    """
    if not name:
        raise HTTPException(status_code=400, detail="App name cannot be empty.")

    # Strictly allow only a-z, A-Z, 0-9, _, - and must start with alphanumeric
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", name):
        raise HTTPException(
            status_code=400,
            detail="Invalid app name. Only alphanumeric characters, underscores, and hyphens are allowed, and must not start with a hyphen or underscore."
        )

    return name

def validate_compose_project_name(name):
    """
    Validates that the project name is safe to use in file paths.
    Only allows alphanumeric characters, underscores, and hyphens.
    """
    if not name:
        raise HTTPException(status_code=400, detail="Project name cannot be empty.")

    # Strictly allow only a-z, A-Z, 0-9, _, - and must start with alphanumeric
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", name):
        raise HTTPException(
            status_code=400,
            detail="Invalid project name. Only alphanumeric characters, underscores, and hyphens are allowed, and must not start with a hyphen or underscore."
        )

    # Check for path traversal attempts explicitly (double check, though regex handles it)
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid project name.")

    return name


def find_yml_files(path):
    """
    find docker-compose.yml files in path
    (B23: sync os.walk — must be called via run_in_thread/to_thread from
    async contexts, see the wrappers in actions/compose.py)
    """
    matches = {}
    base = Path(path)
    if not base.is_dir() or base.is_symlink():
        return matches
    directories = [base] + sorted((p for p in base.iterdir() if p.is_dir() and not p.is_symlink()), key=lambda p: p.name)
    for directory in directories:
        for filename in ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"):
            file = directory / filename
            if file.is_file() and not file.is_symlink():
                matches[directory.name] = str(file.absolute())
                break
    return matches


def get_readme_file(path):
    """
    find case insensitive readme.md in path and return the contents
    """
    for file in os.listdir(path):
        full = os.path.join(path, file)
        if file.lower() == "readme.md" and os.path.isfile(full):
            with open(full) as f:
                return f.read()
    return None


def get_logo_file(path):
    """
    find case insensitive logo.png in path and return the contents
    """
    for file in os.listdir(path):
        full = os.path.join(path, file)
        if file.lower() == "logo.png" and os.path.isfile(full):
            with open(full, "rb") as f:
                return f.read()
    return None
