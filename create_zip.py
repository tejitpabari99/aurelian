"""
Create a zip archive of the project, excluding files ignored by .gitignore.
The zip is saved to zips/<timestamp>.zip
"""

import os
import subprocess
import zipfile
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ZIPS_DIR = os.path.join(PROJECT_ROOT, "zips")


def get_tracked_and_untracked_files():
    """Use git to list all files that are NOT ignored (tracked + untracked non-ignored)."""
    # Get tracked files
    tracked = subprocess.check_output(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        text=True,
    ).strip().splitlines()

    # Get untracked files that are NOT ignored
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=PROJECT_ROOT,
        text=True,
    ).strip().splitlines()

    all_files = sorted(set(tracked + untracked))
    return [f for f in all_files if f]  # filter out empty strings


def get_git_dir_files():
    """Walk the .git directory and return all file paths relative to PROJECT_ROOT."""
    git_dir = os.path.join(PROJECT_ROOT, ".git")
    git_files = []
    if os.path.isdir(git_dir):
        for root, _dirs, filenames in os.walk(git_dir):
            for fname in filenames:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, PROJECT_ROOT)
                git_files.append(rel)
    return git_files


def create_zip():
    os.makedirs(ZIPS_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"{timestamp}.zip"
    zip_path = os.path.join(ZIPS_DIR, zip_filename)

    files = get_tracked_and_untracked_files()
    git_files = get_git_dir_files()
    all_files = files + git_files

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in all_files:
            full_path = os.path.join(PROJECT_ROOT, rel_path)
            if os.path.isfile(full_path):
                # Store inside a top-level folder named with the timestamp
                arcname = os.path.join(timestamp, rel_path)
                zf.write(full_path, arcname)
                count += 1

    print(f"Created zip with {count} files (including .git): {zip_path}")
    return zip_path


if __name__ == "__main__":
    create_zip()
