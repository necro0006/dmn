import asyncio
import json
import logging
import sys
import re
from urllib.parse import urlparse
from curl_cffi.requests import AsyncSession

# Configuration
DOMAINS_FILE = "domains.json"
CONCURRENCY_LIMIT = 10
TIMEOUT = 30
USER_AGENT_IMPERSONATE = "chrome"

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("DomainChecker")

class DomainChecker:
    def __init__(self, domains_file):
        self.domains_file = domains_file
        self.semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        self.updated = False

    def load_domains(self):
        try:
            with open(self.domains_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"{self.domains_file} not found.")
            sys.exit(1)

    def save_domains(self, data):
        if self.updated:
            with open(self.domains_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            logger.info(f"✅ Successfully updated {self.domains_file}")
        else:
            logger.info("No updates were necessary.")

    def is_suspicious_redirect(self, original_url, final_url, html_content=""):
        """
        Analyzes if a redirect is valid or suspicious (e.g. to a parking page, login page, or completely unrelated site).
        """
        original = urlparse(original_url)
        final = urlparse(final_url)

        # 1. Host Change Check
        if original.netloc != final.netloc:
            # If subdomains match (e.g., www.site.com -> site.com), it's fine.
            orig_domain = original.netloc.replace("www.", "")
            final_domain = final.netloc.replace("www.", "")
            
            if orig_domain == final_domain:
                return False # Safe redirect (www or http/https)

            # 2. Path Suspicion (Redirected to login/blocked page?)
            weird_paths = ["/login", "/giris", "/engel", "/suspend", "/parking", "/account/login"]
            for path in weird_paths:
                if path in final.path.lower():
                    logger.warning(f"⚠️ Suspicious redirect path detected: {final_url}")
                    return True

            # 3. Content Suspicion (Parking/Error pages)
            if html_content:
                keywords = ["domain expired", "domain suspended", "under construction", "site blocked", "tib ", "btk "]
                lower_content = html_content.lower()[:5000] # Check header/top body
                for kw in keywords:
                    if kw in lower_content:
                        logger.warning(f"⚠️ Suspicious content detected: '{kw}' in {final_url}")
                        return True
            
            logger.info(f"ℹ️ Domain changed: {original.netloc} -> {final.netloc}")
            return False # Accepted domain change

        return False

    async def check_domain(self, key, config, session):
        original_url = config.get("base_url")
        if not original_url:
            return

        async with self.semaphore:
            try:
                logger.info(f"Checking {key}: {original_url}")
                
                # Make request follows redirects by default
                response = await session.get(
                    original_url, 
                    impersonate=USER_AGENT_IMPERSONATE, 
                    timeout=TIMEOUT,
                    allow_redirects=True
                )

                final_url = response.url.rstrip("/")
                original_stripped = original_url.rstrip("/")

                # CRITICAL CHANGE: Check for redirect FIRST, separate from Status Code.
                # User wants to capture new URL even if it ends up in a Cloudflare (403/503) page.
                if final_url != original_stripped:
                    # Validate the redirect
                    if not self.is_suspicious_redirect(original_stripped, final_url, response.text):
                        logger.info(f"🔄 UPDATE {key}: {original_stripped} -> {final_url} (Status: {response.status_code})")
                        config["base_url"] = final_url
                        
                        # Auto-update Icon
                        try:
                            domain = urlparse(final_url).netloc.replace("www.", "")
                            config["icon_url"] = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
                        except:
                            pass
                            
                        self.updated = True
                        return # Stop processing, we found a new domain

                # If no redirect (or rejected), then check status code for logging
                if response.status_code == 200:
                    logger.debug(f"✅ {key} is OK.")
                elif response.status_code in [403, 503]:
                    logger.warning(f"🛡️ {key} returned {response.status_code} (Cloudflare/Protection?) - No working redirect detected.")
                else:
                    logger.warning(f"❌ {key} returned {response.status_code}")

            except Exception as e:
                logger.error(f"❌ Error checking {key}: {e}")

    async def run(self):
        data = self.load_domains()
        
        # Use AsyncSession for optimal TLS fingerprinting
        async with AsyncSession() as session:
            tasks = []
            for key, config in data.items():
                tasks.append(self.check_domain(key, config, session))
            
            await asyncio.gather(*tasks)

        self.save_domains(data)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    checker = DomainChecker(DOMAINS_FILE)
    asyncio.run(checker.run())
