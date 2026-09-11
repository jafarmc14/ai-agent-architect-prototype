"""Technical defaults; the data owner must approve before scheduling --apply."""
from pydantic import BaseModel, ConfigDict, Field


class RetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    raw_conversation_days: int = Field(default=30, ge=1, le=3650)
    log_days: int = Field(default=30, ge=1, le=3650)
    audit_days: int = Field(default=365, ge=1, le=3650)
    evaluation_days: int = Field(default=90, ge=1, le=3650)
    pii_days: int = Field(default=7, ge=1, le=3650)
    batch_size: int = Field(default=500, ge=1, le=5000)
