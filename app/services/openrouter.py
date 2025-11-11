import aiohttp
import base64
import logging
from io import BytesIO
from typing import Optional, Dict
from PIL import Image
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


def remove_green_screen(image_bytes: bytes, tolerance: int = 50) -> bytes:
    """
    Convert green screen background to transparency using chroma keying

    Args:
        image_bytes: Image bytes with green screen background
        tolerance: Color tolerance for green detection (0-255, higher = more aggressive)

    Returns:
        Image bytes with transparent background
    """
    try:
        # Open image and convert to RGBA
        img = Image.open(BytesIO(image_bytes))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Convert to numpy array for efficient processing
        data = np.array(img)

        # Define target green color (RGB: 0, 255, 0)
        target_green = np.array([0, 255, 0])

        # Calculate color distance from target green for each pixel
        # We only check RGB channels (first 3 channels)
        diff = np.abs(data[:, :, :3] - target_green)

        # Create mask: pixels are considered green if all RGB channels are within tolerance
        # For green (0, 255, 0), we want:
        # - R channel close to 0
        # - G channel close to 255
        # - B channel close to 0
        is_green = (
            (diff[:, :, 0] < tolerance) &  # R close to 0
            (diff[:, :, 1] < tolerance) &  # G close to 255
            (diff[:, :, 2] < tolerance)    # B close to 0
        )

        # Set alpha channel to 0 (fully transparent) for green pixels
        data[is_green, 3] = 0

        # Convert back to PIL Image
        result = Image.fromarray(data, 'RGBA')

        # Save to bytes
        output = BytesIO()
        result.save(output, format='PNG')
        output.seek(0)

        logger.info(f"Green screen removal completed. Processed {np.sum(is_green)} pixels to transparent")

        return output.getvalue()

    except Exception as e:
        logger.error(f"Error in remove_green_screen: {str(e)}")
        # Return original image if processing fails
        return image_bytes


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
                "stream": False,  # Explicitly disable streaming for image responses
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
                "max_tokens": 4096  # Increased for image generation (1290 image tokens needed)
            }

            logger.info(f"Sending request to OpenRouter API with model: {self.model}")

            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"OpenRouter API response received successfully")
                        logger.info(f"Response keys: {result.keys()}")
                        logger.info(f"Full API response: {result}")

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

                                # Handle dict format (some APIs return {url: "...", type: "...", image_url: {...}})
                                if isinstance(image_data, dict):
                                    # Try different possible keys for the image URL
                                    image_url = (image_data.get('url') or
                                                image_data.get('data') or
                                                image_data.get('image_url'))

                                    # If image_url is also a dict, extract the url from it
                                    if isinstance(image_url, dict):
                                        logger.debug(f"image_url is dict: {image_url.keys()}")
                                        image_url = image_url.get('url') or image_url.get('data')

                                    if image_url:
                                        image_data = image_url
                                        logger.debug(f"Extracted URL from dict: {str(image_url)[:100]}")
                                    else:
                                        logger.error(f"Dict format image data without url/data/image_url field: {image_data.keys()}")
                                        logger.error(f"Full dict content: {image_data}")
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

                                # Apply chroma key to convert green screen to transparency
                                logger.info("Applying chroma key to remove green screen background")
                                transparent_image_bytes = remove_green_screen(processed_image_bytes)

                                return {
                                    "success": True,
                                    "image_bytes": transparent_image_bytes,
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

                                    # Apply chroma key to convert green screen to transparency
                                    logger.info("Applying chroma key to remove green screen background (fallback path)")
                                    transparent_image_bytes = remove_green_screen(processed_image_bytes)

                                    return {
                                        "success": True,
                                        "image_bytes": transparent_image_bytes,
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
