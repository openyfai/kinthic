# ARIA Omniscience Protocol

This is a simple guide to expanding ARIA's vision to your entire PC.

## The Strategy: "Global Eyes, Local Hands"
We want ARIA to be able to **SEE** everything, but only **TOUCH** her laboratory.

### 1. The Eyes (READ ACCESS)
To give her global vision, we need to modify these tools in `aria/tools/`:
- **file_reader.py**: Remove the check that restricts paths to the project root.
- **system.py (ListDirectory)**: Allow it to accept any absolute path (e.g., `C:/Users`).

### 2. The Hands (WRITE ACCESS)
To keep her safe, we **KEEP** these restrictions:
- **code_editor.py**: Must still only allow writing to `e:/AGI/workspace/`.
- **system.py (Docker)**: The Docker sandbox should stay locked to the workspace for writing.

### 3. The Knowledge
Update `identity.py` to tell her:
> "Your vision is now system-wide. You can read any file on this PC to gain context, but your construction work must remain in `/workspace`."

---
*Created for Yuseff's ARIA Architecture.*
