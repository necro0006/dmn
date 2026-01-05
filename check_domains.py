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
        # allow_redirects=True will follow 3xx redirects automatically
        resp = requests.get(url, impersonate="chrome", timeout=20, allow_redirects=True)
        return resp
    except Exception as e:
        print(f"    Request failed: {e}")
        return None

def check_domain_generic(key, current_url):
    print(f"Checking {key}: {current_url}")
    
    resp = make_request(current_url)
    if not resp:
        return current_url # Network error, keep old
        
    final_url = resp.url.rstrip("/")
    current_stripped = current_url.rstrip("/")
    
    # Check status code
    if resp.status_code == 200:
        # Check if domain changed
        if final_url != current_stripped:
            # Parse hosts to check if it's just a path change on same domain
            current_host = urlparse(current_url).netloc.replace("www.", "")
            final_host = urlparse(final_url).netloc.replace("www.", "")
            
            if current_host == final_host:
                print(f"  Same domain redirect to {final_url} (Ignoring)")
                return current_url

            print(f"  Redirected to: {final_url}")
            
            # Update to new URL
            return final_url
            
        print("  Current URL is OK.")
        return current_url
        
    elif resp.status_code in [403, 503, 500]:
        print(f"  Status {resp.status_code} (Possible Block/Error)")
        # If blocked, we usually DO NOT want to update to this URL if it failed,
        # UNLESS the initial URL resulted in a redirect to a blocked page?
        # But if the initial URL itself returned 403, we keep it (maybe temporary).
        return current_url
        
    else:
        print(f"  Status {resp.status_code}")
        return current_url

def check_dizipal_increment(current_url):
    # Special logic for Dizipal numeric increments
    print(f"Checking Dizipal Increment: {current_url}")
    
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
    
    base_part_match = re.search(r"^(.*?)dizipal\d+(.*?)$", current_url)
    if not base_part_match:
        return current_url
        
    prefix = base_part_match.group(1)
    suffix = base_part_match.group(2)
    
    # Try next numbers
    for i in range(1, 15):
        next_num = num + i
        next_url = f"{prefix}dizipal{next_num}{suffix}"
        print(f"  Trying: {next_url}")
        
        resp = make_request(next_url)
        # Accept 200 OK
        if resp and resp.status_code == 200:
            print(f"  Found new working URL: {next_url}")
            return next_url
            
    print("  Could not find a new working URL.")
    return current_url

def main():
    data = get_current_domains()
    updated = False
    
    for key, config in data.items():
        base_url = config.get("base_url")
        if not base_url: continue
        
        new_url = base_url
        
        # dizzy/dizipal logic
        if "dizipal" in key:
            new_url = check_dizipal_increment(base_url)
        else:
            # Generic check for everything else (Dizilla, HDfilm, etc.)
            new_url = check_domain_generic(key, base_url)
            
        if new_url != base_url:
            data[key]["base_url"] = new_url
            # Update icon
            try:
                domain = new_url.replace("https://", "").replace("http://", "").split("/")[0]
                data[key]["icon_url"] = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
            except:
                pass
            updated = True
            
    if updated:
        save_domains(data)
    else:
        print("No updates needed.")

if __name__ == "__main__":
    main()
