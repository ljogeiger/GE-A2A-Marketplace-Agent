import os
import base64
import json
import logging
import httpx
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from google.auth import default
from google.auth.transport.requests import Request as GoogleRequest
from dcr.utils import register_okta_client, save_client_mapping, find_client_by_order_id, validate_jwt

# --- Logger ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
app = FastAPI()

# Default redirect URI for initial provisioning (can be updated later)
DEFAULT_REDIRECT_URI = os.environ.get(
    "DEFAULT_REDIRECT_URI",
    "https://vertexaisearch.cloud.google.com/oauth-redirect")


# --- Google Procurement API ---
async def approve_account(payload: dict):
    """


    Checks if the account is active, and approves it if not.


    Triggered by eventType: ACCOUNT_CREATION_REQUESTED (or similar).


    """

    provider_id = payload.get("providerId")

    account_id = payload.get("account", {}).get("id")

    if not provider_id or not account_id:

        logger.warning(
            "Missing providerId or account.id for account approval check")

        return

    resource_name = f"providers/{provider_id}/accounts/{account_id}"

    logger.info(f"Checking account status: {resource_name}")

    credentials, project_id = default()

    credentials.refresh(GoogleRequest())

    base_url = "https://cloudcommerceprocurement.googleapis.com/v1"

    resource_url = f"{base_url}/{resource_name}"

    approve_url = f"{resource_url}:approve"

    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:

        try:

            # 1. Check State

            get_resp = await client.get(resource_url, headers=headers)

            get_resp.raise_for_status()

            account_data = get_resp.json()

            state = account_data.get("state")

            logger.info(f"Account {resource_name} state: {state}")

            if state == "ACCOUNT_ACTIVE":

                logger.info("Account is already ACTIVE. No action needed.")

                return

            # 2. Approve if not active

            logger.info(f"Approving account {resource_name}...")

            # Body required for accounts.approve

            json_body = {"reason": "Approved via Marketplace Agent"}

            post_resp = await client.post(approve_url,
                                          json=json_body,
                                          headers=headers)

            post_resp.raise_for_status()

            logger.info(f"Account {resource_name} approved successfully.")

        except Exception as e:

            logger.error(
                f"Failed to process account approval for {resource_name}: {e}")
            raise HTTPException(status_code=400,
                                detail=f"Account approval failed: {str(e)}")
            # We log but do not raise, so flow can continue if needed.

            # However, if account isn't active, subsequent steps might fail?

            # DCR doesn't strictly depend on Account Active status in this code,

            # but business logic might. We'll proceed.


# --- Models ---
class PubSubMessage(BaseModel):
    data: str
    messageId: str
    publishTime: str


class EventEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str


class RegistrationRequest(BaseModel):
    software_statement: str


class DCRResponse(BaseModel):
    client_id: str
    client_secret: str
    client_secret_expires_at: int = 0


@app.post("/dcr")
async def handle_event(request: Request):
    """
    Hybrid Handler:
    1. Handles Pub/Sub events (Async Marketplace provisioning).
    2. Handles direct DCR requests (Gemini Enterprise client registration).
    """
    logger.info("Received request on /dcr")
    logger.info(f"Request Headers: {request.headers}")

    # Read the body
    try:
        body = await request.json()
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON body")
        try:
            raw_body = await request.body()
            logger.info(f"Raw Body: {raw_body.decode('utf-8')}")
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    logger.info(f"Successfully parsed JSON body.")
    logger.info(f"Request Body Content: {body}")
    logger.info(f"Request Body Keys: {list(body.keys())}")

    # --- Path A: Direct DCR Request (Sync) ---
    if "software_statement" in body:
        logger.info("Detected DCR Request (software_statement present)")
        try:
            reg_request = RegistrationRequest(**body)
            decoded_token = validate_jwt(reg_request.software_statement)
        except Exception as e:
            logger.error(f"JWT Validation failed: {e}")
            raise HTTPException(status_code=400,
                                detail=f"JWT Validation failed: {str(e)}")

        order_id = decoded_token.get("google", {}).get("order")
        redirect_uris = decoded_token.get("auth_app_redirect_uris")

        logger.info(f"Extracted Order ID from JWT: {order_id}")
        logger.info(f"Extracted Redirect URIs from JWT: {redirect_uris}")

        if not order_id:
            logger.error("Missing 'google.order' in JWT")
            raise HTTPException(status_code=400,
                                detail="Missing 'google.order' in JWT")
        if not redirect_uris:
            logger.error("Missing 'auth_app_redirect_uris' in JWT")
            raise HTTPException(
                status_code=400,
                detail="Missing 'auth_app_redirect_uris' in JWT")

        logger.info(f"DCR Request for Order ID: {order_id}")

        # Check DB
        logger.info(f"Looking up client for order_id: {order_id} in database...")
        existing_client = find_client_by_order_id(order_id)
        if existing_client:
            logger.info(f"Returning existing client for order {order_id}")
            return DCRResponse(client_id=existing_client.client_id,
                               client_secret=existing_client.client_secret,
                               client_secret_expires_at=0)

        # Order Validation Failed
        logger.warning(
            f"Order ID {order_id} not found in client records. Ensure the order is processed via Pub/Sub first."
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid Order ID: Order not found in client records.")

    # --- Path B: Pub/Sub Event (Async) ---
    logger.info("Detected Pub/Sub Event")
    try:
        if "message" in body:
            message_data = body["message"]["data"]
        elif "data" in body:  # Sometimes directly in data depending on envelope
            message_data = body["data"]
        else:
            logger.warning("Unknown event format (neither DCR nor Pub/Sub)")
            return {"status": "ignored", "reason": "Unknown format"}

        decoded_data = base64.b64decode(message_data).decode("utf-8")
        logger.info(f"Decoded Data: {decoded_data}")

        payload = json.loads(decoded_data)

        # Handle Account Creation (Check & Approve)
        event_type = payload.get("eventType")
        if event_type == "ACCOUNT_CREATION_REQUESTED":
            logger.info(
                "Detected ACCOUNT_CREATION_REQUESTED. Checking status...")
            await approve_account(payload)

        # TODO: Check type of entlitnement request by status.
        # TODO: Handle entitlment cancallation (deprovision client id/secret) in Okta.

        # Extract Order ID.
        order_id = (payload.get("entitlement", {}).get("orderId")
                    or payload.get("account", {}).get("orderId")
                    or payload.get("orderId") or payload.get("id")
                    or payload.get("name"))

        if not order_id:
            logger.error(
                f"Could not find orderId in payload keys: {payload.keys()}")
            return {"status": "error", "message": "Missing orderId"}

        logger.info(f"Processing Order ID: {order_id}")

        # Register in Okta (Async Provisioning)
        existing = find_client_by_order_id(order_id)
        if existing:
            logger.info(
                f"Client already exists for order {order_id}. Skipping.")
        else:
            client_id, client_secret = await register_okta_client(
                order_id, [DEFAULT_REDIRECT_URI])
            save_client_mapping(order_id, client_id, client_secret)
            logger.info(f"Registered new client for order {order_id}")

        return {"status": "success", "orderId": order_id}

    except Exception as e:
        logger.error(f"Error processing event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
