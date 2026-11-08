"""Configura apenas o runner efemero GitHub Actions; nunca banco principal."""

import os
from pathlib import Path
import secrets


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("GITHUB_ENV"):
        raise ValueError("Use exclusivamente no runner GitHub Actions.")
    db_password = secrets.token_hex(32)
    rabbit_password = secrets.token_hex(32)
    values = {
        "HUNTER_ENV": "test",
        "HUNTER_QUEUE_TESTS": "1",
        "HUNTER_COLLECTION_ENABLED": "0",
        "HUNTER_QUEUE_PREFIX": "hunter_test",
        "HUNTER_SCAN_SECONDS": "2",
        "HUNTER_RETRY_SECONDS": "1",
        "JWT_SECRET_KEY": secrets.token_hex(32),
        "HUNTER_RABBIT_USER": "hunter",
        "HUNTER_RABBIT_PASSWORD": rabbit_password,
        "HUNTER_TEST_DB_PASSWORD": db_password,
        "DATABASE_URL": f"postgresql://hunter_test:{db_password}@127.0.0.1:55432/hunter_test",
        "RABBITMQ_URL": f"amqp://hunter:{rabbit_password}@127.0.0.1:5673/hunter_test",
        "HUNTER_BROWSER_CHANNEL": "chromium",
    }
    values["HUNTER_TEST_DATABASE_URL"] = values["DATABASE_URL"]
    values["MIGRATION_DATABASE_URL"] = values["DATABASE_URL"]
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")
    print("Ambiente CI isolado preparado; valores secretos omitidos.")


if __name__ == "__main__":
    main()
