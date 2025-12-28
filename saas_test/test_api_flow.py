import requests
import time
import json
import sys

API_URL = "http://localhost:8000"

def test_api_generation():
    # 1. Define schema
    # 1. Define schema matching SchemaConfig Pydantic model
    schema = {
        "name": "Test Integration Schema",
        "tables": [
            {
                "name": "users",
                "row_count": 50
            }
        ],
        "columns": {
            "users": [
                {
                    "name": "id",
                    "type": "int", 
                    "distribution_params": {"distribution": "sequence"}
                },
                {
                    "name": "name", 
                    "type": "text", 
                    "distribution_params": {"distribution": "fake.name"}
                }
            ]
        }
    }
    
    # 2. Submit Job
    print("🚀 Submitting job...")
    try:
        resp = requests.post(f"{API_URL}/jobs", json={"schema_config": schema}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        job_id = data["job_id"]
        print(f"✅ Job ID: {job_id}")
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Is uvicorn running?")
        sys.exit(1)
    
    # 3. Poll Status
    status = "queued"
    for _ in range(30): # Timeout after 30s
        time.sleep(1)
        resp = requests.get(f"{API_URL}/jobs/{job_id}")
        data = resp.json()
        status = data["status"]
        progress = data.get("progress", 0)
        message = data.get("message", "")
        print(f"🔄 Status: {status} ({progress}%) - {message}")
        
        if status == "SUCCESS":
            print(f"🎉 Result: {data.get('result')}")
            break
        if status == "FAILURE":
            print(f"❌ Failure: {data}")
            sys.exit(1)
            
    if status != "SUCCESS":
        print("❌ Timed out waiting for job completion")
        sys.exit(1)
        
    print("✅ Test Passed!")

if __name__ == "__main__":
    test_api_generation()
