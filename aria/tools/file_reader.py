"""
File Reader Tool for accessing local files securely.
"""

from __future__ import annotations

import logging
from pathlib import Path
import aiofiles
from aria.tools.base import BaseTool

log = logging.getLogger("aria.tools.file_reader")

class FileReaderTool(BaseTool):
    name = "read_file"
    description = "Reads the text content of a local file."
    schema = {
        "file_path": "string (the absolute or relative path to the file)",
    }

    async def execute(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        if not file_path:
            return "Error: 'file_path' argument is required."

        path = Path(file_path).resolve()
        log.info(f"Reading file: {path}")

        if not path.exists():
            return f"Error: File not found at path: {path}"
        
        if not path.is_file():
            return f"Error: Path is not a file: {path}"

        try:
            async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
                # Read up to first 10,000 characters to prevent context overflow
                content = await f.read(10000)
                
            if len(content) == 10000:
                content += "\n...[TRUNCATED due to length]"
                
            return f"Contents of {path.name}:\n\n{content}"
            
        except UnicodeDecodeError:
            return f"Error: File {path.name} appears to be binary or has an unsupported encoding."
        except Exception as e:
            log.error(f"Failed to read file {path}: {e}")
            return f"Error reading file: {str(e)}"
