import sqlite3
import json
from agent.security.audit_logger import AuditLogger

def test_audit_logger_creates_db_and_logs(tmp_path):
    db_path = tmp_path / "audit.db"
    logger = AuditLogger(db_path)
    
    assert db_path.exists()
    
    logger.log_command("worker_1", "echo test", 0)
    logger.log_security_violation("worker_1", "PATH_GUARDIAN_BLOCK", "Blocked access to /etc/passwd")
    logger.log_network_egress("worker_1", "github.com", True)
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT event_type, worker_id, details FROM audit_events ORDER BY id ASC")
        rows = cursor.fetchall()
        
    assert len(rows) == 3
    
    assert rows[0][0] == "COMMAND_EXECUTION"
    assert rows[0][1] == "worker_1"
    details_1 = json.loads(rows[0][2])
    assert details_1["command"] == "echo test"
    assert details_1["exit_code"] == 0
    
    assert rows[1][0] == "SECURITY_VIOLATION"
    assert rows[1][1] == "worker_1"
    details_2 = json.loads(rows[1][2])
    assert details_2["violation_type"] == "PATH_GUARDIAN_BLOCK"
    
    assert rows[2][0] == "NETWORK_EGRESS"
    assert rows[2][1] == "worker_1"
    details_3 = json.loads(rows[2][2])
    assert details_3["target_host"] == "github.com"
    assert details_3["allowed"] is True
