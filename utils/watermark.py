import os
from PIL import Image, ImageDraw, ImageFont
import math


def apply_watermark(input_path, output_path, artist_name, opacity=22):
    try:
        img = Image.open(input_path).convert('RGBA')
        w, h = img.size

        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        text = f"© {artist_name}"
        font_size = max(12, min(w, h) // 60)

        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # Coin bas-droite, petite marge
        margin = 12
        x = w - text_w - margin
        y = h - text_h - margin
        draw.text((x, y), text, font=font, fill=(255, 255, 255, opacity))

        combined = Image.alpha_composite(img, overlay)
        combined.convert('RGB').save(output_path, 'JPEG', quality=85)
        return True
    except Exception as e:
        print(f"Watermark error: {e}")
        return False


def generate_thumbnail(input_path, output_path, size=(400, 400)):
    try:
        img = Image.open(input_path)
        img.thumbnail(size, Image.LANCZOS)
        img.convert('RGB').save(output_path, 'JPEG', quality=80)
        return True
    except Exception as e:
        print(f"Thumbnail error: {e}")
        return False
