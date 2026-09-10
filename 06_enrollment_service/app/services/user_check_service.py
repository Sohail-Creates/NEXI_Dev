import httpx
import os
from typing import Dict, Optional
from fastapi import HTTPException
from shared.security import internal_service_headers


class UserCheckService:
    """Service to check if user exists in Central Server"""
    
    def __init__(self):
        self.central_server_url = os.getenv("CENTRAL_SERVER_URL", "http://localhost:8000")
        self.timeout = int(os.getenv("SERVICE_TIMEOUT", 30))
    
    async def check_user_exists(self, user_name: str) -> Dict:
        """
        Check if user exists in Central Server
        
        Args:
            user_name: Name of the user to check
            
        Returns:
            Dict with user existence info
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.central_server_url}/users/check",
                    params={"name": user_name},
                    headers=internal_service_headers(),
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "exists": result.get("exists", False),
                        "user_id": result.get("user_id"),
                        "enrollment_date": result.get("enrollment_date"),
                        "sample_count": result.get("sample_count", {"images": 0, "audio": 0})
                    }
                elif response.status_code == 404:
                    return {
                        "exists": False,
                        "user_id": None,
                        "enrollment_date": None,
                        "sample_count": None
                    }
                else:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Central Server error: {response.text}"
                    )
                    
        except httpx.RequestError as e:
            print(f"[UserCheck] Central Server unavailable: {str(e)}")
            return {
                "exists": False,
                "user_id": None,
                "enrollment_date": None,
                "sample_count": None
            }
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error checking user: {str(e)}"
            )
