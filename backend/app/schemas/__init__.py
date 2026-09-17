from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class TokenOut(BaseModel):
    access_token: str
    email: str


class AgentRunIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    model: str | None = None


class ResumeIn(BaseModel):
    run_id: int
    approved: bool = True


class DocTextIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class DocUpdateIn(BaseModel):
    filename: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1)


class RagQueryIn(BaseModel):
    query: str
    top_k: int | None = None


class McpCallIn(BaseModel):
    name: str
    args: dict = {}


class ConversationIn(BaseModel):
    title: str = "新会话"
