"""Generation routes for LLM service - HTTP endpoints for text generation."""

import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["generation"])


# Module-level helper function for fallback responses (used in multiple routes)
def _get_fallback_response(language: str, query: str) -> str:
    """Get intelligent fallback response when generation fails."""
    query_lower = query.lower()
    
    if language == "ur":
        # Urdu greetings
        if any(word in query_lower for word in ["السلام", "سلام", "ہلو", "ہائے", "کیسے ہو"]):
            return "السلام علیکم! میں NEXI ہوں، آپ کا خودکار معاون۔ آپ سے کیا پوچھنے کا موضوع ہے؟"
        # Urdu introduction
        elif any(word in query_lower for word in ["تمھارا نام", "تمہارا نام", "کون ہو", "تم کون"]):
            return "میں NEXI ہوں، آپ کا ذہین معاون۔ مجھے آپ سے ملنا خوشی سے ہے۔"
        # Urdu help requests
        elif any(word in query_lower for word in ["مدد", "کیا کر سکتے", "کیا آپ"]):
            return "میں آپ کی مدد کے لیے یہاں ہوں۔ براہ کرم اپنی سوال یا تلاش بتائیں اور میں آپ کو بہترین جواب دوں گا۔"
        # Urdu learning
        elif any(word in query_lower for word in ["سیکھ", "سیکھنا", "جانیں", "بتا"]):
            return "میں آپ کو سیکھنے میں مدد کرنے کے لیے خوشی سے تیار ہوں۔ کوئی بھی موضوع چنیں اور آئیے مل کر سیکھتے ہیں۔"
        # Default Urdu response
        else:
            return "معاف کیجیے، میں اس وقت مناسب جواب تیار نہیں کر سکا۔ براہ کرم دوبارہ کوشش کریں یا ایک مختلف سوال پوچھیں۔"
    
    else:
        # English greetings
        if any(word in query_lower for word in ["hello", "hi", "hey", "greet", "greeting"]):
            return "Hello! I'm NEXI, your intelligent assistant. What would you like to know or talk about today?"
        # English introduction
        elif any(word in query_lower for word in ["name", "who", "what are you", "introduce yourself"]):
            return "I'm NEXI, your AI assistant. I'm here to help you learn, answer questions, and have meaningful conversations."
        # English help requests
        elif any(word in query_lower for word in ["help", "can you", "what can you do"]):
            return "I'm here to help! I can answer questions, have conversations, assist with learning, and understand your mood and preferences. What would you like to know?"
        # English learning
        elif any(word in query_lower for word in ["teach", "learn", "explain", "how"]):
            return "I'd be happy to help you learn! Tell me what subject or topic you're interested in, and I'll explain it in a way that's easy to understand."
        # Default English response
        else:
            return "I apologize, I'm having trouble generating a response right now. Please try again with a different question or rephrase your query."


# Request/Response Models
class UserContextModel(BaseModel):
    """User profile context."""
    user_id: Optional[str] = None
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    mood: Optional[str] = None  # Can be string like "happy", "sad", etc.
    language: Optional[str] = "en"
    interests: Optional[List[str]] = []
    enrolled_timestamp: Optional[str] = None
    last_interaction: Optional[str] = None


class VisionContextModel(BaseModel):
    """Visual information context."""
    face_detected: Optional[bool] = False
    mood: Optional[str] = None
    emotion_scores: Optional[Dict[str, float]] = None
    confidence: Optional[float] = 0.0
    face_count: Optional[int] = 0
    objects: Optional[List[str]] = []
    emotion: Optional[str] = None
    description: Optional[str] = None


class ConversationTurnModel(BaseModel):
    """Single turn in conversation history."""
    user: str
    assistant: str
    timestamp: Optional[str] = None


class GenerateRequest(BaseModel):
    """Request to generate response."""
    query: str = Field(..., description="User query/prompt", min_length=1, max_length=2000)
    language: Optional[str] = Field("en", description="Language: 'en' or 'ur'")
    user_context: Optional[UserContextModel] = None
    vision_context: Optional[VisionContextModel] = None
    knowledge_items: Optional[List[Dict[str, Any]]] = []
    conversation_history: Optional[List[ConversationTurnModel]] = []
    
    max_response_tokens: Optional[int] = Field(None, ge=10, le=500)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)


class GenerateResponse(BaseModel):
    """Response from text generation."""
    success: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


def create_generation_routes(inference_engine, prompt_builder, model_loader, hybrid_manager=None) -> APIRouter:
    """
    Create generation routes with injected dependencies.
    
    Args:
        inference_engine: InferenceEngine instance (local LLM)
        prompt_builder: PromptBuilder instance
        model_loader: ModelLoader instance
        hybrid_manager: HybridInferenceManager instance (optional, for OpenRouter + fallback)
    
    Returns:
        APIRouter configured with generation routes
    """
    
    @router.post("/generate", response_model=GenerateResponse)
    async def generate_response(request: GenerateRequest) -> GenerateResponse:
        """
        Generate text response using LLM with robust error handling.
        
        This endpoint accepts a user query with optional context from other NEXI services
        and returns an AI-generated response tailored to the user.
        """
        try:
            # Check if model is loaded
            if not model_loader.is_loaded():
                return GenerateResponse(
                    success=False,
                    error={
                        "code": "MODEL_NOT_LOADED",
                        "message": "LLM model is not loaded. Please initialize the service.",
                    }
                )
            
            # Validate language
            language = request.language.lower() if request.language else "en"
            if language not in ["en", "ur", "urdu"]:
                language = "en"
            if language == "urdu":
                language = "ur"
            
            # Validate query
            query = request.query.strip() if request.query else ""
            if not query or len(query) < 1:
                return GenerateResponse(
                    success=False,
                    error={
                        "code": "EMPTY_QUERY",
                        "message": "Query cannot be empty",
                    }
                )
            
            # Build prompt with context
            logger.info(f"Building prompt for language: {language}")
            
            full_prompt, token_breakdown = prompt_builder.build_full_prompt(
                user_query=request.query,
                language=language,
                user_context=request.user_context.dict() if request.user_context else None,
                vision_context=request.vision_context.dict() if request.vision_context else None,
                knowledge_items=request.knowledge_items or [],
                conversation_history=[h.dict() for h in request.conversation_history] if request.conversation_history else None,
                token_counter=None,
            )
            
            logger.info(f"Token breakdown: {token_breakdown}")
            
            # Validate prompt
            is_valid, error_msg = inference_engine.validate_prompt(full_prompt)
            if not is_valid:
                logger.warning(f"Prompt validation failed: {error_msg}")
                return GenerateResponse(
                    success=False,
                    error={
                        "code": "INVALID_PROMPT",
                        "message": error_msg,
                    }
                )
            
            # Generate response
            logger.info("Starting inference...")
            
            # PRIMARY: Use OpenRouter for both English AND Urdu (faster, better quality)
            # FALLBACK: Local LLM if OpenRouter unavailable
            if hybrid_manager:
                logger.info(f"Using OpenRouter (primary) for {language} language - with local LLM fallback")
                generated_text, inference_metadata = await hybrid_manager.generate(
                    prompt=full_prompt,
                    system_prompt="",
                    max_tokens=request.max_response_tokens,
                    temperature=request.temperature,
                    language=language,
                )
            else:
                logger.warning("OpenRouter not available - using local LLM as fallback")
                generated_text, inference_metadata = await inference_engine.generate(
                    prompt=full_prompt,
                    max_tokens=request.max_response_tokens,
                    temperature=request.temperature,
                    top_p=request.top_p,
                )
            
            # VALIDATE Response Quality - Critical Bug Fix
            # Validate response is not corrupted (all exclamation marks, all special chars, etc.)
            if generated_text:
                generated_text = generated_text.strip()
                
                # Check if response is corrupted (70%+ special characters)
                if len(generated_text) > 0:
                    special_char_ratio = sum(1 for c in generated_text if c in "!@#$%^&*()_+-={}[]|:;<>?,./") / len(generated_text)
                    if special_char_ratio > 0.7:
                        logger.error(f"Response corrupted (special chars: {special_char_ratio:.1%}), falling back")
                        generated_text = _get_fallback_response(language, query)
                
                # Check if response is too short (likely error)
                elif len(generated_text) < 5 and request.max_response_tokens != request.max_response_tokens or request.max_response_tokens is None:
                    logger.warning(f"Response too short ({len(generated_text)} chars), may be error")
                    # Still use it, but log warning
            
            # Default to fallback if empty
            if not generated_text:
                logger.warning("Empty response received, using fallback")
                generated_text = _get_fallback_response(language, query)
            
            # Prepare response
            response_data = {
                "response": generated_text,
                "language": language,
                "metadata": {
                    **inference_metadata,
                    "tokens": token_breakdown,
                },
            }
            
            logger.info("Response generated successfully")
            
            return GenerateResponse(
                success=True,
                data=response_data,
            )
            
        except TimeoutError as e:
            logger.error(f"Inference timeout: {str(e)}")
            return GenerateResponse(
                success=False,
                error={
                    "code": "INFERENCE_TIMEOUT",
                    "message": f"Model inference exceeded timeout: {str(e)}",
                }
            )
        except RuntimeError as e:
            logger.error(f"Runtime error: {str(e)}")
            return GenerateResponse(
                success=False,
                error={
                    "code": "RUNTIME_ERROR",
                    "message": str(e),
                }
            )
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return GenerateResponse(
                success=False,
                error={
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred during generation.",
                }
            )
    
    @router.get("/health", response_model=Dict[str, Any])
    async def health_check():
        """Check service and model health status."""
        status = {
            "service": "ok",
            "model_loaded": model_loader.is_loaded(),
            "timestamp": datetime.now().isoformat(),
        }
        
        if model_loader.is_loaded():
            status["status_code"] = 200
        else:
            status["status_code"] = 503
            status["message"] = "Model not loaded"
        
        return status
    
    @router.get("/model-info", response_model=Dict[str, Any])
    async def model_info():
        """Get information about loaded model."""
        if not model_loader.is_loaded():
            raise HTTPException(
                status_code=503,
                detail="Model not loaded",
            )
        
        try:
            tokenizer = model_loader.get_tokenizer()
            
            return {
                "model": "SmolLM2-1.7B-Instruct",
                "tokenizer": tokenizer.__class__.__name__,
                "vocab_size": len(tokenizer),
                "max_context_tokens": 8192,
                "supported_languages": ["en", "ur"],
            }
        except Exception as e:
            logger.error(f"Error getting model info: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve model information",
            )
    
    return router
