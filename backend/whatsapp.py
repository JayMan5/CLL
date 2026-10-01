import os
import logging
import requests
from typing import Dict, Any

# Setup logging
logger = logging.getLogger("courtlog.whatsapp")

# Webhook configuration - default to a local simulator endpoint on our own server
WHATSAPP_WEBHOOK_URL = os.environ.get(
    "WHATSAPP_WEBHOOK_URL", 
    "http://localhost:8000/api/whatsapp/webhook-simulator"
)
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_API_TOKEN", "mock_whatsapp_token_xyz123")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "10987654321")

def send_adjournment_broadcast(case_id: str, next_date: str, reason_code: str, group_id: str = "registry-group-104") -> Dict[str, Any]:
    """
    Simulates sending a WhatsApp Business API message using templates.
    Compiles a broadcast payload and sends it to the configured webhook or API.
    """
    # Compile the template message
    message_text = f"SUIT NO: {case_id} adjourned to {next_date}. Reason: {reason_code}. File routing back to Registry."
    
    # Official Meta Cloud API structure simulation
    payload = {
        "messaging_product": "whatsapp",
        "to": group_id,
        "type": "template",
        "template": {
            "name": "court_adjournment_alert",
            "language": {
                "code": "en"
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": case_id},
                        {"type": "text", "text": next_date},
                        {"type": "text", "text": reason_code}
                    ]
                }
            ]
        },
        # Including compiled text for easy inspection in the logs
        "simulated_text": message_text
    }
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "X-Simulator-Secret": os.getenv("SIMULATOR_SECRET", ""),
        "Content-Type": "application/json"
    }
    
    logger.info(f"Triggering WhatsApp broadcast for case {case_id}")
    logger.info(f"Target Webhook: {WHATSAPP_WEBHOOK_URL}")
    logger.info("Broadcast payload prepared")
    
    response_data = {
        "status": "simulated",
        "payload": payload,
        "webhook_url": WHATSAPP_WEBHOOK_URL
    }
    
    try:
        # Trigger the HTTP POST to simulate webhook/API ingestion
        response = requests.post(
            WHATSAPP_WEBHOOK_URL,
            json=payload,
            headers=headers,
            timeout=5
        )
        response_data["status_code"] = response.status_code
        response_data["response_body"] = response.text
        
        if response.status_code >= 200 and response.status_code < 300:
            logger.info("WhatsApp webhook broadcast simulation succeeded.")
        else:
            logger.warning(f"WhatsApp webhook simulation returned status {response.status_code}: {response.text}")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to WhatsApp Webhook simulation: {e}")
        response_data["error"] = str(e)
        response_data["status"] = "failed_connection"
        
    return response_data
