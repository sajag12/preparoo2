from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import json

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    avatar_url = db.Column(db.String(200))
    google_id = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to test results
    test_results = db.relationship('TestResult', backref='user', lazy=True)
    
    def __repr__(self):
        return f'<User {self.email}>'
    
    @staticmethod
    def find_or_create(google_id, email, name, avatar_url=None):
        """Find existing user or create new one"""
        user = User.query.filter_by(google_id=google_id).first()
        
        if not user:
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                avatar_url=avatar_url
            )
            db.session.add(user)
        else:
            # Update user info in case it changed
            user.email = email
            user.name = name
            user.avatar_url = avatar_url
            user.last_login = datetime.utcnow()
        
        db.session.commit()
        return user


class TestResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    test_id = db.Column(db.String(20), nullable=False)  # e.g., '1', 'qa1', 'varc1', etc.
    test_type = db.Column(db.String(20), nullable=False)  # 'full_mock' or 'sectional'
    test_name = db.Column(db.String(100), nullable=False)
    
    # Results data
    total_score = db.Column(db.Integer)
    total_possible = db.Column(db.Integer)
    time_spent = db.Column(db.String(20))
    accuracy = db.Column(db.Float)
    correct = db.Column(db.Integer)
    wrong = db.Column(db.Integer)
    skipped = db.Column(db.Integer)
    
    # Store detailed data as JSON
    sections_data = db.Column(db.Text)  # JSON string of sections data
    answer_data = db.Column(db.Text)    # JSON string of answer data
    question_times = db.Column(db.Text) # JSON string of question times
    section_times = db.Column(db.Text)  # JSON string of section times
    
    # Analysis data
    missed_opportunities = db.Column(db.Text)  # JSON string
    time_wasters = db.Column(db.Text)          # JSON string
    swot_analysis = db.Column(db.Text)         # JSON string
    topic_analysis = db.Column(db.Text)        # JSON string
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint to prevent duplicate test results for same user and test
    __table_args__ = (db.UniqueConstraint('user_id', 'test_id', name='unique_user_test'),)
    
    def __repr__(self):
        return f'<TestResult {self.user_id}-{self.test_id}>'
    
    def to_dict(self):
        """Convert TestResult to dictionary format similar to session data"""
        result = {
            'test_name': self.test_name,
            'test_id': self.test_id,
            'test_type': self.test_type,
            'total_score': self.total_score,
            'total_possible': self.total_possible,
            'time_spent': self.time_spent,
            'accuracy': round(self.accuracy, 1) if self.accuracy else 0,
            'correct': self.correct,
            'wrong': self.wrong,
            'skipped': self.skipped,
            'created_at': self.created_at
        }
        
        # Parse JSON fields
        if self.sections_data:
            result['sections'] = json.loads(self.sections_data)
        
        if self.answer_data:
            result['answer_data'] = json.loads(self.answer_data)
            
        if self.question_times:
            result['question_times'] = json.loads(self.question_times)
            
        if self.section_times:
            result['section_times'] = json.loads(self.section_times)
            
        if self.missed_opportunities:
            result['missed_opportunities'] = json.loads(self.missed_opportunities)
            
        if self.time_wasters:
            result['time_wasters'] = json.loads(self.time_wasters)
            
        if self.swot_analysis:
            result['swot_analysis'] = json.loads(self.swot_analysis)
            
        if self.topic_analysis:
            result['topic_analysis'] = json.loads(self.topic_analysis)
            
        # Add section_name for sectional tests
        if self.test_type == 'sectional':
            result['section_name'] = self.test_name.replace('Sectional Mock - ', '')
            # For sectional tests, also provide 'score' key for template compatibility
            result['score'] = self.total_score
            
        return result
    
    @staticmethod
    def create_from_session_data(user_id, test_id, session_data):
        """Create TestResult from session data"""
        # Determine test type using multiple indicators
        test_name = session_data.get('test_name', '')
        section_name = session_data.get('section_name', '')
        
        # Check if it's sectional based on multiple indicators
        is_sectional = (
            test_name.startswith('Sectional Mock') or 
            bool(section_name) or 
            str(test_id).startswith(('qa', 'varc', 'lrdi'))
        )
        test_type = 'sectional' if is_sectional else 'full_mock'
        
        # Calculate metrics based on test type
        if test_type == 'sectional':
            # For sectional tests, use direct values
            total_score = session_data.get('score', 0)
            total_possible = session_data.get('total_possible', 0)
            time_spent = session_data.get('time_spent', 'N/A')
            correct = session_data.get('correct', 0)
            wrong = session_data.get('wrong', 0)
            skipped = session_data.get('skipped', 0)
            total_attempted = correct + wrong
            accuracy = (correct / total_attempted * 100) if total_attempted > 0 else 0
        else:
            # For full mock tests, aggregate from sections
            sections = session_data.get('sections', [])
            total_score = session_data.get('total_score', 0)
            total_possible = session_data.get('total_possible', 0)
            time_spent = session_data.get('time_spent', 'N/A')
            correct = sum(sec.get('correct', 0) for sec in sections)
            wrong = sum(sec.get('wrong', 0) for sec in sections)
            skipped = sum(sec.get('skipped', 0) for sec in sections)
            total_attempted = correct + wrong
            accuracy = (correct / total_attempted * 100) if total_attempted > 0 else 0
        
        # Create new test result
        test_result = TestResult(
            user_id=user_id,
            test_id=str(test_id),
            test_type=test_type,
            test_name=session_data.get('test_name', ''),
            total_score=total_score,
            total_possible=total_possible,
            time_spent=time_spent,
            accuracy=round(accuracy, 1),
            correct=correct,
            wrong=wrong,
            skipped=skipped
        )
        
        # Store JSON data
        if 'sections' in session_data:
            test_result.sections_data = json.dumps(session_data['sections'])
            
        if 'answer_data' in session_data:
            test_result.answer_data = json.dumps(session_data['answer_data'])
            
        if 'question_times' in session_data:
            test_result.question_times = json.dumps(session_data['question_times'])
            
        if 'section_times' in session_data:
            test_result.section_times = json.dumps(session_data['section_times'])
            
        if 'missed_opportunities' in session_data:
            test_result.missed_opportunities = json.dumps(session_data['missed_opportunities'])
            
        if 'time_wasters' in session_data:
            test_result.time_wasters = json.dumps(session_data['time_wasters'])
            
        if 'swot_analysis' in session_data:
            test_result.swot_analysis = json.dumps(session_data['swot_analysis'])
            
        if 'topic_analysis' in session_data:
            test_result.topic_analysis = json.dumps(session_data['topic_analysis'])
        
        return test_result
    
    @staticmethod
    def get_user_test_result(user_id, test_id):
        """Get user's test result for a specific test"""
        return TestResult.query.filter_by(user_id=user_id, test_id=str(test_id)).first()
    
    @staticmethod
    def create_or_update_test_result(user_id, test_id, session_data):
        """Create new test result or update existing one (safer for retakes)"""
        try:
            # Try to find existing result
            existing_result = TestResult.get_user_test_result(user_id, test_id)
            
            if existing_result:
                print(f"DEBUG: Updating existing test result for user {user_id}, test {test_id}")
                # Update existing result with new data
                
                # Determine test type using multiple indicators
                test_name = session_data.get('test_name', '')
                section_name = session_data.get('section_name', '')
                
                # Check if it's sectional based on multiple indicators
                is_sectional = (
                    test_name.startswith('Sectional Mock') or 
                    bool(section_name) or 
                    str(test_id).startswith(('qa', 'varc', 'lrdi'))
                )
                test_type = 'sectional' if is_sectional else 'full_mock'
                
                # Calculate metrics based on test type
                if test_type == 'sectional':
                    # For sectional tests, use direct values
                    total_score = session_data.get('score', 0)
                    total_possible = session_data.get('total_possible', 0)
                    time_spent = session_data.get('time_spent', 'N/A')
                    correct = session_data.get('correct', 0)
                    wrong = session_data.get('wrong', 0)
                    skipped = session_data.get('skipped', 0)
                    total_attempted = correct + wrong
                    accuracy = (correct / total_attempted * 100) if total_attempted > 0 else 0
                else:
                    # For full mock tests, aggregate from sections
                    sections = session_data.get('sections', [])
                    total_score = session_data.get('total_score', 0)
                    total_possible = session_data.get('total_possible', 0)
                    time_spent = session_data.get('time_spent', 'N/A')
                    correct = sum(sec.get('correct', 0) for sec in sections)
                    wrong = sum(sec.get('wrong', 0) for sec in sections)
                    skipped = sum(sec.get('skipped', 0) for sec in sections)
                    total_attempted = correct + wrong
                    accuracy = (correct / total_attempted * 100) if total_attempted > 0 else 0
                
                # Update fields
                existing_result.test_name = session_data.get('test_name', '')
                existing_result.total_score = total_score
                existing_result.total_possible = total_possible
                existing_result.time_spent = time_spent
                existing_result.accuracy = round(accuracy, 1)
                existing_result.correct = correct
                existing_result.wrong = wrong
                existing_result.skipped = skipped
                existing_result.updated_at = datetime.utcnow()
                
                # Update JSON data
                if 'sections' in session_data:
                    existing_result.sections_data = json.dumps(session_data['sections'])
                    
                if 'answer_data' in session_data:
                    existing_result.answer_data = json.dumps(session_data['answer_data'])
                    
                if 'question_times' in session_data:
                    existing_result.question_times = json.dumps(session_data['question_times'])
                    
                if 'section_times' in session_data:
                    existing_result.section_times = json.dumps(session_data['section_times'])
                    
                if 'missed_opportunities' in session_data:
                    existing_result.missed_opportunities = json.dumps(session_data['missed_opportunities'])
                    
                if 'time_wasters' in session_data:
                    existing_result.time_wasters = json.dumps(session_data['time_wasters'])
                    
                if 'swot_analysis' in session_data:
                    existing_result.swot_analysis = json.dumps(session_data['swot_analysis'])
                
                return existing_result, True  # Return (result, is_update)
            else:
                print(f"DEBUG: Creating new test result for user {user_id}, test {test_id}")
                # Create new result
                new_result = TestResult.create_from_session_data(user_id, test_id, session_data)
                return new_result, False  # Return (result, is_update)
                
        except Exception as e:
            print(f"ERROR in create_or_update_test_result: {e}")
            # Fallback to creating new result
            new_result = TestResult.create_from_session_data(user_id, test_id, session_data)
            return new_result, False
    
    def update_metrics(self):
        """Update metrics by recalculating from stored data"""
        if not self.sections_data:
            return False
            
        try:
            sections = json.loads(self.sections_data)
            
            if self.test_type == 'sectional':
                # For sectional tests, there should be one section with the metrics
                if sections and len(sections) > 0:
                    # Try to find metrics in the sections data
                    section = sections[0] if isinstance(sections, list) else sections
                    if isinstance(section, dict) and 'correct' in section:
                        self.correct = section.get('correct', 0)
                        self.wrong = section.get('wrong', 0)
                        self.skipped = section.get('skipped', 0)
                        self.total_score = section.get('score', 0)
                        
                        total_attempted = self.correct + self.wrong
                        self.accuracy = round((self.correct / total_attempted * 100), 1) if total_attempted > 0 else 0
                        return True
            else:
                # For full mock tests, aggregate from sections
                if isinstance(sections, list):
                    self.correct = sum(sec.get('correct', 0) for sec in sections)
                    self.wrong = sum(sec.get('wrong', 0) for sec in sections)
                    self.skipped = sum(sec.get('skipped', 0) for sec in sections)
                    self.total_score = sum(sec.get('score', 0) for sec in sections)
                    
                    total_attempted = self.correct + self.wrong
                    self.accuracy = round((self.correct / total_attempted * 100), 1) if total_attempted > 0 else 0
                    return True
                    
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            pass
            
        return False
    
    @staticmethod
    def fix_all_metrics():
        """Fix metrics for all test results that have incorrect data"""
        fixed_count = 0
        results = TestResult.query.filter(
            db.or_(
                TestResult.correct.is_(None),
                TestResult.wrong.is_(None), 
                TestResult.skipped.is_(None),
                TestResult.total_score < 0,
                db.and_(TestResult.correct == 0, TestResult.wrong == 0, TestResult.skipped == 0)
            )
        ).all()
        
        for result in results:
            if result.update_metrics():
                fixed_count += 1
                
        if fixed_count > 0:
            db.session.commit()
            
        return fixed_count 