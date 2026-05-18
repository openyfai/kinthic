import pytest
from pathlib import Path
from aria.tools.code_editor import CodeEditorTool
from aria.utils.config import VYN_BACKUPS, WORKSPACE_DIR, ensure_vyn_home

@pytest.mark.asyncio
async def test_failsafe_backup_for_edits(tmp_path):
    # Ensure VYN HOME structures are created
    ensure_vyn_home()

    # Create a mock file in the workspace
    file_name = "test_failsafe_backup.txt"
    test_file_path = WORKSPACE_DIR / file_name
    original_content = "Hello, this is original line 1.\nHello, this is original line 2."
    
    test_file_path.write_text(original_content, encoding="utf-8")

    # Define edit proposal
    proposal = {
        "id": "test_bkp",
        "file_path": str(test_file_path),
        "target_content": "original line 1",
        "replacement_content": "edited line 1",
        "explanation": "Testing backups."
    }

    # Verify backups directory exists
    assert VYN_BACKUPS.exists()

    # Apply the edit
    tool = CodeEditorTool()
    tool._apply_edit_logic(proposal)

    # 1. Verify file content updated successfully
    updated_content = test_file_path.read_text(encoding="utf-8")
    assert "edited line 1" in updated_content
    assert "original line 1" not in updated_content

    # 2. Verify a backup file was created in VYN_BACKUPS
    backups = list(VYN_BACKUPS.glob("test_failsafe_backup.txt_*.bak"))
    assert len(backups) >= 1

    # Get the latest backup file
    backup_file = backups[0]
    backup_content = backup_file.read_text(encoding="utf-8")
    
    # 3. Verify backup content matches the original content perfectly
    assert backup_content == original_content

    # Clean up test files
    if test_file_path.exists():
        test_file_path.unlink()
    for bk in backups:
        if bk.exists():
            bk.unlink()
