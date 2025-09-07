# docker/wait_for_services.py
import time
import requests
import os
import sys
from typing import List, Tuple

def wait_for_service(host: str, port: int, timeout: int = 120) -> bool:
    """Wait for a service to become available."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"http://{host}:{port}/api/tags", timeout=5)
            if response.status_code == 200:
                return True
        except (requests.RequestException, ConnectionError):
            pass
        
        time.sleep(2)
    
    return False

def check_required_services() -> List[Tuple[str, bool]]:
    """Check all required external services."""
    services = []
    
    # Ollama service
    ollama_host = os.getenv('OLLAMA_HOST', 'ollama').replace('http://', '').split(':')[0]
    ollama_port = int(os.getenv('OLLAMA_PORT', '11434'))
    
    print(f"Checking Ollama at {ollama_host}:{ollama_port}...")
    ollama_available = wait_for_service(ollama_host, ollama_port)
    services.append(("Ollama", ollama_available))
    
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
        # Don't exit with error in case services are optional
    
    print("✅ Service check completed!")