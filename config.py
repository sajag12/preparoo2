import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'replace-this-with-a-real-secret-key-please'
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Google OAuth configuration
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    
    # OAuth settings
    # Set DEVELOPMENT=true in your .env file for local development
    # This allows HTTP for localhost, otherwise HTTPS is enforced
    OAUTHLIB_INSECURE_TRANSPORT = os.environ.get('DEVELOPMENT', '').lower() == 'true'
    OAUTHLIB_RELAX_TOKEN_SCOPE = True 