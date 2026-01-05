import json
import re
import sys
import time
from urllib.parse import urlparse
import requests as std_requests

# Defensive imports
try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

try:
    import cloudscraper
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
except ImportError:
    cloudscraper = None
    scraper = None

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

def get_manual_redirect(resp, original_url):
    """Detects redirects in Location headers or Meta Refresh in body"""
    # 1. Location Header (even on 403)
    if "Location" in resp.headers:
        new_url = resp.headers["Location"]
        if not new_url.startswith("http"):
            parsed = urlparse(original_url)
            new_url = f"{parsed.scheme}://{parsed.netloc}{new_url}"
        return new_url
    
    # 2. Meta Refresh (Status 200/403)
    try:
        content = resp.text.lower()
        if 'http-equiv="refresh"' in content or "http-equiv='refresh'" in content:
            # Pattern: content="0;url=https://newdomain.com"
            match = re.search(r'url=([^\s"\'>]+)', content)
            if match:
                new_url = match.group(1).strip("'\"")
                if not new_url.startswith("http"):
                    parsed = urlparse(original_url)
                    new_url = f"{parsed.scheme}://{parsed.netloc}{new_url}"
                return new_url
    except:
        pass
    return None

def make_request(url, redirects=0):
    """Robust request with multiple fallbacks and universal redirect detection"""
    if redirects > 5:
        return None
        
    methods = []
    # Priority 1: Cloudscraper
    if scraper:
        methods.append(("cloudscraper", lambda u: scraper.get(u, timeout=20, allow_redirects=True)))
    # Priority 2: curl_cffi
    if cffi_requests:
        methods.append(("curl_cffi", lambda u: cffi_requests.get(u, impersonate="chrome", timeout=20, allow_redirects=True)))
    # Priority 3: standard requests
    methods.append(("std_requests", lambda u: std_requests.get(u, timeout=20, allow_redirects=True, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })))
    
    for name, method in methods:
        try:
            resp = method(url)
            if not resp: continue
            
            # CHECK FOR REDIRECTS (on 200 or 403)
            # Many sites use 403 + Location or Meta Refresh as challenge/landing
            if resp.status_code in [200, 403]:
                new_url = get_manual_redirect(resp, url)
                if new_url and new_url.rstrip("/") != url.rstrip("/"):
                    print(f"    Detected manual redirect ({name}) to: {new_url}")
                    return make_request(new_url, redirects + 1)
            
            if resp.status_code == 200:
                return resp
            
            print(f"    {name} got status: {resp.status_code}")
        except Exception as e:
            print(f"    {name} attempt failed: {e}")
            
    return None

def check_domain_generic(key, current_url):
    print(f"Checking {key}: {current_url}")
    
    resp = make_request(current_url)
    if not resp:
        return current_url # Network error, keep old
        
    final_url = resp.url.rstrip("/")
    current_stripped = current_url.rstrip("/")
    
    # Check for domain change regardless of status code
    if final_url != current_stripped:
        current_host = urlparse(current_stripped).netloc.replace("www.", "")
        final_host = urlparse(final_url).netloc.replace("www.", "")
        
        if current_host != final_host:
            # Domain changed!
            path = urlparse(final_url).path.lower()
            # Suspicious patterns that usually indicate block pages or auth walls
            suspicious = ["blocked", "engel", "giris", "login", "captcha", "forbidden", "access-denied"]
            is_suspicious = any(ps in path for ps in suspicious)
            
            if not is_suspicious:
                print(f"  Domain changed to: {final_url} (Status: {resp.status_code})")
                return final_url
            else:
                print(f"  Redirected to suspicious path: {path} (Ignoring domain change)")
    
    # Check status code for current or slightly changed path
    if resp.status_code == 200:
        print("  Current URL is OK.")
        return current_url
        
    elif resp.status_code in [403, 503, 500]:
        print(f"  Status {resp.status_code} (Possible Block/Error)")
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
