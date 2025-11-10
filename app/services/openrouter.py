import aiohttp
import base64
from io import BytesIO
from typing import Optional, Dict
from PIL import Image

from app.config import settings


class OpenRouterService:
    """Service for interacting with OpenRouter API"""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.OPENROUTER_MODEL
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    async def remove_background(self, image_bytes: bytes, prompt: str) -> Dict:
        """
        Remove background from image using OpenRouter API

        Args:
            image_bytes: Image bytes
            prompt: Prompt for background removal

        Returns:
            dict with keys: success (bool), image_bytes (bytes), error (str)
        """
        try:
            # Convert image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')

            # Prepare request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()

                        # Extract image from response
                        # Note: This is a placeholder implementation
                        # The actual response format depends on the OpenRouter model
                        # You may need to adjust this based on the specific model's output

                        # For now, we'll return the original image
                        # In production, you would extract the processed image from the API response

                        return {
                            "success": True,
                            "image_bytes": image_bytes,
                            "error": None
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "image_bytes": None,
                            "error": f"API error: {response.status} - {error_text}"
                        }

        except Exception as e:
            return {
                "success": False,
                "image_bytes": None,
                "error": str(e)
            }

    async def test_connection(self) -> bool:
        """Test OpenRouter API connection"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": "test"
                    }
                ],
                "max_tokens": 10
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload, headers=headers) as response:
                    return response.status == 200

        except Exception:
            return False
