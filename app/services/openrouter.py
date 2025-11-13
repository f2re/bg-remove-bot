import aiohttp
import base64
import logging
from io import BytesIO
from typing import Optional, Dict
from PIL import Image
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


def detect_dominant_background_color(image_bytes: bytes, requested_color: tuple = None, border_thickness: int = 10, tolerance: int = 30) -> tuple:
    """
    Detect the actual dominant background color by analyzing image borders and clustering similar colors.

    This improved algorithm:
    1. Samples pixels from all image borders (not just corners)
    2. Groups similar colors together using tolerance-based clustering
    3. Finds the dominant color cluster
    4. Returns the average color of the dominant cluster

    Args:
        image_bytes: Image bytes
        requested_color: The color we requested from AI (for validation)
        border_thickness: Thickness of border region to sample (in pixels)
        tolerance: Color similarity tolerance for clustering (0-255)

    Returns:
        RGB tuple of the detected dominant background color
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        if img.mode != 'RGB' and img.mode != 'RGBA':
            img = img.convert('RGB')

        width, height = img.size
        data = np.array(img)

        # Sample border pixels (all edges)
        border_thickness = min(border_thickness, width // 10, height // 10)
        border_pixels = []

        # Top border
        border_pixels.append(data[:border_thickness, :, :3].reshape(-1, 3))
        # Bottom border
        border_pixels.append(data[-border_thickness:, :, :3].reshape(-1, 3))
        # Left border (excluding corners to avoid duplication)
        border_pixels.append(data[border_thickness:-border_thickness, :border_thickness, :3].reshape(-1, 3))
        # Right border (excluding corners to avoid duplication)
        border_pixels.append(data[border_thickness:-border_thickness, -border_thickness:, :3].reshape(-1, 3))

        # Combine all border pixels
        all_border_pixels = np.concatenate(border_pixels)

        logger.info(f"Sampled {len(all_border_pixels)} border pixels from {border_thickness}px border")

        # Cluster similar colors together using tolerance-based approach
        # This groups colors like RGB(0,0,255), RGB(1,1,253), RGB(2,0,254) together
        color_clusters = {}

        for pixel in all_border_pixels:
            pixel_tuple = tuple(pixel)

            # Check if this pixel belongs to an existing cluster
            found_cluster = False
            for cluster_center, cluster_pixels in color_clusters.items():
                # Calculate color distance
                distance = np.linalg.norm(np.array(pixel_tuple) - np.array(cluster_center))

                if distance <= tolerance:
                    # Add to existing cluster
                    cluster_pixels.append(pixel_tuple)
                    found_cluster = True
                    break

            if not found_cluster:
                # Create new cluster
                color_clusters[pixel_tuple] = [pixel_tuple]

        logger.info(f"Found {len(color_clusters)} color clusters with tolerance={tolerance}")

        # Find the largest cluster (most pixels)
        dominant_cluster_center = None
        dominant_cluster_size = 0
        dominant_cluster_pixels = []

        for cluster_center, cluster_pixels in color_clusters.items():
            cluster_size = len(cluster_pixels)
            if cluster_size > dominant_cluster_size:
                dominant_cluster_size = cluster_size
                dominant_cluster_center = cluster_center
                dominant_cluster_pixels = cluster_pixels

        if not dominant_cluster_pixels:
            logger.warning("No color clusters found, using requested color")
            return requested_color if requested_color else (0, 255, 0)

        # Calculate average color of the dominant cluster (more accurate than using first pixel)
        cluster_array = np.array(dominant_cluster_pixels)
        avg_color = tuple(np.round(np.mean(cluster_array, axis=0)).astype(int))

        cluster_percentage = (dominant_cluster_size / len(all_border_pixels)) * 100

        logger.info(f"Dominant cluster: {dominant_cluster_size} pixels ({cluster_percentage:.1f}% of border)")
        logger.info(f"Cluster center: {dominant_cluster_center}, Average color: {avg_color}")

        # If we have a requested color, validate that dominant color is close to it
        if requested_color:
            distance = np.linalg.norm(np.array(avg_color) - np.array(requested_color))

            if distance > 150:
                logger.warning(f"Detected color {avg_color} is far from requested {requested_color} (distance: {distance:.1f})")

                # Try to find a cluster closer to requested color
                sorted_clusters = sorted(color_clusters.items(), key=lambda x: len(x[1]), reverse=True)

                for cluster_center, cluster_pixels in sorted_clusters[:5]:  # Check top 5 clusters
                    cluster_avg = tuple(np.round(np.mean(np.array(cluster_pixels), axis=0)).astype(int))
                    dist = np.linalg.norm(np.array(cluster_avg) - np.array(requested_color))

                    # Require at least 5% of border pixels
                    if dist < 150 and len(cluster_pixels) > len(all_border_pixels) * 0.05:
                        avg_color = cluster_avg
                        logger.info(f"Using alternative cluster: {cluster_avg} (distance: {dist:.1f}, size: {len(cluster_pixels)})")
                        break

        return avg_color

    except Exception as e:
        logger.error(f"Error detecting dominant color: {str(e)}", exc_info=True)
        return requested_color if requested_color else (0, 255, 0)


def remove_colored_background(image_bytes: bytes, target_color: tuple = (0, 255, 0), tolerance: int = 50, auto_detect: bool = True, edge_feather: bool = True) -> bytes:
    """
    Convert colored background to transparency using chroma keying with smart color detection.

    This improved algorithm:
    1. Auto-detects the dominant background color using border clustering
    2. Uses Euclidean distance for better color matching (handles variations)
    3. Optionally applies edge feathering for smoother transitions

    Args:
        image_bytes: Image bytes with colored background
        target_color: RGB tuple of color to remove (default: green)
        tolerance: Color tolerance for detection (0-255, higher = more aggressive)
        auto_detect: If True, automatically detect actual background color instead of using target_color directly
        edge_feather: If True, apply semi-transparency to edge pixels for smoother results

    Returns:
        Image bytes with transparent background
    """
    try:
        # Auto-detect the actual background color if requested
        if auto_detect:
            # Use tolerance for detection as well
            detection_tolerance = min(30, tolerance // 2)
            detected_color = detect_dominant_background_color(
                image_bytes,
                requested_color=target_color,
                tolerance=detection_tolerance
            )
            logger.info(f"Auto-detected background color {detected_color} (requested was {target_color})")
            actual_target = detected_color
        else:
            actual_target = target_color

        # Open image and convert to RGBA
        img = Image.open(BytesIO(image_bytes))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Convert to numpy array for efficient processing
        data = np.array(img).astype(np.float32)

        # Define target color
        target = np.array(actual_target, dtype=np.float32)

        # Calculate Euclidean distance from target color for each pixel
        # This better handles color variations than checking each channel separately
        color_distances = np.linalg.norm(data[:, :, :3] - target, axis=2)

        # Create mask based on distance threshold
        # Convert tolerance (per-channel) to Euclidean distance
        # For RGB, max distance when all channels differ by tolerance is: sqrt(3 * tolerance^2)
        distance_threshold = np.sqrt(3) * tolerance

        # Full transparency for pixels within tolerance
        is_background = color_distances <= distance_threshold

        # Set alpha to 0 for background pixels
        data[is_background, 3] = 0

        # Optional: Edge feathering for smoother transitions
        if edge_feather:
            # Create a feather zone for pixels just outside the threshold
            feather_range = tolerance * 0.5
            feather_distance_threshold = distance_threshold + feather_range

            is_feather_zone = (color_distances > distance_threshold) & (color_distances <= feather_distance_threshold)

            # Calculate alpha based on distance (linear falloff)
            # Pixels at distance_threshold get alpha=255, at feather_distance_threshold get alpha=255
            # This creates a smooth transition
            if np.any(is_feather_zone):
                feather_pixels_distances = color_distances[is_feather_zone]
                # Normalize to 0-1 range
                normalized_distances = (feather_pixels_distances - distance_threshold) / feather_range
                # Calculate alpha (0 at threshold, 255 at feather edge)
                feather_alpha = (normalized_distances * 255).astype(np.uint8)

                # Apply feathered alpha, but don't make pixels MORE opaque
                current_alpha = data[is_feather_zone, 3].astype(np.uint8)
                data[is_feather_zone, 3] = np.minimum(current_alpha, feather_alpha)

                logger.info(f"Applied edge feathering to {np.sum(is_feather_zone)} pixels")

        # Convert back to uint8
        data = data.astype(np.uint8)

        # Convert back to PIL Image
        result = Image.fromarray(data, 'RGBA')

        # Save to bytes
        output = BytesIO()
        result.save(output, format='PNG')
        output.seek(0)

        transparent_pixels = np.sum(is_background)
        total_pixels = data.shape[0] * data.shape[1]
        transparency_percent = (transparent_pixels / total_pixels) * 100

        logger.info(f"Chroma key removal completed for color {actual_target} with tolerance={tolerance}")
        logger.info(f"Removed {transparent_pixels:,} pixels ({transparency_percent:.1f}% of image)")

        return output.getvalue()

    except Exception as e:
        logger.error(f"Error in remove_colored_background: {str(e)}", exc_info=True)
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

    async def remove_background(self, image_bytes: bytes, prompt: str, background_color: tuple = None) -> Dict:
        """
        Remove background from image using OpenRouter API with image editing model

        Args:
            image_bytes: Image bytes
            prompt: Prompt for background removal (должен быть специфичным)
            background_color: RGB tuple for background color. AI will generate this color,
                            then chroma keying will be applied to make it transparent.
                            If None, result will have the AI-generated background (typically white).

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
                        # logger.info(f"Full API response: {result}")

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

                                # AI cannot generate transparent backgrounds directly!
                                # Always apply chroma keying when background_color is specified
                                if background_color:
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

                                    # AI cannot generate transparent backgrounds - always use chroma keying
                                    if background_color:
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
