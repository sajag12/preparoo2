import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'replace-this-with-a-real-secret-key-please'
    
    # Database configuration
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Google OAuth configuration
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    
    # OAuth settings for Railway deployment
    if os.environ.get('PORT') or os.environ.get('RAILWAY_ENVIRONMENT'):
        # Production Railway environment
        PREFERRED_URL_SCHEME = 'https'
        OAUTHLIB_INSECURE_TRANSPORT = False
        OAUTHLIB_RELAX_TOKEN_SCOPE = True
        OAUTHLIB_IGNORE_SCOPE_CHANGE = True
    else:
        # Local development
        OAUTHLIB_INSECURE_TRANSPORT = True
        OAUTHLIB_RELAX_TOKEN_SCOPE = True
        OAUTHLIB_IGNORE_SCOPE_CHANGE = True 