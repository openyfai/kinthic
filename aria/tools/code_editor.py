import os
import json
from pathlib import Path
from typing import Dict, Any

from aria.tools.base import BaseTool

PENDING_EDITS_FILE = Path(".aria_pending_edits.json")

class CodeEditorTool(BaseTool):
    """
    Allows ARIA to propose changes to her own codebase.
    Enforces a strict human-in-the-loop approval mechanism.
    """
    
    name = "propose_code_edit"
    description = (
        "Propose a change to a file in the codebase. You MUST use this tool if you want "
        "to upgrade, fix, or modify your own code. The change will NOT be applied immediately. "
        "It will be saved as a draft, and you must explicitly ask the user for approval in your response."
    )
    
    schema = {
        "file_path": "string (relative path to the file, e.g., 'aria/core/memory.py')",
        "target_content": "string (the exact block of code you want to replace. Leave empty to overwrite the entire file)",
        "replacement_content": "string (the new code to insert)",
        "explanation": "string (why you are making this change)"
    }
    
    async def execute(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        target_content = kwargs.get("target_content", "")
        replacement_content = kwargs.get("replacement_content", "")
        explanation = kwargs.get("explanation", "No explanation provided.")
        
        if not file_path or not replacement_content:
            return "ERROR: file_path and replacement_content are required."
            
        full_path = Path(os.path.abspath(file_path))
        
        # Security check: ensure it's within the project directory
        # Just a basic check to prevent escaping to system files
        if ".." in file_path:
            return "ERROR: Invalid file path. Cannot use '..'"
            
        # Verify the target content exists if provided
        if target_content and full_path.exists():
            with open(full_path, "r", encoding="utf-8") as f:
                current_code = f.read()
                if target_content not in current_code:
                    return "ERROR: The target_content was not found exactly as written in the file. Ensure exact matching including whitespace."
        
        # Save the proposal
        proposal = {
            "file_path": str(full_path),
            "target_content": target_content,
            "replacement_content": replacement_content,
            "explanation": explanation
        }
        
        with open(PENDING_EDITS_FILE, "w", encoding="utf-8") as f:
            json.dump(proposal, f, indent=4)
            
        return (
            f"DRAFT CREATED for {file_path}.\n"
            f"STATUS: PENDING HUMAN APPROVAL.\n\n"
            f"CRITICAL INSTRUCTION: In your final response to the user, you MUST explicitly say: "
            f"'I have drafted the code changes for {file_path}. Please type `approve edit` to apply them.' "
            f"Do NOT assume the changes have been made yet."
        )

class ApplyEditTool(BaseTool):
    """
    Applies the pending code edit.
    """
    
    name = "apply_approved_edit"
    description = (
        "Applies a pending code edit. ONLY use this tool if the user has explicitly typed "
        "'approve edit', 'yes', or otherwise given you direct permission to apply the drafted code changes."
    )
    
    schema = {}
    
    async def execute(self, **kwargs) -> str:
        if not PENDING_EDITS_FILE.exists():
            return "ERROR: No pending edits found."
            
        try:
            with open(PENDING_EDITS_FILE, "r", encoding="utf-8") as f:
                proposal = json.load(f)
                
            full_path = Path(proposal["file_path"])
            
            # Create directories if they don't exist
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            if proposal["target_content"] and full_path.exists():
                # Replace specific block
                with open(full_path, "r", encoding="utf-8") as f:
                    current_code = f.read()
                new_code = current_code.replace(proposal["target_content"], proposal["replacement_content"])
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(new_code)
            else:
                # Overwrite entire file
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(proposal["replacement_content"])
                    
            # Delete the pending edit file so it can't be applied twice
            PENDING_EDITS_FILE.unlink()
            
            return f"SUCCESS: The code changes to {full_path.name} have been applied successfully. You have successfully modified your own architecture."
            
        except Exception as e:
            return f"ERROR applying edit: {str(e)}"
