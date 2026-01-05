import json
from curl_cffi import requests
import re
import sys
import time
from urllib.parse import urlparse

DOMAINS_FILE = "domains.json"

def get_current_domains():
    try:
        with open(DOMAINS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: {DOMAINS_FILE} not found.")
        sys.exit(1)

def save_domains(data):
    with open(DOMAINS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    print(f"Updated {DOMAINS_FILE}")

def make_request(url):
    """Robust request using curl_cffi with chrome impersonation"""
    try:
        # verify=False sometimes helps with weird cert chains, but we can try True first or default
        resp = requests.get(url, impersonate="chrome", timeout=15, allow_redirects=True)
        return resp
    except Exception as e:
        print(f"    Request failed: {e}")
        return None

def check_dizipal(current_url):
    print(f"Checking Dizipal: {current_url}")
    
    # 1. Check current
    resp = make_request(current_url)
    if resp and resp.status_code == 200:
        print("  Current URL is OK.")
        return current_url

    # 2. Extract number and increment
    match = re.search(r"dizipal(\d+)", current_url)
    if not match:
        print("  No number found in URL to increment.")
        return current_url

    num = int(match.group(1))
    
    # Handle cases like https://dizipal123.com or https://www.dizipal123.com
    # Best way: Split by the number, but that's risky if number appears twice.
    # We will reconstruct carefully.
    
    base_part_match = re.search(r"^(.*?)dizipal\d+(.*?)$", current_url)
    if not base_part_match:
        return current_url
        
    prefix = base_part_match.group(1) # e.g. https://
    suffix = base_part_match.group(2) # e.g. .com
    
    # Try next 10 numbers (increased to catch up if behind)
    for i in range(1, 10):
        next_num = num + i
        next_url = f"{prefix}dizipal{next_num}{suffix}"
        print(f"  Trying: {next_url}")
        
        resp = make_request(next_url)
        if resp and resp.status_code == 200:
            print(f"  Found new working URL: {next_url}")
            return next_url
            
    print("  Could not find a new working URL.")
    return current_url

def check_dizilla(current_url):
    print(f"Checking Dizilla: {current_url}")
    resp = make_request(current_url)
    
    if not resp:
        return current_url

    final_url = resp.url.rstrip("/")
    
    # Check status
    if resp.status_code != 200:
        print(f"  Status {resp.status_code}")
        # If 403 despite cffi, it's really tough. But cffi usually passes.
        return current_url
        
    # Validation: content must contain "Dizilla" or "__NEXT_DATA__"
    # cffi body is in resp.text
    if "__NEXT_DATA__" in resp.text or "Dizilla" in resp.text:
        if final_url != current_url.rstrip("/"):
                print(f"  Redirected to valid domain: {final_url}")
                return final_url
        print("  Current URL is OK.")
        return current_url
    else:
        print(f"  Validation FAILED for {final_url} (Parking/Fake site detected)")
        return current_url 

def check_generic(key, current_url):
    print(f"Checking Generic ({key}): {current_url}")
    resp = make_request(current_url)
    
    if not resp:
        return current_url
        
    final_url = resp.url.rstrip("/")
    current_stripped = current_url.rstrip("/")
    
    if resp.status_code == 200:
        if final_url != current_stripped:
            # Basic validation: ensure path didn't change to /login or something
            path = urlparse(final_url).path
            if path in ["", "/", "/index.php", "/index.html"]:
                print(f"  Updated to: {final_url}")
                return final_url
        print("  OK.")
        return current_url
    else:
        print(f"  Status: {resp.status_code}")
    
    return current_url

def main():
    data = get_current_domains()
    updated = False
    
    for key, config in data.items():
        base_url = config.get("base_url")
        if not base_url: continue
        
        new_url = base_url
        
        if key == "dizipal" or key == "dizipalorjinal":
            new_url = check_dizipal(base_url)
        elif key == "dizilla":
            new_url = check_dizilla(base_url)
        else:
            new_url = check_generic(key, base_url)
            
        if new_url != base_url:
            data[key]["base_url"] = new_url
            # Update icon if domain changed
            domain = new_url.replace("https://", "").replace("http://", "").split("/")[0]
            data[key]["icon_url"] = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
            updated = True
            
    if updated:
        save_domains(data)
    else:
        print("No updates needed.")

if __name__ == "__main__":
    main()
