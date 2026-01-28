from PIL import Image
import numpy as np

def process_logo(input_path, output_path, new_color=(0, 122, 255), size=(200, 200), threshold=240):
    """
    Process a logo by removing white background, resizing, and changing color.
    
    Parameters:
    - input_path: Path to the input image
    - output_path: Path to save the processed image
    - new_color: RGB tuple for the new logo color (default: blue)
    - size: Target size as (width, height) tuple
    - threshold: Brightness threshold for background removal (0-255)
    """
    
    # Open the image
    img = Image.open(input_path)
    
    # Convert to RGBA if not already
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Convert to numpy array for processing
    data = np.array(img)
    
    # Separate channels
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    
    # Create mask for white/light pixels (background)
    # Pixels where all RGB values are above threshold
    white_mask = (r > threshold) & (g > threshold) & (b > threshold)
    
    # Create mask for dark pixels (logo)
    logo_mask = ~white_mask
    
    # Create new image data
    new_data = np.zeros_like(data)
    
    # Set logo pixels to new color with full opacity
    new_data[logo_mask] = [new_color[0], new_color[1], new_color[2], 255]
    
    # Set background to transparent
    new_data[white_mask] = [0, 0, 0, 0]
    
    # Convert back to image
    processed_img = Image.fromarray(new_data, 'RGBA')
    
    # Crop to content (remove extra whitespace)
    bbox = processed_img.getbbox()
    if bbox:
        processed_img = processed_img.crop(bbox)
    
    # Resize maintaining aspect ratio
    processed_img.thumbnail(size, Image.Resampling.LANCZOS)
    
    # Save the result
    processed_img.save(output_path, 'PNG')
    print(f"✓ Logo processed successfully!")
    print(f"✓ Saved to: {output_path}")
    print(f"✓ Final size: {processed_img.size}")

# Example usage
if __name__ == "__main__":
    import argparse
    
    # Color options
    COLOR_BLUE = (0, 122, 255)
    COLOR_GREEN = (52, 199, 89)
    COLOR_PURPLE = (175, 82, 222)
    COLOR_RED = (255, 59, 48)
    COLOR_ORANGE = (255, 149, 0)
    COLOR_BLACK = (0, 0, 0)
    COLOR_TEAL = (48, 176, 199)
    COLOR_PINK = (255, 45, 85)
    
    COLORS = {
        'blue': COLOR_BLUE,
        'green': COLOR_GREEN,
        'purple': COLOR_PURPLE,
        'red': COLOR_RED,
        'orange': COLOR_ORANGE,
        'black': COLOR_BLACK,
        'teal': COLOR_TEAL,
        'pink': COLOR_PINK
    }
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Process logo: remove background, resize, and change color')
    parser.add_argument('input', help='Input image file path')
    parser.add_argument('output', help='Output image file path')
    parser.add_argument('-c', '--color', default='blue', 
                        choices=list(COLORS.keys()),
                        help='Logo color (default: blue)')
    parser.add_argument('-s', '--size', type=int, default=300,
                        help='Maximum width/height in pixels (default: 300)')
    parser.add_argument('-t', '--threshold', type=int, default=240,
                        help='Background removal threshold 0-255 (default: 240)')
    parser.add_argument('--rgb', type=int, nargs=3, metavar=('R', 'G', 'B'),
                        help='Custom RGB color (e.g., --rgb 255 100 50)')
    
    args = parser.parse_args()
    
    # Determine color
    if args.rgb:
        selected_color = tuple(args.rgb)
    else:
        selected_color = COLORS[args.color]
    
    # Process the logo
    process_logo(
        input_path=args.input,
        output_path=args.output,
        new_color=selected_color,
        size=(args.size, args.size),
        threshold=args.threshold
    )