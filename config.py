import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
    DEBUG = os.getenv('FLASK_ENV') == 'development'
    
    # Hardcoded credentials (for demo purposes only)
    VALID_CREDENTIALS = {
        "admin@123.com": "admin123"
    }
    
    # Flask configuration
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Application settings
    ALLOWED_EXTENSIONS = {'csv'}
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = 1800  # 30 minutes