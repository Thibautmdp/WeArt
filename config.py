import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

# En production, les fichiers vont sur Cloudflare R2
USE_R2 = os.environ.get('R2_BUCKET_NAME') is not None


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-prod')

    # PostgreSQL en prod (Neon), SQLite en local
    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'artiste.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

    UPLOAD_FOLDER = UPLOAD_FOLDER
    ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_AUDIO_EXT = {'mp3', 'wav', 'ogg', 'flac', 'm4a'}
    ALLOWED_VIDEO_EXT = {'mp4', 'webm', 'mov', 'avi'}

    # Cloudflare R2
    R2_ENDPOINT = os.environ.get('R2_ENDPOINT', '')
    R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY', '')
    R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY', '')
    R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', '')
    R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL', '')  # URL publique du bucket

    HF_API_KEY = os.environ.get('HF_API_KEY', '')
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY', '')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
