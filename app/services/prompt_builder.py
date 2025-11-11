from typing import Dict


class PromptBuilder:
    """Service for building optimized prompts for background removal"""

    @staticmethod
    def build_prompt(image_analysis: Dict) -> str:
        """
        Build optimal prompt based on image analysis for background removal

        Args:
            image_analysis: Dictionary with image analysis results

        Returns:
            Optimized prompt for background removal
        """
        # Base instruction for background removal with green screen (chroma key approach)
        # Green screen is better supported by Gemini and will be post-processed to transparency
        base_prompt = (
            "Edit this image: Remove the entire background completely and replace it with a solid bright green background (RGB: 0, 255, 0). "
            "Keep ONLY the main subject in the foreground. "
            "Ensure clean, sharp edges around the subject with no green spill or halos. "
        )

        # Handle complex edges (hair, fur)
        if image_analysis.get('has_hair', False):
            base_prompt += (
                "The subject has complex edges like hair or fur - preserve every fine detail, "
                "maintain soft natural edges around hair strands with pixel-perfect separation from the green background. "
                "Avoid any green color bleeding into the hair strands. "
            )

        # Handle transparent objects (glass, reflections)
        if image_analysis.get('has_transparent_objects', False):
            base_prompt += (
                "Preserve any glass, transparent materials, or reflective surfaces on the subject. "
                "Keep their natural transparency and reflections intact, but ensure the background behind them is solid green. "
            )

        # Handle motion blur
        if image_analysis.get('has_motion_blur', False):
            base_prompt += (
                "The image has motion blur - preserve the natural blur effect on the subject's edges "
                "while maintaining clean separation from the green background. "
            )

        # Handle brightness and contrast
        brightness = image_analysis.get('brightness', 128)
        if brightness < 100:
            base_prompt += (
                "The image is dark - carefully separate the subject from the background, "
                "enhance edge detection in low light, ensure the green background is uniformly bright (RGB: 0, 255, 0). "
            )
        elif brightness > 200:
            base_prompt += (
                "The image is bright - preserve bright highlights on the subject, "
                "maintain consistent green background color throughout (RGB: 0, 255, 0). "
            )

        # Add critical requirements for green screen output
        base_prompt += (
            "Requirements: "
            "1) Background must be solid bright green (RGB: 0, 255, 0) with no gradients or variations. "
            "2) Subject edges must be pixel-perfect with clean separation and no green color cast. "
            "3) Preserve all fine details like hair strands with no green bleeding. "
            "4) Maintain the subject's original colors without any green tint or reflection. "
            "5) Output as PNG format. "
            "6) The green background should be uniform across the entire background area."
        )

        return base_prompt

    @staticmethod
    def build_simple_prompt() -> str:
        """Build simple default prompt for background removal"""
        return (
            "Edit this image: Remove the entire background and replace it with a solid bright green background (RGB: 0, 255, 0). "
            "Keep only the main subject. The green background must be uniform with no gradients. "
            "Preserve clean edges with no green spill, natural colors, and all details of the subject. "
            "Output as PNG format."
        )

    @staticmethod
    def build_custom_prompt(user_requirements: str, image_analysis: Dict) -> str:
        """
        Build custom prompt combining user requirements and image analysis

        Args:
            user_requirements: User's specific requirements
            image_analysis: Dictionary with image analysis results

        Returns:
            Custom prompt
        """
        base_prompt = PromptBuilder.build_prompt(image_analysis)
        return f"{user_requirements}. {base_prompt}"
