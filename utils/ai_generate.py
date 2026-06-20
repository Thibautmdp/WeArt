import os
import uuid
import requests
from config import UPLOAD_FOLDER


def generate_image_pollinations(prompt, width=768, height=768):
    """Generate image via Pollinations.ai — free, no API key needed."""
    import urllib.parse
    encoded = urllib.parse.quote(prompt)
    seed = uuid.uuid4().int % 100000
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&nologo=true"

    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 200 and resp.headers.get('content-type', '').startswith('image'):
            filename = f"ai_img_{uuid.uuid4().hex}.jpg"
            filepath = os.path.join(UPLOAD_FOLDER, 'originals', filename)
            with open(filepath, 'wb') as f:
                f.write(resp.content)
            return filename
    except Exception as e:
        print(f"Pollinations error: {e}")
    return None


def generate_image_hf(prompt, api_key):
    """Generate image via Hugging Face Inference API (Stable Diffusion XL).
    Returns (filename, error_type) where error_type is None, 'rate_limit', or 'error'."""
    if not api_key:
        return None, None
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"inputs": prompt, "parameters": {"width": 768, "height": 768, "num_inference_steps": 30}}

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code == 200 and 'image' in resp.headers.get('content-type', ''):
            filename = f"ai_img_{uuid.uuid4().hex}.jpg"
            filepath = os.path.join(UPLOAD_FOLDER, 'originals', filename)
            with open(filepath, 'wb') as f:
                f.write(resp.content)
            return filename, None
        if resp.status_code == 429:
            return None, 'rate_limit'
        print(f"HF image error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"HF image exception: {e}")
    return None, 'error'


def generate_music_hf(prompt, api_key):
    """Generate music via Hugging Face MusicGen.
    Returns (filename, error_type) where error_type is None, 'rate_limit', or 'error'."""
    if not api_key:
        return None, None
    API_URL = "https://api-inference.huggingface.co/models/facebook/musicgen-small"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"inputs": prompt}

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code == 200 and 'audio' in resp.headers.get('content-type', ''):
            filename = f"ai_music_{uuid.uuid4().hex}.wav"
            filepath = os.path.join(UPLOAD_FOLDER, 'audio', filename)
            with open(filepath, 'wb') as f:
                f.write(resp.content)
            return filename, None
        if resp.status_code == 429:
            return None, 'rate_limit'
        print(f"HF music error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"HF music exception: {e}")
    return None, 'error'
