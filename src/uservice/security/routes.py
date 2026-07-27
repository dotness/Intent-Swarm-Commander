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
    expected_passphrase = os.environ.get("COMMANDER_PASSPHRASE")
    if not expected_passphrase:
        expected_passphrase = "dev_passphrase"  # fallback for development
        
    if req.passphrase != expected_passphrase:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    # Grant necessary scopes for the dashboard
    scopes = ["smeac:create", "smeac:read", "hitl:decide", "hitl:read"]
    
    # Issue a token with a 24-hour lifetime for the dashboard
    result = await issue_jit_credential(
        agent_name=req.commander_id,
        scopes=scopes,
        lifetime_seconds=86400
    )
    
    return result
