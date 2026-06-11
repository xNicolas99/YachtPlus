import os
import glob

files = glob.glob("backend/api/**/*.py", recursive=True)

for filepath in files:
    try:
        with open(filepath, "r") as f:
            content = f.read()

        if "import get_settings" in content and "settings = get_settings()" in content:
            # We don't want global settings.
            pass

    except Exception as e:
        pass
