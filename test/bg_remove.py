#!/usr/bin/env python3
"""
Standalone test script for background removal using chroma keying.

This script simulates the background removal process without making actual API calls
to OpenRouter. It uses the existing chroma key function to remove colored backgrounds.

Usage:
    python test/bg_remove.py
"""

import sys
import os
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PIL import Image
import logging
import numpy as np
import matplotlib.pyplot as plt
from collections import Counter

# Import the chroma key function from openrouter service
from app.services.openrouter import remove_colored_background, detect_dominant_background_color
from app.services.image_processor import ImageProcessor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def plot_color_histogram(image_path: str, output_path: str, title: str = "Color Distribution"):
    """
    Plot histogram of pixel colors in an image.

    Creates a visualization showing:
    - RGB channel histograms
    - Top 10 most common colors with their counts

    Args:
        image_path: Path to input image
        output_path: Path to save histogram plot
        title: Title for the plot
    """
    try:
        logger.info(f"Generating color histogram for {image_path}...")

        # Load image
        img = Image.open(image_path)

        # Convert to RGBA if not already
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Convert to numpy array
        data = np.array(img)

        # Get image dimensions
        height, width = data.shape[:2]
        total_pixels = height * width

        # Create figure with subplots
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle(title, fontsize=16, fontweight='bold')

        # Plot 1: RGB Histograms
        ax1 = axes[0, 0]
        colors = ['red', 'green', 'blue']
        channel_names = ['Red', 'Green', 'Blue']

        for i, (color, name) in enumerate(zip(colors, channel_names)):
            channel_data = data[:, :, i].flatten()
            ax1.hist(channel_data, bins=256, alpha=0.6, color=color, label=name, range=(0, 256))

        ax1.set_xlabel('Pixel Value')
        ax1.set_ylabel('Frequency')
        ax1.set_title('RGB Channel Distribution')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Plot 2: Alpha Channel Histogram (transparency)
        ax2 = axes[0, 1]
        alpha_data = data[:, :, 3].flatten()
        ax2.hist(alpha_data, bins=256, color='gray', alpha=0.7, range=(0, 256))
        ax2.set_xlabel('Alpha Value')
        ax2.set_ylabel('Frequency')
        ax2.set_title('Alpha Channel (Transparency)')
        ax2.grid(True, alpha=0.3)

        # Add transparency statistics
        transparent_pixels = np.sum(alpha_data == 0)
        opaque_pixels = np.sum(alpha_data == 255)
        semi_transparent = total_pixels - transparent_pixels - opaque_pixels

        stats_text = f"Transparent: {transparent_pixels:,} ({transparent_pixels/total_pixels*100:.1f}%)\n"
        stats_text += f"Opaque: {opaque_pixels:,} ({opaque_pixels/total_pixels*100:.1f}%)\n"
        stats_text += f"Semi-transparent: {semi_transparent:,} ({semi_transparent/total_pixels*100:.1f}%)"

        ax2.text(0.02, 0.98, stats_text, transform=ax2.transAxes,
                verticalalignment='top', fontsize=9, bbox=dict(boxstyle='round',
                facecolor='wheat', alpha=0.5))

        # Plot 3: Top 10 Most Common Colors
        ax3 = axes[1, 0]

        # Get unique colors and their counts (only non-transparent pixels)
        non_transparent_mask = data[:, :, 3] > 0
        rgb_data = data[:, :, :3][non_transparent_mask]

        if len(rgb_data) > 0:
            # Convert RGB pixels to tuples for counting
            pixels_as_tuples = [tuple(pixel) for pixel in rgb_data]
            color_counts = Counter(pixels_as_tuples)

            # Get top 10 most common colors
            top_colors = color_counts.most_common(10)

            # Create bar chart
            y_pos = np.arange(len(top_colors))
            counts = [count for _, count in top_colors]
            color_rgbs = [color for color, _ in top_colors]

            # Normalize RGB values for matplotlib (0-1 range)
            bar_colors = [(r/255, g/255, b/255) for r, g, b in color_rgbs]

            bars = ax3.barh(y_pos, counts, color=bar_colors, edgecolor='black', linewidth=1)

            # Add RGB labels
            labels = [f"RGB{color}" for color in color_rgbs]
            ax3.set_yticks(y_pos)
            ax3.set_yticklabels(labels, fontsize=8)
            ax3.set_xlabel('Pixel Count')
            ax3.set_title('Top 10 Most Common Colors (Non-transparent)')
            ax3.grid(True, alpha=0.3, axis='x')

            # Add count labels on bars
            for i, (bar, count) in enumerate(zip(bars, counts)):
                width = bar.get_width()
                ax3.text(width, bar.get_y() + bar.get_height()/2,
                        f' {count:,} ({count/len(pixels_as_tuples)*100:.1f}%)',
                        ha='left', va='center', fontsize=8)
        else:
            ax3.text(0.5, 0.5, 'No non-transparent pixels',
                    ha='center', va='center', transform=ax3.transAxes)
            ax3.set_title('Top 10 Most Common Colors (Non-transparent)')

        # Plot 4: Color Distribution Statistics
        ax4 = axes[1, 1]
        ax4.axis('off')

        # Calculate statistics
        stats = []
        stats.append(f"Image: {Path(image_path).name}")
        stats.append(f"Size: {width} x {height} pixels")
        stats.append(f"Total pixels: {total_pixels:,}")
        stats.append(f"Mode: {img.mode}")
        stats.append("")
        stats.append("Channel Statistics:")

        for i, name in enumerate(['Red', 'Green', 'Blue', 'Alpha']):
            channel = data[:, :, i].flatten()
            stats.append(f"  {name}:")
            stats.append(f"    Mean: {np.mean(channel):.2f}")
            stats.append(f"    Std Dev: {np.std(channel):.2f}")
            stats.append(f"    Min: {np.min(channel)}")
            stats.append(f"    Max: {np.max(channel)}")

        if len(rgb_data) > 0:
            stats.append("")
            stats.append(f"Unique colors (non-transparent): {len(color_counts):,}")

        stats_text = '\n'.join(stats)
        ax4.text(0.1, 0.95, stats_text, transform=ax4.transAxes,
                verticalalignment='top', fontfamily='monospace', fontsize=9)

        # Adjust layout and save
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        logger.info(f"Histogram saved to {output_path}")

        # Close the plot to free memory
        plt.close(fig)

        return True

    except Exception as e:
        logger.error(f"Error generating histogram: {str(e)}", exc_info=True)
        return False


def test_chromakey_selection(image_path: str):
    """
    Test intelligent chromakey color selection.

    This demonstrates how the bot selects the optimal chromakey color
    with maximum distance from all colors in the subject image.

    Args:
        image_path: Path to input image
    """
    try:
        logger.info("=" * 60)
        logger.info("Testing Intelligent Chromakey Selection")
        logger.info("=" * 60)

        # Read image
        with open(image_path, 'rb') as f:
            image_bytes = f.read()

        # Use the intelligent chromakey selector
        processor = ImageProcessor()
        chromakey_color, color_name, min_distance = processor.select_optimal_chromakey_color(image_bytes)

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"RESULT: Best chromakey color is {color_name.upper()}")
        logger.info(f"RGB: {chromakey_color}")
        logger.info(f"Minimum distance to subject: {min_distance:.1f}")
        logger.info("=" * 60)
        logger.info("")

        return chromakey_color, color_name

    except Exception as e:
        logger.error(f"Error in chromakey selection test: {str(e)}", exc_info=True)
        return (0, 255, 0), "green"


def test_background_removal(
    input_path: str = "test/source.png",
    output_path: str = "test/transparent.png",
    target_color: tuple = None,  # Will be auto-selected if None
    tolerance: int = 50,
    auto_detect: bool = True,
    edge_feather: bool = True
):
    """
    Test background removal using chroma keying.

    This simulates what OpenRouter would do:
    1. Analyze image to select optimal chromakey color (max distance from subject)
    2. AI generates image with that chromakey background (simulated by using source as-is)
    3. Chroma keying is applied to make the background transparent

    Args:
        input_path: Path to input image
        output_path: Path to save output image
        target_color: RGB tuple of background color to remove. If None, will be intelligently selected
        tolerance: Color tolerance for chroma keying (0-255)
        auto_detect: If True, automatically detect the background color
        edge_feather: If True, apply edge feathering for smoother transitions
    """
    try:
        logger.info(f"Starting background removal test")
        logger.info(f"Input: {input_path}")
        logger.info(f"Output: {output_path}")
        logger.info(f"Target color: {target_color}")
        logger.info(f"Tolerance: {tolerance}")
        logger.info(f"Auto-detect: {auto_detect}")

        # Read input image
        logger.info("Reading input image...")
        with open(input_path, 'rb') as f:
            image_bytes = f.read()

        # Display image info
        img = Image.open(input_path)
        logger.info(f"Image size: {img.size}")
        logger.info(f"Image mode: {img.mode}")
        logger.info(f"Image format: {img.format}")

        # If no target color specified, intelligently select optimal chromakey color
        if target_color is None:
            logger.info("\n" + "=" * 60)
            logger.info("Step 1: Intelligent Chromakey Selection")
            logger.info("=" * 60)
            processor = ImageProcessor()
            target_color, color_name, min_distance = processor.select_optimal_chromakey_color(image_bytes)
            logger.info(f"\n✓ Selected: {color_name.upper()} RGB{target_color}")
            logger.info(f"  Safety distance: {min_distance:.1f}")
            logger.info("")

        # Detect dominant background color if requested
        if auto_detect:
            logger.info("\n" + "=" * 60)
            logger.info("Step 2: Detect Actual Background Color")
            logger.info("=" * 60)
            detected_color = detect_dominant_background_color(image_bytes, requested_color=target_color)
            logger.info(f"✓ Detected background color: {detected_color}")
            logger.info("")

        # Apply chroma keying to remove background
        logger.info("\n" + "=" * 60)
        logger.info("Step 3: Apply Chroma Key Background Removal")
        logger.info("=" * 60)
        logger.info(f"Target color: {target_color}")
        logger.info(f"Tolerance: {tolerance}")
        logger.info(f"Edge feather: {edge_feather}")
        logger.info("")
        result_bytes = remove_colored_background(
            image_bytes=image_bytes,
            target_color=target_color,
            tolerance=tolerance,
            auto_detect=auto_detect,
            edge_feather=edge_feather
        )

        # Save result
        logger.info(f"Saving result to {output_path}...")
        with open(output_path, 'wb') as f:
            f.write(result_bytes)

        # Display result info
        result_img = Image.open(output_path)
        logger.info(f"Result size: {result_img.size}")
        logger.info(f"Result mode: {result_img.mode}")

        # Check if transparency was applied
        if result_img.mode == 'RGBA':
            data = np.array(result_img)
            transparent_pixels = np.sum(data[:, :, 3] == 0)
            total_pixels = data.shape[0] * data.shape[1]
            transparency_percent = (transparent_pixels / total_pixels) * 100
            logger.info(f"Transparent pixels: {transparent_pixels}/{total_pixels} ({transparency_percent:.2f}%)")

        logger.info("Background removal completed successfully!")
        logger.info(f"Output saved to: {output_path}")

        # Generate histograms
        logger.info("\nGenerating color histograms...")

        # Histogram for source image
        source_hist_path = str(Path(output_path).parent / "histogram_source.png")
        plot_color_histogram(
            input_path,
            source_hist_path,
            title="Source Image - Color Distribution"
        )

        # Histogram for result image
        result_hist_path = str(Path(output_path).parent / "histogram_result.png")
        plot_color_histogram(
            output_path,
            result_hist_path,
            title="Result Image - Color Distribution (After Background Removal)"
        )

        logger.info(f"Histograms saved:")
        logger.info(f"  Source: {source_hist_path}")
        logger.info(f"  Result: {result_hist_path}")

        return True

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        logger.error(f"Make sure {input_path} exists")
        return False

    except Exception as e:
        logger.error(f"Error during background removal: {str(e)}", exc_info=True)
        return False


def main():
    """Main entry point for the test script."""

    # Define paths
    test_dir = Path(__file__).parent
    input_path = test_dir / "source.png"
    output_path = test_dir / "transparent.png"

    # Check if input file exists
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        logger.info("Please create test/source.png with an image that has a solid background")
        logger.info("For best results, use an image with a green, blue, or other solid color background")
        return False

    # Run test with auto-detection enabled
    logger.info("=" * 60)
    logger.info("Background Removal Test - Auto-detect mode")
    logger.info("=" * 60)

    # First, demonstrate intelligent chromakey selection
    logger.info("\n🎨 Demonstrating intelligent chromakey color selection...")
    logger.info("This shows how the bot chooses the best color for background removal.\n")

    chromakey_color, color_name = test_chromakey_selection(str(input_path))

    # Now run the actual background removal test
    logger.info("\n📸 Running background removal with selected chromakey color...\n")

    success = test_background_removal(
        input_path=str(input_path),
        output_path=str(output_path),
        target_color=None,  # Auto-select optimal chromakey color
        tolerance=40,
        auto_detect=True,
        edge_feather=True  # Enable smooth edge transitions
    )

    if success:
        logger.info("\n" + "=" * 60)
        logger.info("Test completed successfully!")
        logger.info(f"Check the result at: {output_path}")
        logger.info("=" * 60)
    else:
        logger.error("\n" + "=" * 60)
        logger.error("Test failed!")
        logger.error("=" * 60)

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
