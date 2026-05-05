"""
Mock services for testing enrollment workflow
Fixed to match actual enrollment service expectations
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import random
import uuid
import socket
import sys
import platform
import multiprocessing

# ==================== DATA MODELS ====================
class UserRegistration(BaseModel):
    user_name: str
    age: Optional[int] = None
    relation: Optional[str] = None
    enrollment_timestamp: Optional[str] = None
    # Support both single embeddings (legacy) and arrays (5+5 new format)
    face_embedding: Optional[List[float]] = None
    voice_embedding: Optional[List[float]] = None
    face_embeddings: Optional[List[List[float]]] = None  # Array of 5 embeddings
    voice_embeddings: Optional[List[List[float]]] = None  # Array of 5 embeddings
    avg_face_confidence: Optional[float] = None
    avg_voice_quality: Optional[float] = None
    sample_count: Optional[dict] = None

# ==================== VISION SERVICE (Port 8001) ====================
vision_app = FastAPI(title="Mock Vision Service")

@vision_app.get("/health")
async def vision_health():
    return {"status": "healthy", "service": "Vision Service"}

@vision_app.post("/process-face")
async def process_face(file: UploadFile = File(...)):
    """Process face image and return embedding"""
    fake_embedding = [random.uniform(-1, 1) for _ in range(512)]
    
    print(f"[Vision] Processed: {file.filename}")
    
    return {
        "embedding": fake_embedding,
        "confidence": round(random.uniform(0.85, 0.98), 4),
        "face_detected": True
    }

# ==================== AUDIO SERVICE (Port 8002) ====================
audio_app = FastAPI(title="Mock Audio Service")

@audio_app.get("/health")
async def audio_health():
    return {"status": "healthy", "service": "Audio Service"}

@audio_app.post("/process-voice")
async def process_voice(file: UploadFile = File(...)):
    """Process voice sample and return embedding"""
    fake_embedding = [random.uniform(-1, 1) for _ in range(256)]
    
    print(f"[Audio] Processed: {file.filename}")
    
    return {
        "embedding": fake_embedding,
        "quality_score": round(random.uniform(0.80, 0.95), 4),
        "voice_detected": True
    }

# ==================== CENTRAL SERVER (Port 8000) ====================
central_app = FastAPI(title="Mock Central Server")

# In-memory user database
users_db = {}

@central_app.get("/health")
async def central_health():
    return {"status": "healthy", "service": "Central Server"}

@central_app.post("/users/register")  #  REQUIRED ENDPOINT
async def register_user(user_data: UserRegistration):
    """Register a new user with embeddings - supports 5+5 array format"""
    try:
        # Generate unique user ID
        user_id = f"USER_{uuid.uuid4().hex[:8].upper()}"
        
        # Determine if using new (arrays) or legacy (single) format
        if user_data.face_embeddings and user_data.voice_embeddings:
            # NEW FORMAT: 5 face embeddings + 5 voice embeddings
            face_embedding_dims = len(user_data.face_embeddings[0]) if user_data.face_embeddings else 0
            voice_embedding_dims = len(user_data.voice_embeddings[0]) if user_data.voice_embeddings else 0
            sample_count = user_data.sample_count
            print(f"[Central]  NEW FORMAT: {len(user_data.face_embeddings)} face embeddings + {len(user_data.voice_embeddings)} voice embeddings")
        else:
            # LEGACY FORMAT: single embeddings
            face_embedding_dims = len(user_data.face_embedding) if user_data.face_embedding else 0
            voice_embedding_dims = len(user_data.voice_embedding) if user_data.voice_embedding else 0
            sample_count = {"images": 1, "audio": 1}
            print(f"[Central]  LEGACY FORMAT: single embeddings")
        
        # Store user data
        users_db[user_id] = {
            "user_id": user_id,
            "user_name": user_data.user_name,
            "age": user_data.age,
            "relation": user_data.relation,
            "avg_face_confidence": user_data.avg_face_confidence,
            "avg_voice_quality": user_data.avg_voice_quality,
            "enrollment_timestamp": user_data.enrollment_timestamp,
            "face_embedding_dims": face_embedding_dims,
            "voice_embedding_dims": voice_embedding_dims,
            "sample_count": sample_count,
            "status": "active"
        }
        
        print(f"[Central] Registered: {user_id} - {user_data.user_name} (Samples: {sample_count})")
        
        return {
            "user_id": user_id,
            "status": "registered",
            "message": f"User '{user_data.user_name}' registered successfully with {sample_count.get('images', 1)} image(s) and {sample_count.get('audio', 1)} audio sample(s)"
        }
        
    except Exception as e:
        print(f"[Central] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@central_app.get("/users/list")
async def list_users():
    """Return list of all registered users"""
    return {
        "total_users": len(users_db),
        "users": list(users_db.values())
    }

@central_app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get specific user details"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    return users_db[user_id]

# ==================== PORT UTILITIES ====================
def is_port_in_use(port: int, host: str = "localhost") -> bool:
    """Check if a port is already in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True

def kill_process_on_port(port: int):
    """Attempt to kill the process using the specified port (Windows)"""
    if platform.system() != "Windows":
        return False
    
    try:
        import subprocess
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=True
        )
        
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/PID", pid], 
                            capture_output=True, 
                            check=True
                        )
                        print(f"   Killed process {pid} on port {port}")
                        return True
                    except subprocess.CalledProcessError:
                        pass
    except Exception as e:
        print(f"   Could not kill process on port {port}: {e}")
    
    return False

def check_and_free_ports(ports: dict):
    """Check ports and attempt to free them if in use"""
    ports_in_use = []
    
    for service_name, port in ports.items():
        if is_port_in_use(port):
            print(f" Port {port} ({service_name}) is in use, attempting to free...")
            if kill_process_on_port(port):
                import time
                time.sleep(0.5)
                if not is_port_in_use(port):
                    print(f"   Port {port} is now available")
                    continue
            ports_in_use.append((service_name, port))
    
    if ports_in_use:
        print("\n Error: The following ports are still in use:")
        for service_name, port in ports_in_use:
            print(f"  - {service_name}: port {port}")
        print("\nManually kill processes:")
        print("  netstat -ano | findstr \":8000 :8001 :8002\"")
        print("  taskkill /F /PID <PID>")
        sys.exit(1)

# ==================== SERVICE RUNNERS ====================
def run_vision_mock():
    print("[VISION MOCK] Starting on port 8001...")
    uvicorn.run(vision_app, host="127.0.0.1", port=8001, log_level="error")

def run_audio_mock():
    print("[AUDIO MOCK] Starting on port 8002...")
    uvicorn.run(audio_app, host="127.0.0.1", port=8002, log_level="error")

def run_central_mock():
    print("[CENTRAL MOCK] Starting on port 8000...")
    uvicorn.run(central_app, host="127.0.0.1", port=8000, log_level="error")

# ==================== MAIN ====================
if __name__ == "__main__":
    service_ports = {
        "Central Server": 8000,
        "Vision Service": 8001,
        "Audio Service": 8002
    }
    
    print("\n" + "=" * 60)
    print("[MOCK SERVICES] Starting Mock Services")
    print("=" * 60)
    print("  - Central Server: http://localhost:8000")
    print("  - Vision Service: http://localhost:8001")
    print("  - Audio Service: http://localhost:8002")
    print("=" * 60)
    
    # Check and free ports
    print("\n[MOCK SERVICES] Checking port availability...")
    check_and_free_ports(service_ports)
    
    print("\n[MOCK SERVICES] All ports available!")
    print("Press Ctrl+C to stop all services\n")
    
    # Start all services
    processes = [
        multiprocessing.Process(target=run_central_mock, name="Central"),
        multiprocessing.Process(target=run_vision_mock, name="Vision"),
        multiprocessing.Process(target=run_audio_mock, name="Audio")
    ]
    
    for p in processes:
        p.start()
    
    # Wait a moment for services to start
    import time
    time.sleep(2)
    print("[MOCK SERVICES] All services running!\n")
    
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\n[MOCK SERVICES] Stopping services...")
        for p in processes:
            p.terminate()
            p.join()
        print("Services stopped\n")