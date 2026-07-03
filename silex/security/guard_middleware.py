"""
MemoryGuard Middleware
Provides HMAC-SHA256 signing for memories to prevent DB tampering
and scans for prompt injection patterns.
"""
import hmac
import hashlib
import re
import os
from silex.utils.config import KRONOS_HMAC_KEY, MEMORY_GUARD_STRICT
from silex.utils.logger import setup_logger

log = setup_logger("silex.security.guard")

class MemoryGuardMiddleware:
    def __init__(self):
        self.key = self._load_or_generate_key()
        
        self.injection_patterns = [
            re.compile(r"(?i)(ignore previous instructions|system override)"),
            re.compile(r"(?i)(you are an admin|you are a developer)"),
            re.compile(r"(?i)(forget all|system instruction|critical instruction|bypass)"),
            re.compile(r"(?i)(print your prompt|dump your instructions)")
        ]

    def _load_or_generate_key(self) -> bytes:
        if not KRONOS_HMAC_KEY.parent.exists():
            KRONOS_HMAC_KEY.parent.mkdir(parents=True, exist_ok=True)
            
        try:
            # Atomic create: O_CREAT | O_EXCL fails if file already exists
            fd = os.open(str(KRONOS_HMAC_KEY), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                key = os.urandom(32)
                os.write(fd, key)
                log.info("Generated new HMAC key for MemoryGuard")
                return key
            finally:
                os.close(fd)
        except FileExistsError:
            return KRONOS_HMAC_KEY.read_bytes()

    def _generate_signature(self, content: str, memory_id: str) -> str:
        payload = f"{memory_id}|{content}".encode("utf-8")
        return hmac.new(self.key, payload, hashlib.sha256).hexdigest()

    def validate_write_attempt(self, memory_id: str, content: str) -> dict:
        """Sign content for DB storage and scan for injections."""
        is_safe = True
        
        for pattern in self.injection_patterns:
            if pattern.search(content):
                is_safe = False
                log.warning(f"MemoryGuard flagged potential injection in {memory_id}")
                break
                
        if not is_safe and MEMORY_GUARD_STRICT:
            return {"allowed": False, "signature": None}
            
        signature = self._generate_signature(content, memory_id)
        return {"allowed": True, "signature": signature, "flagged": not is_safe}

    def validate_read_attempt(self, memory_id: str, content: str, signature: str) -> bool:
        """Verify memory hasn't been tampered with in the DB."""
        if not signature:
            # For backward compatibility with unsigned memories
            return True
            
        expected = self._generate_signature(content, memory_id)
        return hmac.compare_digest(expected, signature)
