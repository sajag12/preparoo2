#!/usr/bin/env python3
"""
Railway deployment initialization script
This script initializes the database tables for Railway deployment
"""

import os
import sys
from app import app
from models import db

def init_railway_db():
    """Initialize database tables for Railway deployment"""
    try:
        with app.app_context():
            print("🚀 Starting Railway database initialization...")
            
            # Test database connection
            from sqlalchemy import text
            result = db.session.execute(text('SELECT 1'))
            print("✅ Database connection successful")
            
            # Create all tables
            print("📋 Creating database tables...")
            db.create_all()
            print("✅ Database tables created successfully!")
            
            # Verify tables were created
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            print(f"📊 Created tables: {', '.join(tables)}")
            
            # Commit any pending changes
            db.session.commit()
            print("✅ Railway database initialization completed successfully!")
            
            return True
            
    except Exception as e:
        print(f"❌ Railway database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = init_railway_db()
    sys.exit(0 if success else 1) 