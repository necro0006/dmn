import json
import requests
import re
import sys
import time

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

def check_dizipal(current_url):
    print(f"Checking Dizipal: {current_url}")
    
    # 1. Check current
    try:
        resp = requests.get(current_url, timeout=10)
        if resp.status_code == 200:
            print("  Current URL is OK.")
            return current_url
    except Exception as e:
        print(f"  Current URL failed: {e}")

    # 2. Extract number and increment
    match = re.search(r"dizipal(\d+)", current_url)
    if not match:
        print("  No number found in URL to increment.")
        return current_url

    num = int(match.group(1))
    base_part = current_url.split(f"dizipal{num}")[0]
    suffix = current_url.split(f"dizipal{num}")[1] if len(current_url.split(f"dizipal{num}")) > 1 else ""
    
    # Try next 5 numbers
    for i in range(1, 6):
        next_num = num + i
        next_url = f"{base_part}dizipal{next_num}{suffix}"
        print(f"  Trying: {next_url}")
        try:
            resp = requests.get(next_url, timeout=10)
            if resp.status_code == 200:
                print(f"  Found new working URL: {next_url}")
                return next_url
        except:
            continue
            
    print("  Could not find a new working URL.")
    return current_url

def check_dizilla(current_url):
    print(f"Checking Dizilla: {current_url}")
    try:
        resp = requests.get(current_url, timeout=10, allow_redirects=True)
        final_url = resp.url.rstrip("/")
        
        if resp.status_code != 200:
            print(f"  Status {resp.status_code}")
            return current_url # Keep old if failing
            
        # Validation: content must contain "Dizilla" or "__NEXT_DATA__"
        if "__NEXT_DATA__" in resp.text or "Dizilla" in resp.text:
            if final_url != current_url.rstrip("/"):
                 print(f"  Redirected to valid domain: {final_url}")
                 return final_url
            print("  Current URL is OK.")
            return current_url
        else:
            print(f"  Validation FAILED for {final_url} (Parking/Fake site detected)")
            return current_url # Do NOT update to fake site
            
    except Exception as e:
        print(f"  Check failed: {e}")
        return current_url

def check_generic(key, current_url):
    print(f"Checking Generic ({key}): {current_url}")
    try:
        # User-Agent is critical for some sites (Cloudflare)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        resp = requests.get(current_url, headers=headers, timeout=15, allow_redirects=True)
        final_url = resp.url.rstrip("/")
        current_stripped = current_url.rstrip("/")
        
        if resp.status_code == 200:
            if final_url != current_stripped:
                # Basic validation: ensure path didn't change to /login or something
                if requests.utils.urlparse(final_url).path in ["", "/", "/index.php"]:
                    print(f"  Updated to: {final_url}")
                    return final_url
            print("  OK.")
            return current_url
    except Exception as e:
        print(f"  Error: {e}")
    
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
