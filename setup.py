#!/usr/bin/env python3
"""
Setup script for CAT Prep App with Google OAuth
This script helps you set up the environment and check configuration.
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.8 or higher"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version.split()[0]}")
    return True

def check_virtual_environment():
    """Check if running in a virtual environment"""
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ Running in virtual environment")
        return True
    else:
        print("⚠️  Not running in virtual environment")
        print("Recommendation: Create and activate a virtual environment")
        return False

def install_requirements():
    """Install required packages"""
    try:
        print("📦 Installing requirements...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Requirements installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install requirements")
        return False

def check_env_file():
    """Check if .env file exists and has required variables"""
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found")
        print("Creating .env template...")
        create_env_template()
        return False
    
    # Check for required variables
    required_vars = [
        'GOOGLE_OAUTH_CLIENT_ID',
        'GOOGLE_OAUTH_CLIENT_SECRET',
        'SECRET_KEY'
    ]
    
    with open(env_file, 'r') as f:
        content = f.read()
    
    missing_vars = []
    for var in required_vars:
        if f"{var}=" not in content or f"{var}=your_" in content:
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing or incomplete environment variables: {', '.join(missing_vars)}")
        print("Please update your .env file with actual values")
        return False
    
    print("✅ .env file configured")
    return True

def create_env_template():
    """Create a template .env file"""
    template = """# Google OAuth Configuration
GOOGLE_OAUTH_CLIENT_ID=your_google_client_id_here
GOOGLE_OAUTH_CLIENT_SECRET=your_google_client_secret_here

# Flask Configuration
SECRET_KEY=your_super_secret_key_here_replace_this_with_a_real_secret_key
DATABASE_URL=sqlite:///app.db

# Development settings (set to False in production)
OAUTHLIB_INSECURE_TRANSPORT=True
OAUTHLIB_RELAX_TOKEN_SCOPE=True
"""
    
    with open(".env", "w") as f:
        f.write(template)
    print("✅ Created .env template file")

def check_static_files():
    """Check if required static files exist"""
    static_dir = Path("static")
    if not static_dir.exists():
        print("❌ Static directory not found")
        return False
    
    # Check for question set files (these might not exist in a fresh setup)
    question_files = [
        "Complete_VARC_Question_Set.csv",
        "DILR_Question_Set.csv", 
        "QA_Question_Set.csv"
    ]
    
    missing_files = []
    for file in question_files:
        if not (static_dir / file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"⚠️  Missing question set files: {', '.join(missing_files)}")
        print("Note: These files are required for the app to function properly")
        return False
    
    print("✅ Static files present")
    return True

def test_imports():
    """Test if all required packages can be imported"""
    try:
        import flask
        import flask_login
        import flask_dance
        import flask_sqlalchemy
        import python_dotenv
        print("✅ All required packages can be imported")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 CAT Prep App Setup")
    print("=" * 50)
    
    checks = [
        ("Python Version", check_python_version),
        ("Virtual Environment", check_virtual_environment),
        ("Install Requirements", install_requirements),
        ("Test Imports", test_imports),
        ("Environment File", check_env_file),
        ("Static Files", check_static_files),
    ]
    
    all_passed = True
    for name, check_func in checks:
        print(f"\n🔍 Checking {name}...")
        if not check_func():
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 Setup complete! You can now run the app with:")
        print("   python app.py")
    else:
        print("⚠️  Setup incomplete. Please address the issues above.")
        print("\nNext steps:")
        print("1. Set up Google OAuth credentials in Google Cloud Console")
        print("2. Update .env file with your actual credentials")
        print("3. Add question set CSV files to the static directory")
    
    print("\n📚 For detailed instructions, see README.md")

if __name__ == "__main__":
    main() 