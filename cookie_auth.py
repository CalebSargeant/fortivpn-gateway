#!/usr/bin/env python3
"""
FortiVPN Cookie Authentication via Microsoft SAML
Extracts session cookies for openfortivpn using Selenium and 1Password CLI
"""
import os
import time
import subprocess
import logging
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration from environment
VPN_GATEWAY = os.environ.get("VPN_GATEWAY")
VPN_PORT = os.environ.get("VPN_PORT", "443")
OP_ITEM_NAME = os.environ.get("OP_ITEM_NAME", "Microsoft")
OP_VAULT = os.environ.get("OP_VAULT", "Private")
COOKIE_FILE = os.environ.get("COOKIE_FILE", "/shared/vpn_cookie.txt")
REFRESH_INTERVAL = int(os.environ.get("REFRESH_INTERVAL", "21600"))  # 6 hours default
AUTH_TIMEOUT = int(os.environ.get("AUTH_TIMEOUT", "60"))  # Authentication timeout in seconds
WATCH_INTERVAL = int(os.environ.get("WATCH_INTERVAL", "5"))  # Check for cookie deletion every 5 seconds

if not VPN_GATEWAY:
    logger.error("VPN_GATEWAY environment variable must be set")
    raise ValueError("VPN_GATEWAY environment variable must be set")

def get_1password_field(item_name, field_name, vault="Private"):
    """Fetch a field from 1Password using the CLI"""
    logger.debug(f"Fetching field '{field_name}' from 1Password item '{item_name}' in vault '{vault}'")
    try:
        result = subprocess.run(
            ["op", "item", "get", item_name, "--vault", vault, "--format", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        item_data = json.loads(result.stdout)
        
        for field in item_data.get("fields", []):
            if field.get("id") == field_name or field.get("label") == field_name:
                logger.debug(f"Successfully retrieved field '{field_name}'")
                return field.get("value", "")
        
        logger.error(f"Field '{field_name}' not found in item '{item_name}'")
        raise ValueError(f"Field '{field_name}' not found in item '{item_name}'")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch {field_name} from 1Password: {e.stderr}")
        raise ValueError(f"Failed to fetch {field_name} from 1Password: {e.stderr}")

def get_1password_otp(item_name, vault="Private"):
    """Fetch TOTP code from 1Password using the CLI"""
    logger.debug(f"Fetching OTP from 1Password item '{item_name}' in vault '{vault}'")
    try:
        result = subprocess.run(
            ["op", "item", "get", item_name, "--vault", vault, "--otp"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.debug("OTP retrieved successfully")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch OTP from 1Password: {e.stderr}")
        raise ValueError(f"Failed to fetch OTP from 1Password: {e.stderr}")

def extract_cookie():
    """Extract VPN session cookie via Microsoft SAML authentication"""
    logger.info("Starting cookie extraction")
    logger.info(f"Target VPN: {VPN_GATEWAY}:{VPN_PORT}")
    
    # Fetch credentials from 1Password
    logger.info(f"Fetching credentials from 1Password item: {OP_ITEM_NAME} in vault: {OP_VAULT}")
    EMAIL = get_1password_field(OP_ITEM_NAME, "username", OP_VAULT)
    PASSWORD = get_1password_field(OP_ITEM_NAME, "password", OP_VAULT)
    logger.info(f"Email: {EMAIL}")
    
    # Set up Chrome options for headless mode
    logger.info("Configuring Chrome browser options")
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.binary_location = "/usr/bin/chromium"
    
    # Set up the driver
    logger.info("Initializing Chrome WebDriver")
    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Step 1: Navigate to FortiVPN SAML login endpoint
        logger.info("Step 1: Navigating to FortiVPN SAML login")
        saml_url = f"https://{VPN_GATEWAY}:{VPN_PORT}/remote/saml/start?redirect=1"
        driver.get(saml_url)
        time.sleep(3)
        driver.save_screenshot("/tmp/fortivpn_saml_start.png")
        logger.debug("Screenshot saved: /tmp/fortivpn_saml_start.png")
        
        # Step 2: Wait for Microsoft redirect
        logger.info("Step 2: Waiting for Microsoft authentication page")
        WebDriverWait(driver, 10).until(
            lambda d: "login.microsoftonline.com" in d.current_url or "login.microsoft.com" in d.current_url
        )
        logger.debug(f"Redirected to: {driver.current_url}")
        
        # Step 3: Enter email
        logger.info("Step 3: Entering email in Microsoft login")
        ms_email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='loginfmt']"))
        )
        ms_email_input.clear()
        ms_email_input.send_keys(EMAIL)
        logger.debug("Email entered")
        
        # Click Next button
        next_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Next']"))
        )
        next_button.click()
        logger.debug("Next button clicked")
        
        # Step 4: Enter password
        logger.info("Step 4: Entering password")
        time.sleep(2)
        ms_password_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password'], input[name='passwd']"))
        )
        ms_password_input.send_keys(PASSWORD)
        time.sleep(1)
        logger.info("Password entered successfully")
        driver.save_screenshot("/tmp/fortivpn_password_entered.png")
        
        # Click Sign in button
        signin_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Sign in']"))
        )
        signin_button.click()
        logger.debug("Sign in button clicked")
        
        # Step 5: Handle OTP if required
        logger.info("Step 5: Checking for OTP requirement")
        time.sleep(3)
        driver.save_screenshot("/tmp/fortivpn_after_password.png")
        
        otp_handled = False
        try:
            otp_input = driver.find_element(By.CSS_SELECTOR, "input[type='tel'], input[name='otc']")
            logger.info("OTP page detected, fetching code from 1Password")
            otp_code = get_1password_otp(OP_ITEM_NAME, OP_VAULT)
            otp_input.clear()
            otp_input.send_keys(otp_code)
            logger.debug("OTP code entered")
            
            verify_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Verify']"))
            )
            verify_button.click()
            logger.info("OTP submitted successfully")
            otp_handled = True
            time.sleep(3)
        except Exception as otp_error:
            logger.debug(f"No OTP page found or OTP handling failed: {otp_error}")
            if "OTP page detected" in str(otp_error):
                logger.error("OTP was detected but handling failed - check 1Password configuration")
                raise

        # Step 6: Wait for authentication to complete
        logger.info("Step 6: Waiting for authentication to complete")

        # Handle "Stay signed in?" prompt with multiple attempts
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                driver.save_screenshot(f"/tmp/fortivpn_prompt_check_{attempt}.png")
                logger.debug(f"Current URL: {driver.current_url}")

                # Check for "Stay signed in?" prompt
                try:
                    yes_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and (@value='Yes' or @id='idSIButton9')]"))
                    )
                    logger.info("Found 'Stay signed in?' prompt, clicking Yes")
                    yes_button.click()
                    time.sleep(3)
                    break
                except:
                    logger.debug(f"No 'Stay signed in' prompt found (attempt {attempt + 1})")

                # Check for "No" button and click it if "Yes" not found
                try:
                    no_button = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and (@value='No' or @id='idBtn_Back')]"))
                    )
                    logger.info("Found 'Stay signed in?' prompt with No button, clicking No to proceed")
                    no_button.click()
                    time.sleep(3)
                    break
                except:
                    logger.debug("No 'No' button found either")

                # Check if we're already redirected away from Microsoft
                if "login.microsoftonline.com" not in driver.current_url and "login.microsoft.com" not in driver.current_url:
                    logger.info("Already redirected away from Microsoft")
                    break

                time.sleep(2)
            except Exception as e:
                logger.debug(f"Error checking for prompts: {e}")
                if attempt == max_attempts - 1:
                    logger.warning("Max attempts reached for prompt handling")

        # Wait for redirect away from Microsoft (more flexible with better error handling)
        redirect_successful = False
        try:
            logger.info(f"Waiting for redirect away from Microsoft authentication (timeout: {AUTH_TIMEOUT}s)...")
            WebDriverWait(driver, AUTH_TIMEOUT).until(
                lambda d: "login.microsoftonline.com" not in d.current_url and "login.microsoft.com" not in d.current_url
            )
            logger.info(f"✓ Left Microsoft auth page. Current URL: {driver.current_url}")
            redirect_successful = True
            time.sleep(2)  # Give time for any additional redirects
            driver.save_screenshot("/tmp/fortivpn_after_redirect.png")
        except Exception as e:
            logger.error(f"Wait for redirect timed out: {e}")
            logger.info(f"Current URL when timeout occurred: {driver.current_url}")
            driver.save_screenshot("/tmp/fortivpn_timeout.png")

            # Check page source for clues
            page_text = driver.find_element(By.TAG_NAME, "body").text
            logger.debug(f"Page text: {page_text[:500]}")

            # If still on Microsoft page, try to find and click any remaining buttons
            if "login.microsoftonline.com" in driver.current_url or "login.microsoft.com" in driver.current_url:
                logger.info("Still on Microsoft page, checking for any remaining interactive elements...")
                try:
                    # Try to find any submit buttons
                    submit_buttons = driver.find_elements(By.XPATH, "//input[@type='submit'] | //button[@type='submit']")
                    if submit_buttons:
                        logger.info(f"Found {len(submit_buttons)} submit button(s)")
                        for idx, button in enumerate(submit_buttons):
                            logger.info(f"Button {idx}: value='{button.get_attribute('value')}', id='{button.get_attribute('id')}'")
                        # Click the first clickable button
                        for button in submit_buttons:
                            if button.is_displayed() and button.is_enabled():
                                logger.info(f"Clicking button: {button.get_attribute('value') or button.get_attribute('id')}")
                                button.click()
                                time.sleep(5)
                                break
                except Exception as btn_e:
                    logger.debug(f"Error finding/clicking buttons: {btn_e}")

        # Try to navigate directly to the VPN gateway to pick up cookies
        logger.info("Attempting to navigate to VPN gateway to collect cookies")
        try:
            driver.get(f"https://{VPN_GATEWAY}:{VPN_PORT}/")
            time.sleep(3)
            logger.info(f"Successfully navigated to VPN gateway. Current URL: {driver.current_url}")
        except Exception as e:
            logger.warning(f"Could not navigate to VPN gateway: {e}")
        
        driver.save_screenshot("/tmp/fortivpn_final.png")
        
        # Extract cookies from VPN domain
        cookies = driver.get_cookies()
        logger.info(f"Found {len(cookies)} total cookies from current domain")

        # Log current domain for debugging
        logger.info(f"Current domain: {driver.current_url}")

        # Find the SVPNCOOKIE (or similar session cookie)
        session_cookie = None
        vpn_cookies = []

        for cookie in cookies:
            logger.debug(f"Cookie: {cookie['name']} = {cookie['value'][:20] if len(cookie['value']) > 20 else cookie['value']}...")
            # Collect VPN-related cookies
            if cookie['name'] in ['SVPNCOOKIE', 'APSCOOKIE', 'SVPNID', 'SVPNURL']:
                vpn_cookies.append(cookie)
                if cookie['name'] == 'SVPNCOOKIE':
                    session_cookie = f"{cookie['name']}={cookie['value']}"
                    logger.info(f"✓ Found primary session cookie: {cookie['name']}")

        # If no SVPNCOOKIE, try other VPN cookies
        if not session_cookie and vpn_cookies:
            session_cookie = "; ".join([f"{c['name']}={c['value']}" for c in vpn_cookies])
            logger.info(f"Using alternative VPN cookies: {', '.join([c['name'] for c in vpn_cookies])}")

        if not session_cookie:
            # If no VPN-specific cookies found, this might indicate auth didn't complete
            logger.error("No VPN session cookies found!")
            logger.error("This usually means authentication did not complete successfully.")
            logger.error("Check the screenshots in /tmp/ for more details:")
            logger.error("  - /tmp/fortivpn_timeout.png (if timeout occurred)")
            logger.error("  - /tmp/fortivpn_final.png (final state)")

            # Still save whatever cookies we have for debugging
            if cookies:
                fallback_cookie = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                logger.warning(f"Saving all {len(cookies)} cookies as fallback")
                with open(COOKIE_FILE, 'w') as f:
                    f.write(fallback_cookie)

            raise ValueError("No VPN session cookie found - authentication may have failed")

        # Save cookie to file
        logger.info(f"Saving cookie to {COOKIE_FILE}")
        with open(COOKIE_FILE, 'w') as f:
            f.write(session_cookie)
        
        logger.info("✓ Cookie extraction completed successfully!")
        logger.info(f"Session cookie: {session_cookie[:50]}..." if len(session_cookie) > 50 else f"Session cookie: {session_cookie}")
        return session_cookie
        
    except Exception as e:
        logger.error(f"Error occurred: {str(e)}")
        try:
            driver.save_screenshot("/tmp/fortivpn_error.png")
            logger.debug("Error screenshot saved: /tmp/fortivpn_error.png")
        except:
            pass
        raise
    finally:
        try:
            logger.info("Closing browser")
            driver.quit()
        except:
            logger.debug("Browser already closed")

def cookie_refresh_loop():
    """Continuously refresh the cookie before expiration or when deleted"""
    logger.info("Starting cookie refresh loop")
    logger.info(f"Refresh interval: {REFRESH_INTERVAL} seconds")
    logger.info(f"Watch interval: {WATCH_INTERVAL} seconds (checks for cookie deletion)")

    while True:
        try:
            # Extract cookie if it doesn't exist
            if not os.path.exists(COOKIE_FILE):
                logger.info("Cookie file not found, extracting new cookie...")
                extract_cookie()

            # Wait for next refresh, but check periodically if cookie was deleted
            elapsed = 0
            while elapsed < REFRESH_INTERVAL:
                time.sleep(WATCH_INTERVAL)
                elapsed += WATCH_INTERVAL

                # If cookie file was deleted (VPN requested re-auth), break immediately
                if not os.path.exists(COOKIE_FILE):
                    logger.info("Cookie file deleted - VPN requested re-authentication")
                    break

            # If we completed the full interval, do a proactive refresh
            if elapsed >= REFRESH_INTERVAL:
                logger.info(f"Refresh interval reached ({REFRESH_INTERVAL}s), refreshing cookie...")
                # Delete old cookie and extract new one
                if os.path.exists(COOKIE_FILE):
                    os.remove(COOKIE_FILE)
                extract_cookie()

        except Exception as e:
            logger.error(f"Cookie extraction failed: {str(e)}")
            logger.info("Retrying in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    # Run initial extraction only if cookie doesn't exist
    if not os.path.exists(COOKIE_FILE):
        logger.info("No existing cookie found, performing initial extraction...")
        extract_cookie()
    else:
        logger.info(f"Existing cookie found at {COOKIE_FILE}, skipping initial extraction")

    # If CONTINUOUS_REFRESH is set, run continuous refresh loop
    if os.environ.get("CONTINUOUS_REFRESH", "false").lower() == "true":
        cookie_refresh_loop()
    else:
        logger.info("One-time extraction complete. Set CONTINUOUS_REFRESH=true for continuous mode.")
