from ..settings import Settings
import os
import fnmatch
from fastapi import HTTPException
import re

settings = Settings()


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
    """
    matches = {}
    for root, _, filenames in os.walk(path, followlinks=True):
        for _ in set().union(
            fnmatch.filter(filenames, "docker-compose.yml"),
            fnmatch.filter(filenames, "docker-compose.yaml"),
        ):
            key = root.split("/")[-1]
            matches[key] = os.path.join(os.getcwd(), root + "/" + _)
    return matches


def get_readme_file(path):
    """
    find case insensitive readme.md in path and return the contents
    """

    readme = None

    for file in os.listdir(path):
        if file.lower() == "readme.md" and os.path.isfile(os.path.join(path, file)):
            file = open(os.path.join(path, file))
            readme = file.read()
            file.close()
            break

    return readme


def get_logo_file(path):
    """
    find case insensitive logo.png in path and return the contents
    """

    logo = None

    for file in os.listdir(path):
        if file.lower() == "logo.png" and os.path.isfile(os.path.join(path, file)):
            file = open(os.path.join(path, file))
            logo = file.read()
            file.close()
            break

    return logo
