import os
import base64
import json
import logging
import httpx
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from google.auth import default
from google.auth.transport.requests import Request as GoogleRequest
from dcr.utils import register_okta_client, save_client_mapping, find_client_by_order_id
from dcr.jwt_validation import validate_jwt

# --- Logger ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
app = FastAPI()

# Default redirect URI for initial provisioning (can be updated later)
DEFAULT_REDIRECT_URI = os.environ.get(
    "DEFAULT_REDIRECT_URI",
    "https://vertexaisearch.cloud.google.com/oauth-redirect")


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

    # Read the body
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    logger.info(f"Request Body Keys: {list(body.keys())}")

    # --- Path A: Direct DCR Request (Sync) ---
    if "software_statement" in body:
        logger.info("Detected DCR Request (software_statement present)")
        try:
            reg_request = RegistrationRequest(**body)
            decoded_token = await validate_jwt(reg_request.software_statement)
        except Exception as e:
            logger.error(f"JWT Validation failed: {e}")
            raise HTTPException(status_code=400,
                                detail=f"JWT Validation failed: {str(e)}")

        order_id = decoded_token.get("google", {}).get("order")
        redirect_uris = decoded_token.get("auth_app_redirect_uris")

        if not order_id:
            raise HTTPException(status_code=400,
                                detail="Missing 'google.order' in JWT")
        if not redirect_uris:
            raise HTTPException(
                status_code=400,
                detail="Missing 'auth_app_redirect_uris' in JWT")

        logger.info(f"DCR Request for Order ID: {order_id}")

        # Check DB
        existing_client = find_client_by_order_id(order_id)
        if existing_client:
            logger.info(f"Returning existing client for order {order_id}")
            return DCRResponse(client_id=existing_client.client_id,
                               client_secret=existing_client.client_secret,
                               client_secret_expires_at=0)

        # Create New
        logger.info(f"Provisioning new client for order {order_id}")
        client_id, client_secret = await register_okta_client(
            order_id, redirect_uris)
        save_client_mapping(order_id, client_id, client_secret)

        return DCRResponse(client_id=client_id,
                           client_secret=client_secret,
                           client_secret_expires_at=0)

    # --- Path B: Pub/Sub Event (Async) ---
    logger.info("Detected Potential Pub/Sub Event")
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
