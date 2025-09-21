#!/usr/bin/env python3
"""
BoursoBankScrap.py

Educational example to:
 - perform the cookie/token collection described in the referenced blog post
 - download account transactions as CSV via the "exporter-mouvements" endpoint
 - parse CSV into a pandas DataFrame

WARNING: Keep credentials local and secure. This script may break if Boursorama changes their pages,
or if 2FA is required on your account.

Source / inspiration: "Boursorama: auth flow & scraping" (November 16, 2024).
https://studiopixl.com/2024-11-16/boursorama-login
"""
import sys
import re
import io
import os
import csv
import getpass
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
import pandas as pd

__version__ = "1.0.0"

# ---------- CONFIG ----------
BASE = "https://clients.boursobank.com"
LOGIN_PAGE = f"{BASE}/connexion/"
CLAVIER_URL = f"{BASE}/connexion/clavier-virtuel?_hinclude=1"
PASSWORD_POST = f"{BASE}/connexion/saisie-mot-de-passe"
EXPORT_URL = f"{BASE}/budget/exporter-mouvements"
OUTPUT_FOLDER = "output"
SAVE_FILE = os.path.join(OUTPUT_FOLDER, "last_run.txt")

# Known SVG length -> digit map found in the referenced article.
# The article uses base64/svg-detected-lengths. These were observed in Nov 2024; adjust if needed.
B64_SVG_LEN_MAP = {
    419: 0,
    259: 1,
    1131: 2,
    979: 3,
    763: 4,
    839: 5,
    1075: 6,
    1359: 7,
    1023: 8,
    1047: 9,
}

# ---------- Helpers ----------
def debug(msg):
    print("[DEBUG]", msg, file=sys.stderr)

def extract_token_from_login(html_text):
    """
    From the login page HTML, find the form token: name like form[_token] or input[name="form[_token]"].
    """
    soup = BeautifulSoup(html_text, "html.parser")
    token_input = soup.find("input", attrs={"name": re.compile(r"form\[_token\]")})
    if token_input and token_input.get("value"):
        return token_input["value"]
    # fallback try any hidden input called '_token'
    token_input = soup.find("input", attrs={"name": "_token"})
    if token_input and token_input.get("value"):
        return token_input["value"]
    return None

def build_encoded_password(numeric_password: str, digit_to_group: dict):
    """
    Convert numeric password like '12345678' to the server-expected chain:
      'AAA|BBB|CCC|...'
    where AAA is the 3-letter group for digit 1, etc.
    """
    groups = []
    for ch in numeric_password:
        d = int(ch)
        group = digit_to_group.get(d)
        if group is None:
            raise ValueError(f"No mapping for digit {d}.")
        groups.append(group)
    return "|".join(groups)

# ---------- Main flow ----------
def main(dry_run, client_number,numeric_password,account,from_date):
    # User inputs
    #client_number = input("Client number (digits): ").strip()

    if not client_number.isdigit():
        print("Client number should be digits only.", file=sys.stderr)
        return
    #numeric_password = getpass.getpass("Numeric 8-digit password (will not echo): ").strip()
    if not (numeric_password.isdigit() and len(numeric_password) in (8,)):
        print("Password must be digits (8 digits by default).", file=sys.stderr)
        return

    # Date range for transactions (last 30 days by default)
    to_date = datetime.today()

    session = requests.Session()
    # set a user agent similar to a browser
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    })

    if not dry_run:
        ##########################################
        ### Step 1: Magic cookie the gathering ###
        ##########################################
        debug("### Step 1: Magic cookie the gathering ###")

        # Step 1: initial GET to collect cookies and token
        debug("Fetching login page to collect initial cookies and token...")
        resp_login_1 = session.get(LOGIN_PAGE)
        resp_login_1.raise_for_status()

        # The page sets a __brs_mit cookie in JS — the site may require that cookie to be present.
        m = re.search(r'__brs_mit\s*=\s*([^";\s]+)', resp_login_1.text)
        if not m:
            raise ValueError("Cookie not found in HTML")
        else:
            debug("Found __brs_mit cookie.")

        cookie_value = m.group(1)
        session.cookies.set("__brs_mit", cookie_value)

        resp_login_2 = session.get(LOGIN_PAGE)
        resp_login_2.raise_for_status()
        # The article mentions some cookies are set in the returned page. We'll use session cookies as-is.
        cookies = session.cookies.get_dict()
        token = extract_token_from_login(resp_login_2.text)
        if token is None:
            debug("Could not find form[_token]. The page structure may have changed.")
        else:
            debug("Found form token.")

        #####################################
        ### Step 2: SVG based obfuscation ###
        #####################################
        debug("### Step 2: SVG based obfuscation ###")

        # Step 2: fetch keypad and compute mapping
        debug("Fetching keypad / SVG mapping...")
        """
        Request the clavier-virtuel page and parse:
          - per-button data-matrix-key (3-letter group)
          - the SVG content, derive path length and map to digits using B64_SVG_LEN_MAP
        Returns mapping digit -> 3-letter-group
        """
        resp_clavier = session.get(CLAVIER_URL)
        resp_clavier.raise_for_status()
        soup = BeautifulSoup(resp_clavier.text, "html.parser")

        # The page contains several elements with data-matrix-key and an <img> inside.
        mapping = {}  # digit -> 3-letter-group
        for btn in soup.select("[data-matrix-key]"):
            matrix_key = btn.get("data-matrix-key")
            # find the inner img; prefer path 'd' attribute length
            img = btn.find("img")
            if img:
                # try to find path(s) and compute length of path d attribute
                path = img.get("src")
                path_len = len(path)

            digit = B64_SVG_LEN_MAP.get(path_len)
            if digit is None:
                debug(f"Unknown img/path length: {path_len}. You may need to update B64_SVG_LEN_MAP.")
                continue
            mapping[int(digit)] = matrix_key

        if len(mapping) < 10:
            debug(f"Only found mapping for {len(mapping)} digits; expected 10. Aborting.")
            # but we can still try to continue — likely will fail
        else:
            debug("Found full mapping for digits 0-9.")


        ##########################
        ### Step 3: Loggin in! ###
        ##########################
        debug("### Step 3: Loggin in! ###")

        # Step 3: build encoded password (sequence of 3-letter groups separated by '|')
        try:
            encoded_password = build_encoded_password(numeric_password, mapping)
        except Exception as e:
            print("Error encoding password:", e, file=sys.stderr)
            return

        # Need matrixRandomChallenge value — often present as data-matrix-random-challenge in the keypad html.
        # Try to extract it by requesting the clavier page again and parsing for the attribute.
        matrix_random_challenge = None
        m = re.search(
            r'\$\(\s*"\[data-matrix-random-challenge\]"\s*\)\.val\(\s*([\'"])(?P<val>.*?)\1\s*\)',
            resp_clavier.text,
            re.S
        )
        if m:
            matrix_random_challenge = m.group('val')

        if not matrix_random_challenge:
            debug("Could not extract matrixRandomChallenge automatically. The value may be embedded differently.")

        # perform login POST
        debug("Submitting login form...")
        # Build multipart/form-data fields as the blog describes. Keep passwordAck as {} and fakePassword as placeholders.
        data = {
            "form[clientNumber]": client_number,
            "form[password]": encoded_password,
            "form[ajx]": "1",
            "form[platformAuthenticatorAvailable]": "-1",
            "form[passwordAck]": "{}",
            "form[fakePassword]": "•" * len(numeric_password),
            "form[_token]": token,
            "form[matrixRandomChallenge]": matrix_random_challenge,
        }

        # Headers typical for AJAX form submit
        headers = {
            "Referer": LOGIN_PAGE,
            "X-Requested-With": "XMLHttpRequest",
        }

        post_resp = session.post(PASSWORD_POST, data=data, headers=headers)
        # The site may return JSON or redirect with cookies. Inspect response.
        if post_resp.status_code not in (200, 302):
            debug(f"Login POST returned status {post_resp.status_code}. Response snippet:\n{post_resp.text[:400]}")
            print("Login probably failed (status != 200/302). See debug output.", file=sys.stderr)
            return

        debug("Login POST done. Inspecting cookies for auth tokens...")
        current_cookies = session.cookies.get_dict()
        # The article notes some final cookies like brsxds_* and ckln<sha>. We'll just proceed with whatever cookies we have.

        ################################
        ### Step 4: Fetching my data ###
        ################################
        debug("### Step 4: Fetching my data ###")

        # Step 4: fetch CSV exporter
        params = {
            'movementSearch[selectedAccounts][]': f"{account}",  # MUST set to a real account id; we'll try to auto-discover
            'movementSearch[fromDate]': from_date.strftime('%d/%m/%Y'),
            'movementSearch[toDate]': to_date.strftime('%d/%m/%Y'),
            'movementSearch[format]': 'CSV',
            'movementSearch[filteredBy]': 'filteredByCategory',
            'movementSearch[catergory]': '',
            'movementSearch[operationTypes]': '',
            'movementSearch[myBudgetPage]': 1,
            'movementSearch[submit]': ''
        }

        # Try to discover account id from "mon-budget/generate" endpoint (server-side rendered HTML)
        debug("Attempting to discover account id from mon-budget/generate ...")
        budget_url = f"{BASE}/mon-budget/generate"
        resp_budget = session.get(budget_url)
        if resp_budget.status_code == 200:
            soup = BeautifulSoup(resp_budget.text, "html.parser")
            # try to find input or select for movementSearch[selectedAccounts][] or account ids in HTML
            acc_input = soup.find(attrs={"name": "movementSearch[selectedAccounts][]"})
            if acc_input and acc_input.get("value"):
                params['movementSearch[selectedAccounts][]'] = acc_input.get("value")
            else:
                # some accounts are rendered as options
                opt = soup.select_one("select[name='movementSearch[selectedAccounts][]'] option")
                if opt and opt.get("value"):
                    params['movementSearch[selectedAccounts][]'] = opt.get("value")

        if not params['movementSearch[selectedAccounts][]']:
            print("Could not auto-discover an account id. You must set 'movementSearch[selectedAccounts][]' to your account id in the script.", file=sys.stderr)
            return

        debug(f"Downloading CSV for account {params['movementSearch[selectedAccounts][]']} from {params['movementSearch[fromDate]']} to {params['movementSearch[toDate]']}")
        csv_resp = session.get(EXPORT_URL, params=params)
        if csv_resp.status_code != 200:
            debug(f"CSV fetch returned status {csv_resp.status_code}. Response snippet:\n{csv_resp.text[:500]}")
            print("Failed to fetch CSV. The response may be HTML error page (range invalid or no results) or site changed.", file=sys.stderr)
            return

        # Check if response is HTML (error) rather than CSV
        content_type = csv_resp.headers.get("Content-Type", "")
        if "text/csv" not in content_type and csv_resp.text.strip().startswith("<"):
            debug("Response appears to be HTML, not CSV. The request likely failed or returned an error page.")
            print("CSV exporter returned HTML (likely an error). See debug logs.", file=sys.stderr)
            return

        # Parse CSV into pandas
        try:
            df = pd.read_csv(io.StringIO(csv_resp.text), sep=";")  # CSV exporter commonly uses semicolons in FR locale
        except Exception:
            # try comma
            df = pd.read_csv(io.StringIO(csv_resp.text))

        # Output result
        print("Transactions fetched. DataFrame head:")
        print(df.head().to_string(index=False))

        account_name_output = params['movementSearch[selectedAccounts][]']
    else :
        account_name_output = f"dry_run_{account}"
        df = pd.read_csv(io.StringIO("fake file"))

    # Example CSV file
    outfn = f"boursorama_transactions_{account_name_output}_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.csv"
    outfn_path = os.path.join(OUTPUT_FOLDER, outfn)

    df.to_csv(outfn_path, index=False)
    print(f"Saved CSV to {outfn_path}")

    # Save current date for next time
    with open(SAVE_FILE, "w") as f:
        f.write(datetime.today().isoformat())

if __name__ == "__main__":
    print(f"Running version {__version__}")
    print(f"Run on: {datetime.fromisoformat(datetime.today())}")
    print("Current working directory:", os.getcwd())
    print("Script directory:", os.path.dirname(os.path.abspath(__file__)))

    # sys.argv[0] is the script name, so parameters start at index 1
    if len(sys.argv) != 5:
        print(f"Usage: python {sys.argv[0]} dry_run client_number numeric_password account")
        sys.exit(1)

    #
    prev_date = datetime.today() - timedelta(days=30)

    # Create folder if it doesn't exist
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    if os.path.exists(SAVE_FILE):
        # Read previous date
        with open(SAVE_FILE, "r") as f:
            prev_str = f.read().strip()
            try:
                prev_date = datetime.fromisoformat(prev_str)
                diff = datetime.today() - prev_date
                print(f"Last run was on: {prev_date}")
                print(f"Time since last run: {diff}")

                # Stop if diff is less than 25 days
                if diff.days < 30:
                    print("⏹ Stopping: less than 30 days since last run.")
                    sys.exit(0)

            except ValueError:
                print("Invalid date format in save file")

    flag = sys.argv[1].lower() in ("true", "1", "yes")
    main(flag, sys.argv[2], sys.argv[3], sys.argv[4], prev_date)

