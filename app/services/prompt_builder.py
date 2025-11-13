from typing import Dict, Tuple


class PromptBuilder:
    """Service for building optimized prompts for background removal"""

    @staticmethod
    def build_prompt(image_analysis: Dict, background_color: Tuple[int, int, int] = None, transparent: bool = False) -> str:
        """
        Build optimal prompt based on image analysis for background removal

        Args:
            image_analysis: Dictionary with image analysis results
            background_color: RGB tuple for background color (default: white 255,255,255)
            transparent: If True, request transparent background instead of colored

        Returns:
            Optimized prompt for background removal
        """
        # Handle transparent background request
        if transparent:
            return PromptBuilder.build_transparent_prompt(image_analysis)

        # Default to white if no color specified
        if background_color is None:
            background_color = (255, 255, 255)

        r, g, b = background_color
        color_name = PromptBuilder._get_color_name(background_color)

        # Base instruction for background removal with specified color
        base_prompt = (
            f"Edit this image: Remove the entire background completely and replace it with a solid bright {color_name} background (RGB: {r}, {g}, {b}). "
            "Keep ONLY the main subject in the foreground. "
            f"Ensure clean, sharp edges around the subject with no {color_name} spill or halos. "
        )

        # Handle complex edges (hair, fur)
        if image_analysis.get('has_hair', False):
            base_prompt += (
                "The subject has complex edges like hair or fur - preserve every fine detail, "
                f"maintain soft natural edges around hair strands with pixel-perfect separation from the {color_name} background. "
                f"Avoid any {color_name} color bleeding into the hair strands. "
            )

        # Handle transparent objects (glass, reflections)
        if image_analysis.get('has_transparent_objects', False):
            base_prompt += (
                "Preserve any glass, transparent materials, or reflective surfaces on the subject. "
                f"Keep their natural transparency and reflections intact, but ensure the background behind them is solid {color_name}. "
            )

        # Handle motion blur
        if image_analysis.get('has_motion_blur', False):
            base_prompt += (
                "The image has motion blur - preserve the natural blur effect on the subject's edges "
                f"while maintaining clean separation from the {color_name} background. "
            )

        # Handle brightness and contrast
        brightness = image_analysis.get('brightness', 128)
        if brightness < 100:
            base_prompt += (
                "The image is dark - carefully separate the subject from the background, "
                f"enhance edge detection in low light, ensure the {color_name} background is uniformly bright (RGB: {r}, {g}, {b}). "
            )
        elif brightness > 200:
            base_prompt += (
                "The image is bright - preserve bright highlights on the subject, "
                f"maintain consistent {color_name} background color throughout (RGB: {r}, {g}, {b}). "
            )

        # Add critical requirements for colored screen output
        base_prompt += (
            "Requirements: "
            f"1) Background must be solid bright {color_name} (RGB: {r}, {g}, {b}) with no gradients or variations. "
            f"2) Subject edges must be pixel-perfect with clean separation and no {color_name} color cast. "
            f"3) Preserve all fine details like hair strands with no {color_name} bleeding. "
            f"4) Maintain the subject's original colors without any {color_name} tint or reflection. "
            "5) Output as PNG format. "
            f"6) The {color_name} background should be uniform across the entire background area."
        )

        return base_prompt

    @staticmethod
    def build_transparent_prompt(image_analysis: Dict) -> str:
        """
        Build prompt specifically for transparent background (PNG with alpha channel)

        Args:
            image_analysis: Dictionary with image analysis results

        Returns:
            Optimized prompt for transparent background removal
        """
        # Base instruction for transparent background
        base_prompt = (
            "Edit this image: Remove the entire background completely and replace it with FULL TRANSPARENCY (alpha channel = 0). "
            "Keep ONLY the main subject in the foreground. "
            "The background must be completely transparent - not white, not colored, but truly transparent with alpha = 0. "
            "Ensure clean, sharp edges around the subject. "
        )

        # Handle complex edges (hair, fur)
        if image_analysis.get('has_hair', False):
            base_prompt += (
                "The subject has complex edges like hair or fur - preserve every fine detail and strand. "
                "Maintain soft, natural edges around hair with pixel-perfect transparency behind each strand. "
                "Use alpha blending for semi-transparent edges. "
            )

        # Handle transparent objects (glass, reflections)
        if image_analysis.get('has_transparent_objects', False):
            base_prompt += (
                "Preserve any glass, transparent materials, or reflective surfaces on the subject. "
                "Keep their natural transparency and reflections intact using appropriate alpha channel values. "
                "The subject's transparency should be preserved, but the background should be fully transparent (alpha = 0). "
            )

        # Handle motion blur
        if image_analysis.get('has_motion_blur', False):
            base_prompt += (
                "The image has motion blur - preserve the natural blur effect on the subject's edges "
                "while maintaining clean transparency separation. Use alpha blending for smooth transitions. "
            )

        # Handle brightness and contrast
        brightness = image_analysis.get('brightness', 128)
        if brightness < 100:
            base_prompt += (
                "The image is dark - carefully separate the subject from the background using enhanced edge detection. "
                "Ensure proper alpha channel values even in dark areas. "
            )
        elif brightness > 200:
            base_prompt += (
                "The image is bright - preserve bright highlights on the subject while maintaining clear transparency. "
            )

        # Critical requirements for transparent PNG output
        base_prompt += (
            "\n\nCritical requirements: "
            "1) Output must be PNG format with alpha channel (RGBA). "
            "2) Background must have alpha = 0 (completely transparent, not white or any color). "
            "3) Subject edges must be clean with proper alpha blending for anti-aliasing. "
            "4) Preserve all fine details like hair strands with semi-transparent alpha for natural edges. "
            "5) The subject itself keeps full opacity (alpha = 255) except for naturally transparent parts. "
            "6) No colored background whatsoever - pure transparency only."
        )

        return base_prompt

    @staticmethod
    def build_simple_prompt() -> str:
        """Build simple default prompt for background removal"""
        return (
            "Edit this image: Remove the entire background and replace it with a solid bright white background (RGB: 255, 255, 255). "
            "Keep only the main subject. The white background must be uniform with no gradients. "
            "Preserve clean edges with no white spill, natural colors, and all details of the subject. "
            "Output as PNG format."
        )

    @staticmethod
    def build_custom_prompt(user_requirements: str, image_analysis: Dict, background_color: Tuple[int, int, int] = None) -> str:
        """
        Build custom prompt combining user requirements and image analysis

        Args:
            user_requirements: User's specific requirements
            image_analysis: Dictionary with image analysis results
            background_color: RGB tuple for background color

        Returns:
            Custom prompt
        """
        base_prompt = PromptBuilder.build_prompt(image_analysis, background_color)
        return f"{user_requirements}. {base_prompt}"

    @staticmethod
    def _get_color_name(rgb: Tuple[int, int, int]) -> str:
        """
        Get human-readable color name from RGB tuple

        Args:
            rgb: RGB tuple (r, g, b)

        Returns:
            Color name as string
        """
        r, g, b = rgb

        # Define common colors
        color_map = {
            (0, 255, 0): "green",
            (0, 0, 255): "blue",
            (255, 0, 255): "magenta",
            (0, 255, 255): "cyan",
            (255, 255, 0): "yellow",
            (255, 0, 0): "red",
            (255, 255, 255): "white",
            (0, 0, 0): "black",
        }

        # Exact match
        if rgb in color_map:
            return color_map[rgb]

        # Approximate match based on dominant channel
        if r > g and r > b:
            if g > 100 and b < 100:
                return "orange" if g < 200 else "yellow"
            elif b > 100 and g < 100:
                return "magenta"
            else:
                return "red"
        elif g > r and g > b:
            if r > 100 and b < 100:
                return "yellow"
            elif b > 100 and r < 100:
                return "cyan"
            else:
                return "green"
        elif b > r and b > g:
            if r > 100 and g < 100:
                return "magenta"
            elif g > 100 and r < 100:
                return "cyan"
            else:
                return "blue"
        else:
            # Similar values
            if r > 200 and g > 200 and b > 200:
                return "white"
            elif r < 50 and g < 50 and b < 50:
                return "black"
            else:
                return "gray"
