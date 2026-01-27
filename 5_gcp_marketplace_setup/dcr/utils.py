import os
import json
import logging
import httpx
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel
from fastapi import HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests
from google.cloud import firestore

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Configuration ---
OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN")
OKTA_API_TOKEN = os.environ.get("OKTA_API_TOKEN")

# Firestore Configuration
# We assume the default project credentials are sufficient.
# Collection name to store client mappings
COLLECTION_NAME = "marketplace_clients"

# Initialize Firestore Client
try:
    db = firestore.Client()
except Exception as e:
    logger.warning(
        f"Could not initialize Firestore client. Ensure GOOGLE_APPLICATION_CREDENTIALS are set if running locally. Error: {e}"
    )
    db = None

# JWT Configuration (i.e JWT audience)
PROVIDER_URL = os.environ.get("PROVIDER_URL", "https://google.com")

CERT_URL = "https://www.googleapis.com/service_accounts/v1/metadata/x509/cloud-agentspace@system.gserviceaccount.com"

ALLOW_TEST_ISSUER_ENV = os.environ.get("ALLOW_TEST_ISSUER", "false")
ALLOW_TEST_ISSUER = ALLOW_TEST_ISSUER_ENV.lower() == "true"
TEST_SERVICE_ACCOUNT = os.environ.get("TEST_SERVICE_ACCOUNT")
CERT_BASE_URL = "https://www.googleapis.com/service_accounts/v1/metadata/x509/"
TEST_ISSUER_URL = f"{CERT_BASE_URL}{TEST_SERVICE_ACCOUNT}" if TEST_SERVICE_ACCOUNT else None


class ClientRecord(BaseModel):
    order_id: str
    client_id: str
    client_secret: str


# --- DB Functions (Firestore) ---


def find_client_by_order_id(order_id: str) -> Optional[ClientRecord]:
    if not db:
        logger.error("Firestore client is not initialized.")
        return None

    logger.info(f"Checking Firestore for order {order_id}...")
    try:
        doc_ref = db.collection(COLLECTION_NAME).document(order_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            logger.info(f"Found client record for order {order_id}")
            return ClientRecord(**data)
        else:
            logger.info(f"No client record found for order {order_id}")
            return None
    except Exception as e:
        logger.error(f"Error querying Firestore for order {order_id}: {e}")
        return None


def save_client_mapping(order_id: str, client_id: str, client_secret: str):
    if not db:
        logger.error(
            "Firestore client is not initialized. Cannot save mapping.")
        return

    logger.info(f"Saving client mapping for order {order_id} to Firestore...")
    try:
        doc_ref = db.collection(COLLECTION_NAME).document(order_id)
        record = ClientRecord(order_id=order_id,
                              client_id=client_id,
                              client_secret=client_secret)
        doc_ref.set(record.dict())
        logger.info(f"Successfully saved client mapping for {order_id}")
    except Exception as e:
        logger.error(f"Error saving to Firestore for order {order_id}: {e}")


# --- JWT Validation ---
def validate_jwt(jwt_token: str) -> dict:
    """
    Validates the JWT token from Google using google-auth library.
    """
    try:
        # Determine which certs to use.
        request = requests.Request()

        # 1. Verify JWT signature, exp, and aud.
        # id_token.verify_token handles signature verification using keys from certs_url,
        # and validates 'exp' and 'aud' claims.
        try:
            decoded_jwt = id_token.verify_token(jwt_token,
                                                request,
                                                audience=PROVIDER_URL,
                                                certs_url=CERT_URL)
        except ValueError as e:
            # If prod verification failed and test is allowed, try test issuer
            if ALLOW_TEST_ISSUER and TEST_ISSUER_URL:
                logger.info(
                    "Validation against prod issuer failed, trying test issuer..."
                )
                decoded_jwt = id_token.verify_token(jwt_token,
                                                    request,
                                                    audience=PROVIDER_URL,
                                                    certs_url=TEST_ISSUER_URL)
            else:
                raise e

        # 2. Verify 'iss' claim matches exactly.
        # verify_token ensures the token was signed by keys from the certs_url,
        # but we also check the 'iss' string as requested.
        issuer = decoded_jwt.get("iss")
        expected_issuers = [CERT_URL]
        if ALLOW_TEST_ISSUER and TEST_ISSUER_URL:
            expected_issuers.append(TEST_ISSUER_URL)

        if issuer not in expected_issuers:
            raise ValueError(
                f"Invalid issuer: {issuer}. Expected one of {expected_issuers}"
            )

        # 3. Verify 'sub' claim (Procurement Account ID).
        # user instruction: don't check sub claim, but add comments saying it's recommended.
        # Recommendation: Verify that 'sub' is a valid Procurement Account ID by cross-referencing
        # with information received from Marketplace Procurement Pub/Sub.
        sub = decoded_jwt.get("sub")
        # if not is_valid_account(sub):
        #    raise ValueError(f"Invalid account ID: {sub}")

        return decoded_jwt

    except ValueError as e:
        logger.error(f"JWT Validation failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Bad Request: JWT token validation failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in validate_jwt: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error during JWT validation: {e}")


# --- Okta API Interaction ---
async def register_okta_client(order_id: str,
                               redirect_uris: list[str]) -> Tuple[str, str]:
    if not OKTA_DOMAIN or not OKTA_API_TOKEN:
        raise ValueError("OKTA_DOMAIN and OKTA_API_TOKEN must be set.")

    headers = {
        "Authorization": f"SSWS {OKTA_API_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    # NOTE: When you create the app you may want to include all users or specific users.
    # We are not assigning users here, so will need to manage access via Okta UI.
    client_payload = {
        "client_name": f"Gemini Agent - Order {order_id}",
        "application_type": "web",
        "redirect_uris": redirect_uris,
        "response_types": ["code"],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "client_secret_post",
        "scope": "openid profile email offline_access"
    }
    okta_dcr_url = f"{OKTA_DOMAIN}/oauth2/v1/clients"
    logger.info(f"Registering Okta client at: {okta_dcr_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(okta_dcr_url,
                                         json=client_payload,
                                         headers=headers)
            response.raise_for_status()
            okta_client = response.json()
            new_client_id = okta_client.get("client_id")
            new_client_secret = okta_client.get("client_secret")
            if not new_client_id or not new_client_secret:
                raise HTTPException(
                    status_code=500,
                    detail=
                    "Failed to retrieve client credentials from Okta DCR response"
                )
            logger.info(
                f"Successfully registered Okta client: {new_client_id}")
            return new_client_id, new_client_secret
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Okta DCR Error ({e.response.status_code}): {e.response.text}")
        raise HTTPException(
            status_code=500,
            detail=f"Error registering client in Okta: {e.response.text}")
    except Exception as e:
        logger.error(f"Error calling Okta DCR: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during Okta DCR interaction: {e}")
