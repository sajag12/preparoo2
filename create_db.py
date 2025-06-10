#!/usr/bin/env python3
"""
Database creation script for CAT Prep App
Run this script to create all database tables including the new TestResult table
"""

from app import app
from models import db

def create_tables():
    """Create all database tables"""
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Database tables created successfully!")
        
        # Print created tables
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"Created tables: {', '.join(tables)}")

if __name__ == '__main__':
    create_tables() 