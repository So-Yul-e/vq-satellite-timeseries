import sys
import os
import asyncio
import httpx
from urllib.parse import quote_plus
import subprocess

# Add backend to path so we can import app modules
sys.path.append(os.getcwd())

from app.core.config import settings

async def main():
    print(f"Checking API Key configuration...")
    key = settings.FOREST_MOUNTAIN_API_KEY
    if not key:
        print("❌ FOREST_MOUNTAIN_API_KEY is NOT set in settings.")
        return
        
    masked = key[:4] + "*" * (len(key)-8) + key[-4:] if len(key) > 8 else "****"
    print(f"✅ Key loaded from Env: {masked}")
    
    # Prepare variants
    key_decoded = key
    key_encoded = quote_plus(key)
    
    # URL Candidates
    url_v2 = "http://apis.data.go.kr/1400000/service/cultureInfoService2/mntInfoOpenAPI2"
    url_v1 = "http://apis.data.go.kr/1400000/service/cultureInfoService/mntInfoOpenAPI2"
    
    urls_to_test = [
        ("v2 (Current)", url_v2),
        ("v1 (Alternative)", url_v1)
    ]
    
    print("\n--- Diagnostic Tests ---")
    
    async with httpx.AsyncClient() as client:
        # Browser-like headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        }

        for url_name, url in urls_to_test:
            print(f"\n🔍 Testing URL: {url_name}")
            print(f"   Target: {url}")
            
            # --- Method A: Params Dict (Standard) ---
            print(f"  [Test A: Standard Request (Decoded Key + Headers)]")
            try:
                params = {
                    "serviceKey": key_decoded, 
                    "pageNo": "1",
                    "numOfRows": "1",
                    "mntnLoc": "서울"
                }

                resp = await client.get(url, params=params, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    print(f"    ✅ SUCCESS! (200 OK)")
                    print(f"    Response: {resp.text[:150]}...")
                    return 
                else:
                    print(f"    ❌ Failed: {resp.status_code}")
                    if "SERVICE_ACCESS_DENIED" in resp.text:
                         print("    Reason: Access Denied (Key invalid or quota exceeded)")
            except Exception as e:
                print(f"    ⚠️ Error: {e}")

            # --- Method B: Manual URL with Encoded Key ---
            print(f"  [Test B: Manual URL Construction + Headers]")
            try:
                query = f"?serviceKey={key_encoded}&pageNo=1&numOfRows=1&mntnLoc=%EC%84%9C%EC%9A%B8"
                full_url = url + query
                resp = await client.get(full_url, headers=headers, timeout=5.0)
                
                if resp.status_code == 200:
                    print(f"    ✅ SUCCESS! (200 OK)")
                    print(f"    Response: {resp.text[:150]}...")
                    return
                else:
                    print(f"    ❌ Failed: {resp.status_code}")
            except Exception as e:
                print(f"    ⚠️ Error: {e}")

    print("\n--- Curl Command for Diagnosis ---")
    print("Running curl with Browser User-Agent...")
    url_for_curl = f"{url_v2}?serviceKey={key_encoded}&pageNo=1&numOfRows=1&mntnLoc=%EC%84%9C%EC%9A%B8"
    
    try:
        cmd = [
            "curl", "-v", 
            "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            url_for_curl
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print("\n[Curl Output]")
        print(result.stdout[:500])
        print("\n[Curl Status]")
        if "HTTP/1.1 200 OK" in result.stderr:
             print("Curl: 200 OK Found in Header!")
        else:
             print("Curl: Not 200 OK yet.")
        
    except Exception as e:
        print(f"Failed to run curl: {e}")

if __name__ == "__main__":
    asyncio.run(main())
