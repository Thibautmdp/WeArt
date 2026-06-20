from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

MEDIA_TYPES = [
    ('painting', 'Peinture'),
    ('photography', 'Photographie'),
    ('sculpture', 'Sculpture'),
    ('digital_art', 'Art Numérique'),
    ('illustration', 'Illustration'),
    ('music', 'Musique'),
    ('video', 'Vidéo'),
    ('3d', '3D'),
    ('animation', 'Animation'),
    ('mixed', 'Art Mixte'),
]


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    avatar_path = db.Column(db.String(300), default='default_avatar.jpg')
    banner_path = db.Column(db.String(300))
    location = db.Column(db.String(100))
    website = db.Column(db.String(200))
    instagram_url = db.Column(db.String(200))
    twitter_url = db.Column(db.String(200))
    is_artist = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cv_formation = db.Column(db.Text)
    cv_experiences = db.Column(db.Text)
    cv_awards = db.Column(db.Text)
    cv_skills = db.Column(db.Text)
    ai_generations_today = db.Column(db.Integer, default=0)
    ai_last_reset = db.Column(db.Date, nullable=True)

    artworks = db.relationship('Artwork', backref='artist', lazy='dynamic', cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    received_messages = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient', lazy='dynamic')
    notifications = db.relationship('Notification', foreign_keys='Notification.user_id', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_following(self, user):
        return Follow.query.filter_by(follower_id=self.id, followed_id=user.id).first() is not None

    def follower_count(self):
        return Follow.query.filter_by(followed_id=self.id).count()

    def following_count(self):
        return Follow.query.filter_by(follower_id=self.id).count()

    def get_name(self):
        return self.display_name or self.username

    AI_DAILY_LIMIT = 5

    def can_generate_ai(self):
        today = date.today()
        if self.ai_last_reset != today:
            self.ai_generations_today = 0
            self.ai_last_reset = today
        return self.ai_generations_today < self.AI_DAILY_LIMIT

    def increment_ai_generation(self):
        today = date.today()
        if self.ai_last_reset != today:
            self.ai_generations_today = 0
            self.ai_last_reset = today
        self.ai_generations_today += 1


class Artwork(db.Model):
    __tablename__ = 'artwork'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    media_type = db.Column(db.String(30), nullable=False, default='photography')
    file_path = db.Column(db.String(300))
    watermarked_path = db.Column(db.String(300))
    thumbnail_path = db.Column(db.String(300))
    artist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    tags = db.Column(db.String(500))
    medium = db.Column(db.String(100))
    year_created = db.Column(db.Integer)
    is_ai_generated = db.Column(db.Boolean, default=False)
    ai_prompt = db.Column(db.Text)
    is_for_sale = db.Column(db.Boolean, default=False)
    price = db.Column(db.Float)
    is_sold = db.Column(db.Boolean, default=False)
    print_available = db.Column(db.Boolean, default=False)
    print_price = db.Column(db.Float)
    view_count = db.Column(db.Integer, default=0)
    like_count = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    likes = db.relationship('Like', backref='artwork', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='artwork', lazy='dynamic', cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='artwork', lazy='dynamic')
    creation_steps = db.relationship('CreationStep', lazy='dynamic', cascade='all, delete-orphan')

    def get_media_label(self):
        return dict(MEDIA_TYPES).get(self.media_type, self.media_type)

    def is_image(self):
        return self.media_type in ('painting', 'photography', 'digital_art', 'illustration', 'mixed', '3d', 'animation')

    def is_audio(self):
        return self.media_type == 'music'

    def is_video(self):
        return self.media_type == 'video'

    def get_display_path(self):
        return self.watermarked_path or self.file_path or ''

    def get_tags_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]


class Follow(db.Model):
    __tablename__ = 'follow'
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('follower_id', 'followed_id'),)


class Like(db.Model):
    __tablename__ = 'like'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    artwork_id = db.Column(db.Integer, db.ForeignKey('artwork.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'artwork_id'),)


class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    artwork_id = db.Column(db.Integer, db.ForeignKey('artwork.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User', backref='comments')
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')


class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    __tablename__ = 'notification'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    type = db.Column(db.String(30))  # like, comment, follow, message, sale, reply
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    artwork_id = db.Column(db.Integer, db.ForeignKey('artwork.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    actor = db.relationship('User', foreign_keys=[actor_id])
    artwork = db.relationship('Artwork', foreign_keys=[artwork_id])


class PasswordReset(db.Model):
    __tablename__ = 'password_reset'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='reset_tokens')


class CreationStep(db.Model):
    __tablename__ = 'creation_step'
    id = db.Column(db.Integer, primary_key=True)
    artwork_id = db.Column(db.Integer, db.ForeignKey('artwork.id'), nullable=False, index=True)
    order = db.Column(db.Integer, default=0)
    title = db.Column(db.String(150))
    description = db.Column(db.Text)
    image_path = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    artwork_id = db.Column(db.Integer, db.ForeignKey('artwork.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    order_type = db.Column(db.String(20), default='original')  # original, print
    status = db.Column(db.String(20), default='pending')  # pending, paid, shipped, completed, cancelled
    stripe_payment_intent = db.Column(db.String(200))
    shipping_address = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    buyer = db.relationship('User', foreign_keys=[buyer_id], backref='orders')
