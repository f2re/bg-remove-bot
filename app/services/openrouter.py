import aiohttp
import base64
import logging
from io import BytesIO
from typing import Optional, Dict
from PIL import Image
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


def detect_dominant_background_color(image_bytes: bytes, requested_color: tuple = None, corner_sample_size: int = 50) -> tuple:
    """
    Detect the actual dominant background color in the image by analyzing corners

    Args:
        image_bytes: Image bytes
        requested_color: The color we requested from AI (for validation)
        corner_sample_size: Size of corner regions to sample

    Returns:
        RGB tuple of the detected dominant background color
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode != 'RGB' and img.mode != 'RGBA':
            img = img.convert('RGB')

        width, height = img.size
        data = np.array(img)

        # Sample all four corners (background is typically in corners)
        corners = []
        sample_size = min(corner_sample_size, width // 4, height // 4)

        # Top-left
        corners.append(data[:sample_size, :sample_size, :3])
        # Top-right
        corners.append(data[:sample_size, -sample_size:, :3])
        # Bottom-left
        corners.append(data[-sample_size:, :sample_size, :3])
        # Bottom-right
        corners.append(data[-sample_size:, -sample_size:, :3])

        # Combine all corner pixels
        corner_pixels = np.concatenate([c.reshape(-1, 3) for c in corners])

        # Count unique colors and find most common
        from collections import Counter
        color_counts = Counter(map(tuple, corner_pixels))

        if not color_counts:
            logger.warning("No colors found in corners, using requested color")
            return requested_color if requested_color else (0, 255, 0)

        # Get top color
        dominant_color, count = color_counts.most_common(1)[0]

        # If we have a requested color, validate that dominant color is close to it
        if requested_color:
            # Calculate color distance
            distance = np.linalg.norm(np.array(dominant_color) - np.array(requested_color))

            # If distance is reasonable (within 100), use dominant color
            # If too far, it might not be the background
            if distance > 150:
                logger.warning(f"Detected color {dominant_color} is too far from requested {requested_color} (distance: {distance:.1f})")
                # Try to find a color closer to requested
                for color, cnt in color_counts.most_common(10):
                    dist = np.linalg.norm(np.array(color) - np.array(requested_color))
                    if dist < 150 and cnt > len(corner_pixels) * 0.05:  # At least 5% of corner pixels
                        dominant_color = color
                        logger.info(f"Using alternative color {color} (distance: {dist:.1f}, count: {cnt})")
                        break

        logger.info(f"Detected dominant background color: {dominant_color} (count: {count}, total corner pixels: {len(corner_pixels)})")

        return dominant_color

    except Exception as e:
        logger.error(f"Error detecting dominant color: {str(e)}")
        return requested_color if requested_color else (0, 255, 0)


def remove_colored_background(image_bytes: bytes, target_color: tuple = (0, 255, 0), tolerance: int = 50, auto_detect: bool = True) -> bytes:
    """
    Convert colored background to transparency using chroma keying with smart color detection

    Args:
        image_bytes: Image bytes with colored background
        target_color: RGB tuple of color to remove (default: green)
        tolerance: Color tolerance for detection (0-255, higher = more aggressive)
        auto_detect: If True, automatically detect actual background color instead of using target_color directly

    Returns:
        Image bytes with transparent background
    """
    try:
        # Auto-detect the actual background color if requested
        if auto_detect:
            detected_color = detect_dominant_background_color(image_bytes, requested_color=target_color)
            logger.info(f"Auto-detected background color {detected_color} (requested was {target_color})")
            actual_target = detected_color
        else:
            actual_target = target_color

        # Open image and convert to RGBA
        img = Image.open(BytesIO(image_bytes))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Convert to numpy array for efficient processing
        data = np.array(img)

        # Define target color
        target = np.array(actual_target)

        # Calculate color distance from target for each pixel
        # We only check RGB channels (first 3 channels)
        diff = np.abs(data[:, :, :3] - target)

        # Create mask: pixels are considered matching if all RGB channels are within tolerance
        is_target_color = (
            (diff[:, :, 0] < tolerance) &
            (diff[:, :, 1] < tolerance) &
            (diff[:, :, 2] < tolerance)
        )

        # Set alpha channel to 0 (fully transparent) for matching pixels
        data[is_target_color, 3] = 0

        # Convert back to PIL Image
        result = Image.fromarray(data, 'RGBA')

        # Save to bytes
        output = BytesIO()
        result.save(output, format='PNG')
        output.seek(0)

        logger.info(f"Chroma key removal completed for color {actual_target}. Processed {np.sum(is_target_color)} pixels to transparent")

        return output.getvalue()

    except Exception as e:
        logger.error(f"Error in remove_colored_background: {str(e)}")
        # Return original image if processing fails
        return image_bytes


# Backward compatibility
def remove_green_screen(image_bytes: bytes, tolerance: int = 50) -> bytes:
    """
    Convert green screen background to transparency using chroma keying
    (Backward compatibility wrapper)

    Args:
        image_bytes: Image bytes with green screen background
        tolerance: Color tolerance for green detection (0-255, higher = more aggressive)

    Returns:
        Image bytes with transparent background
    """
    return remove_colored_background(image_bytes, target_color=(0, 255, 0), tolerance=tolerance)


class OpenRouterService:
    """Service for interacting with OpenRouter API for image editing"""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        # Use Gemini 2.5 Flash Image for image editing capabilities
        # You can override this in settings with OPENROUTER_MODEL
        self.model = settings.OPENROUTER_MODEL or "google/gemini-2.5-flash-image-preview"
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    async def remove_background(self, image_bytes: bytes, prompt: str, background_color: tuple = None, transparent: bool = False) -> Dict:
        """
        Remove background from image using OpenRouter API with image editing model

        Args:
            image_bytes: Image bytes
            prompt: Prompt for background removal (должен быть специфичным)
            background_color: RGB tuple for background color (for white/colored backgrounds)
            transparent: If True, request transparent background (no chroma keying)

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

                                # Apply chroma key only if not requesting transparent directly
                                if transparent:
                                    # AI should have generated transparent background directly
                                    logger.info("Using AI-generated transparent background directly (no chroma keying)")
                                    final_image_bytes = processed_image_bytes
                                elif background_color:
                                    # Apply chroma key to convert colored background to transparency
                                    logger.info(f"Applying chroma key to remove {background_color} background")
                                    final_image_bytes = remove_colored_background(processed_image_bytes, target_color=background_color)
                                else:
                                    # No post-processing needed (e.g., white background for photos)
                                    final_image_bytes = processed_image_bytes

                                return {
                                    "success": True,
                                    "image_bytes": final_image_bytes,
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

                                    # Apply chroma key only if not requesting transparent directly
                                    if transparent:
                                        logger.info("Using AI-generated transparent background directly (fallback path)")
                                        final_image_bytes = processed_image_bytes
                                    elif background_color:
                                        logger.info(f"Applying chroma key to remove {background_color} background (fallback path)")
                                        final_image_bytes = remove_colored_background(processed_image_bytes, target_color=background_color)
                                    else:
                                        final_image_bytes = processed_image_bytes

                                    return {
                                        "success": True,
                                        "image_bytes": final_image_bytes,
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
