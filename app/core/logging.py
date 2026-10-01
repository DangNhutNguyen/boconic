import logging
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Patterns to mask sensitive data
PATTERNS_TO_MASK = [
    (re.compile(r'(password[\'\"]?\s*[:=]\s*[\'\"]?)([^\'\"\s]+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(token[\'\"]?\s*[:=]\s*[\'\"]?)([^\'\"\s]+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(api[_-]?key[\'\"]?\s*[:=]\s*[\'\"]?)([^\'\"\s]+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(secret[\'\"]?\s*[:=]\s*[\'\"]?)([^\'\"\s]+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(session[\'\"]?\s*[:=]\s*[\'\"]?)([^\'\"\s]+)', re.IGNORECASE), r'\1[REDACTED]'),
]

class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern, repl in PATTERNS_TO_MASK:
                msg = pattern.sub(repl, msg)
            record.msg = msg
        return True

def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("boconic")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)
        
    return logger

logger = setup_logging()
