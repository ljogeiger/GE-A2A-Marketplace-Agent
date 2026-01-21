import os
import json
import logging
import httpx
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel
from fastapi import HTTPException

# --- Logger ---
logger = logging.getLogger(__name__)

# --- Configuration ---
OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN")
OKTA_API_TOKEN = os.environ.get("OKTA_API_TOKEN")
DB_FILE = "clients_db.json"

class ClientRecord(BaseModel):
    order_id: str
    client_id: str
    client_secret: str

# --- DB Functions ---
def load_db() -> Dict[str, ClientRecord]:
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, 'r') as f:
            data = json.load(f)
        return {k: ClientRecord(**v) for k, v in data.items()}
    except json.JSONDecodeError:
        logger.warning(f"{DB_FILE} is corrupted.")
        return {}

def save_db(db: Dict[str, ClientRecord]):
    with open(DB_FILE, 'w') as f:
        json.dump({k: v.dict() for k, v in db.items()}, f, indent=2)

def find_client_by_order_id(order_id: str) -> Optional[ClientRecord]:
    return load_db().get(order_id)

def save_client_mapping(order_id: str, client_id: str, client_secret: str):
    db = load_db()
    db[order_id] = ClientRecord(order_id=order_id,
                                client_id=client_id,
                                client_secret=client_secret)
    save_db(db)

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
    client_payload = {
        "client_name": f"Gemini Agent - Order {order_id}",
        "application_type": "web",
        "redirect_uris": redirect_uris,
        "response_types": ["code"],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "client_secret_post"
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
