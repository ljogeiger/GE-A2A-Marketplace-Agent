import os
import time
import uuid
import uvicorn
import httpx
from fastapi import FastAPI, HTTPException, Body, Request
from pydantic import BaseModel
import json
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import logging
from jose import jwt as jose_jwt, JWTError, jwk
from jose.utils import base64url_decode
import calendar
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

# Import shared utilities
from dcr.utils import (ClientRecord, find_client_by_order_id,
                       save_client_mapping, register_okta_client)

# Load environment variables from .env file at the very beginning
load_dotenv()

# --- Logger ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
PROVIDER_URL = os.environ.get("PROVIDER_URL", "https://google.com")
CERT_URL = "https://www.googleapis.com/service_accounts/v1/metadata/x509/cloud-agentspace@system.gserviceaccount.com"
OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN")

if not OKTA_DOMAIN:
    raise ValueError(
        "OKTA_DOMAIN environment variable must be set (e.g., in .env file).")
if not OKTA_DOMAIN.startswith("https://"):
    raise ValueError(
        f"OKTA_DOMAIN must start with https://, but got {OKTA_DOMAIN}")

# Okta API Token for SSWS authentication
OKTA_API_TOKEN = os.environ.get("OKTA_API_TOKEN")
if not OKTA_API_TOKEN:
    raise ValueError("OKTA_API_TOKEN environment variable must be set.")

ALLOW_TEST_ISSUER_ENV = os.environ.get("ALLOW_TEST_ISSUER", "false")
ALLOW_TEST_ISSUER = ALLOW_TEST_ISSUER_ENV.lower() == "true"
TEST_SERVICE_ACCOUNT = os.environ.get("TEST_SERVICE_ACCOUNT")
CERT_BASE_URL = "https://www.googleapis.com/service_accounts/v1/metadata/x509/"
TEST_ISSUER_URL = f"{CERT_BASE_URL}{TEST_SERVICE_ACCOUNT}" if TEST_SERVICE_ACCOUNT else None

CERT_CACHE: Dict[str, Any] = {}

app = FastAPI()


# --- Pydantic Models ---
class RegistrationRequest(BaseModel):
    software_statement: str


class DCRResponse(BaseModel):
    client_id: str
    client_secret: str
    client_secret_expires_at: int


# --- JWT Validation ---
async def get_google_public_keys(iss: str) -> Dict[str, Any]:
    cached_entry = CERT_CACHE.get(iss)
    current_time = time.time()
    if cached_entry and cached_entry["expires"] > current_time:
        return cached_entry["keys"]
    logger.info(f"Fetching public keys from {iss}")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(iss)
            response.raise_for_status()
            certs = response.json()
            cache_control = response.headers.get("Cache-Control", "")
            max_age = 3600
            if "max-age" in cache_control:
                try:
                    max_age = int(
                        cache_control.split("max-age=")[1].split(",")[0])
                except ValueError:
                    pass
            expires = current_time + max_age
            CERT_CACHE[iss] = {"keys": certs, "expires": expires}
            return certs
        except Exception as e:
            logger.error(f"Error fetching certs from {iss}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Could not fetch verification keys: {e}")


async def validate_jwt(jwt_token: str) -> dict:
    try:
        unverified_header = jose_jwt.get_unverified_header(jwt_token)
        kid = unverified_header.get("kid")
        if not kid: raise JWTError("JWT missing 'kid' in header")
        unverified_claims = jose_jwt.get_unverified_claims(jwt_token)
        issuer = unverified_claims.get("iss")
        if not issuer: raise JWTError("JWT missing 'iss' claim")
        is_prod_issuer = issuer == CERT_URL
        is_test_issuer = ALLOW_TEST_ISSUER and TEST_ISSUER_URL and issuer == TEST_ISSUER_URL
        if not (is_prod_issuer or is_test_issuer):
            expected_issuers = [CERT_URL]
            if ALLOW_TEST_ISSUER and TEST_ISSUER_URL:
                expected_issuers.append(TEST_ISSUER_URL)
            raise JWTError(
                f"Invalid issuer. Expected one of {expected_issuers}, but got {issuer}"
            )
        public_keys = await get_google_public_keys(issuer)
        if kid not in public_keys:
            if CERT_CACHE.get(issuer): CERT_CACHE[issuer]["expires"] = 0
            public_keys = await get_google_public_keys(issuer)
            if kid not in public_keys:
                raise JWTError(f"Certificate for key id {kid} not found.")
        cert_pem = public_keys[kid]
        try:
            public_key = jwk.construct(cert_pem, algorithm="RS256")
        except Exception as e:
            raise JWTError(f"Failed to load public key for kid {kid}: {e}")
        decoded_jwt = jose_jwt.decode(jwt_token,
                                      public_key,
                                      algorithms=["RS256"],
                                      audience=PROVIDER_URL)
        return decoded_jwt
    except JWTError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Bad Request: JWT token validation failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in validate_jwt: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error during JWT validation: {e}")


# --- DCR API Endpoint ---
@app.post("/dcr", response_model=DCRResponse)
async def dcr_handler(reg_request: RegistrationRequest, request: Request):
    logger.info(f"Received request on /dcr")
    logger.info(f"Request headers: {request.headers}")
    try:
        decoded_token = validate_jwt(reg_request.software_statement)
    except HTTPException as e:
        logger.error(f"DCR handler JWT validation error: {e.detail}")
        raise e
    order_id = decoded_token.get("google", {}).get("order")
    redirect_uris = decoded_token.get("auth_app_redirect_uris")
    if not order_id:
        raise HTTPException(
            status_code=400,
            detail="Bad Request: Missing 'google.order' in JWT")
    if not redirect_uris:
        raise HTTPException(
            status_code=400,
            detail="Bad Request: Missing 'auth_app_redirect_uris' in JWT")
    existing_client = find_client_by_order_id(order_id)
    if existing_client:
        return DCRResponse(client_id=existing_client.client_id,
                           client_secret=existing_client.client_secret,
                           client_secret_expires_at=0)
    new_client_id, new_client_secret = await register_okta_client(
        order_id, redirect_uris)
    save_client_mapping(order_id, new_client_id, new_client_secret)
    return DCRResponse(client_id=new_client_id,
                       client_secret=new_client_secret,
                       client_secret_expires_at=0)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
