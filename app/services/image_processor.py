from PIL import Image, ImageStat
from io import BytesIO
from typing import Dict, Tuple
import numpy as np
from sklearn.cluster import KMeans
import logging

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Service for image analysis and processing"""

    def analyze_image(self, image_bytes: bytes, detect_subject_color: bool = False) -> Dict:
        """
        Analyze image to determine optimal processing parameters

        Args:
            image_bytes: Image bytes
            detect_subject_color: If True, perform detailed color analysis for subject detection

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

            # Add subject color analysis if requested
            if detect_subject_color:
                subject_color = self._detect_subject_dominant_color(image)
                analysis["subject_dominant_color"] = subject_color
                analysis["is_subject_green"] = self._is_color_green(subject_color)

            return analysis

        except Exception as e:
            logger.error(f"Error in analyze_image: {str(e)}")
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

    def _detect_subject_dominant_color(self, image: Image.Image, n_colors: int = 5) -> Tuple[int, int, int]:
        """
        Detect dominant color of the subject (foreground) using clustering

        Assumes the subject is in the center of the image.

        Args:
            image: PIL Image object
            n_colors: Number of color clusters to detect

        Returns:
            RGB tuple of dominant color
        """
        try:
            # Resize for faster processing
            img_small = image.resize((200, 200))

            # Get center region (assuming subject is in center)
            width, height = img_small.size
            center_x, center_y = width // 2, height // 2
            crop_size = min(width, height) // 2

            # Crop center region
            left = max(0, center_x - crop_size // 2)
            top = max(0, center_y - crop_size // 2)
            right = min(width, center_x + crop_size // 2)
            bottom = min(height, center_y + crop_size // 2)

            center_crop = img_small.crop((left, top, right, bottom))

            # Convert to numpy array
            pixels = np.array(center_crop).reshape(-1, 3)

            # Use KMeans to find dominant colors
            kmeans = KMeans(n_clusters=n_colors, random_state=42, n_init=10)
            kmeans.fit(pixels)

            # Get the most common cluster (dominant color)
            labels, counts = np.unique(kmeans.labels_, return_counts=True)
            dominant_cluster = labels[np.argmax(counts)]
            dominant_color = kmeans.cluster_centers_[dominant_cluster]

            # Return as RGB tuple
            return tuple(int(c) for c in dominant_color)

        except Exception as e:
            logger.error(f"Error detecting subject color: {str(e)}")
            # Return neutral gray as fallback
            return (128, 128, 128)

    def _is_color_green(self, rgb: Tuple[int, int, int], threshold: float = 0.3) -> bool:
        """
        Check if a color is predominantly green

        Args:
            rgb: RGB tuple (r, g, b)
            threshold: Minimum green dominance ratio (0-1)

        Returns:
            True if color is green
        """
        try:
            r, g, b = rgb

            # Avoid division by zero
            total = r + g + b
            if total == 0:
                return False

            # Calculate green ratio
            green_ratio = g / total

            # Green should be dominant and significantly higher than red and blue
            is_green = (
                green_ratio > threshold and
                g > r and
                g > b and
                g > 80  # Minimum absolute green value
            )

            logger.info(f"Color analysis: RGB{rgb}, green_ratio={green_ratio:.2f}, is_green={is_green}")

            return is_green

        except Exception as e:
            logger.error(f"Error checking if color is green: {str(e)}")
            return False

    def select_optimal_chromakey_color(self, image_bytes: bytes) -> Tuple[Tuple[int, int, int], str, float]:
        """
        Select optimal chromakey color with MAXIMUM distance from ALL colors in the image.

        This ensures the selected background color will be easy to remove without affecting
        the subject, regardless of the subject's colors.

        Strategy:
        1. Sample all pixels from the image (downsampled for performance)
        2. Test candidate chromakey colors (green, blue, magenta, cyan, yellow, red)
        3. For each candidate, calculate the MINIMUM distance to any pixel in the image
        4. Select the candidate with the MAXIMUM minimum distance (safest color)

        Example:
        - Image with blue and yellow subject → green chromakey selected (far from both)
        - Image with green subject → magenta chromakey selected (complementary color)

        Args:
            image_bytes: Image bytes

        Returns:
            Tuple of (RGB color, color_name, min_distance_score)
        """
        try:
            image = Image.open(BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # Downsample for performance (200x200 gives good coverage)
            img_small = image.resize((200, 200))
            pixels = np.array(img_small).reshape(-1, 3).astype(np.float32)

            # Candidate chromakey colors (bright, saturated colors for easy removal)
            candidate_colors = {
                'green': (0, 255, 0),
                'blue': (0, 0, 255),
                'magenta': (255, 0, 255),
                'cyan': (0, 255, 255),
                'yellow': (255, 255, 0),
                'red': (255, 0, 0),
            }

            best_color = None
            best_color_name = "green"
            max_min_distance = 0  # Maximum of minimum distances

            logger.info(f"Analyzing {len(pixels)} pixels to select optimal chromakey color...")

            # For each candidate color, find the minimum distance to ANY pixel in the image
            results = []
            for color_name, color_rgb in candidate_colors.items():
                target = np.array(color_rgb, dtype=np.float32)

                # Calculate Euclidean distance from this candidate to ALL pixels
                distances = np.linalg.norm(pixels - target, axis=1)

                # Key metrics:
                # - min_distance: closest any pixel gets to this chromakey color
                # - avg_distance: average distance (indicates general separation)
                # - percentile_10: 10th percentile distance (robustness check)
                min_distance = np.min(distances)
                avg_distance = np.mean(distances)
                percentile_10 = np.percentile(distances, 10)

                # Score = weighted combination favoring safe minimum distance
                # We want a color where even the CLOSEST pixel is far away
                score = min_distance * 0.5 + percentile_10 * 0.3 + (avg_distance * 0.2)

                results.append({
                    'name': color_name,
                    'rgb': color_rgb,
                    'min_distance': min_distance,
                    'avg_distance': avg_distance,
                    'percentile_10': percentile_10,
                    'score': score
                })

                logger.info(
                    f"  {color_name:8s}: min={min_distance:6.1f}, "
                    f"avg={avg_distance:6.1f}, p10={percentile_10:6.1f}, score={score:6.1f}"
                )

                # Track best score
                if score > max_min_distance:
                    max_min_distance = score
                    best_color = color_rgb
                    best_color_name = color_name

            # Sort results by score
            results.sort(key=lambda x: x['score'], reverse=True)

            logger.info(f"\n✓ Selected chromakey: {best_color_name.upper()} RGB{best_color}")
            logger.info(f"  Safety score: {max_min_distance:.1f}")
            logger.info(f"  Min distance to any pixel: {results[0]['min_distance']:.1f}")

            # If the minimum distance is too low (<50), warn about potential issues
            if results[0]['min_distance'] < 50:
                logger.warning(
                    f"⚠️  Warning: Best chromakey color {best_color_name} is only {results[0]['min_distance']:.1f} units away "
                    "from subject colors. May require higher tolerance for removal."
                )
                logger.warning(f"   Subject may contain colors similar to {best_color_name}.")

            return best_color, best_color_name, results[0]['min_distance']

        except Exception as e:
            logger.error(f"Error selecting chromakey color: {str(e)}", exc_info=True)
            # Default to green (classic chromakey)
            return (0, 255, 0), "green", 0.0

    def select_alternative_background_color(self, image_bytes: bytes) -> Tuple[int, int, int]:
        """
        DEPRECATED: Use select_optimal_chromakey_color() instead.

        Kept for backward compatibility.
        """
        color, _, _ = self.select_optimal_chromakey_color(image_bytes)
        return color
