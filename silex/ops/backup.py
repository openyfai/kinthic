import os
import zipfile
import logging
from pathlib import Path

from silex.utils.config import KRONOS_HOME

log = logging.getLogger("kronos.backup")

def export_backup(output_filename: str) -> None:
    """
    Exports the ~/.kronos directory to a zip file.
    Specifically excludes secrets.json to prevent credential leakage.
    """
    kronos_dir = Path(KRONOS_HOME)
    out_path = Path(output_filename).absolute()
    
    if not kronos_dir.exists():
        print(f"Error: Kronos directory {kronos_dir} does not exist.")
        return

    excluded_files = {"secrets.json"}
    
    print(f"Starting backup of {kronos_dir} to {out_path}...")
    
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(kronos_dir):
            # Skip python cache dirs
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
                
            for file in files:
                if file in excluded_files:
                    print(f"Skipping {file} (security exclusion)")
                    continue
                    
                file_path = Path(root) / file
                # Skip the output file itself if it's being written into the kronos dir
                if file_path.absolute() == out_path:
                    continue
                    
                arcname = file_path.relative_to(kronos_dir)
                zipf.write(file_path, arcname)
                
    print(f"Backup successfully exported to {out_path}")
