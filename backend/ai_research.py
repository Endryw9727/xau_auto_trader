import os
import uuid
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from emergentintegrations.llm.chat import LlmChat, UserMessage

from auth import get_current_user
from db import db

router = APIRouter(prefix="/api/ai", tags=["ai"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# Multi-LLM routing per research task. Kimi (Moonshot) is not yet wired (no key).
TASK_ROUTING = {
    "explain_significance": {"provider": "anthropic", "model": "claude-sonnet-4-6",
                             "label": "Explain Significance", "desc": "Interpret the audit verdict & mtc_robust column."},
    "propose_hypotheses": {"provider": "openai", "model": "gpt-5.4",
                           "label": "Propose Hypotheses", "desc": "Suggest new research hypotheses to test."},
    "critique_edge": {"provider": "anthropic", "model": "claude-sonnet-4-6",
                      "label": "Critique Edge", "desc": "Stress-test a KEEP/EXCLUDE verdict for robustness."},
    "summarize_diagnostics": {"provider": "openai", "model": "gpt-5.4-mini",
                              "label": "Summarize Diagnostics", "desc": "Plain-language summary of bot reports."},
}

PROVIDERS = [
    {"id": "anthropic", "model": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6", "enabled": True},
    {"id": "openai", "model": "gpt-5.4", "label": "GPT-5.4", "enabled": True},
    {"id": "openai", "model": "gpt-5.4-mini", "label": "GPT-5.4 Mini", "enabled": True},
    {"id": "moonshot", "model": "kimi", "label": "Kimi (Moonshot) — soon", "enabled": False},
]

SYSTEM_PROMPT = (
    "You are a READ-ONLY quantitative trading research assistant for a Research Console. "
    "STRICT RULES, NEVER violate:\n"
    "1. You ONLY receive metrics that have ALREADY been computed by an external statistics engine. "
    "You MUST NOT compute, recompute, fabricate, or estimate any statistic, t-stat, p-value, or backtest yourself. "
    "If a number is not in the provided context, say it is not available.\n"
    "2. You operate in REPORT-ONLY mode: you explain results and propose research hypotheses to test next. "
    "You CANNOT place, modify, route, or recommend arming any real or live order. "
    "The system flag allow_real_live is permanently FALSE and live execution is DISARMED. "
    "Never suggest enabling live trading.\n"
    "3. Be concise, technical, and objective. Reference the exact metric names provided "
    "(oos_t_stat, p_value, bonferroni_significant, bh_significant, mtc_robust, verdict).\n"
    "4. When asked for hypotheses, frame them as falsifiable tests, not trade signals."
)


class ChatIn(BaseModel):
    task: str = "explain_significance"
    provider: str | None = None
    model: str | None = None
    message: str
    context: dict | str | None = None
    conversation_id: str | None = None


@router.get("/config")
async def config(user: dict = Depends(get_current_user)):
    return {"tasks": TASK_ROUTING, "providers": PROVIDERS, "report_only": True,
            "live_armed": False, "allow_real_live": False}


@router.post("/chat")
async def chat(body: ChatIn, user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="LLM key not configured")

    route = TASK_ROUTING.get(body.task, TASK_ROUTING["explain_significance"])
    provider = body.provider or route["provider"]
    model = body.model or route["model"]
    if provider == "moonshot":
        raise HTTPException(status_code=400, detail="Kimi (Moonshot) is not enabled yet.")

    conversation_id = body.conversation_id or str(uuid.uuid4())

    ctx_text = ""
    if body.context:
        ctx_text = body.context if isinstance(body.context, str) else json.dumps(body.context, indent=2)[:12000]

    prompt = body.message
    if ctx_text:
        prompt = (
            "Here are the ALREADY-COMPUTED metrics (read-only context). "
            "Do not recompute anything — only interpret these:\n```json\n"
            f"{ctx_text}\n```\n\nTask: {route['label']}\n\nUser question: {body.message}"
        )

    chat_client = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=conversation_id,
        system_message=SYSTEM_PROMPT,
    ).with_model(provider, model)

    reply = ""
    try:
        reply = await chat_client.send_message(UserMessage(text=prompt))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    now = datetime.now(timezone.utc).isoformat()
    await db.ai_conversations.update_one(
        {"id": conversation_id},
        {"$setOnInsert": {"id": conversation_id, "user_email": user["email"], "created_at": now},
         "$set": {"updated_at": now, "task": body.task, "provider": provider, "model": model},
         "$push": {"messages": {"$each": [
             {"role": "user", "content": body.message, "ts": now},
             {"role": "assistant", "content": reply, "provider": provider, "model": model, "ts": now},
         ]}}},
        upsert=True,
    )

    return {"conversation_id": conversation_id, "reply": reply, "provider": provider,
            "model": model, "task": body.task, "report_only": True}


@router.get("/conversations")
async def conversations(user: dict = Depends(get_current_user)):
    convs = await db.ai_conversations.find(
        {"user_email": user["email"]}, {"_id": 0, "messages": 0}
    ).sort("updated_at", -1).to_list(50)
    return {"conversations": convs}


@router.get("/conversations/{conversation_id}")
async def conversation(conversation_id: str, user: dict = Depends(get_current_user)):
    conv = await db.ai_conversations.find_one({"id": conversation_id}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
