"""
tests/test_whatsapp_flow.py
============================
Automated test suite verifying the WhatsApp webhook integration service.
"""

import pytest
import httpx
import asyncio

WHATSAPP_BOT_URL = "http://localhost:9000"

@pytest.mark.anyio
async def test_whatsapp_health():
    """Verify rag-whatsapp health endpoint."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{WHATSAPP_BOT_URL}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("service") == "rag-whatsapp"


@pytest.mark.anyio
async def test_whatsapp_greeting_webhook():
    """Verify webhook handles greeting messages properly."""
    payload = {
        "event": "message.received",
        "data": {
            "id": "false_919876543210@c.us_3EB012345678",
            "fromMe": False,
            "from": "919876543210@c.us",
            "body": "Hello"
        }
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{WHATSAPP_BOT_URL}/webhook", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "processing"


@pytest.mark.anyio
async def test_whatsapp_rag_query_webhook():
    """Verify webhook handles citizen RAG queries properly."""
    payload = {
        "event": "message.received",
        "data": {
            "id": "false_919876543210@c.us_3EB099999999",
            "fromMe": False,
            "from": "919876543210@c.us",
            "body": "Who is the DM of West Tripura?"
        }
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{WHATSAPP_BOT_URL}/webhook", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "processing"


if __name__ == "__main__":
    asyncio.run(test_whatsapp_health())
    asyncio.run(test_whatsapp_greeting_webhook())
    asyncio.run(test_whatsapp_rag_query_webhook())
    print("✅ All WhatsApp flow tests passed!")
