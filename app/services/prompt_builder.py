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
        # Base instruction for background removal - очень специфичный и детальный
        base_prompt = (
            "Edit this image: Remove the entire background completely and make it fully transparent. "
            "Keep ONLY the main subject in the foreground. "
        )

        # Handle complex edges (hair, fur)
        if image_analysis.get('has_hair', False):
            base_prompt += (
                "The subject has complex edges like hair or fur - preserve every fine detail, "
                "maintain soft natural edges around hair strands, avoid any white halos or artifacts. "
            )

        # Handle transparent objects (glass, reflections)
        if image_analysis.get('has_transparent_objects', False):
            base_prompt += (
                "Preserve any glass, transparent materials, or reflective surfaces on the subject. "
                "Keep their natural transparency and reflections intact. "
            )

        # Handle motion blur
        if image_analysis.get('has_motion_blur', False):
            base_prompt += (
                "The image has motion blur - preserve the natural blur effect on the subject's edges. "
            )

        # Handle brightness and contrast
        brightness = image_analysis.get('brightness', 128)
        if brightness < 100:
            base_prompt += (
                "The image is dark - carefully separate the subject from dark background, "
                "enhance edge detection in low light. "
            )
        elif brightness > 200:
            base_prompt += (
                "The image is bright - preserve bright highlights on the subject, "
                "avoid overexposure when removing background. "
            )

        # Add critical requirements
        base_prompt += (
            "Requirements: "
            "1) Background must be 100% transparent (alpha channel = 0). "
            "2) Subject edges must be clean and natural, no pixelation. "
            "3) Preserve all shadows and highlights on the subject itself. "
            "4) Maintain the subject's original colors and lighting. "
            "5) Output as PNG with transparency."
        )

        return base_prompt

    @staticmethod
    def build_simple_prompt() -> str:
        """Build simple default prompt for background removal"""
        return (
            "Edit this image: Remove the entire background and make it fully transparent. "
            "Keep only the main subject. The background must be 100% transparent (alpha = 0). "
            "Preserve clean edges, natural colors, and all details of the subject. "
            "Output as PNG with transparency."
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
