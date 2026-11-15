import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.uservice.security.jit import issue_jit_credential

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    commander_id: str
    passphrase: str

class LoginResponse(BaseModel):
    token: str
    agent_id: str
    expires_at: str
    lifetime_seconds: int

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    expected_passphrase = os.environ.get("COMMANDER_PASSPHRASE", "").strip()
    if not expected_passphrase:
        raise HTTPException(
            status_code=500,
            detail="COMMANDER_PASSPHRASE is not configured",
        )

    if req.passphrase != expected_passphrase:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    # Grant necessary scopes for the dashboard and C4ISR endpoints
    scopes = [
        "smeac:create",
        "smeac:read",
        "hitl:decide",
        "hitl:read",
        "swarm:read",
        "swarm:create",
        "swarm:delete",
        "threat:read",
        "threat:write",
        "analytics:read",
        "analytics:write",
    ]
    
    # Issue a token with a 24-hour lifetime for the dashboard
    result = await issue_jit_credential(
        agent_name=req.commander_id,
        scopes=scopes,
        lifetime_seconds=86400
    )
    
    return result
