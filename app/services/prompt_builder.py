from typing import Dict


class PromptBuilder:
    """Service for building optimized prompts for background removal"""

    @staticmethod
    def build_prompt(image_analysis: Dict) -> str:
        """
        Build optimal prompt based on image analysis

        Args:
            image_analysis: Dictionary with image analysis results

        Returns:
            Optimized prompt for background removal
        """
        base_prompt = "Remove background completely, "

        # Handle complex edges (hair, fur)
        if image_analysis.get('has_hair', False):
            base_prompt += "preserve detailed hair strands with soft edges, avoid halos, "

        # Handle transparent objects (glass, reflections)
        if image_analysis.get('has_transparent_objects', False):
            base_prompt += "keep glass reflections and realistic transparency, "

        # Handle motion blur
        if image_analysis.get('has_motion_blur', False):
            base_prompt += "preserve motion blur and smooth edges, "

        # Handle brightness and contrast
        brightness = image_analysis.get('brightness', 128)
        if brightness < 100:
            base_prompt += "enhance subject in low light, "
        elif brightness > 200:
            base_prompt += "preserve highlights and bright areas, "

        # Add general requirements
        base_prompt += "maintain natural lighting, clean cutout, high precision"

        return base_prompt

    @staticmethod
    def build_simple_prompt() -> str:
        """Build simple default prompt"""
        return "Remove background completely, maintain natural lighting, clean cutout, high precision"

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
