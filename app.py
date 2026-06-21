import os
import re
import uuid
import hmac
import hashlib
import time
import secrets
import mimetypes
import stripe
import boto3
try:
    import cloudinary
    import cloudinary.uploader
except ImportError:
    cloudinary = None
from flask import (Flask, render_template, redirect, url_for, request,
                   flash, jsonify, send_from_directory, abort, session, Response, stream_with_context)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from config import Config, UPLOAD_FOLDER
from models import (db, User, Artwork, Follow, Like, Comment,
                    Message, Notification, Order, PasswordReset, CreationStep, MEDIA_TYPES)
from utils.watermark import apply_watermark, generate_thumbnail
from utils.ai_generate import generate_image_pollinations, generate_image_hf, generate_music_hf

app = Flask(__name__)
app.config.from_object(Config)

# Client Cloudflare R2 (None en local si pas configuré)
_r2 = None
def get_r2():
    global _r2
    if _r2 is None and app.config.get('R2_ENDPOINT'):
        _r2 = boto3.client(
            's3',
            endpoint_url=app.config['R2_ENDPOINT'],
            aws_access_key_id=app.config['R2_ACCESS_KEY'],
            aws_secret_access_key=app.config['R2_SECRET_KEY'],
            region_name='auto',
        )
    return _r2


def use_cloudinary():
    return bool(cloudinary and app.config.get('CLOUDINARY_CLOUD_NAME'))


def cloudinary_upload_file(local_path, subfolder, filename):
    if not use_cloudinary():
        return
    cloudinary.config(
        cloud_name=app.config['CLOUDINARY_CLOUD_NAME'],
        api_key=app.config['CLOUDINARY_API_KEY'],
        api_secret=app.config['CLOUDINARY_API_SECRET'],
        secure=True
    )
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    resource_type = 'video' if ext in (app.config['ALLOWED_AUDIO_EXT'] | app.config['ALLOWED_VIDEO_EXT']) else 'image'
    name_no_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
    cloudinary.uploader.upload(
        local_path,
        public_id=f"weart/{subfolder}/{name_no_ext}",
        resource_type=resource_type,
        overwrite=True
    )

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Connecte-toi pour accéder à cette page.'

stripe.api_key = app.config['STRIPE_SECRET_KEY']


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def allowed_file(filename, category='image'):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if category == 'image':
        return ext in app.config['ALLOWED_IMAGE_EXT']
    if category == 'audio':
        return ext in app.config['ALLOWED_AUDIO_EXT']
    if category == 'video':
        return ext in app.config['ALLOWED_VIDEO_EXT']
    return False


def save_upload(file, subfolder):
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    dest = os.path.join(UPLOAD_FOLDER, subfolder, unique_name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    file.save(dest)
    if use_cloudinary():
        cloudinary_upload_file(dest, subfolder, unique_name)
    elif get_r2():
        mime = mimetypes.guess_type(unique_name)[0] or 'application/octet-stream'
        with open(dest, 'rb') as f:
            get_r2().upload_fileobj(f, app.config['R2_BUCKET_NAME'],
                                    f"{subfolder}/{unique_name}",
                                    ExtraArgs={'ContentType': mime})
    return unique_name


def save_upload_path(local_path, subfolder, unique_name):
    """Upload un fichier déjà sauvegardé localement vers le cloud."""
    if use_cloudinary():
        cloudinary_upload_file(local_path, subfolder, unique_name)
    elif get_r2():
        mime = mimetypes.guess_type(unique_name)[0] or 'application/octet-stream'
        with open(local_path, 'rb') as f:
            get_r2().upload_fileobj(f, app.config['R2_BUCKET_NAME'],
                                    f"{subfolder}/{unique_name}",
                                    ExtraArgs={'ContentType': mime})


def make_media_token(filename):
    if not filename:
        return 'notoken'
    ts = str(int(time.time()) // 3600)
    key = app.config['SECRET_KEY'].encode()
    sig = hmac.new(key, f"{filename}{ts}".encode(), hashlib.sha256).hexdigest()[:16]
    return sig


def verify_media_token(filename, token):
    for delta in (0, -1):
        ts = str(int(time.time()) // 3600 + delta)
        key = app.config['SECRET_KEY'].encode()
        sig = hmac.new(key, f"{filename}{ts}".encode(), hashlib.sha256).hexdigest()[:16]
        if hmac.compare_digest(sig, token):
            return True
    return False


def notify(user_id, type_, actor_id=None, artwork_id=None):
    if user_id == actor_id:
        return
    n = Notification(user_id=user_id, type=type_, actor_id=actor_id, artwork_id=artwork_id)
    db.session.add(n)


# ─── Auth ─────────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('feed'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Ce nom d\'utilisateur est déjà pris.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé.', 'error')
        elif len(password) < 6:
            flash('Le mot de passe doit faire au moins 6 caractères.', 'error')
        else:
            user = User(username=username, email=email, display_name=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Bienvenue ! Ton compte est créé.', 'success')
            return redirect(url_for('edit_profile'))
    return render_template('auth/register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('explore'))
    if request.method == 'POST':
        identifier = request.form['identifier'].strip()
        password = request.form['password']
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember') == 'on')
            return redirect(request.args.get('next') or url_for('explore'))
        flash('Identifiant ou mot de passe incorrect.', 'error')
    return render_template('auth/login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('feed'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'profile':
            current_user.display_name = request.form.get('display_name', '').strip()
            current_user.bio = request.form.get('bio', '').strip()
            current_user.location = request.form.get('location', '').strip()
            current_user.website = request.form.get('website', '').strip()
            current_user.instagram_url = request.form.get('instagram_url', '').strip()
            current_user.twitter_url = request.form.get('twitter_url', '').strip()
            db.session.commit()
            flash('Profil mis à jour.', 'success')
        elif action == 'password':
            old = request.form.get('old_password')
            new = request.form.get('new_password')
            if not current_user.check_password(old):
                flash('Mot de passe actuel incorrect.', 'error')
            elif len(new) < 6:
                flash('Le nouveau mot de passe doit faire au moins 6 caractères.', 'error')
            else:
                current_user.set_password(new)
                db.session.commit()
                flash('Mot de passe mis à jour.', 'success')
    return render_template('auth/settings.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    reset_link = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            PasswordReset.query.filter_by(user_id=user.id).delete()
            token = secrets.token_urlsafe(32)
            db.session.add(PasswordReset(user_id=user.id, token=token))
            db.session.commit()
            reset_link = url_for('reset_password', token=token, _external=True)
        else:
            flash('Si cet email existe, un lien de réinitialisation sera affiché.', 'info')
    return render_template('auth/forgot_password.html', reset_link=reset_link)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    from datetime import datetime as dt
    reset = PasswordReset.query.filter_by(token=token).first_or_404()
    if (dt.utcnow() - reset.created_at).total_seconds() > 3600:
        db.session.delete(reset)
        db.session.commit()
        flash('Ce lien a expiré. Fais une nouvelle demande.', 'error')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        new_password = request.form.get('password', '')
        if len(new_password) < 6:
            flash('Le mot de passe doit faire au moins 6 caractères.', 'error')
        else:
            reset.user.set_password(new_password)
            db.session.delete(reset)
            db.session.commit()
            flash('Mot de passe réinitialisé ! Tu peux te connecter.', 'success')
            return redirect(url_for('login'))
    return render_template('auth/reset_password.html', token=token)


# ─── Gallery / Feed ───────────────────────────────────────────────────────────

@app.route('/')
def feed():
    media_type = request.args.get('type', 'all')

    if current_user.is_authenticated:
        # Accueil = oeuvres personnelles de l'artiste connecté
        query = Artwork.query.filter_by(artist_id=current_user.id)
        if media_type != 'all':
            query = query.filter_by(media_type=media_type)
        artworks = query.order_by(Artwork.created_at.desc()).all()
        total_likes = sum(a.like_count or 0 for a in artworks)
        total_views = sum(a.view_count or 0 for a in artworks)
        return render_template('gallery/feed.html',
                               artworks=artworks,
                               media_types=MEDIA_TYPES,
                               active_type=media_type,
                               total_likes=total_likes,
                               total_views=total_views,
                               make_token=make_media_token)
    else:
        # Visiteur non connecté : page d'accueil publique
        recent_artworks = Artwork.query.filter_by(is_published=True)\
            .order_by(Artwork.created_at.desc()).limit(8).all()
        return render_template('home.html',
                               recent_artworks=recent_artworks,
                               make_token=make_media_token)


@app.route('/explore')
def explore():
    media_type = request.args.get('type', 'all')
    q = request.args.get('q', '').strip()
    search_by = request.args.get('search_by', 'all')
    query = Artwork.query.filter_by(is_published=True)
    artists = []

    if q:
        like_q = f'%{q}%'
        if search_by == 'artist':
            query = query.filter(False)
            artists = User.query.filter(
                (User.username.ilike(like_q)) | (User.display_name.ilike(like_q))
            ).limit(24).all()
        elif search_by == 'artwork':
            query = query.filter(Artwork.title.ilike(like_q))
        elif search_by == 'tag':
            query = query.filter(Artwork.tags.ilike(like_q))
        else:
            query = query.filter(
                (Artwork.title.ilike(like_q)) | (Artwork.tags.ilike(like_q)) | (Artwork.description.ilike(like_q))
            )
            artists = User.query.filter(
                (User.username.ilike(like_q)) | (User.display_name.ilike(like_q))
            ).limit(12).all()
    elif media_type != 'all':
        query = query.filter_by(media_type=media_type)

    artworks = query.order_by(Artwork.like_count.desc()).limit(48).all()
    return render_template('gallery/explore.html',
                           artworks=artworks,
                           artists=artists,
                           media_types=MEDIA_TYPES,
                           active_type=media_type,
                           search_query=q,
                           search_by=search_by,
                           make_token=make_media_token)


@app.route('/artwork/<int:artwork_id>')
def artwork_detail(artwork_id):
    artwork = Artwork.query.get_or_404(artwork_id)
    artwork.view_count = (artwork.view_count or 0) + 1
    db.session.commit()

    comments = Comment.query.filter_by(artwork_id=artwork_id, parent_id=None)\
                            .order_by(Comment.created_at.asc()).all()
    user_liked = False
    if current_user.is_authenticated:
        user_liked = Like.query.filter_by(
            user_id=current_user.id, artwork_id=artwork_id).first() is not None

    steps = CreationStep.query.filter_by(artwork_id=artwork_id).order_by(CreationStep.order).all()
    token = make_media_token(artwork.get_display_path())
    return render_template('gallery/artwork.html',
                           artwork=artwork,
                           comments=comments,
                           user_liked=user_liked,
                           media_token=token,
                           make_token=make_media_token,
                           steps=steps)


# ─── Profile ──────────────────────────────────────────────────────────────────

@app.route('/artist/<username>')
def portfolio(username):
    artist = User.query.filter_by(username=username).first_or_404()
    media_type = request.args.get('type', 'all')
    query = Artwork.query.filter_by(artist_id=artist.id, is_published=True)
    if media_type != 'all':
        query = query.filter_by(media_type=media_type)
    artworks = query.order_by(Artwork.created_at.desc()).all()

    is_following = False
    if current_user.is_authenticated:
        is_following = current_user.is_following(artist)

    return render_template('profile/portfolio.html',
                           artist=artist,
                           artworks=artworks,
                           media_types=MEDIA_TYPES,
                           active_type=media_type,
                           is_following=is_following,
                           make_token=make_media_token)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.display_name = request.form.get('display_name', '').strip()
        current_user.bio = request.form.get('bio', '').strip()
        current_user.location = request.form.get('location', '').strip()
        current_user.website = request.form.get('website', '').strip()
        current_user.instagram_url = request.form.get('instagram_url', '').strip()
        current_user.twitter_url = request.form.get('twitter_url', '').strip()

        avatar = request.files.get('avatar')
        if avatar and avatar.filename and allowed_file(avatar.filename, 'image'):
            fname = save_upload(avatar, 'originals')
            current_user.avatar_path = fname

        banner = request.files.get('banner')
        if banner and banner.filename and allowed_file(banner.filename, 'image'):
            fname = save_upload(banner, 'originals')
            current_user.banner_path = fname

        db.session.commit()
        flash('Profil mis à jour !', 'success')
        return redirect(url_for('portfolio', username=current_user.username))
    return render_template('profile/edit_profile.html')


@app.route('/cv/edit', methods=['GET', 'POST'])
@login_required
def cv_edit():
    if request.method == 'POST':
        current_user.cv_formation = request.form.get('cv_formation', '').strip()
        current_user.cv_experiences = request.form.get('cv_experiences', '').strip()
        current_user.cv_awards = request.form.get('cv_awards', '').strip()
        current_user.cv_skills = request.form.get('cv_skills', '').strip()
        db.session.commit()
        flash('CV mis à jour !', 'success')
        return redirect(url_for('portfolio', username=current_user.username) + '#cv')
    return render_template('profile/cv_edit.html')


@app.route('/profile/dashboard')
@login_required
def dashboard():
    artworks = Artwork.query.filter_by(artist_id=current_user.id).order_by(Artwork.created_at.desc()).all()
    total_likes = sum(a.like_count or 0 for a in artworks)
    total_views = sum(a.view_count or 0 for a in artworks)
    artworks_for_sale = sum(1 for a in artworks if a.is_for_sale and not a.is_sold and a.is_published)
    artworks_sold = sum(1 for a in artworks if a.is_sold)
    sales = Order.query.join(Artwork).filter(
        Artwork.artist_id == current_user.id, Order.status == 'paid').all()
    total_earned = sum(o.amount for o in sales)
    return render_template('profile/dashboard.html',
                           artworks=artworks,
                           total_likes=total_likes,
                           total_views=total_views,
                           artworks_for_sale=artworks_for_sale,
                           artworks_sold=artworks_sold,
                           sales=sales,
                           total_earned=total_earned,
                           make_token=make_media_token)


# ─── Studio ───────────────────────────────────────────────────────────────────

@app.route('/studio/upload', methods=['GET', 'POST'])
@login_required
def upload_artwork():
    artwork = None
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        media_type = request.form.get('media_type', 'photography')
        tags = request.form.get('tags', '').strip()
        medium = request.form.get('medium', '').strip()
        year = request.form.get('year_created', type=int)
        is_for_sale = request.form.get('is_for_sale') == 'on'
        price = request.form.get('price', type=float)
        print_available = request.form.get('print_available') == 'on'
        print_price = request.form.get('print_price', type=float)

        if not title:
            flash('Le titre est obligatoire.', 'error')
            return render_template('studio/upload.html', media_types=MEDIA_TYPES)

        artwork = Artwork(
            title=title, description=description, media_type=media_type,
            tags=tags, medium=medium, year_created=year,
            is_for_sale=is_for_sale, price=price,
            print_available=print_available, print_price=print_price,
            artist_id=current_user.id
        )

        file = request.files.get('file')
        if file and file.filename:
            is_img = allowed_file(file.filename, 'image')
            is_aud = allowed_file(file.filename, 'audio')
            is_vid = allowed_file(file.filename, 'video')

            if is_img:
                orig_name = save_upload(file, 'originals')
                orig_path = os.path.join(UPLOAD_FOLDER, 'originals', orig_name)
                wm_name = f"wm_{orig_name}"
                wm_path = os.path.join(UPLOAD_FOLDER, 'watermarked', wm_name)
                th_name = f"th_{orig_name}"
                th_path = os.path.join(UPLOAD_FOLDER, 'thumbnails', th_name)
                # Watermark + thumbnail générés localement puis uploadés sur R2
                os.makedirs(os.path.dirname(wm_path), exist_ok=True)
                os.makedirs(os.path.dirname(th_path), exist_ok=True)
                apply_watermark(orig_path, wm_path, current_user.get_name())
                generate_thumbnail(orig_path, th_path)
                save_upload_path(wm_path, 'watermarked', wm_name)
                save_upload_path(th_path, 'thumbnails', th_name)
                artwork.file_path = orig_name
                artwork.watermarked_path = wm_name
                artwork.thumbnail_path = th_name
            elif is_aud:
                artwork.file_path = save_upload(file, 'audio')
            elif is_vid:
                artwork.file_path = save_upload(file, 'video')
            else:
                flash('Format de fichier non supporté.', 'error')
                return render_template('studio/upload.html', media_types=MEDIA_TYPES)

        db.session.add(artwork)
        db.session.commit()
        flash('Œuvre publiée !', 'success')
        return redirect(url_for('feed'))

    return render_template('studio/upload.html', media_types=MEDIA_TYPES, artwork=artwork)


@app.route('/studio/edit/<int:artwork_id>', methods=['GET', 'POST'])
@login_required
def edit_artwork(artwork_id):
    artwork = Artwork.query.get_or_404(artwork_id)
    if artwork.artist_id != current_user.id:
        abort(403)
    if request.method == 'POST':
        artwork.title = request.form.get('title', '').strip()
        artwork.description = request.form.get('description', '').strip()
        artwork.media_type = request.form.get('media_type', artwork.media_type)
        artwork.tags = request.form.get('tags', '').strip()
        artwork.medium = request.form.get('medium', '').strip()
        artwork.year_created = request.form.get('year_created', type=int)
        artwork.is_for_sale = request.form.get('is_for_sale') == 'on'
        artwork.price = request.form.get('price', type=float)
        artwork.print_available = request.form.get('print_available') == 'on'
        artwork.print_price = request.form.get('print_price', type=float)
        artwork.is_published = request.form.get('is_published') == 'on'
        db.session.commit()
        flash('Œuvre mise à jour.', 'success')
        return redirect(url_for('artwork_detail', artwork_id=artwork.id))
    steps = CreationStep.query.filter_by(artwork_id=artwork_id).order_by(CreationStep.order).all()
    return render_template('studio/upload.html', media_types=MEDIA_TYPES, artwork=artwork,
                           steps=steps, make_token=make_media_token)


@app.route('/studio/delete/<int:artwork_id>', methods=['POST'])
@login_required
def delete_artwork(artwork_id):
    artwork = Artwork.query.get_or_404(artwork_id)
    if artwork.artist_id != current_user.id:
        abort(403)
    db.session.delete(artwork)
    db.session.commit()
    flash('Œuvre supprimée.', 'success')
    return redirect(url_for('portfolio', username=current_user.username))


@app.route('/studio/artwork/<int:artwork_id>/steps/add', methods=['POST'])
@login_required
def add_step(artwork_id):
    artwork = Artwork.query.get_or_404(artwork_id)
    if artwork.artist_id != current_user.id:
        abort(403)
    title = request.form.get('step_title', '').strip()
    description = request.form.get('step_description', '').strip()
    image_path = None
    media_file = request.files.get('step_image')
    if media_file and media_file.filename:
        if allowed_file(media_file.filename, 'image'):
            image_path = save_upload(media_file, 'originals')
        elif allowed_file(media_file.filename, 'video'):
            image_path = save_upload(media_file, 'video')
    if not title and not description and not image_path:
        flash("Ajoute au moins un titre, une description ou une photo/vidéo.", 'error')
        return redirect(url_for('edit_artwork', artwork_id=artwork_id) + '?steps=1')
    order = CreationStep.query.filter_by(artwork_id=artwork_id).count()
    step = CreationStep(
        artwork_id=artwork_id,
        order=order,
        title=title or None,
        description=description or None,
        image_path=image_path
    )
    db.session.add(step)
    db.session.commit()
    flash('Étape ajoutée.', 'success')
    return redirect(url_for('edit_artwork', artwork_id=artwork_id) + '?steps=1')


@app.route('/studio/artwork/<int:artwork_id>/steps/<int:step_id>/delete', methods=['POST'])
@login_required
def delete_step(artwork_id, step_id):
    artwork = Artwork.query.get_or_404(artwork_id)
    if artwork.artist_id != current_user.id:
        abort(403)
    step = CreationStep.query.filter_by(id=step_id, artwork_id=artwork_id).first_or_404()
    db.session.delete(step)
    db.session.commit()
    flash('Étape supprimée.', 'success')
    return redirect(url_for('edit_artwork', artwork_id=artwork_id) + '?steps=1')


@app.route('/studio/ai')
@login_required
def ai_studio():
    return render_template('studio/ai_create.html')


@app.route('/api/ai/generate', methods=['POST'])
@login_required
def ai_generate():
    data = request.get_json()
    prompt = data.get('prompt', '').strip()
    gen_type = data.get('type', 'image')

    if not prompt:
        return jsonify({'error': 'Prompt vide'}), 400

    if not current_user.can_generate_ai():
        return jsonify({'error': f'Tu as atteint ta limite de {current_user.AI_DAILY_LIMIT} générations par jour. Reviens demain !'}), 429

    hf_key = app.config.get('HF_API_KEY', '')
    filename = None

    if gen_type == 'image':
        filename = generate_image_pollinations(prompt)
        if not filename and hf_key:
            filename, hf_error = generate_image_hf(prompt, hf_key)
            if hf_error == 'rate_limit':
                return jsonify({'error': 'Le service IA est temporairement surchargé. Réessaie dans 1 à 2 minutes.'}), 429
    elif gen_type == 'music':
        if hf_key:
            filename, hf_error = generate_music_hf(prompt, hf_key)
            if hf_error == 'rate_limit':
                return jsonify({'error': 'Le service IA est temporairement surchargé. Réessaie dans 1 à 2 minutes.'}), 429
        else:
            return jsonify({'error': 'Configure ta clé Hugging Face dans .env pour générer de la musique.'}), 400

    if not filename:
        return jsonify({'error': 'Génération échouée. Réessaie dans quelques secondes.'}), 500

    current_user.increment_ai_generation()
    db.session.commit()

    subfolder = 'audio' if gen_type == 'music' else 'originals'
    token = make_media_token(filename)
    return jsonify({'filename': filename, 'subfolder': subfolder, 'token': token, 'type': gen_type})


@app.route('/api/ai/save', methods=['POST'])
@login_required
def ai_save():
    data = request.get_json()
    filename = data.get('filename', '')
    subfolder = data.get('subfolder', 'originals')
    prompt = data.get('prompt', '')
    title = data.get('title', 'Création IA').strip() or 'Création IA'
    gen_type = data.get('type', 'image')

    media_type = 'music' if gen_type == 'music' else 'digital_art'
    artwork = Artwork(
        title=title, ai_prompt=prompt, is_ai_generated=True,
        media_type=media_type, artist_id=current_user.id
    )

    if subfolder == 'originals' and filename:
        orig_path = os.path.join(UPLOAD_FOLDER, 'originals', filename)
        wm_name = f"wm_{filename}"
        wm_path = os.path.join(UPLOAD_FOLDER, 'watermarked', wm_name)
        th_name = f"th_{filename}"
        th_path = os.path.join(UPLOAD_FOLDER, 'thumbnails', th_name)
        os.makedirs(os.path.dirname(wm_path), exist_ok=True)
        os.makedirs(os.path.dirname(th_path), exist_ok=True)
        apply_watermark(orig_path, wm_path, current_user.get_name())
        generate_thumbnail(orig_path, th_path)
        save_upload_path(orig_path, 'originals', filename)
        save_upload_path(wm_path, 'watermarked', wm_name)
        save_upload_path(th_path, 'thumbnails', th_name)
        artwork.watermarked_path = wm_name
        artwork.file_path = filename
        artwork.thumbnail_path = th_name
    elif subfolder == 'audio':
        audio_path = os.path.join(UPLOAD_FOLDER, 'audio', filename)
        save_upload_path(audio_path, 'audio', filename)
        artwork.file_path = filename

    db.session.add(artwork)
    db.session.commit()
    return jsonify({'redirect': url_for('artwork_detail', artwork_id=artwork.id)})


# ─── Media serving ────────────────────────────────────────────────────────────

@app.route('/media/<subfolder>/<token>/<filename>')
def serve_media(subfolder, token, filename):
    if not verify_media_token(filename, token):
        abort(403)

    # Cloudinary
    if use_cloudinary():
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        name_no_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
        resource_type = 'video' if ext in (app.config['ALLOWED_AUDIO_EXT'] | app.config['ALLOWED_VIDEO_EXT']) else 'image'
        cloud_url = f"https://res.cloudinary.com/{app.config['CLOUDINARY_CLOUD_NAME']}/{resource_type}/upload/weart/{subfolder}/{name_no_ext}.{ext}"
        return redirect(cloud_url)

    # Cloudflare R2
    r2_public = app.config.get('R2_PUBLIC_URL', '')
    if r2_public:
        return redirect(f"{r2_public.rstrip('/')}/{subfolder}/{filename}")

    folder_map = {
        'watermarked': os.path.join(UPLOAD_FOLDER, 'watermarked'),
        'thumbnails': os.path.join(UPLOAD_FOLDER, 'thumbnails'),
        'originals': os.path.join(UPLOAD_FOLDER, 'originals'),
        'audio': os.path.join(UPLOAD_FOLDER, 'audio'),
        'video': os.path.join(UPLOAD_FOLDER, 'video'),
    }
    folder = folder_map.get(subfolder)
    if not folder:
        abort(404)

    filepath = os.path.join(folder, filename)
    if not os.path.isfile(filepath):
        abort(404)

    mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    file_size = os.path.getsize(filepath)
    range_header = request.headers.get('Range')

    if not range_header:
        def full_stream():
            with open(filepath, 'rb') as f:
                while chunk := f.read(65536):
                    yield chunk
        return Response(stream_with_context(full_stream()), status=200,
                        headers={'Content-Type': mime_type,
                                 'Content-Length': file_size,
                                 'Accept-Ranges': 'bytes'})

    m = re.match(r'bytes=(\d+)-(\d*)', range_header)
    if not m:
        abort(416)
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else file_size - 1
    if start >= file_size or end >= file_size or start > end:
        abort(416)
    length = end - start + 1

    def partial_stream():
        with open(filepath, 'rb') as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return Response(stream_with_context(partial_stream()), status=206,
                    headers={'Content-Type': mime_type,
                             'Content-Range': f'bytes {start}-{end}/{file_size}',
                             'Accept-Ranges': 'bytes',
                             'Content-Length': length})


@app.route('/media/avatar/<filename>')
def serve_avatar(filename):
    if use_cloudinary():
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        name_no_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
        cloud_url = f"https://res.cloudinary.com/{app.config['CLOUDINARY_CLOUD_NAME']}/image/upload/weart/originals/{name_no_ext}.{ext}"
        return redirect(cloud_url)
    return send_from_directory(os.path.join(UPLOAD_FOLDER, 'originals'), filename)


# ─── Marketplace ──────────────────────────────────────────────────────────────

@app.route('/marketplace')
def marketplace():
    media_type = request.args.get('type', 'all')
    query = Artwork.query.filter_by(is_for_sale=True, is_sold=False, is_published=True)
    if media_type != 'all':
        query = query.filter_by(media_type=media_type)
    artworks = query.order_by(Artwork.created_at.desc()).all()
    return render_template('marketplace/shop.html',
                           artworks=artworks,
                           media_types=MEDIA_TYPES,
                           active_type=media_type,
                           make_token=make_media_token)


@app.route('/artwork/<int:artwork_id>/buy', methods=['GET', 'POST'])
@login_required
def buy_artwork(artwork_id):
    artwork = Artwork.query.get_or_404(artwork_id)
    if not artwork.is_for_sale or artwork.is_sold:
        flash('Cette œuvre n\'est plus disponible.', 'error')
        return redirect(url_for('artwork_detail', artwork_id=artwork_id))

    if request.method == 'POST':
        order_type = request.form.get('order_type', 'original')
        amount = artwork.price if order_type == 'original' else (artwork.print_price or artwork.price)
        shipping = request.form.get('shipping_address', '').strip()

        stripe_key = app.config.get('STRIPE_SECRET_KEY', '')
        if stripe_key and not stripe_key.startswith('sk_test_CHANGE'):
            try:
                intent = stripe.PaymentIntent.create(
                    amount=int((amount or 0) * 100),
                    currency='eur',
                    metadata={'artwork_id': artwork_id, 'buyer_id': current_user.id,
                              'order_type': order_type}
                )
                order = Order(
                    buyer_id=current_user.id, artwork_id=artwork_id,
                    amount=amount, order_type=order_type,
                    stripe_payment_intent=intent['id'],
                    shipping_address=shipping
                )
                db.session.add(order)
                db.session.commit()
                return render_template('marketplace/checkout.html',
                                       artwork=artwork, order=order,
                                       client_secret=intent['client_secret'],
                                       stripe_public_key=app.config['STRIPE_PUBLIC_KEY'])
            except stripe.error.StripeError as e:
                flash(f'Erreur paiement: {e.user_message}', 'error')
        else:
            order = Order(
                buyer_id=current_user.id, artwork_id=artwork_id,
                amount=amount or 0, order_type=order_type,
                shipping_address=shipping, status='pending'
            )
            db.session.add(order)
            notify(artwork.artist_id, 'sale', actor_id=current_user.id, artwork_id=artwork_id)
            db.session.commit()
            flash('Demande envoyée ! L\'artiste va te contacter.', 'success')
            return redirect(url_for('artwork_detail', artwork_id=artwork_id))

    return render_template('marketplace/buy.html', artwork=artwork, make_token=make_media_token)


@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = app.config.get('STRIPE_WEBHOOK_SECRET', '')
    if not webhook_secret:
        return '', 200
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        return jsonify({'error': 'Invalid signature'}), 400

    if event['type'] == 'payment_intent.succeeded':
        pi = event['data']['object']
        order = Order.query.filter_by(stripe_payment_intent=pi['id']).first()
        if order:
            order.status = 'paid'
            artwork = Artwork.query.get(order.artwork_id)
            if order.order_type == 'original':
                artwork.is_sold = True
            notify(artwork.artist_id, 'sale', actor_id=order.buyer_id, artwork_id=artwork.id)
            db.session.commit()
    return '', 200


@app.route('/orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(buyer_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('marketplace/orders.html', orders=orders, mode='buyer')


@app.route('/sales')
@login_required
def my_sales():
    orders = Order.query.join(Artwork).filter(
        Artwork.artist_id == current_user.id
    ).order_by(Order.created_at.desc()).all()
    return render_template('marketplace/orders.html', orders=orders, mode='seller')


# ─── Social ───────────────────────────────────────────────────────────────────

@app.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def toggle_follow(user_id):
    target = User.query.get_or_404(user_id)
    existing = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
    if existing:
        db.session.delete(existing)
        is_following = False
    else:
        db.session.add(Follow(follower_id=current_user.id, followed_id=user_id))
        notify(user_id, 'follow', actor_id=current_user.id)
        is_following = True
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'is_following': is_following, 'count': target.follower_count()})
    return redirect(request.referrer or url_for('portfolio', username=target.username))


@app.route('/messages')
@login_required
def messages():
    convs = db.session.query(Message).filter(
        (Message.sender_id == current_user.id) | (Message.recipient_id == current_user.id)
    ).order_by(Message.created_at.desc()).all()

    seen = set()
    conversations = []
    for m in convs:
        other_id = m.recipient_id if m.sender_id == current_user.id else m.sender_id
        if other_id not in seen:
            seen.add(other_id)
            other = User.query.get(other_id)
            unread = Message.query.filter_by(
                sender_id=other_id, recipient_id=current_user.id, is_read=False).count()
            conversations.append({'user': other, 'last_message': m, 'unread': unread})

    return render_template('social/messages.html', conversations=conversations)


@app.route('/messages/<username>', methods=['GET', 'POST'])
@login_required
def conversation(username):
    other = User.query.filter_by(username=username).first_or_404()
    if request.method == 'POST':
        body = request.form.get('body', '').strip()
        if body:
            msg = Message(sender_id=current_user.id, recipient_id=other.id, body=body)
            db.session.add(msg)
            notify(other.id, 'message', actor_id=current_user.id)
            db.session.commit()
        return redirect(url_for('conversation', username=username))

    msgs = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == other.id)) |
        ((Message.sender_id == other.id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()

    Message.query.filter_by(sender_id=other.id, recipient_id=current_user.id, is_read=False)\
                 .update({'is_read': True})
    db.session.commit()
    return render_template('social/conversation.html', other=other, messages=msgs)


@app.route('/notifications')
@login_required
def notifications_page():
    notifs = Notification.query.filter_by(user_id=current_user.id)\
                               .order_by(Notification.created_at.desc()).limit(50).all()
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('social/notifications.html', notifications=notifs)


# ─── API JSON ─────────────────────────────────────────────────────────────────

@app.route('/api/like/<int:artwork_id>', methods=['POST'])
@login_required
def api_like(artwork_id):
    artwork = Artwork.query.get_or_404(artwork_id)
    existing = Like.query.filter_by(user_id=current_user.id, artwork_id=artwork_id).first()
    if existing:
        db.session.delete(existing)
        artwork.like_count = max(0, (artwork.like_count or 0) - 1)
        liked = False
    else:
        db.session.add(Like(user_id=current_user.id, artwork_id=artwork_id))
        artwork.like_count = (artwork.like_count or 0) + 1
        liked = True
        notify(artwork.artist_id, 'like', actor_id=current_user.id, artwork_id=artwork_id)
    db.session.commit()
    return jsonify({'liked': liked, 'count': artwork.like_count})


@app.route('/api/comment/<int:artwork_id>', methods=['POST'])
@login_required
def api_comment(artwork_id):
    data = request.get_json()
    body = data.get('body', '').strip()
    parent_id = data.get('parent_id')
    if not body:
        return jsonify({'error': 'Commentaire vide'}), 400
    comment = Comment(body=body, user_id=current_user.id, artwork_id=artwork_id, parent_id=parent_id)
    db.session.add(comment)
    artwork = Artwork.query.get(artwork_id)
    notify(artwork.artist_id, 'comment', actor_id=current_user.id, artwork_id=artwork_id)
    db.session.commit()
    return jsonify({
        'id': comment.id,
        'body': comment.body,
        'author': current_user.get_name(),
        'username': current_user.username,
        'created_at': comment.created_at.strftime('%d/%m/%Y %H:%M'),
        'avatar': current_user.avatar_path
    })


@app.route('/api/feed')
def api_feed():
    page = request.args.get('page', 1, type=int)
    media_type = request.args.get('type', 'all')
    query = Artwork.query.filter_by(is_published=True)
    if media_type != 'all':
        query = query.filter_by(media_type=media_type)
    pagination = query.order_by(Artwork.created_at.desc()).paginate(page=page, per_page=12, error_out=False)

    artworks_data = []
    for a in pagination.items:
        token = make_media_token(a.get_display_path())
        artworks_data.append({
            'id': a.id,
            'title': a.title,
            'artist': a.artist.get_name(),
            'artist_username': a.artist.username,
            'artist_avatar': a.artist.avatar_path,
            'media_type': a.media_type,
            'media_label': a.get_media_label(),
            'is_image': a.is_image(),
            'is_audio': a.is_audio(),
            'is_video': a.is_video(),
            'display_path': a.get_display_path(),
            'thumbnail_path': a.thumbnail_path,
            'like_count': a.like_count or 0,
            'url': url_for('artwork_detail', artwork_id=a.id),
            'token': token,
        })

    return jsonify({'artworks': artworks_data, 'has_more': pagination.has_next, 'next_page': page + 1})


@app.route('/api/notifications/count')
@login_required
def api_notif_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    msgs = Message.query.filter_by(recipient_id=current_user.id, is_read=False).count()
    return jsonify({'notifications': count, 'messages': msgs})


@app.route('/api/search/suggestions')
def api_search_suggestions():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'artists': [], 'artworks': []})
    like_q = f'%{q}%'
    artists = User.query.filter(
        (User.username.ilike(like_q)) | (User.display_name.ilike(like_q))
    ).limit(5).all()
    artworks = Artwork.query.filter_by(is_published=True).filter(
        Artwork.title.ilike(like_q)
    ).limit(5).all()
    return jsonify({
        'artists': [{'name': u.get_name(), 'username': u.username} for u in artists],
        'artworks': [{'title': a.title, 'id': a.id} for a in artworks],
    })


# ─── Init ─────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    # Migration : ajoute les nouvelles colonnes si elles n'existent pas encore
    from sqlalchemy import text, inspect as sa_inspect
    try:
        inspector = sa_inspect(db.engine)
        existing = {col['name'] for col in inspector.get_columns('user')}
        with db.engine.begin() as conn:
            if 'ai_generations_today' not in existing:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN ai_generations_today INTEGER DEFAULT 0'))
            if 'ai_last_reset' not in existing:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN ai_last_reset DATE'))
    except Exception:
        pass

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, threaded=True)
