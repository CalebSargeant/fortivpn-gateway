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
from datetime import datetime
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
COOKIE_FILE = os.environ.get("COOKIE_FILE", "/tmp/vpn_cookie.txt")
REFRESH_INTERVAL = int(os.environ.get("REFRESH_INTERVAL", "3600"))  # 1 hour default

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
            time.sleep(3)
        except:
            logger.debug("No OTP page found")
        
        # Handle "Stay signed in?" prompt
        try:
            yes_button = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Yes']")
            logger.info("Found 'Stay signed in?' prompt, clicking Yes")
            yes_button.click()
            time.sleep(2)
        except:
            logger.debug("No 'Stay signed in' prompt found")
        
        # Step 6: Wait for redirect back to FortiVPN and extract cookie
        logger.info("Step 6: Waiting for authentication to complete")
        
        # Wait for redirect away from Microsoft (more flexible)
        try:
            WebDriverWait(driver, 60).until(
                lambda d: "login.microsoftonline.com" not in d.current_url and "login.microsoft.com" not in d.current_url
            )
            logger.info(f"Left Microsoft auth page. Current URL: {driver.current_url}")
            time.sleep(2)  # Give time for any additional redirects
            driver.save_screenshot("/tmp/fortivpn_after_redirect.png")
        except Exception as e:
            logger.warning(f"Wait for redirect timed out or failed: {e}")
        
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
        logger.info(f"Found {len(cookies)} cookies")
        
        # Find the SVPNCOOKIE (or similar session cookie)
        session_cookie = None
        for cookie in cookies:
            logger.debug(f"Cookie: {cookie['name']} = {cookie['value'][:20] if len(cookie['value']) > 20 else cookie['value']}...")
            if cookie['name'] in ['SVPNCOOKIE', 'APSCOOKIE', 'SVPNID']:
                session_cookie = f"{cookie['name']}={cookie['value']}"
                logger.info(f"Found session cookie: {cookie['name']}")
                break
        
        if not session_cookie:
            # Fallback: use all cookies
            logger.warning("Specific session cookie not found, using all cookies")
            session_cookie = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        # Save cookie to file
        logger.info(f"Saving cookie to {COOKIE_FILE}")
        with open(COOKIE_FILE, 'w') as f:
            f.write(session_cookie)
        
        logger.info("✓ Cookie extraction completed successfully!")
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
    """Continuously refresh the cookie before expiration"""
    logger.info("Starting cookie refresh loop")
    logger.info(f"Refresh interval: {REFRESH_INTERVAL} seconds")
    
    while True:
        try:
            extract_cookie()
            logger.info(f"Next refresh in {REFRESH_INTERVAL} seconds")
            time.sleep(REFRESH_INTERVAL)
        except Exception as e:
            logger.error(f"Cookie extraction failed: {str(e)}")
            logger.info("Retrying in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    # Run initial extraction
    extract_cookie()
    
    # If REFRESH_INTERVAL is set, run continuous refresh loop
    if os.environ.get("CONTINUOUS_REFRESH", "false").lower() == "true":
        cookie_refresh_loop()
    else:
        logger.info("One-time extraction complete. Set CONTINUOUS_REFRESH=true for continuous mode.")
