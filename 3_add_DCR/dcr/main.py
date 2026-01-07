import os
import time
import uuid
import uvicorn
import httpx
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests
import json
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
PROVIDER_URL = os.environ.get(
    "PROVIDER_URL", "https://mycompany.com")  # Your Agent's Provider URL
CERT_URL = "https://www.googleapis.com/service_accounts/v1/metadata/x509/cloud-agentspace@system.gserviceaccount.com"
OKTA_DOMAIN = os.environ.get(
    "OKTA_DOMAIN")  # Your Okta domain, e.g., https://your-tenant.okta.com

# OAuth Client Credentials for this DCR service's app in Okta
OKTA_DCR_CLIENT_ID = os.environ.get("OKTA_DCR_CLIENT_ID")
OKTA_DCR_CLIENT_SECRET = os.environ.get("OKTA_DCR_CLIENT_SECRET")
# Scopes needed for the DCR service to register clients.
OKTA_DCR_SCOPES = os.environ.get("OKTA_DCR_SCOPES",
                                 "okta.clients.register").split(" ")

if not OKTA_DOMAIN:
    raise ValueError("OKTA_DOMAIN environment variable must be set.")
if not OKTA_DCR_CLIENT_ID or not OKTA_DCR_CLIENT_SECRET:
    raise ValueError(
        "OKTA_DCR_CLIENT_ID and OKTA_DCR_CLIENT_SECRET environment variables must be set for OAuth client credentials flow."
    )

DB_FILE = "clients_db.json"
TOKEN_CACHE: Dict[str, Any] = {}

app = FastAPI()


# --- Pydantic Models ---
class RegistrationRequest(BaseModel):
    software_statement: str


class DCRResponse(BaseModel):
    client_id: str
    client_secret: str
    client_secret_expires_at: int


class ClientRecord(BaseModel):
    order_id: str
    client_id: str
    client_secret: str


# --- Simple JSON DB Functions ---
def load_db() -> Dict[str, ClientRecord]:
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, 'r') as f:
            data = json.load(f)
            return {
                order_id: ClientRecord(**record)
                for order_id, record in data.items()
            }
    except json.JSONDecodeError:
        print(
            f"Warning: {DB_FILE} is corrupted or empty. Starting with an empty DB."
        )
        return {}


def save_db(db: Dict[str, ClientRecord]):
    with open(DB_FILE, 'w') as f:
        json.dump({
            order_id: record.dict()
            for order_id, record in db.items()
        },
                  f,
                  indent=2)


def find_client_by_order_id(order_id: str) -> Optional[ClientRecord]:
    db = load_db()
    return db.get(order_id)


def save_client_mapping(order_id: str, client_id: str, client_secret: str):
    db = load_db()
    record = ClientRecord(order_id=order_id,
                          client_id=client_id,
                          client_secret=client_secret)
    db[order_id] = record
    save_db(db)


# --- JWT Validation ---
def validate_jwt(jwt_token: str) -> dict:
    """Validates the JWT token from Google."""
    try:
        decoded_jwt = id_token.verify_token(jwt_token,
                                            requests.Request(),
                                            audience=PROVIDER_URL)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Bad Request: JWT token validation failed: {e}")

    if decoded_jwt.get("iss") != CERT_URL:
        raise HTTPException(status_code=400,
                            detail="Bad Request: Invalid issuer")
    return decoded_jwt


# --- Okta OAuth Token Fetcher ---
async def get_okta_access_token() -> str:
    """Fetches an access token from Okta using client credentials for the DCR service app."""
    cache_key = "okta_dcr_service_token"
    cached = TOKEN_CACHE.get(cache_key)
    current_time = time.time()
    if cached and cached["expires_at"] > current_time:
        return cached["access_token"]

    # Determine the correct token endpoint URL
    # It's often /oauth2/v1/token for the Org Authorization Server
    # or /oauth2/{authServerId}/v1/token for a custom one.
    # We'll assume the Org Authorization Server here.
    token_url = f"{OKTA_DOMAIN}/oauth2/v1/token"
    print(f"Fetching Okta access token from: {token_url}")

    payload = {
        "grant_type": "client_credentials",
        "scope": " ".join(OKTA_DCR_SCOPES),
        "client_id": OKTA_DCR_CLIENT_ID,
        "client_secret": OKTA_DCR_CLIENT_SECRET,
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url,
                                         data=urlencode(payload),
                                         headers=headers)
            response.raise_for_status()
            token_data = response.json()

            access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            TOKEN_CACHE[cache_key] = {
                "access_token": access_token,
                "expires_at":
                current_time + expires_in - 60  # Cache with a 60s buffer
            }
            print("Successfully fetched Okta access token.")
            return access_token
    except httpx.HTTPStatusError as e:
        print(
            f"Okta Token API Error ({e.response.status_code}): {e.response.text}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get Okta access token: {e.response.text}")
    except Exception as e:
        print(f"Error fetching Okta token: {e}")
        raise HTTPException(status_code=500,
                            detail="Internal server error fetching Okta token")


# --- Okta API Interaction ---
async def register_okta_client(order_id: str,
                               redirect_uris: list[str]) -> tuple[str, str]:
    """Registers a new OIDC web application client in Okta using DCR endpoint."""
    access_token = await get_okta_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    client_payload = {
        "client_name": f"Gemini Agent - Order {order_id}",
        "application_type": "web",
        "redirect_uris": redirect_uris,
        "response_types": ["code"],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "client_secret_post",
    }

    okta_dcr_url = f"{OKTA_DOMAIN}/oauth2/v1/clients"
    # Adjust if using a custom auth server: f"{OKTA_DOMAIN}/oauth2/{authServerId}/v1/clients"
    print(f"Registering client at Okta URL: {okta_dcr_url}")

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
                print(f"Okta DCR Response Missing Credentials: {okta_client}")
                raise HTTPException(
                    status_code=500,
                    detail=
                    "Failed to retrieve client credentials from Okta DCR response"
                )

            print(f"Successfully registered client in Okta: {new_client_id}")
            return new_client_id, new_client_secret

    except httpx.HTTPStatusError as e:
        print(
            f"Okta DCR API Error ({e.response.status_code}): {e.response.text}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error registering client in Okta: {e.response.text}")
    except Exception as e:
        print(f"Error calling Okta DCR: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during Okta DCR interaction: {e}")


# --- DCR API Endpoint ---
@app.post("/dcr", response_model=DCRResponse)
async def dcr_handler(reg_request: RegistrationRequest):
    """Handles Dynamic Client Registration."""
    decoded_token = validate_jwt(reg_request.software_statement)
    print(
        f"Received DCR request with software_statement payload: {decoded_token}"
    )

    order_id = decoded_token.get("google", {}).get("order")
    if not order_id:
        raise HTTPException(
            status_code=400,
            detail="Bad Request: Missing 'google.order' in JWT")

    redirect_uris = decoded_token.get("auth_app_redirect_uris")
    if not redirect_uris:
        raise HTTPException(
            status_code=400,
            detail="Bad Request: Missing 'auth_app_redirect_uris' in JWT")

    # --- Idempotency Check ---
    existing_client = find_client_by_order_id(order_id)
    if existing_client:
        print(
            f"Client for order_id {order_id} already exists. Returning existing credentials."
        )
        return DCRResponse(client_id=existing_client.client_id,
                           client_secret=existing_client.client_secret,
                           client_secret_expires_at=0)

    # --- Register new client in Okta ---
    print(f"Registering new client in Okta for order_id {order_id}")
    new_client_id, new_client_secret = await register_okta_client(
        order_id, redirect_uris)

    # --- Persistence ---
    print(f"Saving mapping for order_id {order_id}")
    save_client_mapping(order_id, new_client_id, new_client_secret)

    return DCRResponse(
        client_id=new_client_id,
        client_secret=new_client_secret,
        client_secret_expires_at=0  # MUST be 0
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(
        f"Starting server on port {port} using OAuth Client Credentials for Okta API access."
    )
    uvicorn.run(app, host="0.0.0.0", port=port)
