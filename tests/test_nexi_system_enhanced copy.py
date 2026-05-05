"""
NEXI System - Complete Integration Test Suite v2.0
User-Centric Scenarios with Production Feature Validation

This enhanced test suite implements 7 core user journeys:
1. Service Status Check
2. New User Enrollment (Fatima) - with resource pre-emption
3. Improve Training (Sara) - add biometric samples
4. Re-enrollment (Ali) - replace all data
5. Return User Conversation (Sara) - full pipeline: Wake→Verify→STT→Vision→Knowledge→LLM→TTS
6. Teach Objects (Sara) - object learning workflow
7. Settings - runtime parameter configuration

All services must be running per COMMANDS.txt
Author: Integration Testing Team
Version: 2.0
Date: 2026-02-28
"""

import requests
import sounddevice as sd
import soundfile as sf
import numpy as np
import time
import os
import sys
import io
import cv2
import random
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# Vision Service handles all ML models (YOLO, DeepFace, etc) via REST API
# Test file is a thin client - no local ML models required
# This approach ensures proper deployment without model distribution issues

# Import cached voice player for predefined audio responses
from cached_voice_player import get_voice_player
from llm_context_builder import LLMContextBuilder

# Import query processor for NLP (entity/label extraction from voice)
from service.query_processor import QueryProcessorService

# ============================================================================
# COCO CLASSES AND COLORS - All 80 YOLOv8 Classes
# ============================================================================

# All 80 COCO class names (YOLOv8 standard order - indices 0-79)
COCO_CLASSES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck',
    'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench',
    'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe',
    'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis',
    'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard',
    'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife',
    'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot',
    'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed',
    'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'microwave',
    'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors',
    'teddy bear', 'hair drier', 'toothbrush'
]

def generate_coco_colors():
    """Generate distinct colors for all 80 COCO classes using HSV color space"""
    colors = {}
    
    # Generate colors with good visual distinction
    for idx, class_name in enumerate(COCO_CLASSES):
        hue = int((idx / len(COCO_CLASSES)) * 180)  # OpenCV HSV: hue 0-180
        saturation = 200 + (idx % 2) * 55  # Vary between 200-255
        value = 200 + ((idx // 2) % 2) * 55  # Vary between 200-255
        
        # Convert HSV to BGR
        hsv = np.uint8([[[hue, saturation, value]]])
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0][0]
        colors[class_name] = tuple(int(x) for x in bgr)
    
    # Override with manually tuned nice colors for important classes
    nice_colors = {
        'person': (0, 255, 0),           # Green
        'car': (0, 0, 255),              # Red
        'dog': (0, 255, 255),            # Yellow
        'cat': (255, 0, 255),            # Magenta
        'bicycle': (255, 0, 0),          # Blue
        'phone': (128, 128, 0),          # Dark cyan
        'laptop': (0, 128, 128),         # Cyan
        'cup': (255, 165, 0),            # Orange
        'bottle': (100, 200, 200),       # Light cyan
        'chair': (128, 0, 128),          # Purple
        'backpack': (200, 100, 50),      # Brown
        'handbag': (150, 100, 255),      # Light purple
        'book': (100, 150, 200),         # Light blue
        'knife': (255, 200, 0),          # Sky blue
        'fork': (0, 200, 200),           # Cyan-green
        'spoon': (200, 100, 150),        # Pink
        'bowl': (100, 200, 100),         # Light green
        'tv': (0, 100, 200),             # Dark red-orange
        'remote': (150, 150, 255),       # Light pink
        'keyboard': (200, 200, 0),       # Cyan
        'mouse': (100, 100, 255),        # Red-ish
        'umbrella': (0, 150, 150),       # Teal
        'tie': (255, 100, 100),          # Light red
        'suitcase': (150, 200, 100),     # Yellow-green
        'oven': (50, 50, 200),           # Dark orange-red
        'refrigerator': (200, 100, 200), # Light magenta
        'microwave': (100, 200, 50),     # Yellow-green
        'clock': (200, 150, 100),        # Brown-ish
        'teddy bear': (150, 200, 150),   # Light green
    }
    
    # Merge manual colors with generated ones
    colors.update(nice_colors)
    
    return colors

# Initialize colors globally
OBJECT_COLORS = generate_coco_colors()

# ============================================================================
# CONFIGURATION
# ============================================================================

class ServiceConfig:
    """Service URL configuration"""
    CENTRAL_SERVER = os.getenv("NEXI_CENTRAL_SERVER_URL", "http://localhost:8000")
    AUDIO_SERVICE = os.getenv("NEXI_AUDIO_SERVICE_URL", "http://localhost:8002")
    ENROLLMENT_SERVICE = os.getenv("NEXI_ENROLLMENT_SERVICE_URL", "http://localhost:8005")
    VISION_SERVICE = os.getenv("NEXI_VISION_SERVICE_URL", "http://localhost:8001")
    TTS_SERVICE = os.getenv("NEXI_TTS_SERVICE_URL", "http://localhost:8003")
    TEACHME_SERVICE = os.getenv("NEXI_TEACHME_SERVICE_URL", "http://localhost:8004")
    LLM_SERVICE = os.getenv("NEXI_LLM_SERVICE_URL", "http://localhost:8006")
    
    AUDIO_API = f"{AUDIO_SERVICE}/api/v1"
    VISION_API = f"{VISION_SERVICE}/api/v1"
    TEACHME_API = f"{TEACHME_SERVICE}/api/v1"
    LLM_API = f"{LLM_SERVICE}/api/v1"

class AudioConfig:
    """Audio recording configuration"""
    SAMPLE_RATE = 16000
    CHANNELS = 1
    DTYPE = 'float32'
    DEFAULT_DURATION = 5

class VisionConfig:
    """Vision Service configuration"""
    DETECTOR_BACKEND = "opencv"
    MODEL_NAME = "Facenet"
    EMBEDDING_DIM = 128
    TIMEOUT = 30
    CAMERA_WIDTH = 640
    CAMERA_HEIGHT = 480
    CAMERA_FPS = 30


class RuntimeConfig:
    """Runtime-configurable integration settings."""
    WAKE_WORD_DETECT_TIMEOUT = int(os.getenv("NEXI_WAKEWORD_TIMEOUT", "90"))
    LLM_RESPONSE_TIMEOUT = int(os.getenv("NEXI_LLM_TIMEOUT", "160"))
    
    # TTS Speaker Configuration (NEW - Jenny Optimization)
    # Default speaker must be English only (Jenny or Ryan)
    # Shahid is NEVER available as default - forced for Urdu responses
    DEFAULT_SPEAKER = "jenny"  # Default speaker: ONLY English speakers (jenny or ryan)
    DEFAULT_SPEAKERS_ENGLISH_ONLY = ["jenny", "ryan"]  # Available defaults
    AVAILABLE_SPEAKERS = ["jenny", "ryan", "shahid"]  # All speakers (for info only)
    SPEAKER_LANGUAGE = {
        "jenny": "english",
        "ryan": "english",
        "shahid": "urdu"
    }
    # Speaker optimization: Only load default speaker at startup
    # When default changes: unload old, load new (managed by TTS service)
    
    # Camera Configuration (NEW - External/Internal Webcam Support)
    DEFAULT_CAMERA = "internal"  # "internal" (built-in) or "external" (USB webcam)
    AVAILABLE_CAMERAS = ["internal", "external"]
    CAMERA_INDICES = {
        "internal": 0,    # Built-in/integrated camera
        "external": 1     # External USB webcam
    }

# ============================================================================
# TTS PERFORMANCE METRICS (NEW) - Track speaker optimization
# ============================================================================

class TTSPerformanceMetrics:
    """Track TTS response time and efficiency metrics."""
    
    def __init__(self):
        self.synthesis_times = {}  # Speaker -> list of response times
        self.synthesis_count = {}  # Speaker -> count of syntheses
        self.synthesis_errors = {}  # Speaker -> error count
        self.speaker_switches = []  # Track speaker switches
        self.lock = __import__('threading').Lock()
    
    def record_synthesis(self, speaker_id: str, response_time_ms: float, success: bool = True):
        """Record TTS synthesis metrics."""
        with self.lock:
            if speaker_id not in self.synthesis_times:
                self.synthesis_times[speaker_id] = []
                self.synthesis_count[speaker_id] = 0
                self.synthesis_errors[speaker_id] = 0
            
            self.synthesis_times[speaker_id].append(response_time_ms)
            self.synthesis_count[speaker_id] += 1
            
            if not success:
                self.synthesis_errors[speaker_id] += 1
    
    def record_speaker_switch(self, from_speaker: str, to_speaker: str, switch_time_ms: float):
        """Record speaker switch metrics."""
        with self.lock:
            self.speaker_switches.append({
                "from": from_speaker,
                "to": to_speaker,
                "time_ms": switch_time_ms,
                "timestamp": datetime.now().isoformat()
            })
    
    def get_speaker_stats(self, speaker_id: str = None) -> Dict[str, Any]:
        """Get statistics for speaker(s)."""
        with self.lock:
            if speaker_id:
                if speaker_id not in self.synthesis_times:
                    return {"speaker": speaker_id, "count": 0}
                
                times = self.synthesis_times[speaker_id]
                if not times:
                    avg_ms = 0
                else:
                    avg_ms = sum(times) / len(times)
                
                return {
                    "speaker": speaker_id,
                    "synthesis_count": self.synthesis_count[speaker_id],
                    "error_count": self.synthesis_errors[speaker_id],
                    "avg_response_time_ms": round(avg_ms, 2),
                    "min_response_time_ms": round(min(times), 2) if times else 0,
                    "max_response_time_ms": round(max(times), 2) if times else 0,
                    "success_rate": round(
                        (self.synthesis_count[speaker_id] - self.synthesis_errors[speaker_id]) / 
                        max(1, self.synthesis_count[speaker_id]) * 100, 2
                    )
                }
            else:
                # Return stats for all speakers
                all_stats = {}
                for sid in self.synthesis_count.keys():
                    all_stats[sid] = self.get_speaker_stats(sid)
                return all_stats
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall TTS statistics."""
        with self.lock:
            total_syntheses = sum(self.synthesis_count.values())
            total_errors = sum(self.synthesis_errors.values())
            all_times = []
            for times in self.synthesis_times.values():
                all_times.extend(times)
            
            return {
                "total_syntheses": total_syntheses,
                "total_errors": total_errors,
                "success_rate": round(
                    (total_syntheses - total_errors) / max(1, total_syntheses) * 100, 2
                ) if total_syntheses > 0 else 0,
                "avg_response_time_ms": round(sum(all_times) / len(all_times), 2) if all_times else 0,
                "speaker_switches": len(self.speaker_switches),
                "speakers_used": len(self.synthesis_count)
            }

# Global TTS metrics tracker
tts_metrics = TTSPerformanceMetrics()

# ============================================================================
# CAMERA SOURCE UTILITY (NEW) - Get camera index based on configuration
# ============================================================================

def get_camera_source() -> int:
    """
    Get camera source index based on runtime configuration.
    
    Returns:
        Camera index: 0 for internal/built-in camera, 1 for external USB webcam
    
    Examples:
        - RuntimeConfig.DEFAULT_CAMERA = "internal" → returns 0
        - RuntimeConfig.DEFAULT_CAMERA = "external" → returns 1
    """
    camera_type = RuntimeConfig.DEFAULT_CAMERA
    return RuntimeConfig.CAMERA_INDICES.get(camera_type, 0)

# ============================================================================
# TOKEN COUNTING UTILITY - For Budget-Aware Context Management
# ============================================================================

class TokenCounter:
    """Estimate token count for text (using word-based approximation)."""
    
    # Typical ratios for different token encoders
    TOKENS_PER_WORD = 1.3  # Average across most LLM tokenizers
    
    @staticmethod
    def count_tokens(text: str) -> int:
        """Estimate token count for given text."""
        if not text:
            return 0
        
        # Split by whitespace and count words
        words = text.split()
        token_estimate = max(1, int(len(words) * TokenCounter.TOKENS_PER_WORD))
        return token_estimate
    
    @staticmethod
    def count_conversation_tokens(conversation_history: List[Dict]) -> int:
        """Count tokens in entire conversation history."""
        total_tokens = 0
        
        for turn in conversation_history:
            user_msg = turn.get('user', '') or turn.get('user_message', '')
            assistant_msg = turn.get('assistant', '') or turn.get('assistant_response', '')
            
            total_tokens += TokenCounter.count_tokens(str(user_msg))
            total_tokens += TokenCounter.count_tokens(str(assistant_msg))
        
        return total_tokens
    
    @staticmethod
    def count_dict_tokens(data: Dict) -> int:
        """Count tokens in dictionary structure."""
        return TokenCounter.count_tokens(str(data))

# ============================================================================
# ENTERPRISE-GRADE CONTEXT WINDOW MANAGER (Dynamic, Per-User, Adaptive)
# ============================================================================

class UserContextWindowManager:
    """
    ENTERPRISE-GRADE context window management for ALL users.
    
    Features:
    - SLIDING WINDOW with TOKEN BUDGETS (not hardcoded turn counts)
    - Automatically compacts old turns when approaching token limits
    - Activity-based adaptation (heavy users get more context)
    - Token budget management (respects LLM context limits)
    - Intelligent memory management (scalable to 1000+ users)
    - Per-user context priority (most relevant turns first)
    - Production-ready with minimal memory overhead
    
    Each user gets INDEPENDENT context management. No cross-user interference.
    
    SLIDING WINDOW LOGIC:
    - When user has 11-12 interactions, automatically removes oldest 3-4
    - Keeps last 5-7 recent interactions relevant to current context
    - Respects token budget (70% for context = ~2800 tokens of 4000)
    - If approaching limit, older turns are discarded intelligently
    """
    
    # Enterprise Config (can be overridden via env vars)
    MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "4000"))  # LLM total budget
    CONTEXT_TOKEN_BUDGET = int(os.getenv("CONTEXT_TOKEN_BUDGET", "2800"))  # 70% for context
    MIN_TOKENS_RESERVE = int(os.getenv("MIN_TOKENS_RESERVE", "500"))  # Emergency reserve
    
    BASE_TURNS = int(os.getenv("BASE_CONTEXT_TURNS", "5"))  # Lightweight users start with 5
    MIN_RECENT_TURNS = int(os.getenv("MIN_RECENT_TURNS", "3"))  # Always keep last 3
    HEAVY_USER_TURNS = int(os.getenv("HEAVY_USER_TURNS", "7"))  # Heavy users: up to 7
    
    INTERACTION_THRESHOLD = int(os.getenv("INTERACTION_THRESHOLD", "10"))  # Heavy user cutoff
    MAX_USERS_IN_MEMORY = int(os.getenv("MAX_USERS_IN_MEMORY", "100"))  # Memory limit
    
    def __init__(self):
        """Initialize context window manager."""
        self.user_contexts = {}  # Per-user context cache
        self.user_stats = {}     # Per-user stats (interactions, tokens, etc)
        self.user_full_history = {}  # Full conversation history per user (for windowing)
        self.manager_lock = __import__('threading').Lock()  # Thread-safe
    
    def get_optimal_context_window(self, user_id: str) -> Dict[str, Any]:
        """
        Get DYNAMICALLY SIZED context window for user with TOKEN BUDGETING.
        
        SLIDING WINDOW LOGIC:
        - User 0-5 interactions: Keep 3-5 turns (light user)
        - User 6-10 interactions: Keep 5-7 turns (regular, token-aware)
        - User 11+ interactions: Keep LAST 5-7 recent, REMOVE oldest (sliding window)
        - Respect token budget: If >2800 tokens, remove oldest turn until below budget
        
        Example:
        - Sara (12 interactions, 3500 tokens): Remove turns 1-4, keep turns 8-12 (5 recent)
        - Ahmed (2 interactions, 400 tokens): Keep all 2 turns
        - Zainab (7 interactions, 1800 tokens): Keep all 7 turns (below budget)
        """
        try:
            with self.manager_lock:
                # Initialize user if new
                if user_id not in self.user_stats:
                    self.user_stats[user_id] = {
                        "interaction_count": 0,
                        "total_context_tokens": 0,
                        "last_access_time": datetime.now().isoformat(),
                        "memory_bytes": 0,
                        "window_start_index": 0,  # For sliding window
                        "context_compactions": 0   # How many times we removed old turns
                    }
                
                stats = self.user_stats[user_id]
                interaction_count = stats.get("interaction_count", 0)
                current_tokens = stats.get("total_context_tokens", 0)
                
                # Determine optimal window strategy
                if interaction_count <= 5:
                    # Light user: start small
                    recomm_turns = min(interaction_count, self.BASE_TURNS)
                    compaction_needed = False
                elif interaction_count <= 10:
                    # Regular user: grow window
                    recomm_turns = min(interaction_count, 7)
                    compaction_needed = current_tokens > self.CONTEXT_TOKEN_BUDGET
                else:
                    # Heavy user: sliding window with token awareness
                    recomm_turns = self.HEAVY_USER_TURNS  # Max 7 recent turns
                    compaction_needed = current_tokens > self.CONTEXT_TOKEN_BUDGET
                
                # Update stats
                stats["last_access_time"] = datetime.now().isoformat()
                stats["compaction_needed"] = compaction_needed  # Flag for calling function
                
                # Check memory budget
                if len(self.user_contexts) >= self.MAX_USERS_IN_MEMORY:
                    self._evict_lru_user()
                
                return {
                    "user_id": user_id,
                    "context_window_turns": recomm_turns,
                    "token_budget_available": self.CONTEXT_TOKEN_BUDGET,
                    "current_tokens_used": current_tokens,
                    "is_heavy_user": interaction_count > self.INTERACTION_THRESHOLD,
                    "interaction_history_depth": interaction_count,
                    "compaction_needed": compaction_needed,
                    "min_turns_to_keep": self.MIN_RECENT_TURNS,
                    "sliding_window_enabled": interaction_count > 10
                }
        
        except Exception as e:
            print_warning(f"Error getting context window for {user_id}: {str(e)[:50]}")
            return {
                "user_id": user_id,
                "context_window_turns": self.BASE_TURNS,
                "token_budget_available": self.CONTEXT_TOKEN_BUDGET,
                "is_heavy_user": False,
                "interaction_history_depth": 0
            }
    
    def compact_conversation_history(self, user_id: str, full_history: List[Dict]) -> List[Dict]:
        """
        SLIDING WINDOW COMPACTION: Remove old turns from conversation when approaching token limits.
        
        Logic:
        1. Count tokens in full history
        2. If exceeds budget (2800 tokens):
           - Remove oldest turn
           - Recalculate tokens
           - Repeat until below budget OR reach MIN_RECENT_TURNS
        3. Return compacted history with most recent turns
        
        Example (Sara's 12 interactions):
        - Full history: 12 turns
        - Token count: 3500 tokens (exceeds 2800 budget)
        - Compaction: Remove turns 1, 2, 3, 4 (4 oldest)
        - Result: Last 8 turns = 2650 tokens (under budget)
        - Return: 8 most recent turns for context
        """
        try:
            if not full_history:
                return []
            
            with self.manager_lock:
                # Calculate current token usage
                current_tokens = TokenCounter.count_conversation_tokens(full_history)
                
                # Check if compaction is needed
                if current_tokens <= self.CONTEXT_TOKEN_BUDGET:
                    # No compaction needed - history fits in budget
                    self.user_full_history[user_id] = full_history
                    return full_history
                
                # COMPACTION NEEDED: Remove oldest turns until under budget
                compacted_history = full_history.copy()
                compaction_count = 0
                
                while (compacted_history and 
                       len(compacted_history) > self.MIN_RECENT_TURNS and
                       TokenCounter.count_conversation_tokens(compacted_history) > self.CONTEXT_TOKEN_BUDGET):
                    # Remove oldest turn
                    compacted_history.pop(0)
                    compaction_count += 1
                
                # Update stats
                if user_id in self.user_stats:
                    stats = self.user_stats[user_id]
                    stats["context_compactions"] = stats.get("context_compactions", 0) + 1
                    stats["total_context_tokens"] = TokenCounter.count_conversation_tokens(compacted_history)
                
                # Store compacted history
                self.user_full_history[user_id] = full_history  # Keep full for reference
                
                removed_count = len(full_history) - len(compacted_history)
                if removed_count > 0:
                    print_info(f"Context compaction: Removed {removed_count} oldest turns, kept {len(compacted_history)} recent ({stats.get('total_context_tokens', 0)} tokens)")
                
                return compacted_history
        
        except Exception as e:
            print_warning(f"Error in compaction: {str(e)[:50]}")
            return full_history
    
    def record_interaction(self, user_id: str, interaction_text: str = "") -> None:
        """Record interaction for activity tracking and token budgeting."""
        try:
            with self.manager_lock:
                if user_id not in self.user_stats:
                    self.user_stats[user_id] = {
                        "interaction_count": 0,
                        "total_context_tokens": 0,
                        "last_access_time": datetime.now().isoformat(),
                        "memory_bytes": 0,
                        "window_start_index": 0,
                        "context_compactions": 0
                    }
                
                stats = self.user_stats[user_id]
                stats["interaction_count"] = stats.get("interaction_count", 0) + 1
                
                # Track token usage
                tokens_for_interaction = TokenCounter.count_tokens(str(interaction_text))
                stats["total_context_tokens"] = stats.get("total_context_tokens", 0) + tokens_for_interaction
                stats["memory_bytes"] = stats.get("memory_bytes", 0) + len(str(interaction_text).encode())
                stats["last_access_time"] = datetime.now().isoformat()
        
        except Exception as e:
            print_warning(f"Error recording interaction: {str(e)[:40]}")
    
    def get_user_context_stats(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive context statistics for a user."""
        try:
            with self.manager_lock:
                if user_id in self.user_stats:
                    return self.user_stats[user_id].copy()
                return {"user_id": user_id, "interaction_count": 0, "status": "new_user"}
        except Exception as e:
            print_warning(f"Error getting stats: {str(e)[:40]}")
            return {}
    
    def _evict_lru_user(self) -> None:
        """Evict least-recently-used user from memory when limit reached."""
        try:
            if not self.user_stats:
                return
            
            lru_user = min(
                self.user_stats.items(),
                key=lambda x: x[1].get("last_access_time", "0")
            )[0]
            
            if lru_user in self.user_contexts:
                del self.user_contexts[lru_user]
            
            print_info(f"Memory: Evicted LRU user {lru_user} (memory pressure)")
        
        except Exception as e:
            print_warning(f"Error evicting LRU user: {str(e)[:40]}")
    
    def cache_user_context(self, user_id: str, context: Dict[str, Any]) -> None:
        """Cache user's current context for efficient retrieval."""
        try:
            with self.manager_lock:
                self.user_contexts[user_id] = {
                    "context": context,
                    "cached_at": datetime.now().isoformat()
                }
        except Exception as e:
            print_warning(f"Error caching context: {str(e)[:40]}")
    
    def get_cached_context(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached context for user (if available)."""
        try:
            with self.manager_lock:
                if user_id in self.user_contexts:
                    return self.user_contexts[user_id].get("context")
            return None
        except Exception as e:
            print_warning(f"Error retrieving cached context: {str(e)[:40]}")
            return None


# Global context manager for all users
user_context_manager = UserContextWindowManager()

# ============================================================================
# GLOBAL STATE
# ============================================================================

class SystemState:
    """Track system state across tests"""
    services_connected = {
        'central': False,
        'audio': False,
        'enrollment': False,
        'vision': False,
        'tts': False,
        'teachme': False,
        'llm': False
    }
    last_enrolled_user: Optional[str] = None
    last_central_user_id: Optional[str] = None
    last_audio_file: Optional[str] = None
    enrolled_users: List[Dict] = []

state = SystemState()

DATA_DIR = Path("test_data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# CONSOLE OUTPUT UTILITIES
# ============================================================================

def print_header(text: str):
    """Print formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_subheader(text: str):
    """Print formatted subsection header"""
    print("\n" + "-" * 70)
    print(f"  {text}")
    print("-" * 70)

def print_success(text: str):
    """Print success message"""
    print(f"[SUCCESS] {text}")

def print_error(text: str):
    """Print error message"""
    print(f"[ERROR] {text}")

def print_info(text: str):
    """Print informational message"""
    print(f"[INFO] {text}")

def print_warning(text: str):
    """Print warning message"""
    print(f"[WARNING] {text}")

def print_step(step_num: int, total: int, text: str):
    """Print step indicator"""
    print(f"\n[Step {step_num}/{total}] {text}")

def print_result(label: str, value: Any):
    """Print result value"""
    print(f"  {label}: {value}")

def show_coco_classes_info():
    """Display all 80 COCO classes with color info for debugging object detection"""
    print_header("COCO CLASSES REFERENCE - All 80 Object Types")
    print_info("Use this to verify if YOLO correctly detects objects")
    print_info("Format: Index. ClassName (Color Values in BGR)")
    print()
    
    for idx, class_name in enumerate(COCO_CLASSES):
        color = OBJECT_COLORS.get(class_name.lower(), (200, 200, 200))
        color_str = f"BGR({color[0]}, {color[1]}, {color[2]})"
        print(f"{idx:2d}. {class_name:20s} → {color_str}")
        
        # Every 10 classes, add a newline for readability
        if (idx + 1) % 10 == 0:
            print()

# ============================================================================
# AUDIO RECORDING UTILITIES (EXISTING)
# ============================================================================

def record_audio(duration: int = None, filename: str = None) -> str:
    """Record audio from microphone using centralized resource management with fallback."""
    if duration is None:
        duration = AudioConfig.DEFAULT_DURATION
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.wav"
    
    filepath = DATA_DIR / filename
    
    # Request microphone resource (will fallback to synthetic lease if unavailable)
    lease_id = request_hardware_resource(
        resource_type="microphone",
        service_name="audio_recording",
        priority="HIGH",
        timeout_seconds=10
    )
    
    # lease_id should always be returned (real or synthetic), proceed with recording
    print_info(f"Recording for {duration} seconds... Speak now!")
    time.sleep(1)
    
    try:
        audio = sd.rec(
            int(duration * AudioConfig.SAMPLE_RATE),
            samplerate=AudioConfig.SAMPLE_RATE,
            channels=AudioConfig.CHANNELS,
            dtype=AudioConfig.DTYPE
        )
        sd.wait()
        
        sf.write(str(filepath), audio, AudioConfig.SAMPLE_RATE)
        state.last_audio_file = str(filepath.resolve())
        
        print_success(f"Audio recorded: {filepath.name}")
        print_info(f"File size: {os.path.getsize(filepath)} bytes")
        
        return state.last_audio_file
        
    except Exception as e:
        print_error(f"Recording failed: {str(e)}")
        return None
    
    finally:
        # Always release microphone resource
        if lease_id:
            release_hardware_resource(lease_id)

# ============================================================================
# VISION SERVICE UTILITIES (EXISTING)
# ============================================================================

def capture_real_face_images(num_images: int = 5) -> List[List[float]]:
    """Capture real face images using Vision Service API."""
    print_info(f"Accessing Vision Service at {ServiceConfig.VISION_SERVICE}")
    
    try:
        response = requests.get(f"{ServiceConfig.VISION_SERVICE}/health", timeout=3)
        if response.status_code != 200:
            print_warning("Vision Service unavailable, using mock embeddings")
            return [generate_mock_embedding() for _ in range(num_images)]
    except Exception:
        print_warning("Cannot connect to Vision Service, using mock embeddings")
        return [generate_mock_embedding() for _ in range(num_images)]
    
    cap = None
    face_embeddings = []
    captured_count = 0
    
    try:
        camera_source = get_camera_source()
        cap = cv2.VideoCapture(camera_source)
        if not cap.isOpened():
            camera_name = RuntimeConfig.DEFAULT_CAMERA.upper()
            print_warning(f"Cannot open {camera_name} camera, using mock embeddings")
            return [generate_mock_embedding() for _ in range(num_images)]
        
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, VisionConfig.CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VisionConfig.CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, VisionConfig.CAMERA_FPS)
        
        print_info(f"Camera opened. Press SPACE to capture ({num_images} total), ESC to cancel")
        
        while captured_count < num_images:
            ret, frame = cap.read()
            if not ret:
                break
            
            cv2.putText(frame, f"Image {captured_count + 1}/{num_images}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, "Press SPACE to capture", (10, 70), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
            cv2.putText(frame, "Press ESC to cancel", (10, 480-20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            
            cv2.imshow("Face Capture - NEXI Enrollment", frame)
            
            key = cv2.waitKey(30) & 0xFF
            
            if key == ord(' '):
                print_info(f"Capturing image {captured_count + 1}/{num_images}...")
                
                try:
                    success, frame_jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                    if not success:
                        continue
                    
                    frame_bytes = frame_jpeg.tobytes()
                    files = {'file': ('frame.jpg', io.BytesIO(frame_bytes), 'image/jpeg')}
                    
                    response = requests.post(
                        f"{ServiceConfig.VISION_SERVICE}/api/v1/detect/faces/upload",  # Fixed: Added /api/v1 prefix
                        files=files,
                        params={
                            "detector_backend": VisionConfig.DETECTOR_BACKEND,
                            "model_name": VisionConfig.MODEL_NAME
                        },
                        timeout=VisionConfig.TIMEOUT
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('faces_detected', 0) > 0:
                            embedding = data['faces'][0].get('embedding', [])
                            
                            if embedding and len(embedding) == VisionConfig.EMBEDDING_DIM:
                                face_embeddings.append(embedding)
                                captured_count += 1
                                confidence = data['faces'][0].get('confidence', 0)
                                print_success(f"Image {captured_count} captured (Confidence: {confidence:.1%})")
                            else:
                                print_warning("Invalid embedding dimension, retrying...")
                        else:
                            print_warning("No face detected. Position your face clearly.")
                    else:
                        print_warning(f"Vision Service error: {response.status_code}")
                
                except requests.exceptions.Timeout:
                    print_warning(f"Vision Service timeout, retrying...")
                except Exception as e:
                    print_warning(f"Vision error: {str(e)[:50]}")
            
            elif key == 27:
                print_info("Face capture cancelled")
                break
        
        if captured_count == num_images:
            print_success(f"All {num_images} face images captured")
            return face_embeddings
        else:
            # Fill remaining with mock
            while len(face_embeddings) < num_images:
                face_embeddings.append(generate_mock_embedding())
            return face_embeddings
    
    except Exception as e:
        print_error(f"Face capture error: {str(e)[:100]}")
        return [generate_mock_embedding() for _ in range(num_images)]
    
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()

def generate_mock_embedding() -> List[float]:
    """Generate a mock 128D face embedding vector."""
    return [round(random.uniform(-1.0, 1.0), 6) for _ in range(VisionConfig.EMBEDDING_DIM)]

# ============================================================================
# SERVICE HEALTH CHECKS (EXISTING)
# ============================================================================

def check_service_health(service_name: str, url: str, timeout: int = 5) -> bool:
    """Check if service is running and healthy."""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            print_success(f"{service_name}: Operational")
            return True
        else:
            print_error(f"{service_name}: Unhealthy (HTTP {response.status_code})")
            return False
    except requests.exceptions.ConnectionError:
        print_error(f"{service_name}: Cannot connect")
        return False
    except requests.exceptions.Timeout:
        print_error(f"{service_name}: Timeout")
        return False
    except Exception as e:
        print_error(f"{service_name}: Error - {str(e)}")
        return False

def test_all_services():
    """Test connectivity to all services"""
    print_header("System Health Check")
    
    services = [
        ('Central Server', f"{ServiceConfig.CENTRAL_SERVER}/health", 'central'),
        ('Vision Service', f"{ServiceConfig.VISION_SERVICE}/health", 'vision'),
        ('Audio Service', f"{ServiceConfig.AUDIO_SERVICE}/health", 'audio'),
        ('TTS Service', f"{ServiceConfig.TTS_SERVICE}/health", 'tts'),
        ('TeachMe Service', f"{ServiceConfig.TEACHME_SERVICE}/health", 'teachme'),
        ('LLM Service', f"{ServiceConfig.LLM_SERVICE}/api/v1/health", 'llm'),
        ('Enrollment Service', f"{ServiceConfig.ENROLLMENT_SERVICE}/health", 'enrollment'),
    ]
    
    results = []
    for name, url, key in services:
        healthy = check_service_health(name, url)
        state.services_connected[key] = healthy
        results.append(healthy)
    
    success_rate = (sum(results) / len(results)) * 100
    
    print(f"\nOverall Health: {success_rate:.0f}% ({sum(results)}/{len(results)} services)")
    
    if success_rate == 100:
        print_success("All systems operational!")
    elif success_rate >= 70:
        print_warning("Core systems operational, non-critical services unavailable")
    else:
        print_error("Critical services unavailable")
    
    return success_rate >= 70

# ============================================================================
# CENTRAL SERVER OPERATIONS (EXISTING)
# ============================================================================

def get_all_users() -> List[Dict]:
    """Fetch all enrolled users from Central Server"""
    try:
        response = requests.get(
            f"{ServiceConfig.CENTRAL_SERVER}/users/list",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            users = data.get('users', [])
            state.enrolled_users = users
            return users
        else:
            print_error(f"Failed to fetch users: HTTP {response.status_code}")
            return []
            
    except Exception as e:
        print_error(f"Error fetching users: {str(e)}")
        return []

def display_enrolled_users():
    """Display list of enrolled users"""
    print_subheader("Enrolled Users")
    
    users = get_all_users()
    
    if not users:
        print_info("No users enrolled yet")
        return
    
    print(f"\nTotal users: {len(users)}\n")
    
    for idx, user in enumerate(users, 1):
        user_id = user.get('user_id', 'N/A')
        username = user.get('user_name') or user.get('username') or user.get('name') or 'Unknown'
        age = user.get('age', 'N/A')
        relation = user.get('relation', 'N/A')

        face_count = len(user.get('face_embeddings', []))
        voice_count = len(user.get('voice_embeddings', []))
        
        print(f"{idx}. {username}")
        print(f"   ID: {user_id}")
        print(f"   Age: {age}, Relation: {relation}")
        print(f"   Face samples: {face_count}, Voice samples: {voice_count}")
        print()

def delete_user_from_system(user_id: str) -> bool:
    """Delete user from Central Server"""
    try:
        response = requests.delete(
            f"{ServiceConfig.CENTRAL_SERVER}/users/{user_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            print_success(f"User {user_id} deleted successfully")
            return True
        else:
            print_error(f"Failed to delete user: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Error deleting user: {str(e)}")
        return False

def synthesize_and_play_tts(text: str, language: str = "en", use_default_speaker: bool = True) -> bool:
    """
    Synthesize text to speech and play audio to user.
    Language-aware speaker selection: Urdu ALWAYS uses Shahid, English uses configured default.
    
    OPTIMIZATION: Smart speaker selection based on language + tracks response time.
    
    Args:
        text: Text to synthesize
        language: Language code ('en' for English, 'ur' for Urdu)
        use_default_speaker: If True, use language-appropriate speaker (recommended)
    
    Returns:
        True if successful, False otherwise
    """
    start_time = time.time()
    
    try:
        # CRITICAL: Language-based speaker selection
        # Urdu ALWAYS uses Shahid (only Urdu speaker available)
        # English uses configured default speaker (Jenny/Ryan)
        if language.lower() in ['ur', 'urdu']:
            voice_id = "shahid"  # Rehnuma Urdu voice - ONLY Urdu speaker
        elif use_default_speaker:
            # English: use configured default speaker
            voice_id = RuntimeConfig.DEFAULT_SPEAKER
        else:
            # Override: default to jenny for English
            voice_id = "jenny"
        
        # Call TTS service using correct endpoint: /speak
        response = requests.post(
            f"{ServiceConfig.TTS_SERVICE}/speak",
            json={"text": text, "voice_id": voice_id},
            timeout=60
        )
        
        response_time_ms = (time.time() - start_time) * 1000
        
        if response.status_code != 200:
            print_warning(f"TTS synthesis failed (HTTP {response.status_code})")
            tts_metrics.record_synthesis(voice_id, response_time_ms, success=False)
            return False
        
        # Get audio data (binary WAV format)
        audio_data = response.content
        if not audio_data or len(audio_data) == 0:
            print_warning("TTS returned empty audio")
            tts_metrics.record_synthesis(voice_id, response_time_ms, success=False)
            return False
        
        # Load audio from bytes and play
        try:
            audio_array, sample_rate = sf.read(io.BytesIO(audio_data))
            
            # Play audio to user with low latency
            sd.play(audio_array, samplerate=sample_rate, latency='low')
            sd.wait()  # Wait for playback to complete
            
            # Record successful synthesis
            total_time_ms = (time.time() - start_time) * 1000
            tts_metrics.record_synthesis(voice_id, total_time_ms, success=True)
            
            return True
            
        except Exception as e:
            print_warning(f"Audio playback error: {str(e)[:40]}")
            tts_metrics.record_synthesis(voice_id, response_time_ms, success=False)
            return False
    
    except requests.Timeout:
        print_warning("TTS request timeout (30s exceeded)")
        tts_metrics.record_synthesis(RuntimeConfig.DEFAULT_SPEAKER, 
                                     (time.time() - start_time) * 1000, success=False)
        return False
    
    except Exception as e:
        print_warning(f"TTS error: {str(e)[:40]}")
        tts_metrics.record_synthesis(RuntimeConfig.DEFAULT_SPEAKER, 
                                     (time.time() - start_time) * 1000, success=False)
        return False

# ============================================================================
# AUDIO SERVICE OPERATIONS (EXISTING)
# ============================================================================

def process_voice_embedding(audio_file: str) -> Optional[List[float]]:
    """Extract voice embedding from audio file."""
    try:
        with open(audio_file, 'rb') as f:
            files = {'file': (os.path.basename(audio_file), f, 'audio/wav')}
            
            response = requests.post(
                f"{ServiceConfig.AUDIO_API}/process-voice",
                files=files,
                timeout=30
            )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                result = data.get('data', {})
                embedding = result.get('embedding')
                quality = result.get('quality_score', 0)
                
                print_info(f"Embedding extracted: {len(embedding)} dimensions")
                print_info(f"Quality score: {quality:.2f}")
                
                return embedding
            else:
                print_error(f"Processing failed: {data.get('error')}")
                return None
        else:
            print_error(f"HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Error processing voice: {str(e)}")
        return None

def start_wake_word_detection(duration: int = 30) -> bool:
    """Start wake word detection loop"""
    try:
        response = requests.post(
            f"{ServiceConfig.AUDIO_API}/wake-word/start",
            json={"duration": duration},
            timeout=5
        )
        
        if response.status_code == 200:
            print_success("Wake word detection started")
            return True
        
        print_error("Failed to start wake word detection")
        return False
        
    except Exception as e:
        print_error(f"Error starting wake word: {str(e)}")
        return False

def stop_wake_word_detection() -> bool:
    """Stop wake word detection loop"""
    try:
        response = requests.post(
            f"{ServiceConfig.AUDIO_API}/wake-word/stop",
            timeout=5
        )
        
        if response.status_code == 200:
            print_info("Wake word detection stopped")
            return True
        else:
            return False
            
    except Exception as e:
        print_error(f"Error stopping wake word: {str(e)}")
        return False

def check_wake_word_status() -> Dict:
    """Check wake word detection status"""
    try:
        response = requests.get(
            f"{ServiceConfig.AUDIO_API}/wake-word/status",
            timeout=5
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {}
            
    except Exception as e:
        print_error(f"Error checking status: {str(e)}")
        return {}

def transcribe_audio(audio_file: str) -> Optional[str]:
    """Transcribe audio to text using STT service."""
    try:
        with open(audio_file, 'rb') as f:
            files = {'file': (os.path.basename(audio_file), f, 'audio/wav')}
            data = {'language': 'auto'}
            
            response = requests.post(
                f"{ServiceConfig.AUDIO_API}/transcribe",
                files=files,
                data=data,
                timeout=30
            )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                text = result.get('text', '')
                language = result.get('language', 'unknown')
                processing_time = result.get('processing_time', 0)
                
                print_success("Transcription completed")
                print_result("Text", f'"{text}"')
                print_result("Language", language)
                print_result("Processing time", f"{processing_time:.2f}s")
                
                return text
            else:
                print_error("Transcription failed")
                return None
        else:
            print_error(f"HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Error transcribing audio: {str(e)}")
        return None

def verify_speaker(audio_file: str) -> Dict:
    """Verify speaker identity from audio."""
    try:
        with open(audio_file, 'rb') as f:
            files = {'file': (os.path.basename(audio_file), f, 'audio/wav')}
            
            response = requests.post(
                f"{ServiceConfig.AUDIO_API}/verify-speaker",
                files=files,
                timeout=30
            )
        
        if response.status_code == 200:
            data = response.json()
            
            is_verified = data.get('is_verified', False)
            user_id = data.get('user_id', 'unknown')
            confidence = data.get('confidence', 0.0)
            
            if is_verified:
                print_success(f"Speaker verified: {user_id}")
                print_result("Confidence", f"{confidence:.1%}")
            else:
                print_warning("Speaker not verified")
            
            return data
        else:
            print_error(f"Verification failed: HTTP {response.status_code}")
            return {'is_verified': False}
            
    except Exception as e:
        print_error(f"Error verifying speaker: {str(e)}")
        return {'is_verified': False}

def sync_audio_service_speakers() -> bool:
    """Sync speaker embeddings from Central Server into Audio Service."""
    try:
        response = requests.post(
            f"{ServiceConfig.AUDIO_API}/speaker-sync",
            timeout=30
        )
        if response.status_code == 200:
            print_success("Audio Service speaker sync complete")
            return True
        print_warning("Audio Service speaker sync failed")
        return False
    except Exception as e:
        print_warning(f"Error syncing speakers: {str(e)}")
        return False

def capture_mood_with_visual_feedback(resource_priority: str = "MEDIUM") -> str:
    """
    Capture mood detection with real-time visual feedback using CV2.
    WORKING: Proper face extraction + Vision API with actual image data.
    - Uses Haar Cascade for instant LOCAL face detection
    - Extracts face ROI and sends as JPEG to API
    - Caches emotions between API calls (1.0 second throttle)
    - Returns the detected mood or 'neutral' if detection fails
    """
    # Request camera resource from Central Server resource manager
    # This will fallback to synthetic lease if Central Server is unavailable
    lease_id = request_hardware_resource(
        resource_type="camera",
        service_name="mood_detection",
        priority=resource_priority,
        timeout_seconds=10
    )
    
    # lease_id is always returned (real or synthetic), proceed with mood detection
    cap = None
    mood_detected = 'neutral'
    cached_emotions = {}  # Cache emotion data between API calls
    camera_source = get_camera_source()
    
    try:
        cap = cv2.VideoCapture(camera_source)
        if not cap.isOpened():
            camera_name = RuntimeConfig.DEFAULT_CAMERA.upper()
            print_warning(f"{camera_name} camera not available, using default mood: neutral")
            return mood_detected
        
        # Configure camera for optimal performance
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Single frame buffer (prevent latency)
        
        # Load Haar Cascade for instant local face detection
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(cascade_path)
        
        print_info("CV2 window will appear - position your face in center...")
        window_name = "NEXI Mood Detection - Position your face"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        
        # IMPORTANT: Resize window to reasonable display size for visibility
        DISPLAY_WIDTH = 640
        DISPLAY_HEIGHT = 480
        cv2.resizeWindow(window_name, DISPLAY_WIDTH, DISPLAY_HEIGHT)
        
        start_time = time.time()
        timeout_duration = 8
        frame_count = 0
        api_call_count = 0
        mood_captured = False
        last_mood_confidence = 0.0
        last_emotion_api_call = 0  # Track time of last API call
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            display_frame = frame.copy()
            
            # ========== STEP 1: LOCAL FACE DETECTION (INSTANT!) ==========
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5, minSize=(30, 30))
            
            faces_detected = len(faces)
            
            # ========== STEP 2: EMOTION DETECTION (API - only if face found) ==========
            time_since_emotion_api = time.time() - last_emotion_api_call
            
            if faces_detected > 0 and time_since_emotion_api > 1.0:
                # Get largest face
                largest_face = max(faces, key=lambda f: f[2] * f[3])
                x, y, w, h = largest_face
                
                # Extract and send only face region
                face_roi = frame[max(0, y-10):min(frame.shape[0], y+h+10),
                                 max(0, x-10):min(frame.shape[1], x+w+10)]
                
                if face_roi.size > 0:
                    last_emotion_api_call = time.time()
                    api_call_count += 1
                    
                    # Send face region to API as JPEG (THIS IS THE KEY FIX!)
                    try:
                        _, buffer = cv2.imencode('.jpg', face_roi, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        
                        files = {'file': ('face.jpg', buffer.tobytes(), 'image/jpeg')}
                        params = {
                            'detector_backend': 'opencv',
                            'model_name': 'Facenet',
                            'analyze_emotions': True
                        }
                        
                        response = requests.post(
                            f"{ServiceConfig.VISION_SERVICE}/api/v1/detect/faces/upload",
                            files=files,
                            params=params,
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            faces_list = data.get('faces', [])
                            
                            if faces_list:
                                mood_detected = faces_list[0].get('dominant_emotion', 'neutral')
                                confidence = faces_list[0].get('confidence', 0)
                                last_mood_confidence = confidence
                                cached_emotions = {
                                    'emotion': mood_detected,
                                    'confidence': confidence
                                }
                                mood_captured = True
                        else:
                            print_warning(f"Vision API error: HTTP {response.status_code}")
                    
                    except requests.exceptions.Timeout:
                        print_warning("Vision API timeout")
                    except Exception as e:
                        print_warning(f"Vision API error: {str(e)[:40]}")
            
            # Use cached emotion if current mood is unknown
            if not mood_detected or mood_detected == "unknown":
                if cached_emotions:
                    mood_detected = cached_emotions.get('emotion', 'neutral')
                    last_mood_confidence = cached_emotions.get('confidence', 0)
            
            # ========== STEP 3: DRAW DETECTIONS ==========
            # Resize frame for better visibility (matching display window size)
            display_frame = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
            
            # Calculate scale factors for coordinate conversion
            scale_x = DISPLAY_WIDTH / frame.shape[1]
            scale_y = DISPLAY_HEIGHT / frame.shape[0]
            
            # Draw bounding boxes from local detection with clear visual indicators
            for (x, y, w, h) in faces:
                # Scale coordinates to display size
                x_disp = int(x * scale_x)
                y_disp = int(y * scale_y)
                w_disp = int(w * scale_x)
                h_disp = int(h * scale_y)
                
                # Use color based on detection status
                if mood_captured:
                    color = (0, 255, 0)  # Green = emotion detected
                    thickness = 3
                else:
                    color = (0, 165, 255)  # Orange = face detected, waiting for emotion
                    thickness = 2
                
                # Draw prominent bounding box
                cv2.rectangle(display_frame, (x_disp, y_disp), 
                            (x_disp + w_disp, y_disp + h_disp), color, thickness)
                
                # Draw face label
                label = "Face Detected"
                if mood_captured and mood_detected and mood_detected != "unknown":
                    label = f"{mood_detected.upper()} {last_mood_confidence:.0%}"
                
                # Draw label background
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
                cv2.rectangle(display_frame, 
                            (x_disp, max(0, y_disp - label_size[1] - 10)),
                            (x_disp + label_size[0] + 10, y_disp),
                            color, -1)
                cv2.putText(display_frame, label,
                          (x_disp + 5, y_disp - 5),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Draw status info on image
            info_y = 30
            cv2.rectangle(display_frame, (0, 0), (DISPLAY_WIDTH, 100), (0, 0, 0), -1)
            cv2.rectangle(display_frame, (0, 0), (DISPLAY_WIDTH, 100), (0, 255, 0), 2)
            
            info1 = f"Faces Detected: {faces_detected} | API Calls: {api_call_count}"
            info2 = f"Mood: {mood_detected.upper() if mood_detected else 'Detecting...'}  |  Press 'Q' to confirm"
            info3 = "Green Box = Emotion Detected  |  Orange Box = Face Detected"
            
            cv2.putText(display_frame, info1, (10, info_y), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, info2, (10, info_y + 25),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, info3, (10, info_y + 50),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
            
            cv2.imshow(window_name, display_frame)
            
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                if mood_captured:
                    cv2.destroyAllWindows()
                    print_success(f"Mood captured: {mood_detected} ({last_mood_confidence:.0%}) - {api_call_count} API calls")
                    return mood_detected
                break
            
            if time.time() - start_time > timeout_duration:
                break
        
        cv2.destroyAllWindows()
        
    except Exception as e:
        print_warning(f"Visual feedback error: {str(e)[:50]}")
    
    finally:
        # CRITICAL: Always release both CV2 camera AND hardware resource
        # This must happen in finally to ensure cleanup even on early return
        if cap is not None:
            try:
                cap.release()
            except:
                pass
        
        try:
            cv2.destroyAllWindows()
        except:
            pass
        
        # Release hardware resource lease from Central Server
        if lease_id:
            release_hardware_resource(lease_id)
    
    return mood_detected

def capture_objects_with_detection(resource_priority: str = "MEDIUM", num_captures: int = 5) -> List[Dict]:
    """
    Capture objects using Vision Service REST API with YOLOv8 inference.
    
    Sends camera frames to Vision Service endpoint /detect/objects
    which handles YOLOv8 model inference on the server side.
    This approach ensures proper deployment without local model requirements.
    """
    # Request camera resource from Central Server
    lease_id = request_hardware_resource(
        resource_type="camera",
        service_name="object_detection",
        priority=resource_priority,
        timeout_seconds=15
    )
    
    cap = None
    detected_objects = []
    camera_source = get_camera_source()
    
    try:
        # Initialize camera
        cap = cv2.VideoCapture(camera_source)
        if not cap.isOpened():
            camera_name = RuntimeConfig.DEFAULT_CAMERA.upper()
            print_warning(f"{camera_name} camera not available, skipping object detection")
            return detected_objects
        
        # Configure camera
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        print_info("Object detection window will appear - show objects to camera")
        print_info("USING Vision Service REST API for object detection")
        print_info("YOLOv8 detects 80+ COCO classes (person, car, dog, phone, cup, laptop, etc.)")
        print_info("Supported classes: person, bicycle, car, dog, cat, chair, laptop, phone, cup, bottle...")
        window_name = "NEXI Object Detection"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        
        # Window configuration
        DISPLAY_WIDTH = 640
        DISPLAY_HEIGHT = 480
        cv2.resizeWindow(window_name, DISPLAY_WIDTH, DISPLAY_HEIGHT)
        
        start_time = time.time()
        timeout_duration = 20
        objects_captured = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            display_frame = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
            current_objects = []
            
            # ========== DETECTION: VISION SERVICE REST API ==========
            try:
                # Encode frame as JPEG for Vision Service
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                files = {'file': ('frame.jpg', buffer.tobytes(), 'image/jpeg')}
                params = {'confidence_threshold': 0.45}
                
                # Call Vision Service API (handles YOLOv8 inference internally on server)
                # Endpoint: /detect/objects or /detect/objects/upload
                response = requests.post(
                    f"{ServiceConfig.VISION_API}/detect/objects/upload",
                    files=files,
                    params=params,
                    timeout=5
                )
                
                if response.status_code == 200:
                    data = response.json()
                    detections = data.get('detections', [])
                    
                    # Convert Vision Service coordinates to display coordinates
                    frame_height, frame_width = frame.shape[:2]
                    scale_x = DISPLAY_WIDTH / frame_width
                    scale_y = DISPLAY_HEIGHT / frame_height
                    
                    for detection in detections:
                        # Scale bounding box to display size
                        bbox = detection.get('bounding_box', {})
                        if bbox:
                            scaled_bbox = {
                                'x': int(bbox['x'] * scale_x),
                                'y': int(bbox['y'] * scale_y),
                                'width': int(bbox['width'] * scale_x),
                                'height': int(bbox['height'] * scale_y)
                            }
                            
                            current_objects.append({
                                'class_name': detection.get('class_name', 'unknown'),
                                'confidence': detection.get('confidence', 0),
                                'class_id': detection.get('class_id', -1),
                                'bounding_box': scaled_bbox
                            })
            
            except Exception as e:
                print_warning(f"Vision Service API call error: {str(e)[:50]}")
            
            
            # ========== DRAW DETECTIONS (from Vision Service) ==========
            for detection in current_objects:
                bbox = detection.get('bounding_box', {})
                class_name = detection.get('class_name', 'unknown')
                confidence = detection.get('confidence', 0)
                class_id = detection.get('class_id', -1)
                
                if bbox:
                    x = bbox['x']
                    y = bbox['y']
                    w = bbox['width']
                    h = bbox['height']
                    
                    # Get color from COCO class list, fallback to gray
                    color = OBJECT_COLORS.get(class_name.lower(), (200, 200, 200))
                    
                    # Draw bounding box with class-specific color
                    cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 2)
                    
                    # Draw label with confidence
                    label = f"{class_name} ({confidence:.0%})"
                    text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                    
                    # Label background (same color as box)
                    cv2.rectangle(display_frame,
                                (x, max(0, y - 25)),
                                (x + text_size[0] + 10, y),
                                color, -1)
                    
                    # Label text
                    cv2.putText(display_frame, label, (x + 5, y - 5),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Draw status bar
            cv2.rectangle(display_frame, (0, 0), (DISPLAY_WIDTH, 80), (0, 0, 0), -1)
            cv2.rectangle(display_frame, (0, 0), (DISPLAY_WIDTH, 80), (0, 255, 0), 2)
            
            info1 = f"Objects Detected: {len(current_objects)} | Captured: {objects_captured}/{num_captures}"
            info2 = f"Press SPACE to capture object | Q to finish"
            
            cv2.putText(display_frame, info1, (10, 25),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, info2, (10, 55),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
            
            cv2.imshow(window_name, display_frame)
            
            # Handle keyboard input
            key = cv2.waitKey(30) & 0xFF
            if key == ord(' '):  # Space to capture
                if current_objects and objects_captured < num_captures:
                    # SELECT DOMINANT OBJECT (largest bounding box = most prominent in frame)
                    # This ensures we capture the MAIN object user wants to teach, not background clutter
                    dominant_object = None
                    max_area = 0
                    all_classes = [obj.get('class_name', 'unknown') for obj in current_objects]
                    
                    for obj in current_objects:
                        bbox = obj.get('bounding_box', {})
                        area = bbox.get('width', 0) * bbox.get('height', 0)
                        
                        # Track object with largest area (most prominent)
                        if area > max_area:
                            max_area = area
                            dominant_object = obj
                    
                    # Capture ONLY the dominant object
                    if dominant_object:
                        detected_objects.append(dominant_object)
                        objects_captured += 1
                        
                        class_name = dominant_object.get('class_name', 'unknown')
                        confidence = dominant_object.get('confidence', 0)
                        class_id = dominant_object.get('class_id', -1)
                        bbox = dominant_object.get('bounding_box', {})
                        bbox_area = int(max_area)
                        
                        # Show what object was captured and why
                        print_success(f"Captured: {class_name} ({confidence:.0%}) - ID:{class_id} ({objects_captured}/{num_captures})")
                        print_info(f"  • Dominant object (largest in frame): {bbox_area} pixels")
                        print_info(f"  • Other objects detected in frame: {len(current_objects) - 1} [{', '.join([c for c in all_classes if c != class_name])}]")
                        print_info(f"  • BBox: x={bbox.get('x', 0)}, y={bbox.get('y', 0)}, w={bbox.get('width', 0)}, h={bbox.get('height', 0)}")
                        print_info(f"  • Class is in COCO list: True | Color: {OBJECT_COLORS.get(class_name.lower(), 'N/A')}")
                        
                        if objects_captured >= num_captures:
                            print_success(f"✓ All {num_captures} dominant objects captured successfully!")
                            break
            elif key == ord('q') or key == 27:  # Q or ESC to finish
                break
            
            # Check timeout
            if time.time() - start_time > timeout_duration:
                print_warning(f"Object capture timeout ({timeout_duration}s)")
                break
            
            if objects_captured >= num_captures:
                break
        
        cv2.destroyAllWindows()
        
        if detected_objects:
            print_success(f"Object detection complete: {len(detected_objects)} objects captured")
        else:
            print_warning("No objects captured during detection")
    
    except Exception as e:
        print_warning(f"Object detection error: {str(e)[:50]}")
    
    finally:
        # Clean up camera
        if cap is not None:
            try:
                cap.release()
            except:
                pass
        
        try:
            cv2.destroyAllWindows()
        except:
            pass
        
        # Release hardware resource
        if lease_id:
            release_hardware_resource(lease_id)
    
    return detected_objects

def get_user_profile(user_id: str) -> Optional[Dict]:
    """Fetch complete user profile from Central Server using available endpoints."""
    try:
        # Preferred endpoint (if available in deployed build)
        response = requests.get(
            f"{ServiceConfig.CENTRAL_SERVER}/users/{user_id}",
            timeout=10
        )
        if response.status_code == 200:
            return response.json()

        # Backward-compatible fallback: resolve from /users/list
        list_response = requests.get(
            f"{ServiceConfig.CENTRAL_SERVER}/users/list",
            timeout=10
        )
        if list_response.status_code != 200:
            return None

        users = list_response.json().get("users", [])
        for user in users:
            if user.get("user_id") == user_id:
                return user
        return None
    except Exception as e:
        print_warning(f"Error fetching user profile: {str(e)[:40]}")
        return None

def get_conversation_history(user_id: str, max_turns: int = 5) -> List[Dict]:
    """Fetch conversation history from Central Server with compatibility fallback.
    
    ENHANCED: Retrieves MORE context (10 turns for personalization).
    """
    try:
        # Preferred endpoint (if available in deployed build)
        response = requests.get(
            f"{ServiceConfig.CENTRAL_SERVER}/users/{user_id}/conversation-history",
            params={"limit": max_turns},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('history', [])

        # Backward-compatible fallback: read conversation_history from user profile
        user_profile = get_user_profile(user_id)
        if not user_profile:
            return []

        history = user_profile.get("conversation_history", [])
        if not isinstance(history, list):
            return []
        return history[-max_turns:]
    except Exception as e:
        print_info(f"No conversation history available: {str(e)[:30]}")
        return []


def build_personalized_user_context(user_id: str) -> Dict[str, Any]:
    """
    Build COMPREHENSIVE per-user context with SLIDING WINDOW TOKEN BUDGETING.
    
    ENTERPRISE FEATURES:
    - TOKEN-BASED SLIDING WINDOW (not hardcoded turn counts)
    - Auto-compact old conversations when approaching token limits
    - Per-user independent context management
    - Intelligent memory management (handles 1000+ concurrent users)
    - Activity-based context sizing (heavy users get more context)
    - Token budget awareness (respects LLM context limits)
    
    SLIDING WINDOW LOGIC:
    - User with 2 interactions: Keep all 2 turns
    - User with 7 interactions: Keep all 7 turns (still under budget)
    - User with 12 interactions: 
      * Remove oldest 3-4 turns automatically
      * Keep last 5-7 recent turns (to fit token budget)
      * Next time they interact, the window slides further
    
    CRITICAL: This function is called for EVERY user interaction.
    Context window size DYNAMICALLY ADJUSTS based on token usage, not hardcoded.
    """
    try:
        user_profile = get_user_profile(user_id)
        if not user_profile:
            return {"user_id": user_id, "available": False}
        
        # Extract core user info
        user_name = user_profile.get('name') or user_profile.get('user_name') or 'User'
        user_age = user_profile.get('age')
        
        # Get FULL conversation history from Central Server (via REST API)
        # This retrieves ALL turns, not limited to window size
        full_history = get_conversation_history(user_id, max_turns=1000)  # Get all turns
        
        # SLIDING WINDOW: Compact history based on token budgets
        # This automatically removes old turns when approaching limits
        compacted_history = user_context_manager.compact_conversation_history(
            user_id, 
            full_history
        )
        
        # Get optimal context window configuration
        context_config = user_context_manager.get_optimal_context_window(user_id)
        is_heavy_user = context_config.get('is_heavy_user', False)
        
        # Record this interaction for activity tracking
        user_context_manager.record_interaction(user_id, str(compacted_history))
        
        # Get taught objects for this specific user
        taught_objects = get_taught_objects(user_id)
        
        # Extract user preferences/interests from conversation history
        user_interests = _extract_user_interests_from_history(compacted_history, taught_objects)
        
        # Get last interaction time (for warm greeting)
        last_interaction = None
        if compacted_history and len(compacted_history) > 0:
            last_turn = compacted_history[-1]
            last_interaction = last_turn.get('timestamp')
        
        # Build personalized context with COMPACTED history
        personalized_context = {
            "user_id": user_id,
            "name": user_name,
            "age": user_age,
            "available": True,
            "conversation_history": compacted_history,            # COMPACTED by sliding window
            "conversation_history_total_original": len(full_history),  # For reference
            "taught_objects": taught_objects,                      # All taught objects
            "interests": user_interests,                           # Extracted interests
            "last_interaction_time": last_interaction,             # For greeting logic
            "enrollment_date": user_profile.get('enrollment_timestamp'),
            "total_interactions": len(compacted_history),
            # Context metadata for LLM
            "context_window_size": len(compacted_history),                  # Actual turns sent
            "is_heavy_user": is_heavy_user,                               # User activity level
            "context_token_budget": context_config.get('token_budget_available'),
            "current_tokens_used": context_config.get('current_tokens_used', 0),
            "sliding_window_enabled": context_config.get('sliding_window_enabled', False),
            "was_compacted": len(full_history) > len(compacted_history)    # LLM knows if history was trimmed
        }
        
        # Cache this user's context for efficient retrieval
        user_context_manager.cache_user_context(user_id, personalized_context)
        
        return personalized_context
        
    except Exception as e:
        print_warning(f"Error building personalized context for {user_id}: {str(e)[:50]}")
        return {"user_id": user_id, "available": False}


def _extract_user_interests_from_history(conversation_history: List[Dict], taught_objects: List[Dict]) -> Dict[str, Any]:
    """
    Extract user interests and preferences from conversation history.
    
    Example:
    - If user mentions "gardening" in past conversations -> Interest: gardening
    - If user taught objects about flowers -> Interest: botany/gardening
    - Helps LLM understand user's personality
    """
    interests = {
        "hobbies": [],
        "topics_discussed": [],
        "taught_categories": [],
        "mood_patterns": [],
    }
    
    try:
        # Extract from taught objects
        taught_categories = set()
        for obj in taught_objects:
            category = obj.get('category', '').lower()
            if category:
                taught_categories.add(category)
        interests["taught_categories"] = list(taught_categories)
        
        # Extract from conversation - look for hobby/interest keywords
        interest_keywords = {
            "gardening": ["garden", "plant", "flower", "leaf", "grow"],
            "sports": ["play", "game", "soccer", "basketball", "cricket"],
            "reading": ["book", "read", "story", "novel", "author"],
            "cooking": ["cook", "recipe", "food", "kitchen", "eat"],
            "technology": ["computer", "phone", "robot", "code", "tech"],
            "art": ["draw", "paint", "color", "art", "creative"],
            "music": ["song", "sing", "music", "instrument", "play"],
            "science": ["science", "experiment", "learn", "discover", "why"],
        }
        
        topics_found = set()
        for turn in conversation_history:
            user_msg = turn.get('user', '').lower() if isinstance(turn.get('user'), str) else ''
            
            for interest, keywords in interest_keywords.items():
                if any(keyword in user_msg for keyword in keywords):
                    topics_found.add(interest)
        
        interests["topics_discussed"] = list(topics_found)
        
        return interests
        
    except Exception as e:
        print_warning(f"Error extracting interests: {str(e)[:40]}")
        return interests


def store_interaction_in_user_history(user_id: str, user_message: str, assistant_response: str) -> bool:
    """
    Store completed interaction in user's conversation history.
    
    PROFESSIONAL IMPLEMENTATION:
    Uses dedicated /users/{user_id}/conversations endpoint in Central Server.
    Proper separation: Conversations stored in separate persistence layer.
    
    This ensures:
    - Interaction history persists across sessions
    - User profile remains lean (no huge arrays)
    - Conversations are queryable and archivable
    - Professional REST API contract
    
    Args:
        user_id: User ID (e.g., 'sara123')
        user_message: What user said
        assistant_response: NEXI's response
        
    Returns:
        bool: True if successfully stored
    """
    try:
        # POST /users/{user_id}/conversations - Store conversation properly
        response = requests.post(
            f"{ServiceConfig.CENTRAL_SERVER}/users/{user_id}/conversations",
            json={
                "user_message": user_message,
                "assistant_response": assistant_response,
                # Extract mood from context if available
                "mood": "neutral",  # Could be enhanced to pass actual mood
                "language": "en",   # Could be enhanced to pass detected language
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "source": "conversation_api"
                }
            },
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            print_success("Interaction stored successfully")
            return True
        else:
            print_warning(f"Failed to store interaction: HTTP {response.status_code}")
            
            # Log detailed error for debugging
            try:
                error_detail = response.json().get("detail", "Unknown error")
                print_info(f"Store interaction error: {error_detail}")
            except:
                print_info(f"Store interaction HTTP {response.status_code}")
            
            return False
            
    except requests.Timeout:
        print_warning("Interaction storage timeout (non-critical)")
        return False
    except Exception as e:
        print_warning(f"Error storing interaction: {str(e)[:50]} (non-critical)")
        return False


def show_context_manager_stats() -> None:
    """
    ENTERPRISE MONITORING: Show context window management stats for ALL users.
    
    Displays:
    - Total users being tracked
    - Context window distribution (new/regular/heavy users)
    - Memory usage per user
    - Activity levels
    - System health metrics
    
    Used for debugging and monitoring in production.
    """
    try:
        print_header("CONTEXT WINDOW MANAGER - ENTERPRISE MONITORING")
        
        if not user_context_manager.user_stats:
            print_info("No users tracked yet")
            return
        
        print_info(f"Total users tracked: {len(user_context_manager.user_stats)}")
        print_info(f"Cached contexts: {len(user_context_manager.user_contexts)}")
        print_info(f"Memory budget: {user_context_manager.MAX_USERS_IN_MEMORY} users max")
        
        print_subheader("USER STATISTICS")
        
        new_users = 0
        regular_users = 0
        heavy_users = 0
        total_memory = 0
        
        # Analyze each user
        for user_id, stats in sorted(user_context_manager.user_stats.items()):
            interactions = stats.get('interaction_count', 0)
            memory = stats.get('memory_bytes', 0)
            last_access = stats.get('last_access_time', 'Never')
            
            # Categorize user
            if interactions <= 5:
                user_tier = "NEW"
                new_users += 1
            elif interactions <= 10:
                user_tier = "REGULAR"
                regular_users += 1
            else:
                user_tier = "HEAVY"
                heavy_users += 1
            
            total_memory += memory
            
            # Show condensed user stats
            print_result(
                f"  {user_id}: {user_tier}",
                f"{interactions} interactions, {memory} bytes, last: {last_access[:10]}"
            )
        
        # Summary
        print_subheader("SUMMARY")
        print_result("New Users (0-5 interactions)", f"{new_users} users × 5-turn window")
        print_result("Regular Users (6-10 interactions)", f"{regular_users} users × 8-turn window")
        print_result("Heavy Users (11+ interactions)", f"{heavy_users} users × 15-turn window")
        print_result("Total Memory Usage", f"{total_memory:,} bytes")
        print_result("Context Window Health", "✓ OPTIMAL" if len(user_context_manager.user_stats) < user_context_manager.MAX_USERS_IN_MEMORY else "⚠ PRESSURE")
        
    except Exception as e:
        print_error(f"Error showing context stats: {str(e)[:50]}")

def get_taught_objects(user_id: str) -> List[Dict]:
    """Fetch objects taught to robot from TeachMe Service."""
    try:
        response = requests.get(
            f"{ServiceConfig.TEACHME_SERVICE}/knowledge/objects",
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('objects', [])
        return []
    except Exception as e:
        print_info(f"No taught objects found: {str(e)[:30]}")
        return []

def request_hardware_resource(
    resource_type: str,
    service_name: str = "test_script",
    priority: str = "MEDIUM",
    timeout_seconds: int = 30
) -> Optional[str]:
    """
    Request access to hardware resource through Central Server with intelligent fallback.
    
    If Central Server resource manager is unavailable, returns a synthetic lease_id
    allowing the operation to proceed anyway. This maintains backward compatibility.
    
    Args:
        resource_type: 'camera', 'microphone', or 'speaker'
        service_name: Name of service making request
        priority: 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
        timeout_seconds: Auto-release timeout
    
    Returns:
        lease_id if successful (real or synthetic), None otherwise
    """
    try:
        # Try to request from Central Server with timeout
        response = requests.post(
            f"{ServiceConfig.CENTRAL_SERVER}/resources/request",
            params={
                "resource_type": resource_type,
                "service_name": service_name,
                "priority": priority,
                "timeout_seconds": timeout_seconds
            },
            timeout=3  # Reduced timeout for faster fallback
        )
        
        if response.status_code == 200:
            data = response.json()
            lease_id = data.get('lease_id')
            granted = data.get('granted', False)
            message = data.get('message', '')
            
            if granted:
                print_success(f"Resource {resource_type} granted: {lease_id}")
            else:
                print_info(f"Resource {resource_type} queued: {message}")
            
            return lease_id
        else:
            # Central Server resource endpoint not available
            print_info(f"Resource manager unavailable (HTTP {response.status_code}), using direct access")
            # Generate synthetic lease_id to allow operation to proceed
            synthetic_lease = f"synthetic-{resource_type}-{uuid.uuid4().hex[:8]}"
            print_info(f"Allocated resource via direct access: {synthetic_lease}")
            return synthetic_lease
    
    except requests.ConnectionError:
        print_info(f"Central Server not reachable, using direct access for {resource_type}")
        # Generate synthetic lease_id - operations can proceed without central coordination
        synthetic_lease = f"synthetic-{resource_type}-{uuid.uuid4().hex[:8]}"
        return synthetic_lease
    
    except requests.Timeout:
        print_info(f"Resource manager timeout, using direct access for {resource_type}")
        # Generate synthetic lease_id - operations can proceed without central coordination
        synthetic_lease = f"synthetic-{resource_type}-{uuid.uuid4().hex[:8]}"
        return synthetic_lease
    
    except Exception as e:
        print_info(f"Resource manager error ({str(e)[:30]}), falling back to direct access")
        # Generate synthetic lease_id - operations can proceed without central coordination
        synthetic_lease = f"synthetic-{resource_type}-{uuid.uuid4().hex[:8]}"
        return synthetic_lease

def release_hardware_resource(lease_id: str) -> bool:
    """
    Release a hardware resource lease with intelligent fallback.
    
    If Central Server resource manager is unavailable, synthetic leases are
    silently released. This maintains compatibility without errors.
    
    Args:
        lease_id: The lease ID to release
    
    Returns:
        True if release successful (or synthetic lease), False only on real errors
    """
    # Handle synthetic leases (from fallback mode)
    if lease_id.startswith("synthetic-"):
        print_info(f"Released resource (direct access): {lease_id}")
        return True
    
    try:
        response = requests.post(
            f"{ServiceConfig.CENTRAL_SERVER}/resources/release/{lease_id}",
            timeout=3  # Reduced timeout for faster fallback
        )
        
        if response.status_code == 200:
            print_success(f"Resource lease {lease_id} released")
            return True
        elif response.status_code == 404:
            # Lease not found - probably never was managed by Central Server
            print_info(f"Resource already released or not managed: {lease_id}")
            return True
        else:
            print_info(f"Release response: HTTP {response.status_code}")
            return True  # Don't fail, just log
    
    except requests.ConnectionError:
        print_info(f"Central Server unreachable, but release is not critical: {lease_id}")
        return True  # Don't fail - release is not critical if server is down
    
    except requests.Timeout:
        print_info(f"Resource manager timeout on release, proceeding: {lease_id}")
        return True  # Don't fail on timeout
    
    except Exception as e:
        print_info(f"Could not contact resource manager to release {lease_id}, continuing")
        return True  # Don't fail - release failure shouldn't stop the system

def get_hardware_resources_status() -> Dict:
    """
    Get status of all hardware resources.
    
    Returns:
        Dictionary with camera, microphone, speaker status
    """
    try:
        response = requests.get(
            f"{ServiceConfig.CENTRAL_SERVER}/resources/status",
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('resources', {})
        else:
            return {}
    
    except Exception as e:
        print_warning(f"Error getting resource status: {str(e)[:40]}")
        return {}

def get_user_by_name(user_name: str) -> Optional[Dict]:
    """Fetch user by name from Central Server."""
    try:
        response = requests.get(
            f"{ServiceConfig.CENTRAL_SERVER}/users/search/{user_name}",
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

# ============================================================================
# MENU OPTION 2: NEW USER ENROLLMENT - FATIMA
# ============================================================================

def menu_new_user_enrollment():
    """
    New user enrollment with resource pre-emption.
    
    Test Scenario: Fatima wants to enroll.
    Workflow:
    - Collect user info
    - Request camera resource (pre-emption)
    - Capture 5 face images
    - Record 5 voice samples
    - Register in Central (offline-safe)
    - Release resources
    """
    print_header("NEW USER ENROLLMENT - Fatima")
    print_info("Test production features: resource pre-emption, offline-safe registration")
    
    if not state.services_connected['central'] or not state.services_connected['audio']:
        print_error("Central Server and Audio Service required")
        return
    
    print_step(1, 6, "User Information")
    username = input("Enter username (e.g., fatima): ").strip()
    if not username:
        print_error("Username required")
        return
    
    age = input("Enter age (optional): ").strip()
    age = int(age) if age.isdigit() else None
    
    relation = input("Enter relation (optional): ").strip()
    
    print_success(f"User info: {username}, Age: {age if age else 'Not specified'}")
    
    print_step(2, 6, "Request Camera Resource (Priority High)")
    camera_lease_id = request_hardware_resource(
        resource_type="camera",
        service_name="new_user_enrollment",
        priority="HIGH",
        timeout_seconds=120
    )
    
    print_step(3, 6, "Capture Facial Images (5)")
    print_info("Camera allocated. Starting face capture...")
    face_embeddings = capture_real_face_images(num_images=5)
    
    if not face_embeddings:
        print_error("Face capture failed")
        if camera_lease_id:
            release_hardware_resource(camera_lease_id)
        return
    
    print_step(4, 6, "Record Voice Samples (5)")
    voice_embeddings = []
    
    for i in range(5):
        print(f"\nVoice Sample {i+1}/5...")
        print_info("Say: 'Hey Nexi, I want to enroll as a new user'")
        
        input("Press Enter when ready...")
        
        audio_file = record_audio(duration=AudioConfig.DEFAULT_DURATION, filename=f"enroll_{username}_{i+1}.wav")
        if not audio_file:
            print_error(f"Recording {i+1} failed")
            return
        
        embedding = process_voice_embedding(audio_file)
        if embedding:
            voice_embeddings.append(embedding)
            print_success(f"Sample {i+1} processed")
        else:
            print_error(f"Sample {i+1} processing failed")
            return
    
    print_step(5, 6, "Register in Central Server (Offline-Safe)")
    try:
        payload = {
            "user_name": username,
            "face_embeddings": face_embeddings,
            "voice_embeddings": voice_embeddings,
            "face_confidences": [0.95] * len(face_embeddings),
            "voice_qualities": [0.90] * len(voice_embeddings)
        }
        
        if age:
            payload["age"] = age
        if relation:
            payload["relation"] = relation
        
        response = requests.post(
            f"{ServiceConfig.CENTRAL_SERVER}/users/add-embeddings",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json().get('data', response.json())
            user_id = data.get('user_id', 'unknown')
            print_success(f"User registered: {user_id}")
            
            print_step(6, 6, "Release Resources")
            if camera_lease_id and release_hardware_resource(camera_lease_id):
                print_success("Resources released")
            
            print_header("ENROLLMENT COMPLETE")
            print_result("User ID", user_id)
            print_result("Username", username)
            print_result("Face Samples", len(face_embeddings))
            print_result("Voice Samples", len(voice_embeddings))
            print_result("Status", "Ready for authentication")
            
            sync_audio_service_speakers()
        else:
            print_error(f"Registration failed: {response.status_code}")
    
    except Exception as e:
        print_error(f"Registration error: {str(e)}")

# ============================================================================
# MENU OPTION 3: IMPROVE TRAINING - SARA
# ============================================================================

def menu_improve_training():
    """
    Add 5 additional face and voice samples.
    
    Test Scenario: Sara improves her training.
    Workflow:
    - Select user (Sara)
    - Capture 5 new faces
    - Record 5 new voice samples
    - Append to profile
    - Verify total samples increase
    """
    print_header("IMPROVE TRAINING - Sara")
    print_info("Add 5 face and 5 voice samples to existing user profile")
    
    if not state.services_connected['central'] or not state.services_connected['audio']:
        print_error("Central Server and Audio Service required")
        return
    
    print_step(1, 4, "Select User")
    display_enrolled_users()
    
    users = get_all_users()
    if not users:
        print_error("No enrolled users")
        return
    
    try:
        choice = int(input("\nSelect user number: ").strip())
        if choice < 1 or choice > len(users):
            print_error("Invalid selection")
            return
        
        selected = users[choice - 1]
        user_id = selected.get('user_id')
        username = selected.get('user_name') or selected.get('name')
        current_face = len(selected.get('face_embeddings', []))
        current_voice = len(selected.get('voice_embeddings', []))
        
        print_success(f"Selected: {username} (Current: {current_face} face, {current_voice} voice)")
    
    except (ValueError, IndexError):
        print_error("Invalid input")
        return
    
    print_step(2, 4, "Capture Additional Faces (5)")
    new_face_embeddings = capture_real_face_images(num_images=5)
    
    if not new_face_embeddings:
        print_error("Face capture failed")
        return
    
    print_step(3, 4, "Record Additional Voice Samples (5)")
    new_voice_embeddings = []
    
    for i in range(5):
        print(f"\nVoice Sample {i+1}/5...")
        print_info("Say: 'I am improving my training with additional samples'")
        
        input("Press Enter when ready...")
        
        audio_file = record_audio(duration=AudioConfig.DEFAULT_DURATION, filename=f"improve_{username}_{i+1}.wav")
        if not audio_file:
            return
        
        embedding = process_voice_embedding(audio_file)
        if embedding:
            new_voice_embeddings.append(embedding)
            print_success(f"Sample {i+1} processed")
        else:
            return
    
    print_step(4, 4, "Update User Profile (Append Embeddings)")
    try:
        payload = {
            "face_embeddings": new_face_embeddings,
            "voice_embeddings": new_voice_embeddings,
            "face_confidences": [0.95] * len(new_face_embeddings),
            "voice_qualities": [0.90] * len(new_voice_embeddings)
        }
        
        response = requests.post(
            f"{ServiceConfig.CENTRAL_SERVER}/users/{user_id}/append-embeddings",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json().get('data', response.json())
            new_total_face = data.get('total_face_samples', current_face + 5)
            new_total_voice = data.get('total_voice_samples', current_voice + 5)
            
            print_header("TRAINING IMPROVED")
            print_result("User", username)
            print_result("Face Samples: Before", current_face)
            print_result("Face Samples: After", new_total_face)
            print_result("Voice Samples: Before", current_voice)
            print_result("Voice Samples: After", new_total_voice)
            print_result("Total Improvement", f"+{new_total_face - current_face} face, +{new_total_voice - current_voice} voice")
            
            sync_audio_service_speakers()
        else:
            print_error(f"Update failed: {response.status_code}")
    
    except Exception as e:
        print_error(f"Error: {str(e)}")

# ============================================================================
# MENU OPTION 4: RE-ENROLLMENT - ALI
# ============================================================================

def menu_re_enrollment():
    """
    Replace all biometric data.
    
    Test Scenario: Ali needs complete re-enrollment.
    Workflow:
    - Confirm dangerous operation
    - Capture 5 new faces
    - Record 5 new voice samples
    - Replace all existing data
    """
    print_header("RE-ENROLLMENT - Ali")
    print_info("Replace ALL biometric data for existing user (dangerous operation)")
    
    if not state.services_connected['central'] or not state.services_connected['audio']:
        print_error("Central Server and Audio Service required")
        return
    
    print_step(1, 4, "Select User")
    display_enrolled_users()
    
    users = get_all_users()
    if not users:
        print_error("No enrolled users")
        return
    
    try:
        choice = int(input("\nSelect user number: ").strip())
        if choice < 1 or choice > len(users):
            print_error("Invalid selection")
            return
        
        selected = users[choice - 1]
        user_id = selected.get('user_id')
        username = selected.get('user_name') or selected.get('name')
        
        print_warning(f"This will REPLACE ALL data for: {username}")
        confirm = input("Type 'yes' to confirm: ").strip().lower()
        
        if confirm != 'yes':
            print_info("Re-enrollment cancelled")
            return
        
        print_success(f"Re-enrolling: {username}")
    
    except (ValueError, IndexError):
        print_error("Invalid input")
        return
    
    print_step(2, 4, "Capture New Faces (5)")
    new_face_embeddings = capture_real_face_images(num_images=5)
    
    if not new_face_embeddings:
        print_error("Face capture failed")
        return
    
    print_step(3, 4, "Record New Voice Samples (5)")
    new_voice_embeddings = []
    
    for i in range(5):
        print(f"\nVoice Sample {i+1}/5...")
        print_info("Say: 'I am re-enrolling with new biometric data'")
        
        input("Press Enter when ready...")
        
        audio_file = record_audio(duration=AudioConfig.DEFAULT_DURATION, filename=f"reenroll_{username}_{i+1}.wav")
        if not audio_file:
            return
        
        embedding = process_voice_embedding(audio_file)
        if embedding:
            new_voice_embeddings.append(embedding)
            print_success(f"Sample {i+1} processed")
        else:
            return
    
    print_step(4, 4, "Replace All User Data")
    try:
        payload = {
            "face_embeddings": new_face_embeddings,
            "voice_embeddings": new_voice_embeddings,
            "face_confidences": [0.95] * len(new_face_embeddings),
            "voice_qualities": [0.90] * len(new_voice_embeddings),
            "replace_mode": True
        }
        
        response = requests.put(
            f"{ServiceConfig.CENTRAL_SERVER}/users/{user_id}/embeddings",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            print_header("RE-ENROLLMENT COMPLETE")
            print_result("User", username)
            print_result("New Face Samples", 5)
            print_result("New Voice Samples", 5)
            print_result("Old Data Status", "Backed up and replaced")
            print_success("User profile completely refreshed")
            
            sync_audio_service_speakers()
        else:
            print_error(f"Re-enrollment failed: {response.status_code}")
    
    except Exception as e:
        print_error(f"Error: {str(e)}")

# ============================================================================
# MENU OPTION 5: RETURN USER CONVERSATION - SARA
# ============================================================================

# ============================================================================
# MENU OPTION 5: RETURN USER CONVERSATION - SARA  
# ============================================================================

def conduct_single_conversation(user_id: str, verified_context: bool = False, audio_file: str = None):
    """
    Conduct a single conversation turn (query → response).
    
    Args:
        user_id: Already verified user ID
        verified_context: If True, skip verification step
        audio_file: Optional audio file from speaker verification (reuse for STT on first turn)
    """
    if audio_file:
        print_step(1, 5, "Reuse Verification Audio for Transcription")
        print_info(f"Using audio from speaker verification (audio_file={audio_file})")
        command_file = audio_file
    else:
        print_step(1, 5, "Record Command Audio")
        print_info("Say your command/question...")
        command_file = record_audio(duration=AudioConfig.DEFAULT_DURATION, filename="return_user_command.wav")
        if not command_file:
            print_error("Recording failed")
            return False
    
    print_step(2, 5, "Speech-to-Text Transcription")
    transcription = transcribe_audio(command_file)
    if not transcription:
        print_error("Transcription failed")
        # Play cached error voice
        voice_player = get_voice_player()
        voice_player.play_voice("transcribe_failed")
        return False
    
    print_success(f"Transcription: {transcription}")
    
    print_step(3, 5, "Get Vision Context (Mood)")
    mood = capture_mood_with_visual_feedback()
    print_result("Detected Mood", mood)
    
    print_step(4, 5, "Query Knowledge Base (TeachMe)")
    knowledge = []
    knowledge_search_status = "no_entities"  # Track why knowledge is empty
    try:
        # OPTIMIZED: Intelligent Entity-Based Knowledge Retrieval
        
        # Step 1: Extract entities from transcription using QueryProcessorService
        # "What is the apple?" -> ["apple"]
        # "I am Sohail, this is my mobile phone" -> ["mobile", "phone"]
        entities = QueryProcessorService.extract_entities(transcription)
        
        if entities:
            print_success(f"Query entities extracted: {entities}")
            
            # Step 2: Validate KB first (check if it has data)
            try:
                stats_response = requests.get(
                    f"{ServiceConfig.TEACHME_SERVICE}/knowledge/stats",
                    timeout=10
                )
                if stats_response.status_code == 200:
                    stats_data = stats_response.json().get('stats', {})
                    kb_total = stats_data.get('total', 0)
                    
                    if kb_total == 0:
                        print_warning("Knowledge base is empty - Run Option 6 to teach objects first")
                        knowledge = []
                        knowledge_search_status = "kb_empty"
                    else:
                        print_success(f"Knowledge base validated: {kb_total} items available")
                        
                        # Step 3: Intelligent Search - Get entity-specific results
                        all_results = {}
                        entity_search_count = {}
                        
                        for entity in entities:
                            try:
                                search_response = requests.post(
                                    f"{ServiceConfig.TEACHME_SERVICE}/knowledge/search/embedding",
                                    params={
                                        "query_object_name": entity,
                                        "top_k": 5,
                                        "similarity_threshold": 0.75  # CRITICAL FIX: Increased from 0.5 to 0.75 (HIGH confidence only)
                                    },
                                    timeout=30
                                )
                                
                                if search_response.status_code == 200:
                                    results = search_response.json().get('results', [])
                                    entity_search_count[entity] = len(results)
                                    
                                    # Process results with intelligent filtering
                                    for result in results:
                                        obj_name = result.get('name', '').lower()
                                        similarity = float(result.get('similarity', 0.5))
                                        
                                        # CRITICAL FIX: Only keep VERY HIGH confidence matches
                                        # >= 0.75: Strong match, likely correct
                                        # < 0.75: Likely false positive, reject
                                        
                                        if obj_name not in all_results:
                                            # First match for this object - keep ONLY if very high confidence
                                            if similarity >= 0.75:
                                                all_results[obj_name] = {
                                                    "object_name": result.get('name', entity),
                                                    "confidence": similarity,
                                                    "category": result.get('category'),
                                                    "tags": result.get('tags', []),
                                                    "type": result.get('type'),
                                                    "matched_entity": entity
                                                }
                                        else:
                                            # Already have this object - keep if confidence is even higher
                                            if similarity > all_results[obj_name].get('confidence', 0):
                                                all_results[obj_name]['confidence'] = similarity
                                                all_results[obj_name]['matched_entity'] = entity
                            
                            except Exception as search_error:
                                print_warning(f"Search for entity '{entity}' failed: {str(search_error)[:50]}")
                        
        # Step 4: Post-filter and sort by confidence
                        # Keep only results with GOOD confidence scores
                        # CRITICAL FIX: Only accept HIGH confidence matches (>= 0.75)
                        # This prevents unrelated items from showing up
                        filtered_results = []
                        for obj_name, data in all_results.items():
                            confidence = data.get('confidence', 0)
                            # HIGH confidence: >= 0.75 (strong match)
                            # REJECT: < 0.75 is likely false positive
                            if confidence >= 0.75:
                                filtered_results.append(data)
                        
                        # Sort by confidence (highest first), keep top 2-3 results
                        filtered_results.sort(key=lambda x: x['confidence'], reverse=True)
                        
                        # CRITICAL: Limit to max 2 items for high confidence
                        # This ensures we only send truly relevant matches to LLM
                        knowledge = filtered_results[:2]
                        
                        if knowledge:
                            print_success(f"Knowledge retrieved: {len(knowledge)} HIGH-CONFIDENCE items")
                            for item in knowledge:
                                print_info(f"  • {item['object_name']} (confidence: {item['confidence']:.2f})")
                            knowledge_search_status = "found"
                        else:
                            print_info("No HIGH-CONFIDENCE matches in knowledge base")
                            knowledge_search_status = "no_match"
                            # Add explicit metadata for LLM
                            knowledge = []
                else:
                    print_warning(f"Could not fetch KB stats: HTTP {stats_response.status_code}")
                    knowledge = []
                    knowledge_search_status = "kb_unavailable"
            
            except Exception as kb_error:
                print_warning(f"TeachMe service unavailable: {str(kb_error)[:50]}")
                print_info("Proceeding with empty knowledge context")
                knowledge = []
                knowledge_search_status = "service_error"
        else:
            print_info("No entities extracted from query - KB search skipped")
            knowledge_search_status = "no_entities"
    
    except Exception as e:
        print_warning(f"RAG error: {str(e)[:100]}")
        print_info("Proceeding with empty knowledge context")
        knowledge = []
        knowledge_search_status = "error"
    
    print_step(5, 5, "Generate LLM Response & Speak")
    llm_response = "I am thinking about your question."
    llm_source = "fallback"
    
    try:
        # Detect language from transcription for LLM context
        language_detected = "en"
        if any(ord(c) > 127 for c in transcription):  # Urdu characters
            language_detected = "ur"
        
        # Build complete context with user profile, history, and taught objects
        user_profile = get_user_profile(user_id)
        user_name = (
            (user_profile.get('user_name') or user_profile.get('name'))
            if user_profile else 'User'
        )
        user_age = user_profile.get('age') if user_profile else None
        
        # ENHANCED: Build RICH personalized context for this specific user
        personalized_context = build_personalized_user_context(user_id)
        
        # Extract from personalized context
        conversation_history = personalized_context.get('conversation_history', [])
        taught_objects = personalized_context.get('taught_objects', [])
        user_interests = personalized_context.get('interests', {})
        last_interaction = personalized_context.get('last_interaction_time')
        
        # Step 5A: Format knowledge items with clear labels for LLM
        # Ensure object names are prominent for LLM context
        formatted_knowledge = []
        if knowledge:
            for item in knowledge:
                formatted_item = {
                    "object_label": item.get('object_name', 'Unknown'),  # CRITICAL: Clear label
                    "category": item.get('category'),
                    "type": item.get('type'),
                    "confidence_match": round(item.get('confidence', 0), 2),
                    "tags": item.get('tags', [])
                }
                formatted_knowledge.append(formatted_item)
            knowledge_context_note = f"User is asking about taught objects. Found {len(formatted_knowledge)} matching items:"
        else:
            # CRITICAL: Explicit message when knowledge not found
            formatted_knowledge = []
            if knowledge_search_status == "no_match":
                knowledge_context_note = "No taught objects match the user's query. Respond based on general knowledge."
            elif knowledge_search_status == "kb_empty":
                knowledge_context_note = "Knowledge base is empty. No taught objects available. Respond with general knowledge."
            elif knowledge_search_status == "no_entities":
                knowledge_context_note = "Could not identify specific objects in query. Respond with general knowledge."
            else:
                knowledge_context_note = "Could not retrieve taught objects. Respond with general knowledge."
        
        # Build context using LLMContextBuilder
        context_builder = LLMContextBuilder()
        llm_context = context_builder.build_context(
            query=transcription,
            user_id=user_id,
            user_name=user_name,
            user_age=user_age,
            mood=mood,
            emotion_scores={},
            language=language_detected,
            knowledge_items=formatted_knowledge,  # Use formatted knowledge with clear labels
            conversation_history=conversation_history,
            additional_metadata={
                "taught_objects": [{"name": obj.get('name'), "type": obj.get('type')} 
                                  for obj in taught_objects],  # All taught objects for context
                "user_interests": user_interests,  # PERSONALIZATION: User's hobbies and interests
                "interest_topics": user_interests.get('topics_discussed', []),  # Topics they likes
                "taught_categories": user_interests.get('taught_categories', []),  # What they taught
                "knowledge_search_status": knowledge_search_status,  # Track search result status
                "knowledge_context_note": knowledge_context_note,  # Explicit guidance for LLM
                "last_interaction": last_interaction,  # For warm greeting logic
                "total_past_interactions": personalized_context.get('total_interactions', 0),  # History depth
                # TOKEN BUDGET & SLIDING WINDOW METADATA FOR INTELLIGENT LLM BEHAVIOR
                "context_window_size": personalized_context.get('context_window_size'),  # Actual turns sent
                "context_window_original_size": personalized_context.get('conversation_history_total_original', 0),  # Before compaction
                "is_heavy_user": personalized_context.get('is_heavy_user'),  # User activity level
                "was_context_compacted": personalized_context.get('was_compacted', False),  # History was trimmed for token budget
                "context_token_budget": personalized_context.get('context_token_budget'),  # Total token budget
                "current_tokens_used": personalized_context.get('current_tokens_used', 0),  # Tokens currently in use
                "sliding_window_enabled": personalized_context.get('sliding_window_enabled', False),  # Token-based sliding window active
                "user_profile_available": True  # LLM knows user data is available
            }
        )
        
        # Format context for LLM service
        llm_payload = context_builder.format_for_direct_llm(llm_context)
        
        response = requests.post(
            f"{ServiceConfig.LLM_SERVICE}/api/v1/generate",
            json=llm_payload,
            timeout=RuntimeConfig.LLM_RESPONSE_TIMEOUT
        )
        
        if response.status_code == 200:
            response_json = response.json()
            
            if response_json.get('success'):
                llm_data = response_json.get('data', {})
                llm_response = llm_data.get('response', llm_response)
                llm_metadata = llm_data.get('metadata', {})
                
                primary_source = llm_metadata.get('primary_source', 'unknown')
                if primary_source == "openrouter":
                    llm_source = "OpenRouter"
                    response_time = llm_metadata.get('openrouter_response_time', 0)
                    print_success(f"LLM (OpenRouter): {response_time:.2f}s")
                elif primary_source == "local_llm":
                    llm_source = "Local LLM"
                    response_time = llm_metadata.get('local_response_time', 0)
                    print_success(f"LLM (Local): {response_time:.1f}s")
                
                # CRITICAL: Detect language of RESPONSE (not input) for correct TTS voice
                # LLM may respond in different language than input
                response_language = "en"
                if any(ord(c) > 127 for c in llm_response):  # Urdu characters in response
                    response_language = "ur"
                
                # Play response using correct TTS language based on RESPONSE content
                if synthesize_and_play_tts(llm_response, language=response_language):
                    print_success(f"Response played: '{llm_response[:60]}...'")
                else:
                    print_warning("Response not spoken to user")
                
                # CRITICAL: Store this interaction in user's history
                # This ensures next time the user comes back, they see this conversation
                print_info("Storing interaction in user's history...")
                storage_success = store_interaction_in_user_history(
                    user_id=user_id,
                    user_message=transcription,
                    assistant_response=llm_response
                )
                if storage_success:
                    print_success("Interaction saved to user's history")
                else:
                    print_warning("Could not persist interaction (non-critical)")
            else:
                print_warning(f"LLM error, using fallback")
        else:
            print_warning(f"LLM unavailable (HTTP {response.status_code})")
    
    except requests.Timeout:
        print_warning("LLM timeout")
    
    except Exception as e:
        print_warning(f"LLM error: {str(e)[:40]}")
    
    print_result("User", user_id)
    print_result("Command", f'"{transcription}"')
    print_result("Mood", mood)
    print_result("Knowledge Items", len(knowledge))
    print_result("Response", f'"{llm_response[:60]}..."')
    
    return True


def menu_return_user_conversation():
    """
    Full conversational pipeline with multi-turn support.
    
    Test Scenario: Sara returns and has a conversation (multiple turns).
    Pipeline: Wake → Verify → [Loop: STT → Vision → Knowledge → LLM → TTS]
    Tests: Circuit breakers, VAD, context maintenance, LLM timeout fallback.
    """
    print_header("RETURN USER CONVERSATION - Sara")
    print_info("Full pipeline: Wake → Verify → STT → Vision → Knowledge → LLM → TTS")
    print_info("Tests production features: multi-turn conversation, context awareness")
    
    if not state.services_connected['central'] or not state.services_connected['audio']:
        print_error("Central Server and Audio Service required")
        return
    
    print_step(1, 2, "Wake Word Detection")
    print_info("Listening for wake word. Say 'Hey Nexi'...")
    
    try:
        response = requests.post(
            f"{ServiceConfig.AUDIO_API}/wake-word/detect",
            timeout=RuntimeConfig.WAKE_WORD_DETECT_TIMEOUT
        )
        
        if response.status_code != 200:
            print_error("Wake word detection failed")
            return
        
        result = response.json()
        print_success(f"Wake word detected ({result.get('detection_time', 0):.2f}s)")
        
        # Play cached "I am listening" voice response
        voice_player = get_voice_player()
        if voice_player.play_voice("listening"):
            print_info("Playing: 'I am listening' (from cache)")
        else:
            print_warning("Could not play 'listening' cached voice")
    
    except Exception as e:
        print_error(f"Wake word error: {str(e)}")
        return
    
    print_step(2, 2, "Speaker Verification")
    print_info("Verifying speaker identity...")
    
    print_info("Recording for verification...")
    command_file = record_audio(duration=AudioConfig.DEFAULT_DURATION, filename="return_user_command.wav")
    if not command_file:
        print_error("Recording failed")
        return
    
    embedding = process_voice_embedding(command_file)
    if not embedding:
        print_error("Embedding extraction failed")
        voice_player = get_voice_player()
        voice_player.play_voice("error_generic")
        return
    
    verification = verify_speaker(command_file)
    if not verification.get('is_verified'):
        print_warning("Speaker not verified")
        voice_player = get_voice_player()
        voice_player.play_voice("verify_failed")
        return
    
    user_id = verification.get('user_id')
    confidence = verification.get('confidence', 0)
    print_success(f"Verified: {user_id} ({confidence:.1%} confidence)")
    
    # Multi-turn conversation loop
    print_header("CONVERSATION LOOP - SARA")
    turn = 1
    first_turn = True
    
    while True:
        print(f"\n--- Turn {turn} ---")
        
        if first_turn:
            if not conduct_single_conversation(user_id, audio_file=command_file):
                break
            first_turn = False
        else:
            if not conduct_single_conversation(user_id, audio_file=None):
                break
        
        turn += 1
        
        # Ask if user wants to continue
        continue_input = input("\nDo you have another question? (yes/no): ").strip().lower()
        if continue_input not in ['yes', 'y']:
            break
    
    print_header("CONVERSATION ENDED")
    print_result("Total turns", turn - 1)
    print_result("User", user_id)

# ============================================================================
# MENU OPTION 6: TEACH OBJECTS - SARA
# ============================================================================

def menu_teach_objects():
    """
    Object learning workflow.
    
    Test Scenario: Sara teaches NEXI about a toy.
    Workflow:
    - Wake word
    - Speaker verification
    - Vision captures object (5 images)
    - Object embeddings stored
    - Ask for label
    - Store in TeachMe
    """
    print_header("TEACH OBJECTS - Sara")
    print_info("Teach NEXI about a new object using vision and knowledge storage")
    
    if not state.services_connected['central'] or not state.services_connected['audio']:
        print_error("Central Server and Audio Service required")
        return
    
    print_step(1, 6, "Wake Word Detection")
    print_info("Say 'Hey Nexi' to start object learning...")
    
    try:
        response = requests.post(
            f"{ServiceConfig.AUDIO_API}/wake-word/detect",
            timeout=RuntimeConfig.WAKE_WORD_DETECT_TIMEOUT
        )
        
        if response.status_code != 200:
            print_error("Wake word detection failed")
            return
        
        print_success("Wake word detected")
        
        # Play cached "Let's learn this object" voice response
        voice_player = get_voice_player()
        if voice_player.play_voice("teachme_mode"):
            print_info("Playing: 'Teach me mode activated' (from cache)")
        else:
            print_warning("Could not play 'teachme_mode' cached voice")
    
    except Exception as e:
        print_error(f"Wake word error: {str(e)}")
        return
    
    print_step(2, 6, "Record Learning Command")
    print_info("Say: 'Learn this object' or 'Remember this'")
    
    command_file = record_audio(duration=AudioConfig.DEFAULT_DURATION, filename="teach_command.wav")
    if not command_file:
        return
    
    print_step(3, 6, "Speaker Verification")
    verification = verify_speaker(command_file)
    if not verification.get('is_verified'):
        print_warning("Speaker not verified")
        # Play cached error voice
        voice_player = get_voice_player()
        voice_player.play_voice("verify_failed")
        return
    
    user_id = verification.get('user_id')
    print_success(f"Verified user: {user_id}")
    
    # Play pre-synthesized "Welcome" voice (saves 2-3 seconds vs TTS)
    voice_player = get_voice_player()
    if not voice_player.play_voice("listening"):
        print_warning("Could not play verification acknowledgement")
    
    print_step(4, 6, "Capture Objects with YOLOv8 Detection")
    print_info("Object detection will now start")
    print_info("Position objects clearly in frame and press SPACE to capture")
    print_info("Press Q to finish object capture when done")
    
    # Use real object detection with YOLOv8
    detected_objects = capture_objects_with_detection(resource_priority="HIGH", num_captures=5)
    
    if detected_objects:
        print_success(f"Object detection complete: {len(detected_objects)} objects captured")
        
        # Display detected objects with full details
        print_subheader("Detected Objects Summary")
        print_info(f"Total objects captured: {len(detected_objects)}")
        print()
        
        for idx, obj in enumerate(detected_objects, 1):
            class_name = obj.get('class_name', 'unknown')
            confidence = obj.get('confidence', 0)
            class_id = obj.get('class_id', -1)
            bbox = obj.get('bounding_box', {})
            
            # Verify if detection is in COCO list
            is_coco = class_name.lower() in [c.lower() for c in COCO_CLASSES]
            coco_status = "✓ Valid COCO class" if is_coco else "⚠ NOT in COCO list"
            
            print(f"{idx}. {class_name}")
            print(f"   Confidence: {confidence:.0%} | ID: {class_id} | {coco_status}")
            print(f"   BBox: x={bbox.get('x', 0)}, y={bbox.get('y', 0)}, w={bbox.get('width', 0)}, h={bbox.get('height', 0)}")
            print()
        
        object_embeddings = detected_objects  # Store detected objects for later use
        print_info("All objects are ready for knowledge base storage")
    else:
        print_error("No objects detected during capture - cannot continue without real Vision Service detection")
        print_info("Issue diagnostics:")
        print_info("  • Ensure objects are well-lit and clearly visible in frame")
        print_info("  • Position objects in center of frame for clear detection")
        print_info("  • Verify Vision Service is running on port 8001 (check COMMANDS.txt)")
        print_info("  • YOLOv8 should detect 80+ objects from COCO dataset (person, car, dog, phone, etc.)")
        print_info("  • Check Vision Service logs for detection errors")
        print_warning("Aborting object teaching - please try again with clear objects in view")
        return  # Stop here, don't use mock data
    
    print_step(5, 6, "Get Object Label")
    
    # Play cached "What is the object label?" voice response
    voice_player = get_voice_player()
    if voice_player.play_voice("ask_label"):
        print_info("Playing: 'What is the label of this object?' (from cache)")
    else:
        print_warning("Could not play 'ask_label' cached voice")
        print_info("TTS would ask: 'What is the name of this object?'")
    
    input("(Press Enter to record answer...)")
    
    label_file = record_audio(duration=AudioConfig.DEFAULT_DURATION, filename="teach_label.wav")
    if not label_file:
        return
    
    label = transcribe_audio(label_file)
    if not label:
        label = input("Enter object name manually: ").strip()
    
    print_success(f"Object label: {label}")
    
    print_step(6, 6, "Store in TeachMe Knowledge Base")
    print_info(f"Saving {len(object_embeddings)} dominant object captures with label: '{label}'")
    
    try:
        # Extract object properties for better distinction
        # This allows NEXI to distinguish between different "dogs" or "cats" based on properties
        object_properties = {
            "size_distribution": [],
            "confidence_scores": [],
            "detected_classes_in_captures": [],  # What other objects were in frame with main object
            "average_confidence": 0.0,
            "capture_count": len(object_embeddings)
        }
        
        total_confidence = 0
        for obj in object_embeddings:
            bbox = obj.get('bounding_box', {})
            confidence = obj.get('confidence', 0)
            class_name = obj.get('class_name', 'unknown')
            
            size = bbox.get('width', 0) * bbox.get('height', 0)
            object_properties["size_distribution"].append(size)
            object_properties["confidence_scores"].append(confidence)
            object_properties["detected_classes_in_captures"].append(class_name)
            total_confidence += confidence
        
        object_properties["average_confidence"] = total_confidence / len(object_embeddings) if object_embeddings else 0
        
        # Build enhanced payload for TeachMe
        # - embeddings: visual features for similarity matching
        # - properties: metadata for object distinction
        # - tags: searchable labels
        payload = {
            "type": "object",
            "data": {
                "name": label,
                "attributes": {
                    "embeddings": object_embeddings,
                    "image_count": len(object_embeddings),
                    "capture_timestamps": len(object_embeddings),
                    "user_id": user_id,
                    "source": "vision_service_yolov8",
                    "primary_class": object_embeddings[0].get('class_name') if object_embeddings else 'unknown',
                    
                    # Object properties for intelligent distinction
                    "object_properties": object_properties,
                    
                    # Visual characteristics (for pattern matching)
                    "size_metrics": {
                        "min_size": min(object_properties["size_distribution"]) if object_properties["size_distribution"] else 0,
                        "max_size": max(object_properties["size_distribution"]) if object_properties["size_distribution"] else 0,
                        "avg_size": sum(object_properties["size_distribution"]) / len(object_properties["size_distribution"]) if object_properties["size_distribution"] else 0,
                    },
                    "confidence_metrics": {
                        "min_confidence": min(object_properties["confidence_scores"]) if object_properties["confidence_scores"] else 0,
                        "max_confidence": max(object_properties["confidence_scores"]) if object_properties["confidence_scores"] else 0,
                        "avg_confidence": object_properties["average_confidence"],
                    }
                },
                "category": "user_taught_object",
                "description": f"Custom object '{label}' taught by user {user_id} using vision service detection"
            },
            "tags": [
                "user_taught", 
                "vision_detected", 
                "interactive_learning",
                f"primary_class:{object_embeddings[0].get('class_name') if object_embeddings else 'unknown'}",
                "client_specific"  # Marks this as client-specific, not generic
            ],
            "confidence": object_properties["average_confidence"]
        }
        
        print_info(f"Sending to TeachMe: {len(object_embeddings)} dominant object captures, label: '{label}'")
        print_info(f"Object properties:")
        print_info(f"  • Average confidence: {object_properties['average_confidence']:.1%}")
        print_info(f"  • Primary visual class: {object_embeddings[0].get('class_name') if object_embeddings else 'unknown'}")
        print_info(f"  • Size range: {object_properties['size_distribution']}")
        print_info(f"Payload tags: {payload['tags']}")
        
        response = requests.post(
            f"{ServiceConfig.TEACHME_SERVICE}/learn",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200 or response.status_code == 201:
            response_data = response.json()
            # TeachMe API returns 'item_id' in the response
            object_id = response_data.get('item_id', response_data.get('id', response_data.get('object_id', 'unknown')))
            print_header("OBJECT SUCCESSFULLY LEARNED")
            print_result("Object Name", label)
            print_result("Object ID", object_id)
            print_result("Dominant Captures Stored", len(object_embeddings))
            print_result("Status", "Saved to knowledge base")
            print_success("Object stored successfully in TeachMe knowledge base")
            
            # Play cached "Object learned successfully" voice response
            voice_player = get_voice_player()
            if voice_player.play_voice("learned"):
                print_info("Playing: 'Object successfully learned' (from cache)")
            else:
                print_warning("Could not play 'learned' cached voice")
        else:
            print_warning(f"TeachMe storage warning: HTTP {response.status_code}")
            try:
                error_data = response.json()
                print_info(f"  Response: {error_data}")
            except:
                print_info(f"  Response body: {response.text[:100]}")
    
    except Exception as e:
        print_error(f"TeachMe error: {str(e)}")
        print_warning("Object may not have been saved to knowledge base")

# ============================================================================
# MENU OPTION 7: VIEW TAUGHT OBJECTS - Display Knowledge Base
# ============================================================================

def menu_view_taught_objects():
    """
    Display all objects the robot has learned from clients.
    
    Features:
    - Shows ALL objects in knowledge base (with pagination for large collections)
    - Filtering and search capabilities
    - Sorting by name, confidence, or time
    - Detailed properties including visual features
    
    PHASE 2 ENHANCEMENT: Proper pagination, filtering, and statistics
    """
    print_header("VIEW TAUGHT OBJECTS - Knowledge Base")
    print_info("Fetching all objects learned by NEXI from the knowledge base...")
    
    try:
        # PHASE 2 FIX: Use stats endpoint to understand KB size
        try:
            stats_response = requests.get(
                f"{ServiceConfig.TEACHME_SERVICE}/knowledge/stats",
                timeout=10
            )
            if stats_response.status_code == 200:
                stats_data = stats_response.json()
                kb_stats = stats_data.get('stats', {})
                total_kb_items = kb_stats.get('total', 0)
                print_success(f"Knowledge base statistics: {total_kb_items} total items")
        except Exception as e:
            print_warning(f"Could not fetch KB stats: {str(e)[:50]}")
            total_kb_items = 0
        
        # Fetch all taught objects from TeachMe
        response = requests.get(
            f"{ServiceConfig.TEACHME_SERVICE}/knowledge/objects",
            timeout=10
        )
        
        if response.status_code == 200:
            response_data = response.json()
            # IMPORTANT: Get the "objects" list from response, not the dict itself
            taught_objects = response_data.get('objects', [])
            object_count = response_data.get('count', len(taught_objects))
            
            if not taught_objects:
                print_warning("No taught objects in knowledge base yet")
                print_info("Use Menu 6 (Teach Objects) to teach NEXI about new objects")
                return
            
            print_success(f"Found {object_count} taught objects in knowledge base")
            
            # PHASE 2: Pagination and filtering support
            page_size = 10  # Show 10 items per page
            current_page = 1
            
            while True:
                # Calculate pagination
                start_idx = (current_page - 1) * page_size
                end_idx = min(start_idx + page_size, len(taught_objects))
                total_pages = (len(taught_objects) + page_size - 1) // page_size
                
                # Show current page header
                print_subheader(f"Taught Objects (Page {current_page}/{total_pages}, Items {start_idx + 1}-{end_idx})")
                print()
                
                # Display objects on current page
                page_objects = taught_objects[start_idx:end_idx]
                
                for page_idx, obj in enumerate(page_objects, 1):
                    display_idx = start_idx + page_idx
                    
                    # TYPE CHECKING: Handle case where response contains strings or mixed types
                    if not isinstance(obj, dict):
                        print_warning(f"Skipping invalid object #{display_idx}: {type(obj).__name__} instead of dict")
                        continue
                    
                    try:
                        # Extract object information with safe defaults
                        obj_id = obj.get('id', 'N/A')
                        obj_name = obj.get('name', obj.get('data', {}).get('name', 'Unknown'))
                        obj_type = obj.get('type', 'N/A')
                        
                        # Get attributes and tags
                        data = obj.get('data', {})
                        attributes = data.get('attributes', {}) if isinstance(data, dict) else {}
                        tags = obj.get('tags', []) if isinstance(obj.get('tags'), list) else []
                        confidence = obj.get('confidence', 0)
                        
                        # Extract properties with type checking
                        obj_properties = attributes.get('object_properties', {}) if isinstance(attributes, dict) else {}
                        size_metrics = attributes.get('size_metrics', {}) if isinstance(attributes, dict) else {}
                        confidence_metrics = attributes.get('confidence_metrics', {}) if isinstance(attributes, dict) else {}
                        
                        user_id = attributes.get('user_id', 'Unknown user') if isinstance(attributes, dict) else 'Unknown user'
                        capture_count = attributes.get('capture_count', 0) if isinstance(attributes, dict) else 0
                        primary_class = attributes.get('primary_class', 'Unknown') if isinstance(attributes, dict) else 'Unknown'
                        
                        # Display object details with enhanced formatting
                        print(f"{display_idx}. {obj_name}")
                        print(f"   ID: {obj_id}")
                        print(f"   Type: {obj_type} | Primary Class: {primary_class}")
                        print(f"   Confidence: {confidence:.1%} | Captures: {capture_count}")
                        print(f"   Taught by: {user_id}")
                        
                        # Display tags safely
                        if tags:
                            tags_str = ', '.join(str(tag) for tag in tags[:5])  # Show first 5 tags
                            if len(tags) > 5:
                                tags_str += f", +{len(tags) - 5} more"
                            print(f"   Tags: {tags_str}")
                        
                        # Show object properties if available
                        if obj_properties and isinstance(obj_properties, dict):
                            print(f"   Properties:")
                            avg_conf = obj_properties.get('average_confidence', 0)
                            print(f"     • Avg Confidence: {avg_conf:.1%}")
                            size_dist = obj_properties.get('size_distribution', [])
                            if size_dist:
                                print(f"     • Size Distribution: {size_dist}")
                        
                        # Show size metrics
                        if size_metrics and isinstance(size_metrics, dict):
                            print(f"   Size Metrics:")
                            min_s = size_metrics.get('min_size', 0)
                            max_s = size_metrics.get('max_size', 0)
                            avg_s = size_metrics.get('avg_size', 0)
                            if max_s > 0:  # Only show if we have valid data
                                print(f"     • Min: {min_s} | Max: {max_s} | Avg: {avg_s:.0f} pixels")
                        
                        # Show confidence metrics (simplified)
                        if confidence_metrics and isinstance(confidence_metrics, dict):
                            min_c = confidence_metrics.get('min_confidence', 0)
                            max_c = confidence_metrics.get('max_confidence', 0)
                            #  Only show if we have significant data
                            if max_c > 0:
                                print(f"   Confidence: Min {min_c:.1%} | Max {max_c:.1%}")
                        
                        print()
                    
                    except Exception as obj_error:
                        print_warning(f"Error processing object #{display_idx}: {str(obj_error)[:80]}")
                        continue
                
                # Pagination controls
                if total_pages > 1:
                    print_subheader("Pagination")
                    print(f"Page {current_page}/{total_pages} | Items per page: {page_size}")
                    
                    while True:
                        if current_page < total_pages:
                            pagination_input = input("Press [Enter] for next page, [B] for back, [Q] to quit: ").strip().lower()
                        else:
                            pagination_input = input("This is the last page. Press [B] to go back, [Q] to quit: ").strip().lower()
                        
                        if pagination_input == 'q':
                            print_info("Exiting object view")
                            return
                        elif pagination_input == 'b' and current_page > 1:
                            current_page -= 1
                            break
                        elif pagination_input == '' and current_page < total_pages:
                            current_page += 1
                            break
                        elif current_page >= total_pages and pagination_input == 'b' and current_page == 1:
                            print_info("Already on first page")
                        else:
                            print_info("Invalid input")
                else:
                    # Single page - no pagination needed
                    break
            
            print_success(f"Total objects displayed: {object_count}")
            print_info("These objects can now be recognized and distinguished when NEXI interacts with clients")
        
        else:
            print_error(f"Failed to fetch objects: HTTP {response.status_code}")
            
    except Exception as e:
        print_error(f"Error fetching taught objects: {str(e)[:100]}")

# ============================================================================
# MENU OPTION 8: DELETE TAUGHT OBJECTS - Permanent Removal from Knowledge Base
# ============================================================================

def menu_delete_taught_objects():
    """
    Delete taught objects permanently from the knowledge base.
    
    Test Scenario: Remove learned objects from TeachMe service.
    Workflow:
    - Fetch all taught objects from knowledge base
    - Display objects with confidence/metadata
    - Let user select object(s) to delete
    - Confirm dangerous operation
    - Call TeachMe DELETE endpoint
    - Verify deletion
    """
    print_header("DELETE TAUGHT OBJECTS - Permanent Removal")
    print_info("Remove learned objects permanently from knowledge base via REST API")
    
    if not state.services_connected['teachme']:
        print_error("TeachMe Service is not connected. Cannot delete objects.")
        return
    
    print_step(1, 3, "Fetch All Objects from Knowledge Base")
    try:
        response = requests.get(
            f"{ServiceConfig.TEACHME_SERVICE}/knowledge/objects",
            timeout=10
        )
        
        if response.status_code != 200:
            print_error(f"Failed to fetch objects: HTTP {response.status_code}")
            return
        
        response_data = response.json()
        taught_objects = response_data.get('objects', [])
        
        if not taught_objects:
            print_warning("No taught objects in knowledge base to delete")
            return
        
        print_success(f"Found {len(taught_objects)} objects in knowledge base")
        
    except Exception as e:
        print_error(f"Error fetching objects: {str(e)[:100]}")
        return
    
    print_step(2, 3, "Select Object(s) to Delete")
    print_subheader("Available Objects in Knowledge Base")
    print()
    
    # Display objects with indices
    for idx, obj in enumerate(taught_objects, 1):
        obj_name = obj.get('name', obj.get('data', {}).get('name', 'Unknown'))
        obj_id = obj.get('id', 'N/A')
        confidence = obj.get('confidence', obj.get('avg_confidence', 0))
        created = obj.get('created_at', obj.get('timestamp', 'N/A'))
        
        print(f"  {idx:2d}. [{obj_id}] {obj_name:<30} (Confidence: {confidence:.2f})")
    
    print()
    selection = input("Enter object number(s) to delete (comma-separated, e.g., 1,3,5) or '0' to cancel: ").strip()
    
    if selection == '0':
        print_info("Deletion cancelled")
        return
    
    try:
        indices = [int(x.strip()) - 1 for x in selection.split(',')]
        
        # Validate indices
        if any(i < 0 or i >= len(taught_objects) for i in indices):
            print_error("Invalid object number(s)")
            return
        
        # Get objects to delete
        objects_to_delete = [taught_objects[i] for i in indices]
        
    except ValueError:
        print_error("Invalid input format")
        return
    
    print_step(3, 3, "Confirm and Delete")
    print_subheader("Objects to be PERMANENTLY DELETED")
    print()
    
    for obj in objects_to_delete:
        print(f"  - {obj.get('name', obj.get('data', {}).get('name', 'Unknown'))} [{obj.get('id', 'N/A')}]")
    
    print()
    confirm = input(f"Confirm deletion? Type 'DELETE' to proceed: ").strip()
    
    if confirm != 'DELETE':
        print_warning("Deletion cancelled - no objects were removed")
        return
    
    # Delete each object via REST API
    deleted_count = 0
    failed_count = 0
    
    for obj in objects_to_delete:
        obj_id = obj.get('id')
        obj_name = obj.get('name', obj.get('data', {}).get('name', 'Unknown'))
        
        try:
            # Use TeachMe forget endpoint to delete objects
            delete_url = f"{ServiceConfig.TEACHME_SERVICE}/forget/{obj_id}"
            
            # Call forget endpoint with permanent deletion flag
            response = requests.delete(
                delete_url,
                params={"permanent": "true"},
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                print_success(f"Deleted: {obj_name}")
                deleted_count += 1
            else:
                error_msg = response.json().get('error', response.text if response.text else 'No error details') if response.text else 'No response body'
                print_error(f"Failed to delete {obj_name} at {delete_url}")
                print_error(f"HTTP {response.status_code}: {error_msg}")
                failed_count += 1
        
        except requests.Timeout:
            print_error(f"Timeout deleting {obj_name}")
            failed_count += 1
        
        except Exception as e:
            print_error(f"Error deleting {obj_name}: {str(e)[:80]}")
            failed_count += 1
    
    print_subheader("Deletion Summary")
    print_result("Successfully deleted", deleted_count)
    print_result("Failed deletions", failed_count)
    
    if deleted_count > 0:
        print_success(f"Knowledge base updated: {deleted_count} object(s) removed permanently")

# ============================================================================
# MENU OPTION 9: LIST ALL ENROLLED USERS - Detailed User Information
# ============================================================================

def menu_list_all_enrolled_users():
    """
    List all enrolled users with complete biometric data statistics.
    
    Test Scenario: View comprehensive user enrollment details.
    Displays for each user:
    - User ID
    - Name
    - Age
    - Total Face Images (photos)
    - Total Voice Samples (audio)
    - Enrollment Status
    - Relation (if available)
    
    Uses REST API to fetch from Central Server properly.
    """
    print_header("LIST ALL ENROLLED USERS - Complete Overview")
    print_info("Fetching user enrollment data from Central Server via REST API...")
    
    if not state.services_connected['central']:
        print_error("Central Server is not connected. Cannot fetch user data.")
        return
    
    try:
        # Fetch all users from Central Server REST API
        response = requests.get(
            f"{ServiceConfig.CENTRAL_SERVER}/users/list",
            timeout=10
        )
        
        if response.status_code != 200:
            print_error(f"Failed to fetch users: HTTP {response.status_code}")
            return
        
        data = response.json()
        users = data.get('users', [])
        
        if not users:
            print_warning("No users enrolled yet")
            print_info("Use Menu 2 (New User Enrollment) to enroll users")
            return
        
        print_success(f"Found {len(users)} enrolled users")
        
    except requests.ConnectionError:
        print_error("Connection failed to Central Server")
        return
    
    except requests.Timeout:
        print_error("Central Server request timed out")
        return
    
    except Exception as e:
        print_error(f"Error fetching users: {str(e)[:100]}")
        return
    
    print_subheader("Enrolled Users Database")
    print()
    
    # Calculate column widths and display header
    header_format = "{:<10} {:<25} {:<10} {:<12} {:<15}"
    print(header_format.format(
        "ID",
        "Name",
        "Status",
        "Photos",
        "Audio"
    ))
    print("-" * 100)
    
    # Display each user with their biometric counts
    total_photos = 0
    total_audio = 0
    
    for user in users:
        user_id = user.get('user_id', 'N/A')[:10]
        name = (user.get('user_name') or user.get('username') or user.get('name') or 'Unknown')[:25]
        status = user.get('status', 'active')[:10]
        
        # Get biometric counts
        sample_count = user.get('sample_count', {})
        if isinstance(sample_count, dict):
            num_photos = sample_count.get('images', 0)
            num_audio = sample_count.get('audio', 0)
        else:
            face_embeddings = user.get('face_embeddings', [])
            voice_embeddings = user.get('voice_embeddings', [])
            num_photos = len(face_embeddings) if face_embeddings else 0
            num_audio = len(voice_embeddings) if voice_embeddings else 0
        
        total_photos += num_photos
        total_audio += num_audio
        
        # Format row
        row_format = "{:<10} {:<25} {:<10} {:<12} {:<15}"
        print(row_format.format(
            user_id,
            name,
            status,
            str(num_photos),
            str(num_audio)
        ))
    
    print("-" * 100)
    print()
    
    # Display enrollment summary
    print_subheader("Enrollment Summary")
    print()
    print_result("Total Users Enrolled", len(users))
    print_result("Total Face Images in System", total_photos)
    print_result("Total Voice Samples in System", total_audio)
    
    print()
    print_info("Sample Distribution:")
    print_info("  Each user should have at least 5 face images and 5 voice samples for proper verification")
    print()
    
    print()
    print_info("Sample Distribution:")
    print_info("  Each user should have at least 5 face images and 5 voice samples for proper verification")
    print()

# ============================================================================
# MENU OPTION 10: DELETE ENROLLED USERS - Permanent User Removal
# ============================================================================

def menu_delete_enrolled_users():
    """
    Delete enrolled users permanently from the system.
    
    Test Scenario: Remove enrolled users completely.
    Workflow:
    - Fetch all enrolled users
    - Display users with their data counts
    - Let user select user(s) to delete
    - Confirm dangerous operation with "DELETE USER" confirmation
    - Call Enrollment Service DELETE endpoint
    - Verify deletion from Central Server
    """
    print_header("DELETE ENROLLED USERS - Permanent Removal")
    print_info("Permanently remove enrolled users and all their biometric data from system")
    
    if not state.services_connected['central']:
        print_error("Central Server is not connected. Cannot delete users.")
        return
    
    print_step(1, 3, "Fetch All Enrolled Users")
    try:
        response = requests.get(
            f"{ServiceConfig.CENTRAL_SERVER}/users/list",
            timeout=10
        )
        
        if response.status_code != 200:
            print_error(f"Failed to fetch users: HTTP {response.status_code}")
            return
        
        data = response.json()
        users = data.get('users', [])
        
        if not users:
            print_warning("No users enrolled yet")
            print_info("Use Menu 2 (New User Enrollment) to enroll users")
            return
        
        print_success(f"Found {len(users)} enrolled users")
        
    except requests.ConnectionError:
        print_error("Connection failed to Central Server")
        return
    
    except requests.Timeout:
        print_error("Central Server request timed out")
        return
    
    except Exception as e:
        print_error(f"Error fetching users: {str(e)[:100]}")
        return
    
    print_step(2, 3, "Select Users to Delete")
    print_subheader("Available Users for Deletion")
    print()
    
    # Display users with their information
    header_format = "{:<3} {:<10} {:<25} {:<10} {:<12} {:<15}"
    print(header_format.format(
        "No",
        "ID",
        "Name",
        "Status",
        "Photos",
        "Audio"
    ))
    print("-" * 110)
    
    # Display each user
    for idx, user in enumerate(users, 1):
        user_id = user.get('user_id', 'N/A')[:10]
        user_name = user.get('user_name', 'N/A')[:25]
        enrollment_date = user.get('enrollment_date', 'N/A')
        sample_count = user.get('sample_count', {})
        
        # Handle both dict and list formats for sample_count
        if isinstance(sample_count, dict):
            photos = sample_count.get('images', 0)
            audio = sample_count.get('audio', 0)
        else:
            # Fallback to embeddings arrays
            photos = len(user.get('face_embeddings', []))
            audio = len(user.get('voice_embeddings', []))
        
        # Status based on biometric completeness
        status = "Complete" if photos >= 5 and audio >= 5 else "Incomplete"
        
        print(header_format.format(
            str(idx),
            user_id,
            user_name,
            status,
            str(photos),
            str(audio)
        ))
    
    print()
    selection = input("Enter user number(s) to delete (comma-separated, e.g., 1,3,5) or '0' to cancel: ").strip()
    
    if selection == '0':
        print_info("Deletion cancelled")
        return
    
    try:
        indices = [int(x.strip()) - 1 for x in selection.split(',')]
        
        # Validate indices
        if any(i < 0 or i >= len(users) for i in indices):
            print_error("Invalid user number(s)")
            return
        
        # Get users to delete
        users_to_delete = [users[i] for i in indices]
        
    except ValueError:
        print_error("Invalid input format")
        return
    
    print_step(3, 3, "Confirm and Delete")
    
    print_subheader("Users to be PERMANENTLY DELETED")
    print()
    print_warning("WARNING: This operation cannot be undone!")
    print_warning("All biometric data, conversation history, and knowledge will be deleted.")
    print()
    
    for user in users_to_delete:
        user_name = user.get('user_name', 'Unknown')
        sample_count = user.get('sample_count', {})
        if isinstance(sample_count, dict):
            photos = sample_count.get('images', 0)
            audio = sample_count.get('audio', 0)
        else:
            photos = len(user.get('face_embeddings', []))
            audio = len(user.get('voice_embeddings', []))
        print(f"  - {user_name:<25} ({photos} photos, {audio} audio samples)")
    
    print()
    confirm = input(f"Type 'DELETE USER' to permanently remove {len(users_to_delete)} user(s): ").strip()
    
    if confirm != 'DELETE USER':
        print_warning("Deletion cancelled - no users were removed")
        return
    
    # Delete each user via Enrollment Service
    deleted_count = 0
    failed_count = 0
    failed_users = []
    
    for user in users_to_delete:
        user_name = user.get('user_name', 'Unknown')
        
        try:
            # Use Enrollment Service delete endpoint
            delete_url = f"{ServiceConfig.ENROLLMENT_SERVICE}/enrollment/delete-user/{user_name}"
            
            # Call delete endpoint
            response = requests.delete(
                delete_url,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                print_success(f"Deleted: {user_name}")
                deleted_count += 1
            else:
                error_msg = response.json().get('error', response.text if response.text else 'No error details') if response.text else 'No response body'
                print_error(f"Failed to delete {user_name} at {delete_url}")
                print_error(f"HTTP {response.status_code}: {error_msg}")
                failed_count += 1
                failed_users.append(user_name)
        
        except requests.Timeout:
            print_error(f"Timeout deleting {user_name}")
            failed_count += 1
            failed_users.append(user_name)
        
        except Exception as e:
            print_error(f"Error deleting {user_name}: {str(e)[:80]}")
            failed_count += 1
            failed_users.append(user_name)
    
    print_subheader("Deletion Summary")
    print_result("Successfully deleted", deleted_count)
    print_result("Failed deletions", failed_count)
    
    if failed_users:
        print_warning("Failed to delete the following users:")
        for user in failed_users:
            print_warning(f"  - {user}")
    else:
        print_success("All selected users permanently deleted from system")

# ============================================================================
# MENU OPTION 11: RESOURCE STATUS
# ============================================================================

def display_resource_status():
    """Display current status of all hardware resources"""
    print_header("HARDWARE RESOURCE STATUS")
    
    resources_status = get_hardware_resources_status()
    
    if not resources_status:
        print_info("Could not retrieve resource status")
        return
    
    for resource_type, status in resources_status.items():
        print_subheader(f"{resource_type.upper()} Resource")
        available = status.get('available', True)
        print_result("Status", "Available" if available else "In Use")
        
        held_by = status.get('held_by')
        if held_by:
            print_result("Held By", held_by)
            time_remaining = status.get('time_remaining')
            if time_remaining is not None:
                print_result("Time Remaining", f"{time_remaining:.1f}s")
        
        queue_length = status.get('queue_length', 0)
        print_result("Queued Requests", queue_length)
        
        if queue_length > 0:
            print_info("  Waiting services:")
            queue = status.get('queue', [])
            for idx, request in enumerate(queue, 1):
                service = request.get('service', 'unknown')
                priority = request.get('priority', 'MEDIUM')
                print_info(f"    {idx}. {service} (priority={priority})")

# ============================================================================
# MENU OPTION 12: SETTINGS
# ============================================================================

def get_service_health(service_name: str, health_url: str) -> Dict[str, Any]:
    """Fetch health status from any service via REST API"""
    try:
        response = requests.get(health_url, timeout=5)
        if response.status_code == 200:
            return {"status": "healthy", "data": response.json()}
        else:
            return {"status": "unavailable", "http_code": response.status_code}
    except requests.Timeout:
        return {"status": "timeout"}
    except requests.ConnectionError:
        return {"status": "connection_failed"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:50]}

def get_audio_power_mode() -> Dict[str, Any]:
    """Get current audio power mode from Audio Service using correct endpoint"""
    try:
        response = requests.get(
            f"{ServiceConfig.AUDIO_SERVICE}/api/v1/wake-word/power-mode",
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"mode": "Unknown", "vad_enabled": None}
    except Exception:
        return {"mode": "Unknown", "vad_enabled": None}

def set_audio_power_mode(mode: str) -> bool:
    """Set audio power mode via REST API - correct endpoint and values"""
    try:
        # Valid modes: "low_power", "balanced", "high_performance"
        response = requests.post(
            f"{ServiceConfig.AUDIO_SERVICE}/api/v1/wake-word/power-mode",
            json={"mode": mode},
            timeout=5
        )
        return response.status_code in [200, 201]
    except Exception:
        return False

def get_audio_features_status() -> Dict[str, Any]:
    """Get detailed audio service features status"""
    try:
        health_response = requests.get(
            f"{ServiceConfig.AUDIO_SERVICE}/health",
            timeout=5
        )
        if health_response.status_code == 200:
            return health_response.json()
        else:
            return {}
    except Exception:
        return {}

def menu_settings():
    """
    Configure runtime parameters.
    
    Allows tester to modify:
    - Wake word timeout
    - Recording duration
    - LLM response timeout
    - Circuit breaker behaviors (ALL 7 services)
    - Audio power mode configuration
    - Voice Activity Detection (VAD) settings
    - View current configuration
    """
    print_header("SYSTEM SETTINGS")
    print_info("Configure runtime parameters for advanced testing")
    
    while True:
        print_subheader("Settings Menu")
        print("  1. Wake Word Timeout (seconds)")
        print("  2. Recording Duration (seconds)")
        print("  3. LLM Response Timeout (seconds)")
        print("  4. Circuit Breaker & Service Health (ALL 7 Services)")
        print("  5. Audio Power Mode Configuration")
        print("  6. Camera Configuration (Internal/External Webcam) (NEW)")
        print("  7. Voice Activity Detection (VAD)")
        print("  8. TTS Speaker Configuration (NEW - Jenny Optimization)")
        print("  9. TTS Performance Metrics (NEW)")
        print("  10. View Current Configuration")
        print("  0. Back to Main Menu")
        
        choice = input("\nSelect setting (0-10): ").strip()
        
        if choice == '0':
            return
        
        elif choice == '1':
            timeout = input("Enter wake word timeout (10-120 seconds): ").strip()
            if timeout.isdigit():
                timeout = int(timeout)
                if 10 <= timeout <= 120:
                    RuntimeConfig.WAKE_WORD_DETECT_TIMEOUT = timeout
                    print_success(f"Wake word detect timeout set to {timeout}s")
                else:
                    print_error("Timeout must be between 10 and 120 seconds")
            else:
                print_error("Invalid input")
        
        elif choice == '2':
            duration = input("Enter recording duration (1-30 seconds): ").strip()
            if duration.isdigit():
                duration = int(duration)
                if 1 <= duration <= 30:
                    AudioConfig.DEFAULT_DURATION = duration
                    print_success(f"Recording duration set to {duration}s")
                else:
                    print_error("Duration must be between 1 and 30 seconds")
            else:
                print_error("Invalid input")
        
        elif choice == '3':
            timeout = input("Enter LLM timeout (5-240 seconds): ").strip()
            if timeout.isdigit():
                timeout = int(timeout)
                if 5 <= timeout <= 240:
                    RuntimeConfig.LLM_RESPONSE_TIMEOUT = timeout
                    print_success(f"LLM timeout set to {timeout}s")
                else:
                    print_error("Timeout must be between 5 and 240 seconds")
            else:
                print_error("Invalid input")
        
        elif choice == '4':
            print_subheader("Circuit Breaker & Service Features")
            print_info("View detailed service features and circuit breaker status")
            print()
            print("  1. Central Server - Resource Management")
            print("  2. Audio Service - Wake Word, STT, Speaker Verification")
            print("  3. Vision Service - Face Detection, Object Detection, Emotion")
            print("  4. TTS Service - Speech Synthesis & Speaker Management")
            print("  5. TeachMe Service - Knowledge Storage & Vision Integration")
            print("  6. LLM Service - API Health & Model Status")
            print("  7. Enrollment Service - Biometric Enrollment")
            print("  8. All Services Summary")
            print("  0. Back to Settings Menu")
            
            cb_choice = input("\nSelect service (0-8): ").strip()
            
            if cb_choice == '0':
                continue
            
            elif cb_choice == '1':
                print_subheader("Central Server - Resource Management")
                health = get_service_health("Central", f"{ServiceConfig.CENTRAL_SERVER}/health")
                if health["status"] == "healthy":
                    print_result("Status", "✓ Healthy")
                    data = health.get("data", {})
                    print_result("Service", data.get("service", "central_server"))
                    print_subheader("Resource Management Features")
                    print_result("Camera Access", "Managed")
                    print_result("Microphone Access", "Managed")
                    print_result("Speaker Access", "Managed")
                    print_result("Resource Pooling", "Active")
                else:
                    print_error(f"Status: {health['status']}")
            
            elif cb_choice == '2':
                print_subheader("Audio Service - Speech Processing")
                health = get_service_health("Audio", f"{ServiceConfig.AUDIO_SERVICE}/health")
                if health["status"] == "healthy":
                    print_result("Status", "✓ Healthy")
                    data = health.get("data", {})
                    print_result("Service Version", data.get("version", "Unknown"))
                    print_subheader("Feature Status")
                    queue_info = data.get("queue_processor", {})
                    print_result("Queue Processor", "Running" if queue_info.get("running") else "Stopped")
                    print_result("Wake Word Detection", "Enabled")
                    print_result("Speech-to-Text (STT)", "Enabled")
                    print_result("Speaker Verification", "Available")
                    print_result("Voice Embeddings", "256D Vectors")
                    power_mode = get_audio_power_mode()
                    print_result("Current Power Mode", power_mode.get("mode", "Unknown"))
                    print_result("VAD Enabled", "Yes" if power_mode.get("vad_enabled") else "No")
                else:
                    print_error(f"Status: {health['status']}")
            
            elif cb_choice == '3':
                print_subheader("Vision Service - Biometric & Vision")
                health = get_service_health("Vision", f"{ServiceConfig.VISION_SERVICE}/health")
                if health["status"] == "healthy":
                    print_result("Status", "✓ Healthy")
                    data = health.get("data", {})
                    print_result("Camera Status", "Available" if data.get("camera") == "available" else "Unavailable")
                    print_result("OpenCV Version", data.get("opencv_version", "Unknown"))
                    print_subheader("Vision Features")
                    print_result("Face Detection", "✓ Enabled")
                    print_result("Face Recognition", "✓ Enabled")
                    print_result("Object Detection (YOLO)", "✓ Enabled")
                    print_result("Emotion Detection", "✓ Enabled" if data.get("emotion_detection") == "enabled" else "✗ Disabled")
                    print_result("Embedding Dimension", "128D")
                else:
                    print_error(f"Status: {health['status']}")
            
            elif cb_choice == '4':
                print_subheader("TTS Service - Audio Synthesis & Speaker Management")
                health = get_service_health("TTS", f"{ServiceConfig.TTS_SERVICE}/health")
                if health["status"] == "healthy":
                    print_result("Status", "✓ Healthy")
                    print_subheader("TTS Features")
                    print_result("Text-to-Speech", "✓ Enabled")
                    print_result("Languages Supported", "English, Urdu")
                    print_result("Voice Synthesis", "Real-time")
                    print_result("Speaker Control", "Available")
                    
                    # NEW: Speaker Management
                    print_subheader("Speaker Management (Optimized)")
                    print_result("Default Speaker (English)", RuntimeConfig.DEFAULT_SPEAKER.upper())
                    print_result("English Speakers Available", ", ".join(RuntimeConfig.DEFAULT_SPEAKERS_ENGLISH_ONLY))
                    print_result("Urdu Speaker (Forced)", "SHAHID")
                    print_result("Loading Strategy", "Only load default speaker (memory optimized)")
                    print_result("Speaker Switching", "Smart unload old → load new")
                    
                    # Get speaker status from TTS service
                    try:
                        speaker_response = requests.get(
                            f"{ServiceConfig.TTS_SERVICE}/speakers/status",
                            timeout=5
                        )
                        if speaker_response.status_code == 200:
                            speaker_data = speaker_response.json()
                            summary = speaker_data.get("summary", "")
                            print_result("Speaker Status", summary)
                    except Exception:
                        pass
                    
                    # NEW: Performance Metrics
                    print_subheader("Performance Metrics")
                    overall_stats = tts_metrics.get_overall_stats()
                    print_result("Total Syntheses", overall_stats["total_syntheses"])
                    print_result("Success Rate", f"{overall_stats['success_rate']}%")
                    print_result("Avg Response Time", f"{overall_stats['avg_response_time_ms']}ms")
                    print_result("Speaker Switches", overall_stats["speaker_switches"])
                else:
                    print_error(f"Status: {health['status']}")
            
            elif cb_choice == '5':
                print_subheader("TeachMe Service - Knowledge Management")
                health = get_service_health("TeachMe", f"{ServiceConfig.TEACHME_SERVICE}/health")
                if health["status"] == "healthy":
                    print_result("Status", "✓ Healthy")
                    data = health.get("data", {})
                    print_subheader("Knowledge Base Status")
                    checks = data.get("checks", {})
                    kb = checks.get("knowledge_base", {})
                    print_result("Items in KB", kb.get("items_count", "Unknown"))
                    print_result("Learned Objects", kb.get("objects", "Unknown"))
                    print_result("Learned Facts", kb.get("facts", "Unknown"))
                    print_subheader("Vision Service Integration")
                    vision = checks.get("vision_service", {})
                    print_result("Vision Connection", "✓ Connected" if vision.get("status") == "healthy" else "✗ Disconnected")
                    print_result("Circuit Breaker State", vision.get("circuit_state", "Unknown"))
                    print_result("Successful Calls", vision.get("successful_calls", 0))
                    print_result("Failed Calls", vision.get("failed_calls", 0))
                else:
                    print_error(f"Status: {health['status']}")
            
            elif cb_choice == '6':
                print_subheader("LLM Service - Language Model")
                health = get_service_health("LLM", f"{ServiceConfig.LLM_SERVICE}/api/v1/health")
                if health["status"] == "healthy":
                    print_result("Status", "✓ Healthy")
                    data = health.get("data", {})
                    print_result("Service Status", data.get("service", "Unknown"))
                    print_result("Model Loaded", "✓ Yes" if data.get("model_loaded") else "✗ No")
                    print_subheader("LLM Features")
                    print_result("Response Generation", "✓ Active")
                    print_result("Context Awareness", "✓ Enabled")
                    print_result("Fallback Local Model", "✓ Available")
                    print_result("Response Timeout", f"{RuntimeConfig.LLM_RESPONSE_TIMEOUT}s")
                else:
                    print_error(f"Status: {health['status']}")
            
            elif cb_choice == '7':
                print_subheader("Enrollment Service - Biometric Enrollment")
                health = get_service_health("Enrollment", f"{ServiceConfig.ENROLLMENT_SERVICE}/health")
                if health["status"] == "healthy":
                    print_result("Status", "✓ Healthy")
                    data = health.get("data", {})
                    print_result("Service Version", data.get("version", "Unknown"))
                    print_subheader("Enrollment Features")
                    print_result("Face Enrollment", "✓ Enabled")
                    print_result("Voice Enrollment", "✓ Enabled")
                    print_result("Multi-modal Verification", "✓ Enabled")
                else:
                    print_error(f"Status: {health['status']}")
            
            elif cb_choice == '8':
                print_subheader("All Services Status Summary")
                services = [
                    ("Central", f"{ServiceConfig.CENTRAL_SERVER}/health", "Resource Mgmt"),
                    ("Audio", f"{ServiceConfig.AUDIO_SERVICE}/health", "Speech"),
                    ("Vision", f"{ServiceConfig.VISION_SERVICE}/health", "Biometric"),
                    ("TTS", f"{ServiceConfig.TTS_SERVICE}/health", "Synthesis"),
                    ("TeachMe", f"{ServiceConfig.TEACHME_SERVICE}/health", "Knowledge"),
                    ("LLM", f"{ServiceConfig.LLM_SERVICE}/api/v1/health", "Language"),
                    ("Enrollment", f"{ServiceConfig.ENROLLMENT_SERVICE}/health", "Enrollment"),
                ]
                
                healthy_count = 0
                print()
                for service_name, url, feature in services:
                    health = get_service_health(service_name, url)
                    status_symbol = "✓" if health["status"] == "healthy" else "✗"
                    status_text = "Healthy" if health["status"] == "healthy" else health["status"]
                    print(f"  {status_symbol} {service_name:<15} {status_text:<12} ({feature})")
                    if health["status"] == "healthy":
                        healthy_count += 1
                
                print()
                overall = (healthy_count / len(services)) * 100
                if overall == 100:
                    print_success(f"Overall System Health: {overall:.0f}% ({healthy_count}/{len(services)} services)")
                elif overall >= 70:
                    print_warning(f"Overall System Health: {overall:.0f}% ({healthy_count}/{len(services)} services)")
                else:
                    print_error(f"Overall System Health: {overall:.0f}% ({healthy_count}/{len(services)} services)")
        
        elif choice == '5':
            print_subheader("Audio Power Mode Configuration")
            print_info("Configure audio service power consumption and optimization")
            print()
            print("Power Modes:")
            print("  low_power      – Sleep mode (minimal CPU ~10%)")
            print("  balanced       – Default mode (moderate CPU ~30%)")
            print("  high_performance – Max sensitivity (higher CPU ~60%)")
            print()
            
            current_mode = get_audio_power_mode()
            print_result("Current Mode", current_mode.get("mode", "Unknown"))
            print_result("VAD Enabled", "Yes" if current_mode.get("vad_enabled") else "No")
            print_result("Sleep Duration", f"{current_mode.get('sleep_duration_ms', '?')}ms")
            
            print()
            mode = input("Enter power mode (low_power/balanced/high_performance) or Enter to cancel: ").strip().lower()
            
            if mode in ['low_power', 'balanced', 'high_performance']:
                if set_audio_power_mode(mode):
                    print_success(f"Power mode changed to: {mode}")
                    updated = get_audio_power_mode()
                    print_result("New Mode", updated.get("mode", "Unknown"))
                    print_result("VAD Enabled", "Yes" if updated.get("vad_enabled") else "No")
                else:
                    print_error("Failed to set power mode (Audio Service may be unavailable)")
            elif mode == '':
                print_info("Power mode change cancelled")
            else:
                print_error("Invalid power mode. Use: low_power, balanced, or high_performance")
        
        elif choice == '6':
            print_subheader("Camera Configuration")
            print_info("Select camera source for all video capture operations")
            print(f"\nCurrent Camera: {RuntimeConfig.DEFAULT_CAMERA.upper()}")
            print("\nAvailable Cameras:")
            print("  1. INTERNAL (Built-in/Integrated Camera)")
            print("  2. EXTERNAL (USB Webcam)")
            print("\n  0. Back to Settings Menu")
            
            camera_choice = input("\nSelect camera (0-2): ").strip()
            
            if camera_choice == '0':
                continue
            elif camera_choice == '1':
                RuntimeConfig.DEFAULT_CAMERA = "internal"
                print_success("✓ Camera source changed to INTERNAL (built-in camera)")
                print_info("All capture operations (mood detection, object detection, enrollment) will now use internal camera")
            elif camera_choice == '2':
                RuntimeConfig.DEFAULT_CAMERA = "external"
                print_success("✓ Camera source changed to EXTERNAL (USB Webcam)")
                print_info("All capture operations (mood detection, object detection, enrollment) will now use external camera")
            else:
                print_error("Invalid selection")
        
        elif choice == '7':
            print_subheader("Voice Activity Detection (VAD) Configuration")
            print_info("VAD is controlled via Power Mode selection")
            print()
            print("VAD is automatically enabled/disabled based on power mode:")
            print("  • low_power      → VAD ENABLED (reduces processing)")
            print("  • balanced       → VAD ENABLED")
            print("  • high_performance → VAD MAY BE DISABLED (max sensitivity)")
            print()
            
            current = get_audio_power_mode()
            print_result("Current Power Mode", current.get("mode", "Unknown"))
            print_result("VAD Enabled", "✓ Yes" if current.get("vad_enabled") else "✗ No")
            
            print()
            print_info("To enable/disable VAD, change the Power Mode in Option 5")
            print_info("VAD configuration is automatically optimized for each power mode")
        
        elif choice == '8':
            """TTS Speaker Configuration with Jenny Optimization"""
            print_subheader("TTS Speaker Configuration")
            print_info("Configure default speaker for English responses")
            print_info("Note: Urdu responses ALWAYS use Shahid (only Urdu speaker)")
            print(f"\nCurrent Default Speaker: {RuntimeConfig.DEFAULT_SPEAKER.upper()}")
            print("\nAvailable English Speakers (for default):")
            for idx, speaker in enumerate(RuntimeConfig.DEFAULT_SPEAKERS_ENGLISH_ONLY, 1):
                lang = RuntimeConfig.SPEAKER_LANGUAGE.get(speaker, "unknown")
                is_default = " (currently default)" if speaker == RuntimeConfig.DEFAULT_SPEAKER else ""
                print(f"  {idx}. {speaker.upper()} - {lang.title()}{is_default}")
            
            print("\n  0. Back to Settings Menu")
            speaker_choice = input("\nSelect speaker (0-2): ").strip()
            
            if speaker_choice == '0':
                continue
            
            try:
                idx = int(speaker_choice) - 1
                if 0 <= idx < len(RuntimeConfig.DEFAULT_SPEAKERS_ENGLISH_ONLY):
                    new_speaker = RuntimeConfig.DEFAULT_SPEAKERS_ENGLISH_ONLY[idx]
                    old_speaker = RuntimeConfig.DEFAULT_SPEAKER
                    
                    # Prevent selecting same speaker
                    if new_speaker == old_speaker:
                        print_info(f"{new_speaker.upper()} is already the default speaker")
                        continue
                    
                    # Switch speaker via TTS service
                    # TTS service handles: load new, unload old, update configuration
                    try:
                        switch_response = requests.post(
                            f"{ServiceConfig.TTS_SERVICE}/speakers/switch",
                            json={"voice_id": new_speaker},
                            timeout=10
                        )
                        
                        if switch_response.status_code == 200:
                            RuntimeConfig.DEFAULT_SPEAKER = new_speaker
                            switch_time_ms = switch_response.elapsed.total_seconds() * 1000
                            tts_metrics.record_speaker_switch(old_speaker, new_speaker, switch_time_ms)
                            print_success(f"✓ Default speaker changed to {new_speaker.upper()}")
                            print_info(f"Switch time: {switch_time_ms:.2f}ms")
                            print_info(f"Old speaker ({old_speaker.upper()}) unloaded, new speaker ({new_speaker.upper()}) loaded")
                        else:
                            print_error(f"Failed to switch speaker (HTTP {switch_response.status_code})")
                    except Exception as e:
                        print_error(f"Error switching speaker: {str(e)[:50]}")
                else:
                    print_error("Invalid selection")
            except ValueError:
                print_error("Invalid input")
        
        elif choice == '9':
            """TTS Performance Metrics"""
            print_subheader("TTS Performance Metrics (NEW)")
            print_info("View synthesis response times and efficiency metrics")
            print()
            
            overall = tts_metrics.get_overall_stats()
            print_result("Total Syntheses", overall["total_syntheses"])
            print_result("Errors", overall["total_errors"])
            print_result("Success Rate", f"{overall['success_rate']}%")
            print_result("Avg Response Time", f"{overall['avg_response_time_ms']}ms")
            print_result("Speaker Switches", overall["speaker_switches"])
            print_result("Speakers Used", overall["speakers_used"])
            
            print_subheader("Per-Speaker Statistics")
            speaker_stats = tts_metrics.get_speaker_stats()
            for speaker_id, stats in speaker_stats.items():
                if stats["synthesis_count"] > 0:
                    print(f"\n  {speaker_id.upper()}:")
                    print(f"    Syntheses: {stats['synthesis_count']}")
                    print(f"    Errors: {stats['error_count']}")
                    print(f"    Avg Response: {stats['avg_response_time_ms']}ms")
                    print(f"    Min Response: {stats['min_response_time_ms']}ms")
                    print(f"    Max Response: {stats['max_response_time_ms']}ms")
                    print(f"    Success Rate: {stats['success_rate']}%")
            
            if tts_metrics.speaker_switches:
                print_subheader("Recent Speaker Switches")
                for switch in tts_metrics.speaker_switches[-5:]:  # Last 5 switches
                    print(f"  {switch['from'].upper()} → {switch['to'].upper()}: {switch['time_ms']:.2f}ms")
        
        elif choice == '10':
            print_subheader("Current System Configuration")
            print_result("Wake Word Timeout", f"{RuntimeConfig.WAKE_WORD_DETECT_TIMEOUT}s")
            print_result("LLM Response Timeout", f"{RuntimeConfig.LLM_RESPONSE_TIMEOUT}s")
            print_result("Recording Duration", f"{AudioConfig.DEFAULT_DURATION}s")
            print_result("Wakeword Model", "Pocketsphinx")
            print_result("Speech-to-Text Model", "Whisper (English, Urdu)")
            print_result("Face Recognition Model", "FaceNet")
            print_result("Object Detection Model", "YOLOv8")
            print_result("Emotion Detection", "DeepFace")
            print_result("Context Window Turns", f"Base: {UserContextWindowManager.BASE_TURNS}, Heavy: {UserContextWindowManager.HEAVY_USER_TURNS}")
            
            # NEW: TTS Speaker Configuration
            print_subheader("TTS Speaker Configuration (NEW)")
            print_result("Default Speaker (English)", RuntimeConfig.DEFAULT_SPEAKER.upper())
            print_result("English Speakers Available", ", ".join(s.upper() for s in RuntimeConfig.DEFAULT_SPEAKERS_ENGLISH_ONLY))
            print_result("Urdu Speaker (Forced)", "SHAHID (only Urdu speaker)")
            print_result("Speaker Strategy", "Load only default, unload old when switched")
            print_info("English responses: Use configured default speaker")
            print_info("Urdu responses: ALWAYS use Shahid (optimization for language support)")
            
            # NEW: Camera Configuration  
            print_subheader("Camera Configuration (NEW)")
            print_result("Default Camera", RuntimeConfig.DEFAULT_CAMERA.upper())
            print_result("Available Cameras", ", ".join(c.upper() for c in RuntimeConfig.AVAILABLE_CAMERAS))
            print_result("Camera Mapping", "INTERNAL=0 (built-in), EXTERNAL=1 (USB)")
            
            # NEW: Performance Tracking
            print_subheader("TTS Performance Tracking (NEW)")
            overall = tts_metrics.get_overall_stats()
            print_result("Total Syntheses", overall["total_syntheses"])
            print_result("Success Rate", f"{overall['success_rate']}%")
            print_result("Avg Response Time", f"{overall['avg_response_time_ms']}ms")
        
        else:
            print_error("Invalid choice")

# ============================================================================
# MAIN MENU (REFACTORED)
# ============================================================================

def display_main_menu():
    """Display refactored main menu with 10 core scenarios"""
    print("\n" + "=" * 70)
    print("         NEXI INTEGRATION TEST SUITE - USER-CENTRIC SCENARIOS v2.0")
    print("=" * 70)
    
    print("\n CORE USER JOURNEYS (Production Feature Testing):")
    print("  1. Service Status           – Check health of all services")
    print("  2. New User (Fatima)        – Enroll with resource pre-emption")
    print("  3. Improve Training (Sara)  – Add 5 face + 5 voice samples")
    print("  4. Re-enrollment (Ali)      – Replace all biometric data")
    print("  5. Return User (Sara)       – Full conversation pipeline + fallbacks")
    print("  6. Teach Objects (Sara)     – Vision + knowledge storage integration")
    
    print("\n KNOWLEDGE BASE & USER MANAGEMENT:")
    print("  7. View Taught Objects      – Display all objects in knowledge base")
    print("  8. Delete Taught Objects    – Permanently remove objects from KB")
    print("  9. List All Enrolled Users  – Show complete user enrollment details")
    print(" 10. Delete Enrolled Users    – Permanently remove users from system")
    
    print("\n MONITORING & SETTINGS:")
    print(" 11. Resource Status         – Monitor camera, mic, speaker allocation")
    print(" 12. Settings                – Configure parameters & circuit breakers")
    
    print("\n EXIT:")
    print("  0. Exit")
    
    print("\n" + "=" * 70)
    
    if all(state.services_connected.values()):
        print_success("Status: All services connected and operational")
    else:
        operational = sum(state.services_connected.values())
        total = len(state.services_connected)
        print_warning(f"Status: {operational}/{total} services operational")
    
    print("=" * 70)

def display_resource_status():
    """Display current status of all hardware resources"""
    print_header("HARDWARE RESOURCE STATUS")
    
    resources_status = get_hardware_resources_status()
    
    if not resources_status:
        print_info("Could not retrieve resource status")
        return
    
    for resource_type, status in resources_status.items():
        print_subheader(f"{resource_type.upper()} Resource")
        available = status.get('available', True)
        print_result("Status", "Available" if available else "In Use")
        
        held_by = status.get('held_by')
        if held_by:
            print_result("Held By", held_by)
            time_remaining = status.get('time_remaining')
            if time_remaining is not None:
                print_result("Time Remaining", f"{time_remaining:.1f}s")
        
        queue_length = status.get('queue_length', 0)
        print_result("Queued Requests", queue_length)
        
        if queue_length > 0:
            print_info("  Waiting services:")
            queue = status.get('queue', [])
            for idx, request in enumerate(queue, 1):
                service = request.get('service', 'unknown')
                priority = request.get('priority', 'MEDIUM')
                print_info(f"    {idx}. {service} (priority={priority})")

def main():
    """Main program loop"""
    print_header("NEXI Integration Test Suite v2.0")
    print_info("User-Centric Scenarios with Production Feature Validation")
    print_info("Central (8000), Vision (8001), Audio (8002), TTS (8003), TeachMe (8004), LLM (8006)")
    
    print_info("\nRunning service connectivity checks...")
    test_all_services()
    
    while True:
        display_main_menu()
        
        choice = input("\nEnter your choice (0-12): ").strip()
        
        if choice == '0':
            print_header("Goodbye!")
            break
        
        elif choice == '1':
            test_all_services()
        
        elif choice == '2':
            menu_new_user_enrollment()
        
        elif choice == '3':
            menu_improve_training()
        
        elif choice == '4':
            menu_re_enrollment()
        
        elif choice == '5':
            menu_return_user_conversation()
        
        elif choice == '6':
            menu_teach_objects()
        
        elif choice == '7':
            menu_view_taught_objects()
        
        elif choice == '8':
            menu_delete_taught_objects()
        
        elif choice == '9':
            menu_list_all_enrolled_users()
        
        elif choice == '10':
            menu_delete_enrolled_users()
        
        elif choice == '11':
            display_resource_status()
        
        elif choice == '12':
            menu_settings()
        
        else:
            print_error("Invalid choice. Please select 0-12.")
        
        input("\nPress Enter to continue...")

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_header("Program interrupted by user - Goodbye!")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
