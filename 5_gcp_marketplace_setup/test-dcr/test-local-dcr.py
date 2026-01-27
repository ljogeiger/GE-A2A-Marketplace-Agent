# tests/dcr_test_client.py
import requests
import json
import time
import os
from base64 import b64encode
from google.cloud import iam_credentials_v1
from google.api_core import exceptions as google_exceptions
from dotenv import load_dotenv
import uuid

load_dotenv()

# URL of the agent service app (when running main.py locally)
URL = "http://localhost:8080/"

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "sandbox-aiml")

# Fetch the Test Service Account from an environment variable
TEST_SERVICE_ACCOUNT = os.environ.get("TEST_SERVICE_ACCOUNT")
if not TEST_SERVICE_ACCOUNT:
    raise ValueError(
        "Please set the TEST_SERVICE_ACCOUNT environment variable.")

# Your Agent's Provider URL - should match the one in main.py for 'aud' claim
PROVIDER_URL = os.environ.get("PROVIDER_URL", "https://mycompany.com")
CERT_BASE_URL = "https://www.googleapis.com/service_accounts/v1/metadata/x509/"


def create_signed_jwt(service_account_email: str, payload: dict) -> str | None:
    """Signs a JWT using the specified Google Cloud service account."""
    try:
        client = iam_credentials_v1.IAMCredentialsClient()
        name = f"projects/-/serviceAccounts/{service_account_email}"
        print(f"Signing JWT for service account: {name}")
        # payload must be a JSON string
        response = client.sign_jwt(name=name, payload=json.dumps(payload))
        return response.signed_jwt
    except Exception as e:
        print(f"Error signing JWT: {e}")
        return None


def construct_dcr_request_body(redirect_uris, procurement_account_id, order_id,
                               issuer_url, service_account_email):
    # Current time and expiration time for the JWT
    now = int(time.time())
    expires_at = now + 3600

    # JWT Payload
    jwt_payload = {
        "iss": issuer_url,
        "iat": now,
        "exp": expires_at,
        "aud": PROVIDER_URL,
        "auth_app_redirect_uris": redirect_uris,
        "sub": procurement_account_id,
        "google": {
            "order": order_id
        }
    }

    print(f"JWT Payload: {json.dumps(jwt_payload, indent=2)}")

    signed_jwt = create_signed_jwt(service_account_email, jwt_payload)

    if not signed_jwt:
        raise Exception("Failed to sign JWT")

    request_body = {"software_statement": signed_jwt}

    return json.dumps(request_body, indent=2)


def invoke_dcr(path: str, service_account_email: str):
    redirects = ["https://gemini.google.com/callback"]
    procurement_id = "procurement-account-12345"
    order = f"order-{uuid.uuid4()}"  # Generate unique order ID for testing
    issuer = CERT_BASE_URL + service_account_email

    try:
        payload = construct_dcr_request_body(redirects, procurement_id, order,
                                             issuer, service_account_email)
        print(f"\nConstructed DCR Request Body for order {order}:\n{payload}")

        target_url = URL + path
        print(f"\nInvoking DCR endpoint: {target_url}")

        response = requests.post(target_url,
                                 data=payload,
                                 headers={"Content-Type": "application/json"})
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Body:\n{response.text}")

    except Exception as e:
        print(f"Error invoking function: {e}")


if __name__ == "__main__":
    """
    To run this test client:

    1. Make sure the DCR service (src/main.py) is running.
       Example: python src/main.py

    2. Set the required environment variables:
       export TEST_SERVICE_ACCOUNT="<REDACTED_PII>"
       export PROVIDER_URL="https://mycompany.com" # Or your test aud value

    3. Run this script from the root directory (dcr_service/):
       python tests/dcr_test_client.py
    """
    print("--- Running DCR Test Client ---")
    # We are testing the "/dcr" endpoint in main.py
    invoke_dcr("dcr", TEST_SERVICE_ACCOUNT)
    print("--- DCR Test Client Finished ---")
