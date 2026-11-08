import os
import re
from dataclasses import dataclass, field
from config.settings import database_url, rabbitmq_url, queue_prefix, bounded_int


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    rabbitmq_url: str = field(repr=False)
    prefix: str = 'hunter'
    interval: int = 60
    max_attempts: int = 3
    retry_seconds: int = 30
    recovery_seconds: int = 300

    @classmethod
    def environment(cls):
        database = database_url()
        rabbit = rabbitmq_url()
        prefix = queue_prefix()
        def positive(key, default):
            return bounded_int(key, default, 1, 86400)
        return cls(database, rabbit, prefix,
                   positive('HUNTER_SCAN_SECONDS', 60), positive('HUNTER_MAX_ATTEMPTS', 3),
                   positive('HUNTER_RETRY_SECONDS', 30), positive('HUNTER_RECOVERY_SECONDS', 300))
