import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

# Prevent app.py from auto-initializing the database on import, which causes SQLite path errors on Windows
os.environ["AUTO_CREATE_DB"] = "0"
# Hardcode the DB URI so app.py doesn't generate a broken engine during its global `db.init_app()`
cwd_path = os.getcwd().replace("\\", "/")
os.environ["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{cwd_path}/instance/site.db"

from app import app, db, PortfolioPhoto, Photo

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("CLOUD_API_KEY"),
    api_secret=os.getenv("CLOUD_API_SECRET")
)

def migrate_images():
    # Push an app context globally first so db can bind explicitly
    with app.app_context():
        # Folders where images might be stored currently
        legacy_dir = os.path.join(app.root_path, "static", "uploads")
        
        public_dir = os.getenv("UPLOAD_FOLDER", os.path.join(app.root_path, "instance", "public_uploads"))
        client_dir = os.getenv("CLIENT_UPLOAD_FOLDER", os.path.join(app.root_path, "instance", "client_uploads"))
        
        folders_to_check = [public_dir, client_dir, legacy_dir]

        print("--- Migrating Portfolio Photos ---")
        portfolio_photos = PortfolioPhoto.query.all()
        for p in portfolio_photos:
            if p.filename and not p.filename.startswith("http"):
                # Meaning it's a local file
                uploaded = False
                for folder in folders_to_check:
                    local_path = os.path.join(folder, p.filename)
                    if os.path.exists(local_path):
                        print(f"Uploading {local_path} to Cloudinary...")
                        try:
                            result = cloudinary.uploader.upload(local_path)
                            p.filename = result.get("secure_url")
                            uploaded = True
                            print("Success!")
                            break
                        except Exception as e:
                            print(f"Failed to upload {p.filename}: {e}")
                if not uploaded:
                    print(f"Could not find local file for portfolio image: {p.filename}")

        print("\n--- Migrating Client Photos ---")
        client_photos = Photo.query.all()
        for p in client_photos:
            if p.filename and not p.filename.startswith("http"):
                uploaded = False
                for folder in folders_to_check:
                    local_path = os.path.join(folder, p.filename)
                    if os.path.exists(local_path):
                        print(f"Uploading {local_path} to Cloudinary...")
                        try:
                            result = cloudinary.uploader.upload(local_path)
                            p.filename = result.get("secure_url")
                            uploaded = True
                            print("Success!")
                            break
                        except Exception as e:
                            print(f"Failed to upload {p.filename}: {e}")
                if not uploaded:
                    print(f"Could not find local file for client photo: {p.filename}")

        
        db.session.commit()
        print("\nMigration Complete! Database updated with Cloudinary URLs.")

if __name__ == "__main__":
    migrate_images()
