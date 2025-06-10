#!/usr/bin/env python3
"""
Debug utility to check for test retake issues
"""

from app import app
from models import db, TestResult, User

def check_database_consistency():
    """Check for potential issues in the database"""
    with app.app_context():
        print("=== Database Consistency Check ===")
        
        # Check for duplicate test results
        print("\n1. Checking for duplicate test results...")
        users = User.query.all()
        issues_found = []
        
        for user in users:
            test_counts = {}
            user_results = TestResult.query.filter_by(user_id=user.id).all()
            
            for result in user_results:
                test_id = result.test_id
                if test_id in test_counts:
                    test_counts[test_id] += 1
                else:
                    test_counts[test_id] = 1
            
            # Report duplicates
            for test_id, count in test_counts.items():
                if count > 1:
                    issues_found.append(f"User {user.email} has {count} results for test {test_id}")
                    print(f"  ⚠️  User {user.email} has {count} results for test {test_id}")
        
        if not issues_found:
            print("  ✅ No duplicate test results found")
        
        # Check for missing or invalid data
        print("\n2. Checking for missing or invalid data...")
        invalid_results = TestResult.query.filter(
            db.or_(
                TestResult.total_score.is_(None),
                TestResult.accuracy.is_(None),
                TestResult.correct.is_(None),
                TestResult.wrong.is_(None),
                TestResult.skipped.is_(None)
            )
        ).all()
        
        if invalid_results:
            print(f"  ⚠️  Found {len(invalid_results)} results with missing data")
            for result in invalid_results[:5]:  # Show first 5
                print(f"    - Test {result.test_id} for user {result.user_id} (ID: {result.id})")
        else:
            print("  ✅ All test results have complete data")
        
        # Check for very old timestamps
        print("\n3. Checking for timestamp consistency...")
        results_with_old_updates = TestResult.query.filter(
            TestResult.created_at > TestResult.updated_at
        ).all()
        
        if results_with_old_updates:
            print(f"  ⚠️  Found {len(results_with_old_updates)} results with inconsistent timestamps")
        else:
            print("  ✅ All timestamps are consistent")
        
        return len(issues_found) + len(invalid_results) + len(results_with_old_updates)

def fix_duplicate_results():
    """Remove duplicate test results, keeping the most recent one"""
    with app.app_context():
        print("\n=== Fixing Duplicate Results ===")
        
        # Find all users
        users = User.query.all()
        fixed_count = 0
        
        for user in users:
            # Group results by test_id
            test_groups = {}
            user_results = TestResult.query.filter_by(user_id=user.id).order_by(TestResult.created_at.desc()).all()
            
            for result in user_results:
                test_id = result.test_id
                if test_id not in test_groups:
                    test_groups[test_id] = []
                test_groups[test_id].append(result)
            
            # For each test with duplicates, keep the most recent and delete others
            for test_id, results in test_groups.items():
                if len(results) > 1:
                    print(f"  Fixing duplicates for user {user.email}, test {test_id}")
                    # Keep the first (most recent) result, delete the rest
                    keep_result = results[0]
                    for duplicate_result in results[1:]:
                        print(f"    Deleting duplicate result ID {duplicate_result.id}")
                        db.session.delete(duplicate_result)
                        fixed_count += 1
        
        if fixed_count > 0:
            print(f"\n  Committing {fixed_count} deletions...")
            db.session.commit()
            print(f"  ✅ Fixed {fixed_count} duplicate results")
        else:
            print("  ✅ No duplicates found to fix")
        
        return fixed_count

def main():
    """Main function"""
    print("CAT Prep App - Test Retake Debug Utility")
    print("=" * 50)
    
    # Check for issues
    issues_count = check_database_consistency()
    
    if issues_count > 0:
        print(f"\n⚠️  Found {issues_count} issues")
        
        response = input("\nWould you like to fix duplicate results? (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            fixed_count = fix_duplicate_results()
            print(f"\n✅ Process complete. Fixed {fixed_count} issues.")
        else:
            print("\n⏭️  Skipping fixes. Run this script again to fix issues.")
    else:
        print("\n✅ Database looks good! No issues found.")

if __name__ == "__main__":
    main() 