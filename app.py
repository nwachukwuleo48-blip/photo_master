from flask import Flask, render_template, redirect, url_for, request, flash, abort, send_from_directory, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask import session
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from models import db, User, ClientGallery, Photo, Booking, PortfolioPhoto, ContactMessage
import os
from PIL import Image
import uuid
import re
import secrets
import smtplib
import urllib.parse
from email_utils import send_contact_email, send_gallery_access_email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from datetime import date
import zipfile
from flask import send_file
from io import BytesIO
from pathlib import Path
from datetime import datetime
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
import cloudinary
import cloudinary.uploader
load_dotenv()  # Load variables from .env


cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("CLOUD_API_KEY"),
    api_secret=os.getenv("CLOUD_API_SECRET")
)
EMAIL_USER = (os.getenv("EMAIL_USER") or "").strip()
EMAIL_PASS = (os.getenv("EMAIL_PASS") or "").replace(" ", "").strip()
EMAIL_RECEIVER = (os.getenv("EMAIL_RECEIVER") or "").strip()
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or "nwachukwuleo48@gmail.com").strip().lower()
ADMIN_PASSWORD = (os.getenv("ADMIN_PASSWORD") or "").strip()
PORTFOLIO_CATEGORIES = ("wedding", "birthday", "ceremony", "portrait", "fashion")
PORTFOLIO_SORT_OPTIONS = ("newest", "oldest")


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}

def _on_render() -> bool:
    return bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_ID")) or bool(os.getenv("RENDER_EXTERNAL_URL"))

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[]
)

from flask_bcrypt import Bcrypt
bcrypt = Bcrypt(app)

@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response
# ---------------- CONFIG ----------------
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "devkey")
app.config["PUBLIC_SIGNUP_ENABLED"] = _env_bool("PUBLIC_SIGNUP_ENABLED", default=False)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

# Optional persistent data directory for platforms with mounted disks/volumes.
# Examples: "/var/data" (Linux) or "C:\\data" (Windows).
DATA_DIR = (os.getenv("DATA_DIR") or "").strip()
data_dir = DATA_DIR if DATA_DIR else app.instance_path
os.makedirs(data_dir, exist_ok=True)

def _sqlite_uri(db_path: str) -> str:
    p = Path(db_path)
    posix = p.as_posix()
    if p.is_absolute():
        # SQLAlchemy wants different absolute path forms on Windows vs POSIX.
        if os.name == "nt":
            return f"sqlite:///{posix}"
        return f"sqlite:////{posix.lstrip('/')}"
    return f"sqlite:///{posix}"

_db_url = os.getenv("SQLALCHEMY_DATABASE_URI") or os.getenv("DATABASE_URL")
# Some providers still use "postgres://" which SQLAlchemy doesn't accept.
if _db_url and _db_url.startswith("postgres://"):
    _db_url = "postgresql://" + _db_url[len("postgres://") :]
if _db_url and _on_render() and _db_url.startswith("postgresql://") and "sslmode=" not in _db_url:
    _db_url = f"{_db_url}{'&' if '?' in _db_url else '?'}sslmode=require"

app.config["SQLALCHEMY_DATABASE_URI"] = _db_url or _sqlite_uri(
    os.path.join(data_dir, "site.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Public portfolio uploads
app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", os.path.join(data_dir, "public_uploads"))

# Private client gallery uploads
app.config["CLIENT_UPLOAD_FOLDER"] = os.getenv("CLIENT_UPLOAD_FOLDER", os.path.join(data_dir, "client_uploads"))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

if _on_render():
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if str(db_uri).startswith("sqlite:") and not DATA_DIR:
        print(
            "[WARN] Render detected and DATABASE_URL is not set. Using SQLite on the container filesystem means "
            "your portfolio data will reset on every deploy. Fix: use Render Postgres (set DATABASE_URL) or "
            "mount a persistent disk and set DATA_DIR=/var/data."
        )

    if not (os.getenv("CLOUD_NAME") and os.getenv("CLOUD_API_KEY") and os.getenv("CLOUD_API_SECRET")):
        print(
            "[WARN] Cloudinary env vars are missing. Portfolio/client uploads will fail or fall back to local storage, "
            "which will reset on deploy unless you use a persistent disk."
        )

# ---------------- EXTENSIONS ----------------
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

def _ensure_upload_dirs():
    upload_dir = app.config.get("UPLOAD_FOLDER") or ""
    if upload_dir:
        upload_dir = upload_dir if os.path.isabs(upload_dir) else os.path.join(app.root_path, upload_dir)
        os.makedirs(upload_dir, exist_ok=True)

    client_dir = app.config.get("CLIENT_UPLOAD_FOLDER") or ""
    if client_dir:
        client_dir = client_dir if os.path.isabs(client_dir) else os.path.join(app.root_path, client_dir)
        os.makedirs(client_dir, exist_ok=True)

def _ensure_client_gallery_schema():
    # Lightweight migration so existing SQLite/Postgres databases gain this
    # column without requiring Alembic in production.
    try:
        inspector = inspect(db.engine)
        columns = {col["name"] for col in inspector.get_columns("client_gallery")}
        if "client_email" not in columns:
            db.session.execute(text("ALTER TABLE client_gallery ADD COLUMN client_email VARCHAR(200)"))
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[WARN] Could not ensure client_gallery schema: {e}")

def _bootstrap_admin_user():
    # Optional: set ADMIN_PASSWORD in env to ensure the admin account exists and
    # is always controlled by your deployment configuration (prevents takeover
    # via public signup without email verification).
    if not ADMIN_PASSWORD:
        return

    try:
        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        hashed_password = bcrypt.generate_password_hash(ADMIN_PASSWORD).decode("utf-8")
        if admin is None:
            admin = User(email=ADMIN_EMAIL, password=hashed_password, is_admin=True)
            db.session.add(admin)
        else:
            admin.email = ADMIN_EMAIL
            admin.password = hashed_password
            admin.is_admin = True
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[WARN] Admin bootstrap failed: {e}")

# In production (WSGI servers), __main__ doesn't run. Create tables on startup by default.
if _env_bool("AUTO_CREATE_DB", default=True):
    with app.app_context():
        db.create_all()
        _ensure_client_gallery_schema()
        _ensure_upload_dirs()
        _bootstrap_admin_user()

# ---------------- HELPERS ----------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _generate_access_code() -> str:
    # 6-digit numeric code (easy for clients to type on mobile).
    return f"{secrets.randbelow(1_000_000):06d}"

def generate_slug(title):
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')

def get_dominant_color(image_path):
    image = Image.open(image_path).resize((100,100))
    pixels = list(image.getdata())
    r = sum(p[0] for p in pixels) / len(pixels)
    g = sum(p[1] for p in pixels) / len(pixels)
    b = sum(p[2] for p in pixels) / len(pixels)
    return f"rgb({int(r)}, {int(g)}, {int(b)})"

def _is_admin():
    return current_user.is_authenticated and bool(getattr(current_user, "is_admin", False))

@app.context_processor
def _inject_template_globals():
    return {
        "public_signup_enabled": app.config.get("PUBLIC_SIGNUP_ENABLED", False),
        "is_admin": _is_admin(),
    }

def _abs_path(path):
    return path if os.path.isabs(path) else os.path.join(app.root_path, path)

# ---------------- LOGIN ----------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def send_user_confirmation_email(booking):
    sender_email = EMAIL_USER
    sender_password = EMAIL_PASS
    receiver_email = booking.email  # send to the person who booked

    subject = f"Booking Confirmation – StillPhotos"
    body = f"""
Hi {booking.name},

Thank you for booking a session with StillPhotos!

Here are your booking details:

Event: {booking.event_type}
Date: {booking.event_date}
Message: {booking.message}

We will contact you soon to confirm the details.

– StillPhotos Team
    """

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("Error sending confirmation email to user:", e)

def send_booking_email(booking):
    """
    Sends booking confirmation to the client and notification to the studio.
    `booking` is a Booking object with attributes: name, email, phone, event_type, event_date, time_slot, message
    """

    sender_email = os.environ.get("EMAIL_USER")
    sender_password = os.environ.get("EMAIL_PASS")
    receiver_email = os.environ.get("EMAIL_RECEIVER")  # studio email

    # ---- Email to studio ----
    subject_admin = f"New Booking from {booking.name}"
    html_body_admin = f"""
    <html>
      <body>
        <h2>New Booking Submitted</h2>
        <ul>
          <li><strong>Name:</strong> {booking.name}</li>
          <li><strong>Email:</strong> {booking.email}</li>
          <li><strong>Phone:</strong> {booking.phone}</li>
          <li><strong>Event:</strong> {booking.event_type}</li>
          <li><strong>Date:</strong> {booking.event_date}</li>
          <li><strong>Time Slot:</strong> {booking.time_slot}</li>
          <li><strong>Message:</strong> {booking.message}</li>
        </ul>
      </body>
    </html>
    """

    # ---- Email to client ----
    subject_client = "Booking Confirmation – StillPhotos"
    html_body_client = f"""
    <html>
      <body>
        <h2>Thank you, {booking.name}!</h2>
        <p>Your booking has been received. Here are the details:</p>
        <ul>
          <li><strong>Event:</strong> {booking.event_type}</li>
          <li><strong>Date:</strong> {booking.event_date}</li>
          <li><strong>Time Slot:</strong> {booking.time_slot}</li>
          <li><strong>Message:</strong> {booking.message}</li>
        </ul>
        <p>We will contact you shortly to confirm your session.</p>
        <p>– StillPhotos Studio</p>
      </body>
    </html>
    """

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)

        # ---- Send to studio ----
        msg_admin = MIMEMultipart("alternative")
        msg_admin['From'] = sender_email
        msg_admin['To'] = receiver_email
        msg_admin['Subject'] = subject_admin
        msg_admin.attach(MIMEText(html_body_admin, 'html'))
        server.send_message(msg_admin)

        # ---- Send to client ----
        msg_client = MIMEMultipart("alternative")
        msg_client['From'] = sender_email
        msg_client['To'] = booking.email
        msg_client['Subject'] = subject_client
        msg_client.attach(MIMEText(html_body_client, 'html'))
        server.send_message(msg_client)

        server.quit()
        print("Booking emails sent successfully!")

    except Exception as e:
        print("Error sending booking email:", e)

@app.route("/booking", methods=["GET", "POST"])
def booking():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        event_type = request.form.get("package")
        event_date_str = request.form.get("date")  # comes as string
        time_slot = request.form.get("time_slot")
        message = request.form.get("message")

        # Convert string to date object for SQLite
        from datetime import datetime
        try:
            event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format", "error")
            return redirect(url_for("booking"))

        # Check if this slot is already booked
        existing_booking = Booking.query.filter_by(
            event_date=event_date,
            time_slot=time_slot
        ).first()

        if existing_booking:
            flash("This time slot is already booked. Please choose another.", "error")
            return redirect(url_for("booking"))

        # Create new Booking object
        new_booking = Booking(
            name=name,
            email=email,
            phone=phone,
            event_type=event_type,
            event_date=event_date,
            time_slot=time_slot,
            message=message
        )

        try:
            db.session.add(new_booking)
            db.session.commit()

            # Send emails using the Booking object
            send_booking_email(new_booking)

            flash("Booking submitted successfully! Check your email for confirmation.", "success")

        except Exception as e:
            db.session.rollback()
            flash(f"Error submitting booking: {e}", "error")
            print("Booking Error:", e)

        return redirect(url_for("booking"))

    # GET REQUEST
    bookings = Booking.query.all()
    booked_slots = [{"date": b.event_date, "time": b.time_slot} for b in bookings]

    return render_template(
        "booking.html",
        min_date=date.today().isoformat(),
        booked_slots=booked_slots
    )
# ---------------- PUBLIC ROUTES ----------------
@app.route("/portfolio-file/<path:filename>")
def portfolio_file(filename):
    # Cloudinary URLs are stored directly in the DB; serve them via redirect so
    # older templates that call this route still work.
    if filename.startswith("http://") or filename.startswith("https://"):
        return redirect(filename)

    # Legacy/local files: serve from UPLOAD_FOLDER (use a persistent disk in production).
    if not allowed_file(filename):
        abort(404)

    upload_dir = app.config.get("UPLOAD_FOLDER") or ""
    if not upload_dir:
        abort(404)

    upload_dir = upload_dir if os.path.isabs(upload_dir) else os.path.join(app.root_path, upload_dir)
    filepath = os.path.join(upload_dir, filename)
    if not os.path.exists(filepath):
        abort(404)

    as_attachment = request.args.get("download") == "1"
    return send_from_directory(
        upload_dir,
        filename,
        as_attachment=as_attachment,
        download_name=filename,
    )

@app.route("/")
def home():
    page = request.args.get("page", 1, type=int)
    requested_category = (request.args.get("category") or "").strip().lower()
    requested_sort = (request.args.get("sort") or "").strip().lower()
    selected_category = requested_category if requested_category in PORTFOLIO_CATEGORIES else "all"
    selected_sort = requested_sort if requested_sort in PORTFOLIO_SORT_OPTIONS else "newest"

    query = PortfolioPhoto.query.filter_by(is_public=True)
    if selected_category != "all":
        query = query.filter_by(category=selected_category)

    order_clause = PortfolioPhoto.id.asc() if selected_sort == "oldest" else PortfolioPhoto.id.desc()
    photos = query.order_by(order_clause).paginate(
        page=page,
        per_page=60,
        error_out=False
    )

    return render_template(
        "index.html",
        photos=photos,
        selected_category=selected_category,
        selected_sort=selected_sort,
        category_options=PORTFOLIO_CATEGORIES,
        sort_options=PORTFOLIO_SORT_OPTIONS,
        category_param=None if selected_category == "all" else selected_category,
        sort_param=None if selected_sort == "newest" else selected_sort,
    )
@app.route("/signup", methods=['GET', 'POST'])
def signup():
    if not app.config.get("PUBLIC_SIGNUP_ENABLED", False):
        abort(404)

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()

        if not email or not password or not confirm:
            flash("Please fill out all fields", "warning")
            return redirect(url_for('signup'))

        if password != confirm:
            flash("Passwords do not match","error")
            return redirect(url_for('signup'))

        if User.query.filter_by(email=email).first():
            flash("Email already registered", "info")
            return redirect(url_for('signup'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(email=email, password=hashed_password)

        try:
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            flash("Account created successfully! You are now logged in.", "success")
            return redirect(url_for('home'))
        except Exception:
            db.session.rollback()
            flash("Error creating account", "error")
            return redirect(url_for('signup'))

    return render_template('signup.html')

@limiter.limit("5 per minute")
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash("Please enter both email and password", "warning")
            return redirect(url_for('login'))

        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful", "success")
            return redirect(url_for('home'))

        flash("Invalid login details","error")
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully","success")
    return redirect(url_for("home"))

@app.route("/contact", methods=["GET", "POST"])
def contact():

    if request.method == "GET":
        return render_template("contact.html")

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    event = (request.form.get("event") or "").strip()
    message = (request.form.get("message") or "").strip()

    if not name or not email or not message:
        flash("Please fill out all required fields.", "warning")
        return redirect(url_for("contact"))

    try:

        details = []
        if phone:
            details.append(f"Phone: {phone}")
        if event:
            details.append(f"Shoot Type: {event}")

        stored_message = message
        if details:
            stored_message = "\n".join(details) + "\n\n" + stored_message

        db.session.add(ContactMessage(name=name, email=email, message=stored_message))
        db.session.commit()

        # Optional: send an email notification if SMTP env vars are set.
        if EMAIL_USER and EMAIL_PASS and EMAIL_RECEIVER:
            try:
                send_contact_email(
                    name=name,
                    email=email,
                    phone=phone,
                    event=event,
                    message=message
                )
            except Exception as e:
                print("Contact email error:", e)

        flash("Message sent successfully! We will contact you soon.", "success")

    except Exception as e:
        print("Contact error:", e)
        db.session.rollback()
        flash("Something went wrong. Please try again.", "error")

    return redirect(url_for("home"))


@app.route("/category/<string:category>")
def category_page(category):
    page = request.args.get("page", 1, type=int)
    requested_sort = (request.args.get("sort") or "").strip().lower()
    normalized = (category or "").strip().lower()

    if normalized not in PORTFOLIO_CATEGORIES:
        abort(404)

    args = {"category": normalized, "_anchor": "portfolio"}
    if page and page > 1:
        args["page"] = page
    if requested_sort in PORTFOLIO_SORT_OPTIONS and requested_sort != "newest":
        args["sort"] = requested_sort
    return redirect(url_for("home", **args))

@app.route("/photo/<int:photo_id>")
def single_photo(photo_id):
    photo = PortfolioPhoto.query.get_or_404(photo_id)
    return render_template("single_photo.html", photo=photo)

@app.route("/gallery/<slug>")
def gallery(slug):

    gallery = ClientGallery.query.filter_by(slug=slug).first_or_404()

    # Check if gallery already unlocked in session
    unlocked = _is_admin() or session.get(f"gallery_{gallery.id}", False)
    if not unlocked:
        return redirect(url_for("client_login", slug=gallery.slug))

    page = request.args.get("page", 1, type=int)
    photos = Photo.query.filter_by(gallery_id=gallery.id).paginate(page=page, per_page=40)

    return render_template("gallery.html", gallery=gallery, photos=photos)

@app.route("/client/<slug>", methods=["GET", "POST"])
def client_login(slug):
    gallery = ClientGallery.query.filter_by(slug=slug).first_or_404()

    if _is_admin():
        return redirect(url_for("gallery", slug=gallery.slug))

    if request.method == "POST":
        code = (request.form.get("code") or "").strip()

        if not code:
            flash("Access code is required", "error")
        else:
            is_valid = False

            try:
                is_valid = bcrypt.check_password_hash(gallery.code, code)
            except Exception:
                # Legacy galleries may have stored plaintext codes.
                is_valid = (gallery.code == code)

                # Opportunistically migrate plaintext codes to bcrypt.
                if is_valid:
                    gallery.code = bcrypt.generate_password_hash(code).decode("utf-8")
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

            if is_valid:
                session[f"gallery_{gallery.id}"] = True
                flash("Gallery unlocked.", "success")
                return redirect(url_for("gallery", slug=gallery.slug))

            flash("Invalid access code", "error")

    return render_template("client_login.html", gallery=gallery)

@app.route("/client/<slug>/logout")
def client_logout(slug):
    gallery = ClientGallery.query.filter_by(slug=slug).first_or_404()
    session.pop(f"gallery_{gallery.id}", None)
    flash("Gallery locked.", "info")
    return redirect(url_for("client_login", slug=gallery.slug))

@app.route("/client-photo/<int:photo_id>")
def client_photo(photo_id):
    photo = Photo.query.get_or_404(photo_id)
    gallery = ClientGallery.query.get_or_404(photo.gallery_id)

    if not (_is_admin() or session.get(f"gallery_{gallery.id}", False)):
        abort(403)

    return redirect(photo.filename)

@app.route("/download-gallery/<slug>")
def download_gallery(slug):

    gallery = ClientGallery.query.filter_by(slug=slug).first_or_404()

    # Prevent downloading locked galleries (code-protected access).
    if not (_is_admin() or session.get(f"gallery_{gallery.id}", False)):
        flash("Please unlock this gallery to download photos.", "error")
        return redirect(url_for("client_login", slug=gallery.slug))

    photos = Photo.query.filter_by(gallery_id=gallery.id).all()
    if not photos:
        flash("There are no photos in this gallery to download.", "info")
        return redirect(url_for("gallery", slug=gallery.slug))

    import cloudinary.utils
    
    # Extract public_ids from all secure_urls
    public_ids = []
    for photo in photos:
        # A cloudinary URL looks like: https://res.cloudinary.com/.../image/upload/v1/.../public_id.jpg
        try:
            # We try to extract public_id by splitting. Cloudinary expects the full public_id (with or without extension depending on settings, usually with extension is safer or explicitly stripping it).
            parts = photo.filename.split("/")
            if "upload" in parts:
                idx = parts.index("upload")
                # The public_id starts after the version number (v123...), which might be optional.
                public_id_part = "/".join(parts[idx+1:])
                # remove version if it exists
                if re.match(r"^v\d+$", public_id_part.split("/")[0]):
                    public_id_part = "/".join(public_id_part.split("/")[1:])
                
                # We need the public_id without the file extension if we want it to work correctly for zipping
                public_id = public_id_part.rsplit(".", 1)[0]
                public_ids.append(public_id)
        except Exception as e:
            print("Error parsing cloudinary url:", e)
            continue

    if not public_ids:
        flash("Error generating download link. No valid images found.", "error")
        return redirect(url_for("gallery", slug=gallery.slug))

    try:
        # Generate a zip file containing these specific public IDs
        zip_url = cloudinary.utils.download_zip_url(
            public_ids=public_ids,
            target_public_id=f"gallery_{gallery.slug}",
            allow_missing=True
        )
        return redirect(zip_url)
    except Exception as e:
        print("Error generating zip URL:", e)
        flash("Could not generate gallery download archive.", "error")
        return redirect(url_for("gallery", slug=gallery.slug))
# ---------------- ADMIN ROUTES ----------------
from datetime import datetime

@app.route("/studio-room")
@login_required
def admin_dashboard():
    if not _is_admin():
        flash("Access denied", "error")
        return abort(403)

    filter_date = request.args.get("filter_date")

    bookings_query = Booking.query

    if filter_date:
        try:
            filter_date = datetime.strptime(filter_date, "%Y-%m-%d").date()
            bookings_query = bookings_query.filter_by(event_date=filter_date)
        except ValueError:
            flash("Invalid date format", "error")

    bookings = bookings_query.order_by(Booking.created_at.desc()).all()

    photos = PortfolioPhoto.query.order_by(PortfolioPhoto.id.desc()).all()
    galleries = ClientGallery.query.all()
    users = User.query.order_by(User.created_at.desc()).all()
    admin_user_count = User.query.filter_by(is_admin=True).count()

    stats = {
        "total_photos": PortfolioPhoto.query.count(),
        "total_clients": ClientGallery.query.count(),
        "total_bookings": Booking.query.count(),
        "total_messages": ContactMessage.query.count()
    }

    return render_template(
        "admin.html",
        photos=photos,
        galleries=galleries,
        bookings=bookings,
        users=users,
        admin_user_count=admin_user_count,
        filter_date=filter_date,
        **stats
    )

@app.route("/admin/users/create", methods=["POST"])
@login_required
def admin_create_user():
    if not _is_admin():
        abort(403)

    email = (request.form.get("email") or "").strip().lower()
    password = (request.form.get("password") or "").strip()
    confirm = (request.form.get("confirm_password") or "").strip()
    is_admin = (request.form.get("is_admin") or "").strip() == "1"

    if not email or not password or not confirm:
        flash("Email and password are required.", "warning")
        return redirect(url_for("admin_dashboard") + "#admin-users")

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        flash("Please enter a valid email address.", "warning")
        return redirect(url_for("admin_dashboard") + "#admin-users")

    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("admin_dashboard") + "#admin-users")

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "warning")
        return redirect(url_for("admin_dashboard") + "#admin-users")

    if User.query.filter_by(email=email).first():
        flash("That email is already registered.", "info")
        return redirect(url_for("admin_dashboard") + "#admin-users")

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    new_user = User(email=email, password=hashed_password, is_admin=is_admin)

    try:
        db.session.add(new_user)
        db.session.commit()
        if is_admin:
            flash(f"User created and granted admin access: {email}", "success")
        else:
            flash(f"User created: {email}", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error creating user: {e}", "error")

    return redirect(url_for("admin_dashboard") + "#admin-users")

@app.route("/admin/users/<int:user_id>/set-admin", methods=["POST"])
@login_required
def admin_set_user_admin(user_id):
    if not _is_admin():
        abort(403)

    user = User.query.get_or_404(user_id)
    desired = (request.form.get("is_admin") or "").strip()
    if desired not in {"0", "1"}:
        abort(400)

    desired_admin = desired == "1"
    if user.is_admin and not desired_admin:
        # Prevent locking the app by removing the last admin.
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count <= 1:
            flash("You can't remove admin access from the last admin account.", "error")
            return redirect(url_for("admin_dashboard") + "#admin-users")

    user.is_admin = desired_admin
    try:
        db.session.commit()
        if desired_admin:
            flash(f"Admin access granted to {user.email}.", "success")
        else:
            flash(f"Admin access removed from {user.email}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating admin access: {e}", "error")

    return redirect(url_for("admin_dashboard") + "#admin-users")
# ================= CREATE GALLERY =================
@app.route("/create-gallery", methods=["POST"])
@login_required
def create_gallery():
    if not _is_admin():
        flash("Access denied","error")
        return redirect(url_for("home"))

    # Get client/event name and access code from form
    client_name = (request.form.get("title") or "").strip()
    client_email = (request.form.get("client_email") or "").strip().lower()
    if not client_name:
        flash("Client name is required", "warning")
        return redirect(url_for("admin_dashboard"))
    if client_email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", client_email):
        flash("Please provide a valid client email address.", "warning")
        return redirect(url_for("admin_dashboard"))

    plain_code = (request.form.get("code") or "").strip() or _generate_access_code()
    hashed_code = bcrypt.generate_password_hash(plain_code).decode("utf-8")

    # Generate an unguessable slug to improve privacy and avoid collisions.
    slug_base = generate_slug(client_name) or "gallery"
    slug = f"{slug_base}-{uuid.uuid4().hex[:8]}"
    while ClientGallery.query.filter_by(slug=slug).first() is not None:
        slug = f"{slug_base}-{uuid.uuid4().hex[:8]}"

    # Create new gallery
    new_gallery = ClientGallery(
        client_name=client_name,
        client_email=client_email or None,
        slug=slug,
        code=hashed_code
    )


    try:
        db.session.add(new_gallery)
        db.session.commit()
        client_url = url_for("client_login", slug=new_gallery.slug, _external=True)
        flash(
            f"Client gallery created for {client_name}. Link: {client_url} | Access code: {plain_code}",
            "success"
        )

        if client_email:
            try:
                send_gallery_access_email(
                    to_email=client_email,
                    client_name=client_name,
                    gallery_link=client_url,
                    access_code=plain_code,
                )
                flash(f"Access details sent to {client_email}.", "success")
            except Exception as e:
                print("Gallery access email error:", e)
                flash(
                    f"Gallery created, but email delivery failed for {client_email}. Use 'Send Code' to retry.",
                    "warning"
                )
    except Exception as e:
        db.session.rollback()
        flash(f"Error creating gallery: {e}","error")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/gallery/<int:gallery_id>/generate-access", methods=["POST"])
@login_required
def generate_gallery_access(gallery_id):
    if not _is_admin():
        abort(403)

    gallery = ClientGallery.query.get_or_404(gallery_id)

    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or request.form.get("email") or "").strip().lower()
    if not email:
        email = (gallery.client_email or "").strip().lower()

    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"ok": False, "error": "Please provide a valid email address."}), 400

    # Generate a NEW code each time (cannot recover the old one because it's hashed).
    plain_code = _generate_access_code()
    gallery.code = bcrypt.generate_password_hash(plain_code).decode("utf-8")
    if email:
        gallery.client_email = email

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": f"Could not update access code: {e}"}), 500

    client_url = url_for("client_login", slug=gallery.slug, _external=True)
    message = (
        f"Hello {gallery.client_name},\n\n"
        "Your private gallery is ready.\n\n"
        f"Link: {client_url}\n"
        f"Access code: {plain_code}\n\n"
        "Tip: open the link, enter the code, then you can download individual photos or use 'Download All'.\n\n"
        "StillPhotos"
    )

    # Optional email send (from provided email or saved gallery email).
    email_sent = False
    email_error = None

    if email:
        try:
            send_gallery_access_email(
                to_email=email,
                client_name=gallery.client_name or "Client",
                gallery_link=client_url,
                access_code=plain_code,
            )
            email_sent = True
        except Exception as e:
            email_error = str(e)

    whatsapp_url = "https://wa.me/?text=" + urllib.parse.quote(message)

    return jsonify(
        {
            "ok": True,
            "code": plain_code,
            "client_url": client_url,
            "message": message,
            "whatsapp_url": whatsapp_url,
            "delivery_email": email or None,
            "email_sent": email_sent,
            "email_error": email_error,
        }
    )

@app.route("/upload-client-photos", methods=["POST"])
@login_required
def upload_client_photos():
    if not _is_admin():
        abort(403)

    gallery_id = request.form.get("gallery_id")
    files = request.files.getlist("photo")

    if not gallery_id or not files:
        flash("Gallery and photos required","warning")
        return redirect(url_for("admin_dashboard"))

    for file in files:
        if file.filename and allowed_file(file.filename):

            result = cloudinary.uploader.upload(file)
            image_url = result.get("secure_url")

            if image_url:
                new_photo = Photo(
                    filename=image_url,
                    gallery_id=gallery_id
                )

                try:
                    db.session.add(new_photo)
                except Exception as e:
                    flash(f"Failed to save {file.filename}: {str(e)}","error")

    try:
        db.session.commit()
        flash(f"{len(files)} photos uploaded successfully!","success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error saving photos: {str(e)}","error")

    return redirect(url_for("admin_dashboard"))


@app.route("/upload-portfolio", methods=["POST"])
@login_required
def upload_portfolio():
    if not _is_admin():
        abort(403)

    file = request.files.get("photo")
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()

    if not file or not title or not category or not allowed_file(file.filename):
        flash("All fields required or invalid file type","warning")
        return redirect(url_for("admin_dashboard"))

    try:
        result = cloudinary.uploader.upload(file)
        image_url = result.get("secure_url")
        
        if not image_url:
            raise Exception("Cloudinary upload failed")

        new_photo = PortfolioPhoto(
            filename=image_url,
            title=title,
            category=category,
            is_public=True
        )

        db.session.add(new_photo)
        db.session.commit()

        flash("Portfolio photo uploaded","success")

    except Exception as e:
        print("Upload Error:", e)
        db.session.rollback()
        flash("Error uploading portfolio photo","error")

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete/<int:id>")
@login_required
def delete_photo(id):
    if not _is_admin():
        abort(403)

    photo = PortfolioPhoto.query.get_or_404(id)

    try:
        if photo.filename:
            import re
            import cloudinary.uploader
            parts = photo.filename.split("/")
            if "upload" in parts:
                idx = parts.index("upload")
                public_id_part = "/".join(parts[idx+1:])
                if re.match(r"^v\d+$", public_id_part.split("/")[0]):
                    public_id_part = "/".join(public_id_part.split("/")[1:])
                
                public_id = public_id_part.rsplit(".", 1)[0]
                cloudinary.uploader.destroy(public_id)

        db.session.delete(photo)
        db.session.commit()
        flash("Photo deleted","success")
    except Exception as e:
        print("Delete Error:", e)
        db.session.rollback()
        flash("Error deleting photo","error")

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_photo(id):
    if not _is_admin():
        abort(403)

    photo = PortfolioPhoto.query.get_or_404(id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()

        if not title or not category:
            flash("All fields required","warning")
            return redirect(url_for("edit_photo", id=id))

        photo.title = title
        photo.category = category

        try:
            db.session.commit()
            flash("Photo updated","success")
        except Exception:
            db.session.rollback()
            flash("Error updating photo","error")

        return redirect(url_for("admin_dashboard"))

    return render_template("edit.html", photo=photo)

@app.route("/delete-gallery/<int:id>", methods=["POST"])
@login_required
def delete_gallery(id):
    # Only allow admin
    if not _is_admin():
        abort(403)

    gallery = ClientGallery.query.get_or_404(id)

    # Delete all photos in this gallery from Cloudinary and database
    photos = Photo.query.filter_by(gallery_id=id).all()
    
    import re
    import cloudinary.uploader
    
    for photo in photos:
        if photo.filename:
            try:
                parts = photo.filename.split("/")
                if "upload" in parts:
                    idx = parts.index("upload")
                    public_id_part = "/".join(parts[idx+1:])
                    if re.match(r"^v\d+$", public_id_part.split("/")[0]):
                        public_id_part = "/".join(public_id_part.split("/")[1:])
                    public_id = public_id_part.rsplit(".", 1)[0]
                    cloudinary.uploader.destroy(public_id)
            except Exception as e:
                print(f"Error destroying cloudinary asset {photo.filename}: {e}")
                
        db.session.delete(photo)

    # Delete the gallery itself
    try:
        db.session.delete(gallery)
        db.session.commit()
        flash(f"Gallery '{gallery.client_name}' and its photos have been deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting gallery: {str(e)}","error")

    return redirect(url_for("admin_dashboard"))

@app.route("/delete-booking/<int:id>")
@login_required
def delete_booking(id):

    if not _is_admin():
        abort(403)

    booking = Booking.query.get_or_404(id)

    db.session.delete(booking)
    db.session.commit()

    flash("Booking deleted", "success")

    return redirect(url_for("admin_dashboard"))
# ---------------- RUN ----------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
