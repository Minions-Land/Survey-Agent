import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def _get_unpaywall_email():
    return os.getenv("UNPAYWALL_EMAIL")


class Unpaywall:
    def __init__(self):
        pass

    @staticmethod
    def get_unpaywall_url_by_doi(doi):
        """Try to get an open-access PDF URL from the Unpaywall API."""
        try:
            email = _get_unpaywall_email()
            if not email:
                print("  [WARN] UNPAYWALL_EMAIL was not found in .env")
                return None

            api_url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('best_oa_location') and data['best_oa_location'].get('url_for_pdf'):
                print(f"  [INFO] Unpaywall found a PDF URL: {data['best_oa_location']['url_for_pdf']}")
                return data['best_oa_location']['url_for_pdf']
        except requests.exceptions.RequestException as e:
            print(f"  [WARN] Unpaywall API request failed: {e}")
        except Exception as e:
            print(f"  [WARN] Failed to parse Unpaywall response: {e}")
        return None

    @staticmethod
    def get_unpaywall_search_result_by_title(query):
        """Try to search Unpaywall by title and return the raw API result."""
        try:
            email = _get_unpaywall_email()
            if not email:
                print("  [WARN] UNPAYWALL_EMAIL was not found in .env")
                return None

            api_url = f"https://api.unpaywall.org/v2/search?query={query}&email={email}"
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            print(f"  [WARN] Unpaywall API request failed: {e}")
        except Exception as e:
            print(f"  [WARN] Failed to parse Unpaywall response: {e}")
        return None
