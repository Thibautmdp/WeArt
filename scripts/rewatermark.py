"""
Script one-shot : re-applique le watermark discret sur toutes les images existantes.
Lance avec : python rewatermark.py
"""
import os
import sys

# Ajouter le dossier racine du projet au path
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from app import app, db
from models import Artwork, User
from utils.watermark import apply_watermark

UPLOAD_FOLDER = os.path.join(ROOT, 'uploads')

def rewatermark_all():
    with app.app_context():
        artworks = Artwork.query.filter(Artwork.watermarked_path.isnot(None)).all()
        total = len(artworks)
        print(f">> {total} image(s) a re-traiter\n")

        ok = 0
        skip = 0
        fail = 0

        for aw in artworks:
            original = os.path.join(UPLOAD_FOLDER, 'originals', os.path.basename(aw.file_path))
            watermarked = os.path.join(UPLOAD_FOLDER, 'watermarked', os.path.basename(aw.watermarked_path))

            if not os.path.exists(original):
                print(f"  [SKIP] #{aw.id} — original introuvable : {original}")
                skip += 1
                continue

            artist_name = aw.artist.username if aw.artist else 'WeArt'
            success = apply_watermark(original, watermarked, artist_name)

            if success:
                print(f"  [OK]   #{aw.id} — {aw.title} (@{artist_name})")
                ok += 1
            else:
                print(f"  [ERR]  #{aw.id} — {aw.title}")
                fail += 1

        print(f"\nTerminé : {ok} re-traités, {skip} ignorés, {fail} erreurs.")

if __name__ == '__main__':
    rewatermark_all()
