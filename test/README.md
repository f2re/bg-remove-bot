# Background Removal Test Suite

This directory contains a standalone test script for background removal using chroma keying.

## Files

- `bg_remove.py` - Main test script with histogram visualization
- `source.png` - Your source image (you need to provide this)
- `transparent.png` - Result with removed background (generated)
- `histogram_source.png` - Color distribution of source image (generated)
- `histogram_result.png` - Color distribution after removal (generated)

## Improvements

### 1. Intelligent Chromakey Selection (`select_optimal_chromakey_color`)

**Purpose:** Select the optimal chromakey color with MAXIMUM distance from ALL subject colors.

**Why this matters:**
- Before sending to AI, the bot analyzes the subject image
- It chooses a chromakey color that won't conflict with the subject
- AI generates the image with that safe chromakey background
- Chroma keying cleanly removes it without affecting the subject

**Algorithm:**
1. Sample all pixels from the image (200x200 downsampled)
2. Test 6 candidate colors: green, blue, magenta, cyan, yellow, red
3. For each candidate, calculate distance to EVERY pixel
4. Find minimum distance (closest any pixel gets to the chromakey)
5. Select candidate with the MAXIMUM minimum distance

**Scoring:**
```python
score = min_distance * 0.5 + percentile_10 * 0.3 + avg_distance * 0.2
```

**Examples:**
```
Image with blue + yellow subject:
  green   : min=145.2, avg=187.3, p10=156.8, score=163.4 ✓ SELECTED
  blue    : min=  8.1, avg=125.4, p10= 45.2, score= 42.1
  magenta : min= 98.5, avg=165.2, p10=118.4, score=120.8

Image with green subject:
  magenta : min=156.3, avg=201.5, p10=178.2, score=171.9 ✓ SELECTED
  green   : min= 12.4, avg=145.8, p10= 58.7, score= 52.8
  cyan    : min=102.1, avg=172.4, p10=135.6, score=125.8
```

### 2. Advanced Color Detection (`detect_dominant_background_color`)

**Old approach:**
- Sampled only 4 corners
- Counted exact pixel colors (RGB(0,0,255) ≠ RGB(1,1,253))
- Failed with color variations/gradients

**New approach:**
- Samples entire image border (top, bottom, left, right)
- **Clusters similar colors** using tolerance-based grouping
- Groups color variations like RGB(0,0,255), RGB(1,1,253), RGB(2,0,254) together
- Returns **average color** of dominant cluster
- Better handles gradients and compression artifacts

**Example:**
```
Blue background with variations:
- RGB(0,0,255): 1000 pixels
- RGB(1,1,253): 800 pixels
- RGB(2,0,254): 700 pixels
- RGB(0,1,255): 600 pixels

Old: Detects RGB(0,0,255) - only 1000 pixels
New: Clusters all ~3100 pixels, returns avg RGB(1,0,254)
```

### 3. Improved Chroma Keying (`remove_colored_background`)

**Old approach:**
- Checked each RGB channel independently
- Hard cutoff at tolerance threshold
- Produced hard edges

**New approach:**
- Uses **Euclidean distance** for color matching
- Better handles color variations in 3D color space
- **Edge feathering** for smooth transitions
- Creates semi-transparent pixels near edges
- More natural-looking results

**Mathematical improvements:**
```python
# Old: Per-channel comparison
is_background = (R_diff < tol) AND (G_diff < tol) AND (B_diff < tol)

# New: Euclidean distance
distance = sqrt((R_diff)² + (G_diff)² + (B_diff)²)
is_background = distance < threshold

# Plus feathering zone:
if distance in [threshold, threshold+feather]:
    alpha = interpolate(distance, 0, 255)
```

## Usage

```bash
# Place your test image
cp your_image.png test/source.png

# Run the test
python test/bg_remove.py

# Or from project root
python -m test.bg_remove
```

## Parameters

You can modify these in `main()`:

```python
test_background_removal(
    input_path="test/source.png",
    output_path="test/transparent.png",
    target_color=(0, 0, 255),  # RGB hint (auto-detected)
    tolerance=100,              # Higher = more aggressive removal
    auto_detect=True,           # Auto-detect background color
    edge_feather=True           # Smooth edge transitions
)
```

### Tolerance Guidelines

- **30-50**: Conservative, for solid uniform backgrounds
- **50-80**: Moderate, handles slight compression artifacts
- **80-120**: Aggressive, for gradients and color variations
- **120+**: Very aggressive, may remove subject pixels

## Histogram Visualization

The script generates comprehensive histograms showing:

1. **RGB Channel Distribution** - Color distribution per channel
2. **Alpha Channel (Transparency)** - Shows transparent/opaque/semi-transparent pixels
3. **Top 10 Most Common Colors** - Bar chart with actual colors and pixel counts
4. **Statistics** - Channel means, std dev, unique color count

## How It Works

### Complete Workflow

```
1. Load source image
   ↓
2. SELECT OPTIMAL CHROMAKEY COLOR (NEW!)
   - Analyze all subject colors (200x200 pixels)
   - Test 6 candidate chromakey colors
   - Calculate min distance to ANY subject pixel
   - Select color with MAXIMUM safety distance
   - Example: Blue+Yellow subject → Green chromakey
   ↓
3. [In production] AI generates image with selected chromakey
   - Prompt specifies the chosen chromakey color
   - AI creates image: subject + chromakey background
   - (In test: we use source image as-is)
   ↓
4. Detect actual background color
   - Sample 10px border from all edges
   - Cluster colors with tolerance=30
   - Find largest cluster
   - Calculate average color
   ↓
5. Apply chroma keying
   - Calculate Euclidean distance for each pixel
   - Full transparency if distance < threshold
   - Partial transparency in feather zone
   ↓
6. Generate histograms
   - Source image color distribution
   - Result image color distribution
   ↓
7. Save results
```

## Example Results

### Example 1: Blue Background Image

**Chromakey selection:**
```
Analyzing 40,000 pixels to select optimal chromakey color...
  green   : min=145.2, avg=187.3, p10=156.8, score=163.4
  blue    : min=  8.1, avg=125.4, p10= 45.2, score= 42.1
  magenta : min= 98.5, avg=165.2, p10=118.4, score=120.8
  cyan    : min= 52.3, avg=142.1, p10= 78.4, score= 75.9
  yellow  : min=132.7, avg=178.9, p10=148.3, score=147.2
  red     : min=115.4, avg=168.7, p10=135.2, score=128.3

✓ Selected chromakey: GREEN RGB(0, 255, 0)
  Safety score: 163.4
  Min distance to any pixel: 145.2
```

**Background removal:**

```
Sampled 12,800 border pixels from 10px border
Found 247 color clusters with tolerance=30
Dominant cluster: 8,456 pixels (66.1% of border)
Cluster center: RGB(0,0,255), Average color: RGB(1,0,254)
Chroma key removal completed for color (1, 0, 254) with tolerance=100
Removed 245,632 pixels (48.2% of image)
Applied edge feathering to 12,847 pixels
```

## Troubleshooting

**Too much removed:**
- Decrease `tolerance` (try 50-80)
- Disable `edge_feather`

**Background remains:**
- Increase `tolerance` (try 100-150)
- Check histogram to see actual background colors
- Verify border contains background (not cropped too tight)

**Subject has green/blue tint:**
- Subject too close to background color
- Try different background color in original image
