# docker/wait_for_services.py
import time
import os
import sys
import urllib.request
import urllib.error
from typing import List, Tuple


def wait_for_service(host: str, port: int, timeout: int = 120) -> bool:
    """Wait for a service to become available."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(f"http://{host}:{port}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass

        time.sleep(2)

    return False


def check_required_services() -> List[Tuple[str, bool]]:
    """Check all required external services."""
    services = []

    # Database (if external)
    db_host = os.getenv('DATABASE_HOST')
    if db_host:
        db_port = int(os.getenv('DATABASE_PORT', '5432'))
        print(f"Checking Database at {db_host}:{db_port}...")
        db_available = wait_for_service(db_host, db_port)
        services.append(("Database", db_available))

    return services


if __name__ == "__main__":
    print("🔍 Checking external service dependencies...")

    services = check_required_services()

    all_available = True
    for service_name, available in services:
        status = "✅" if available else "❌"
        print(f"{status} {service_name}: {'Available' if available else 'Unavailable'}")
        if not available:
            all_available = False

    if not all_available:
        print("❌ Some required services are unavailable. Continuing anyway...")

    print("✅ Service check completed!")
