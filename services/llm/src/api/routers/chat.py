from fastapi import APIRouter, Depends, HTTPException, Request

from contracts.chat import ChatRequest, ChatResponse, Usage
from src.api.auth import require_api_key
from src.api.deps import get_llm
from src.config import get_settings
from src.providers.base import (
    LLMMessage,
    LLMProvider,
    LLMRequest,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    _key=Depends(require_api_key),
    llm: LLMProvider = Depends(get_llm),
) -> ChatResponse:
    settings = get_settings()
    llm_request = LLMRequest(
        messages=[LLMMessage(role=m.role, content=m.content) for m in body.messages],
        system=body.system,
        model=body.model,
        max_tokens=body.max_tokens,
        thinking=body.thinking if body.thinking is not None else settings.thinking_default,
    )
    request.state.audit_extra = {"model": body.model or settings.llm_model}
    try:
        result = llm.chat(llm_request)
    except ProviderRateLimited:
        raise HTTPException(status_code=429, detail="LLM provider rate limited")
    except ProviderTimeout:
        raise HTTPException(status_code=504, detail="LLM provider timeout")
    except ProviderError:
        raise HTTPException(status_code=502, detail="LLM provider error")
    request.state.audit_extra.update(
        {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens}
    )

    return ChatResponse(
        content=result.content,
        model=result.model,
        stop_reason=result.stop_reason,
        usage=Usage(input_tokens=result.input_tokens, output_tokens=result.output_tokens),
    )
