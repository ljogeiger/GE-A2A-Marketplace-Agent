import os
import time
import json
import uuid
import requests
import subprocess
from google.cloud import iam_credentials_v1
import google.auth
import google.auth.transport.requests
from google.oauth2 import id_token

# NOTE: run gcloud auth activate-service-account --key-file='<path to your service account json file>' before executing this script.

# --- Configuration ---
DEPLOYED_URL = "https://marketplace-handler-528009937268.us-central1.run.app"
TEST_SA_EMAIL = "pub-sub-service-account@cpe-isv-partner-experiments.iam.gserviceaccount.com"
# Audience must match the PROVIDER_URL configured on the server
PROVIDER_URL = "https://mycompany.com"


def sign_jwt(payload, sa_email):
    """Signs a JWT using the IAM Credentials API (Service Account Impersonation)."""
    # Requires 'roles/iam.serviceAccountTokenCreator' on the SA.
    client = iam_credentials_v1.IAMCredentialsClient()
    name = f"projects/-/serviceAccounts/{sa_email}"
    print(f"Signing JWT with {sa_email}...")

    # payload must be a JSON string for the API
    response = client.sign_jwt(name=name, payload=json.dumps(payload))
    return response.signed_jwt


def get_id_token(audience):
    """Fetches an ID token for invoking the Cloud Run service."""
    print(f"Fetching ID token for audience: {audience}")
    try:
        # Method 1: Use google-auth library
        auth_req = google.auth.transport.requests.Request()
        token = id_token.fetch_id_token(auth_req, audience)
        print("Obtained ID token via google-auth.")
        return token
    except Exception as e:
        print(
            f"google-auth failed to get ID token ({e}). Trying gcloud fallback..."
        )
        try:
            # Method 2: Fallback to gcloud (often reliable for local user credentials)
            # Note: Tokens from `gcloud auth print-identity-token` might have a generic audience,
            # but often work for IAM-based Cloud Run invocation if the user has permissions.
            token = subprocess.check_output(
                ["gcloud", "auth", "print-identity-token"], text=True).strip()
            print("Obtained ID token via gcloud.")
            return token
        except subprocess.CalledProcessError as e2:
            print(f"gcloud failed to get ID token: {e2}")
            return None


def main():
    print("--- DCR Endpoint Test (Deployed + Auth) ---")
    print(f"Target URL: {DEPLOYED_URL}")

    # 1. Construct DCR Payload
    now = int(time.time())
    jwt_payload = {
        "iss":
        f"https://www.googleapis.com/service_accounts/v1/metadata/x509/{TEST_SA_EMAIL}",
        "iat": now,
        "exp": now + 3600,
        "aud": PROVIDER_URL,
        "sub": "test-account-123",
        "auth_app_redirect_uris": ["https://example.com/callback"],
        "google": {
            "order": f"test-order-{uuid.uuid4()}"
        }
    }

    print(f"Generated Order ID: {jwt_payload['google']['order']}")

    # 2. Sign JWT (The "Software Statement")
    try:
        jwt_token = sign_jwt(jwt_payload, TEST_SA_EMAIL)
    except Exception as e:
        print(f"\n[Error] Failed to sign JWT: {e}")
        print(
            "Tip: Ensure you have 'roles/iam.serviceAccountTokenCreator' on the Service Account."
        )
        return

    # 3. Get ID Token (Authentication for Cloud Run)
    run_auth_token = get_id_token(DEPLOYED_URL)
    if not run_auth_token:
        print(
            "\n[Error] Could not generate ID Token for Cloud Run authentication."
        )
        print(
            "Please run 'gcloud auth login' or ensure you have Application Default Credentials set."
        )
        return

    # 4. Send Request
    endpoint = f"{DEPLOYED_URL}/dcr"
    request_body = {"software_statement": jwt_token}
    headers = {"Authorization": f"Bearer {run_auth_token}"}

    print(f"Sending POST request to {endpoint}...")
    try:
        resp = requests.post(endpoint, json=request_body, headers=headers)
        print(f"\nStatus Code: {resp.status_code}")
        try:
            print(f"Response Body: {json.dumps(resp.json(), indent=2)}")
        except:
            print(f"Response Body: {resp.text}")

        # Helper for common error
        if resp.status_code == 400 and "Invalid issuer" in resp.text:
            print("\n[NOTE] Validation Failed: Invalid Issuer")
            print(
                "To verify test tokens, you must configure the Cloud Run service:"
            )
            print(
                f"gcloud run services update marketplace-handler --region us-central1 --set-env-vars ALLOW_TEST_ISSUER=true,TEST_SERVICE_ACCOUNT={TEST_SA_EMAIL}"
            )
        elif resp.status_code in [401, 403]:
            print("\n[NOTE] Authentication/Authorization Failed")
            print(
                "Ensure your user (or the identity running this script) has 'roles/run.invoker' on the Cloud Run service."
            )

    except Exception as e:
        print(f"Request failed: {e}")


if __name__ == "__main__":
    main()
