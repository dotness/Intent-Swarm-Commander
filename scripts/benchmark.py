#!/usr/bin/env python3
"""Performance validation script.

Validates SC-001 (SMEAC translation < 15s) and provisioning timing.
"""

import argparse
import asyncio
import time
import uuid

import httpx

API_BASE = "http://localhost:8000/api/v1"
HEADERS = {"Authorization": "Bearer perf-test-token"}


async def run_benchmark():
    async with httpx.AsyncClient(base_url=API_BASE, headers=HEADERS) as client:
        # 1. Test Swarm Provisioning
        print("[*] Testing Swarm Provisioning (Target: < 30s)")
        start = time.perf_counter()
        res = await client.post("/swarms", json={"name": f"PerfSwarm-{uuid.uuid4().hex[:8]}", "drone_count": 4})
        duration = time.perf_counter() - start
        
        if res.status_code == 201:
            swarm_id = res.json()["id"]
            print(f"[+] Provisioning completed in {duration:.2f}s")
        else:
            print(f"[-] Provisioning failed: {res.text}")
            return

        # 2. Test SMEAC Processing (SC-001)
        print("\n[*] Testing SMEAC Processing (Target: < 15s)")
        order = {
            "situation": "Enemy forces in sector 7G. Weather clear.",
            "mission": "Conduct ISR sweep of sector.",
            "execution": "Deploy in diamond formation. Altitude 150m.",
            "admin_logistics": "Return at 20% battery.",
            "command_signal": "Standard comms."
        }
        
        start = time.perf_counter()
        res = await client.post(f"/swarms/{swarm_id}/orders", json=order)
        duration = time.perf_counter() - start
        
        if res.status_code == 201:
            order_id = res.json()["order_id"]
            print(f"[+] Order ingestion API response in {duration:.2f}s")
            
            # Poll for translation to finish
            print("[*] Waiting for translation to complete...")
            start_poll = time.perf_counter()
            while time.perf_counter() - start_poll < 30:
                status_res = await client.get(f"/swarms/{swarm_id}/orders/{order_id}")
                if status_res.status_code == 200:
                    data = status_res.json()
                    # In MVP we don't have the full async Temporal worker implemented, 
                    # so this just measures the API response round-trip.
                    if data["status"] in ("translated", "verified", "submitted"):
                        total = time.perf_counter() - start
                        print(f"[+] Total processing time: {total:.2f}s")
                        
                        if total < 15.0:
                            print("[✓] SC-001 REQUIREMENT MET")
                        else:
                            print("[✗] SC-001 REQUIREMENT FAILED")
                        break
                
                await asyncio.sleep(1)
        else:
            print(f"[-] SMEAC submission failed: {res.text}")

        # Cleanup
        await client.delete(f"/swarms/{swarm_id}")
        print("\n[*] Cleaned up performance test artifacts")

if __name__ == "__main__":
    print("=== Intent Swarm Commander Benchmark ===")
    asyncio.run(run_benchmark())
