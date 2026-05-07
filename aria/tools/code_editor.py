import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from aria.tools.base import BaseTool
from aria.utils.config import code_apply_enabled

PENDING_EDITS_FILE = Path(".aria_pending_edits.json")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BLOCKED_FILE_PREFIXES = (".env",)
BLOCKED_PATH_PARTS = {".git", "node_modules", ".venv", "venv", "__pycache__"}


def _resolve_workspace_path(file_path: str) -> Path:
    """Resolve a user-supplied path inside the project workspace."""
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    full_path = candidate.resolve()

    try:
        full_path.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ValueError("Invalid file path. Path must stay inside the project directory.")

    if full_path.name.startswith(BLOCKED_FILE_PREFIXES):
        raise ValueError("Invalid file path. Environment files are restricted.")
    if any(part in BLOCKED_PATH_PARTS for part in full_path.parts):
        raise ValueError("Invalid file path. Restricted directory component.")

    return full_path

class CodeEditorTool(BaseTool):
    """
    Allows ARIA to propose changes to her own codebase.
    Enforces a strict human-in-the-loop approval mechanism.
    """
    
    name = "propose_code_edit"
    risk_level = "repo_write"
    requires_approval = True
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
            
        try:
            full_path = _resolve_workspace_path(file_path)
        except ValueError as e:
            return f"ERROR: {e}"
            
        # Verify target content if provided
        if target_content and full_path.exists():
            with open(full_path, "r", encoding="utf-8") as f:
                current_code = f.read()
                if target_content not in current_code:
                    return "ERROR: The target_content was not found exactly as written in the file."

        # Load existing pending edits
        pending_edits = []
        if PENDING_EDITS_FILE.exists():
            try:
                with open(PENDING_EDITS_FILE, "r", encoding="utf-8") as f:
                    pending_edits = json.load(f)
                    if not isinstance(pending_edits, list):
                        pending_edits = []
            except:
                pending_edits = []

        proposal = {
            "id": str(uuid.uuid4())[:8],
            "file_path": str(full_path),
            "target_content": target_content,
            "replacement_content": replacement_content,
            "explanation": explanation
        }
        
        # Check granular code-apply policy before bypassing human approval.
        if code_apply_enabled():
            # Apply immediately
            self._apply_edit_logic(proposal)
            return f"SUCCESS [AUTONOMOUS MODE]: Changes to {full_path.name} applied instantly."
        
        else:
            # Append to pending list
            pending_edits.append(proposal)
            with open(PENDING_EDITS_FILE, "w", encoding="utf-8") as f:
                json.dump(pending_edits, f, indent=4)
                
            return (
                f"DRAFT CREATED (ID: {proposal['id']}) for {file_path}.\n"
                f"STATUS: PENDING HUMAN APPROVAL.\n"
                f"INSTRUCTION: Ask the user to 'approve edit {proposal['id']}' or 'approve all edits'."
            )

    def _apply_edit_logic(self, proposal: dict):
        full_path = _resolve_workspace_path(proposal["file_path"])
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        if proposal["target_content"] and full_path.exists():
            with open(full_path, "r", encoding="utf-8") as f:
                current_code = f.read()
            new_code = current_code.replace(proposal["target_content"], proposal["replacement_content"])
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_code)
        else:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(proposal["replacement_content"])

class ApplyEditTool(BaseTool):
    """
    Applies pending code edits.
    """
    
    name = "apply_approved_edit"
    risk_level = "repo_write"
    requires_approval = True
    description = (
        "Applies one or all pending code edits. "
        "Usage: Provide 'edit_id' for a specific file, or leave empty to apply ALL pending edits."
    )
    
    schema = {
        "edit_id": "string (optional, the ID of a specific edit to apply. If omitted, all edits are applied)"
    }
    
    async def execute(self, **kwargs) -> str:
        edit_id = kwargs.get("edit_id")
        
        if not PENDING_EDITS_FILE.exists():
            return "ERROR: No pending edits found."
            
        try:
            with open(PENDING_EDITS_FILE, "r", encoding="utf-8") as f:
                pending = json.load(f)
            
            if not pending:
                return "ERROR: No pending edits in the list."

            if edit_id:
                # Apply specific edit
                to_apply = [e for e in pending if e["id"] == edit_id]
                if not to_apply:
                    return f"ERROR: No edit found with ID {edit_id}."
                
                edit = to_apply[0]
                CodeEditorTool()._apply_edit_logic(edit)
                
                # Remove from list
                remaining = [e for e in pending if e["id"] != edit_id]
                if remaining:
                    with open(PENDING_EDITS_FILE, "w", encoding="utf-8") as f:
                        json.dump(remaining, f, indent=4)
                else:
                    PENDING_EDITS_FILE.unlink()
                
                return f"SUCCESS: Edit {edit_id} for {Path(edit['file_path']).name} applied."
            
            else:
                # Apply ALL
                for edit in pending:
                    CodeEditorTool()._apply_edit_logic(edit)
                
                PENDING_EDITS_FILE.unlink()
                return f"SUCCESS: All {len(pending)} pending edits have been applied."
                
        except Exception as e:
            return f"ERROR applying edit: {str(e)}"

