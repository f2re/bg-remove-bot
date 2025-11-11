import aiohttp
import base64
import logging
from io import BytesIO
from typing import Optional, Dict
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)


class OpenRouterService:
    """Service for interacting with OpenRouter API for image editing"""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        # Use Gemini 2.5 Flash Image for image editing capabilities
        # You can override this in settings with OPENROUTER_MODEL
        self.model = settings.OPENROUTER_MODEL or "google/gemini-2.5-flash-image-preview"
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    async def remove_background(self, image_bytes: bytes, prompt: str) -> Dict:
        """
        Remove background from image using OpenRouter API with image editing model

        Args:
            image_bytes: Image bytes
            prompt: Prompt for background removal (должен быть специфичным)

        Returns:
            dict with keys: success (bool), image_bytes (bytes), error (str)
        """
        try:
            # Convert image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')

            # Detect image format
            image = Image.open(BytesIO(image_bytes))
            image_format = image.format.lower() if image.format else 'jpeg'
            mime_type = f"image/{image_format}"

            # Prepare request with modalities for image generation
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://bg-removal-bot.com",  # Optional: your site
                "X-Title": "BG Removal Bot"  # Optional: your app name
            }

            payload = {
                "model": self.model,
                "modalities": ["text", "image"],  # Enable image output
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
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.7,
                "max_tokens": 1024
            }

            logger.info(f"Sending request to OpenRouter API with model: {self.model}")

            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"OpenRouter API response received successfully")
                        logger.debug(f"Full API response: {result}")

                        # Extract image from response
                        # The response contains images in the message content
                        try:
                            choices = result.get('choices', [])
                            if not choices:
                                logger.error("No choices in API response")
                                logger.debug(f"Response keys: {result.keys()}")
                                raise ValueError("No choices in API response")

                            message = choices[0].get('message', {})
                            logger.debug(f"Message content: {message}")

                            # Check for images field (new format for image generation)
                            images = message.get('images', [])
                            logger.debug(f"Images field: {images}, type: {type(images)}")

                            if images:
                                # Images are returned as base64 data URLs or URLs
                                image_data = images[0]
                                logger.debug(f"Image data type: {type(image_data)}, first 100 chars: {str(image_data)[:100]}")

                                # Handle dict format (some APIs return {url: "...", type: "..."})
                                if isinstance(image_data, dict):
                                    image_url = image_data.get('url') or image_data.get('data')
                                    if image_url:
                                        image_data = image_url
                                    else:
                                        logger.error(f"Dict format image data without url/data field: {image_data.keys()}")
                                        raise ValueError(f"Unexpected dict format: {image_data.keys()}")

                                # Handle data URL format: data:image/png;base64,xxxx
                                if isinstance(image_data, str):
                                    if image_data.startswith('data:'):
                                        # Extract base64 part
                                        base64_part = image_data.split(',', 1)[1] if ',' in image_data else image_data
                                        processed_image_bytes = base64.b64decode(base64_part)
                                        logger.debug(f"Decoded base64 image, size: {len(processed_image_bytes)} bytes")
                                    elif image_data.startswith('http'):
                                        # It's a URL - need to download
                                        logger.debug(f"Downloading image from URL: {image_data}")
                                        async with session.get(image_data) as img_response:
                                            if img_response.status == 200:
                                                processed_image_bytes = await img_response.read()
                                                logger.debug(f"Downloaded image, size: {len(processed_image_bytes)} bytes")
                                            else:
                                                raise ValueError(f"Failed to download image from URL: {img_response.status}")
                                    else:
                                        # Assume it's raw base64 without prefix
                                        logger.debug("Attempting to decode as raw base64")
                                        processed_image_bytes = base64.b64decode(image_data)
                                        logger.debug(f"Decoded raw base64, size: {len(processed_image_bytes)} bytes")
                                else:
                                    logger.error(f"Unexpected image data type: {type(image_data)}, value: {image_data}")
                                    raise ValueError(f"Unexpected image data type: {type(image_data)}")

                                # Validate it's a valid image
                                Image.open(BytesIO(processed_image_bytes))

                                logger.info("Successfully extracted processed image from API response")
                                return {
                                    "success": True,
                                    "image_bytes": processed_image_bytes,
                                    "error": None
                                }
                            else:
                                # Fallback: check content field for base64 images
                                content = message.get('content', '')
                                if 'base64' in content or content.startswith('data:'):
                                    # Try to extract base64 from content
                                    if content.startswith('data:'):
                                        base64_part = content.split(',', 1)[1] if ',' in content else content
                                    else:
                                        base64_part = content

                                    processed_image_bytes = base64.b64decode(base64_part)
                                    Image.open(BytesIO(processed_image_bytes))  # Validate

                                    return {
                                        "success": True,
                                        "image_bytes": processed_image_bytes,
                                        "error": None
                                    }
                                else:
                                    raise ValueError("No image data found in API response")

                        except Exception as extract_error:
                            logger.error(f"Failed to extract image from response: {str(extract_error)}", exc_info=True)
                            logger.debug(f"Full response structure: {result}")

                            # Try to extract any useful info from the response for debugging
                            if 'choices' in result and result['choices']:
                                msg = result['choices'][0].get('message', {})
                                logger.debug(f"Message keys: {msg.keys()}")
                                logger.debug(f"Content type: {type(msg.get('content'))}")
                                if 'images' in msg:
                                    logger.debug(f"Images structure: {type(msg['images'])}, length: {len(msg['images']) if isinstance(msg['images'], (list, tuple)) else 'N/A'}")
                                    if msg['images']:
                                        logger.debug(f"First image type: {type(msg['images'][0])}")

                            return {
                                "success": False,
                                "image_bytes": None,
                                "error": f"Failed to extract image: {str(extract_error)}"
                            }

                    else:
                        error_text = await response.text()
                        logger.error(f"OpenRouter API error: {response.status} - {error_text}")
                        return {
                            "success": False,
                            "image_bytes": None,
                            "error": f"API error: {response.status} - {error_text}"
                        }

        except Exception as e:
            logger.error(f"Error in remove_background: {str(e)}")
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
                async with session.post(self.base_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    return response.status == 200

        except Exception as e:
            logger.error(f"Connection test failed: {str(e)}")
            return False
