"""
AI Background Remover - RHHHAAAAA Edition
Uses rembg if available, otherwise fallback to simple chroma/edge method
"""

import os
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image

def is_rembg_available():
    try:
        import rembg
        # Also check onnxruntime backend - rembg needs it
        try:
            import onnxruntime
            return True
        except ImportError:
            # rembg installed but no backend - will fallback
            return False
    except ImportError:
        return False

def remove_background(input_path: str, output_path: str, model: str = "u2net", alpha_matting: bool = False) -> Tuple[bool, str]:
    """
    Remove background from image
    Returns (success, message)
    """
    try:
        # Try rembg first (best quality)
        try:
            from rembg import remove
            # Check backend
            try:
                import onnxruntime
            except ImportError:
                print("onnxruntime not found - rembg needs pip install onnxruntime or rembg[cpu]")
                return _fallback_remove_bg(input_path, output_path)

            with open(input_path, 'rb') as i:
                input_data = i.read()
            
            # Optional: choose model
            # model options: u2net, u2net_human_seg, isnet-general-use
            kwargs = {}
            if alpha_matting:
                kwargs["alpha_matting"] = True
            
            output_data = remove(input_data, **kwargs)
            
            with open(output_path, 'wb') as o:
                o.write(output_data)
            
            return True, f"Background removed via rembg ({model})"
        
        except ImportError as e:
            # Fallback: simple method using Pillow - convert white background to transparent
            # This is basic but works for many product photos
            if "onnxruntime" in str(e).lower() or "rembg" in str(e).lower():
                print(f"rembg backend missing: {e}")
            return _fallback_remove_bg(input_path, output_path)
        
        except Exception as e:
            # If rembg fails (including no onnxruntime backend), try fallback
            msg = str(e).lower()
            if "onnxruntime" in msg or "backend" in msg or "no onnx" in msg:
                print(f"rembg backend error: {e} - install with pip install onnxruntime or rembg[cpu]")
                return _fallback_remove_bg(input_path, output_path)
            print(f"rembg failed: {e}, trying fallback")
            return _fallback_remove_bg(input_path, output_path)
    
    except Exception as e:
        return False, f"BG removal failed: {e}"

def _fallback_remove_bg(input_path: str, output_path: str, tolerance: int = 30) -> Tuple[bool, str]:
    """
    Simple fallback: if image has mostly white background, make it transparent
    Also handles green screen-ish removal
    """
    try:
        im = Image.open(input_path).convert("RGBA")
        datas = im.getdata()
        
        new_data = []
        # Sample corners to guess background color
        w, h = im.size
        corners = [
            im.getpixel((0,0)),
            im.getpixel((w-1,0)),
            im.getpixel((0,h-1)),
            im.getpixel((w-1,h-1)),
        ]
        # Average corner color
        avg_r = sum(c[0] for c in corners) // 4
        avg_g = sum(c[1] for c in corners) // 4
        avg_b = sum(c[2] for c in corners) // 4
        
        # If background is near white or near green (for green screen)
        is_white_bg = avg_r > 200 and avg_g > 200 and avg_b > 200
        is_green_bg = avg_g > 150 and avg_r < 150 and avg_b < 150
        
        if not (is_white_bg or is_green_bg):
            # Not a simple background, just convert and save as PNG with alpha
            # For real removal, user needs rembg
            im.save(output_path, "PNG")
            return True, "No simple background detected - saved as PNG with alpha (install rembg for AI removal: pip install rembg)"
        
        for item in datas:
            # If pixel close to background color, make transparent
            if is_white_bg:
                if item[0] > 220 and item[1] > 220 and item[2] > 220:
                    new_data.append((255,255,255,0))
                else:
                    new_data.append(item)
            elif is_green_bg:
                # Green screen removal
                if item[1] > 150 and item[0] < 150 and item[2] < 150 and item[1] > item[0]*1.2:
                    new_data.append((item[0], item[1], item[2], 0))
                else:
                    new_data.append(item)
            else:
                new_data.append(item)
        
        im.putdata(new_data)
        im.save(output_path, "PNG")
        return True, f"Background removed via fallback (bg was {'white' if is_white_bg else 'green'}) - for better results: pip install rembg"
    
    except Exception as e:
        return False, f"Fallback BG removal failed: {e}"

def add_background(input_path: str, output_path: str, bg_color: Tuple[int,int,int] = (255,255,255)) -> Tuple[bool, str]:
    """Add solid background to transparent image"""
    try:
        im = Image.open(input_path).convert("RGBA")
        bg = Image.new("RGBA", im.size, bg_color + (255,))
        combined = Image.alpha_composite(bg, im)
        # Save as RGB if no alpha needed
        if output_path.lower().endswith(('.jpg','.jpeg')):
            combined = combined.convert("RGB")
        combined.save(output_path)
        return True, f"Added background {bg_color}"
    except Exception as e:
        return False, str(e)
