from PIL import Image, ImageStat
from io import BytesIO
from typing import Dict
import numpy as np


class ImageProcessor:
    """Service for image analysis and processing"""

    def analyze_image(self, image_bytes: bytes) -> Dict:
        """
        Analyze image to determine optimal processing parameters

        Args:
            image_bytes: Image bytes

        Returns:
            dict with analysis results
        """
        try:
            image = Image.open(BytesIO(image_bytes))

            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Basic statistics
            stat = ImageStat.Stat(image)
            width, height = image.size

            # Analyze image characteristics
            analysis = {
                "width": width,
                "height": height,
                "has_hair": self._detect_complex_edges(image),
                "has_transparent_objects": self._detect_transparency(image),
                "has_motion_blur": self._detect_blur(image),
                "brightness": sum(stat.mean) / len(stat.mean),
                "contrast": sum(stat.stddev) / len(stat.stddev)
            }

            return analysis

        except Exception as e:
            return {
                "width": 0,
                "height": 0,
                "has_hair": False,
                "has_transparent_objects": False,
                "has_motion_blur": False,
                "brightness": 128,
                "contrast": 50,
                "error": str(e)
            }

    def _detect_complex_edges(self, image: Image.Image) -> bool:
        """
        Detect complex edges (hair, fur, etc.)
        Simple heuristic based on high-frequency content
        """
        try:
            # Convert to grayscale
            gray = image.convert('L')

            # Resize for faster processing
            gray_small = gray.resize((100, 100))

            # Convert to numpy array
            img_array = np.array(gray_small)

            # Calculate edge variance using simple gradient
            grad_x = np.abs(np.diff(img_array, axis=1))
            grad_y = np.abs(np.diff(img_array, axis=0))

            # High variance in gradients indicates complex edges
            edge_variance = np.var(grad_x) + np.var(grad_y)

            # Threshold for complex edges (hair, fur)
            return edge_variance > 1000

        except Exception:
            return False

    def _detect_transparency(self, image: Image.Image) -> bool:
        """
        Detect if image has transparent or semi-transparent objects
        This is a heuristic - checks if image has alpha channel or very bright areas
        """
        try:
            # Check for alpha channel
            if image.mode == 'RGBA':
                return True

            # Check for very bright areas (possible glass/reflections)
            stat = ImageStat.Stat(image)
            max_brightness = max(stat.mean)

            return max_brightness > 240

        except Exception:
            return False

    def _detect_blur(self, image: Image.Image) -> bool:
        """
        Detect motion blur using Laplacian variance
        """
        try:
            # Convert to grayscale
            gray = image.convert('L')

            # Resize for faster processing
            gray_small = gray.resize((100, 100))

            # Convert to numpy array
            img_array = np.array(gray_small)

            # Calculate Laplacian variance
            laplacian = np.abs(np.diff(np.diff(img_array, axis=0), axis=0))
            variance = np.var(laplacian)

            # Low variance indicates blur
            return variance < 100

        except Exception:
            return False

    def resize_if_needed(self, image_bytes: bytes, max_size: int = 4096) -> bytes:
        """
        Resize image if it exceeds max_size

        Args:
            image_bytes: Original image bytes
            max_size: Maximum dimension size

        Returns:
            Resized image bytes
        """
        try:
            image = Image.open(BytesIO(image_bytes))
            width, height = image.size

            if width > max_size or height > max_size:
                # Calculate new size maintaining aspect ratio
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))

                # Resize
                image = image.resize((new_width, new_height), Image.LANCZOS)

            # Save to bytes
            output = BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()

        except Exception:
            return image_bytes
