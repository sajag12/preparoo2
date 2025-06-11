from flask import Flask, render_template, request, session, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin
import csv
import os
import warnings
import traceback

# Import configuration and models
from config import Config
from models import db, User, TestResult

app = Flask(__name__)
app.config.from_object(Config)

# Configure for Railway proxy (HTTPS termination)
if os.environ.get('PORT') or os.environ.get('RAILWAY_ENVIRONMENT'):
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Set OAuth environment variables directly for production
    os.environ['OAUTHLIB_IGNORE_SCOPE_CHANGE'] = '1'
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
else:
    # Set OAuth environment variables for local development
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    os.environ['OAUTHLIB_IGNORE_SCOPE_CHANGE'] = '1'
    os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Add custom Jinja2 filters
def startswith_filter(text, prefix):
    """Custom Jinja2 filter to check if text starts with prefix"""
    return str(text).startswith(str(prefix))

app.jinja_env.filters['startswith'] = startswith_filter

# Create Google OAuth blueprint
google_bp = make_google_blueprint(
    client_id=app.config.get('GOOGLE_OAUTH_CLIENT_ID'),
    client_secret=app.config.get('GOOGLE_OAUTH_CLIENT_SECRET'),
    scope=["https://www.googleapis.com/auth/userinfo.profile", 
           "https://www.googleapis.com/auth/userinfo.email", 
           "openid"]
)
app.register_blueprint(google_bp, url_prefix="/login")

# OAuth token storage model (optional - not actively used)
class OAuth(OAuthConsumerMixin, db.Model):
    provider_user_id = db.Column(db.String(256), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    user = db.relationship("User")

@login_manager.user_loader
def load_user(user_id):
    print(f"DEBUG: load_user called with user_id = {user_id}")
    user = User.query.get(int(user_id))
    print(f"DEBUG: load_user returning user = {user}")
    return user

# Create database tables
def init_db():
    """Initialize the database tables"""
    try:
        with app.app_context():
            # Test database connection first
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            print("Database connection successful")
            
            # Create tables
            db.create_all()
            print("Database tables created successfully")
            
            db.session.commit()
            return True
    except Exception as e:
        print(f"Database initialization error: {e}")
        # Try to rollback in case of error
        try:
            db.session.rollback()
        except:
            pass
        return False

# Initialize database for both Gunicorn and direct execution
def initialize_app():
    """Initialize the app for production deployment"""
    try:
        success = init_db()
        if not success:
            print("WARNING: Database initialization failed, but continuing startup")
    except Exception as e:
        print(f"App initialization error: {e}")

# Call initialization for production deployment (Gunicorn)
if os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('PORT'):
    initialize_app()

# Skip OAuth storage setup - we handle user management manually
# google_bp.storage = SQLAlchemyStorage(OAuth, db.session, user=current_user, user_required=False)

# Flask-Dance event handler for when OAuth token is created
from flask_dance.consumer import oauth_authorized

@oauth_authorized.connect_via(google_bp)
def google_logged_in(blueprint, token):
    try:
        if not token:
            flash('Failed to log in with Google - no token received.', 'error')
            return redirect(url_for('login'))

        # Handle scope warnings as non-fatal
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = blueprint.session.get("/oauth2/v2/userinfo")
            
        if not resp.ok:
            flash('Failed to fetch user info from Google.', 'error')
            return redirect(url_for('login'))

        google_info = resp.json()
        google_id = google_info.get('id')
        email = google_info.get('email')
        name = google_info.get('name')
        avatar_url = google_info.get('picture')

        if not google_id or not email:
            flash('Failed to get required user information from Google.', 'error')
            return redirect(url_for('login'))

        # Find or create user
        user = User.find_or_create(
            google_id=google_id,
            email=email,
            name=name,
            avatar_url=avatar_url
        )

        if user:
            print(f"DEBUG: OAuth event - logging in user: {user}")
            login_user(user, remember=True)
            flash(f'Welcome, {user.name}!', 'success')
            
            # Redirect to mock tests page after successful login
            return redirect(url_for('mock_tests_page'))
        else:
            flash('Failed to create or find user account.', 'error')
            return redirect(url_for('login'))
            
    except Exception as e:
        print(f"ERROR in OAuth callback: {e}")
        # Log the full traceback for debugging
        traceback.print_exc()
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('login'))

# Authentication routes
@app.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('home'))

# Manual route to initiate Google OAuth (alternative to using the login page)
@app.route('/auth/google')
def initiate_google_auth():
    return redirect(url_for('google.login'))

# Health check route for debugging
@app.route('/health')
def health_check():
    try:
        # Test database connection
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        db.session.commit()
        return {'status': 'healthy', 'database': 'connected'}, 200
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}, 500

# Custom redirect after successful OAuth login
@app.route('/after-oauth')
def after_oauth():
    if current_user.is_authenticated:
        # If user came from a protected page, redirect there
        next_page = session.get('next_page')
        if next_page:
            session.pop('next_page', None)
            return redirect(next_page)
        # Otherwise redirect to mock tests
        return redirect(url_for('mock_tests_page'))
    else:
        return redirect(url_for('login'))

# --- Helper for formatting time ---
def format_seconds_to_str(seconds):
    if seconds is None:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"

def get_sections_conf_for_test(test_id):
    """Get the appropriate CSV configuration for a specific test"""
    
    # For full mock tests 1-15, use consistent naming pattern
    if isinstance(test_id, int) and 1 <= test_id <= 15:
        return [
            { 'name': "Verbal Ability and Reading Comprehension", 'csv': f'VARC_#{test_id}.csv', 'short_name': 'VARC' },
            { 'name': "Data Interpretation & Logical Reasoning", 'csv': f'LRDI_#{test_id}.csv', 'short_name': 'LRDI' },
            { 'name': "Quantitative Aptitude", 'csv': f'QA_{test_id}.csv', 'short_name': 'QA' }
        ]
    
    # Handle string test_id (could be from session or database)
    if isinstance(test_id, str) and test_id.isdigit():
        test_num = int(test_id)
        if 1 <= test_num <= 15:
            return [
                { 'name': "Verbal Ability and Reading Comprehension", 'csv': f'VARC_#{test_num}.csv', 'short_name': 'VARC' },
                { 'name': "Data Interpretation & Logical Reasoning", 'csv': f'LRDI_#{test_num}.csv', 'short_name': 'LRDI' },
                { 'name': "Quantitative Aptitude", 'csv': f'QA_{test_num}.csv', 'short_name': 'QA' }
            ]
    
    # Fixed default configuration for fallback (using correct LRDI filename)
    default_conf = [
        { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#1.csv', 'short_name': 'VARC' },
        { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#1.csv', 'short_name': 'LRDI' },
        { 'name': "Quantitative Aptitude", 'csv': 'QA_1.csv', 'short_name': 'QA' }
    ]
    
    return default_conf

def generate_swot_analysis(stats):
    """Generate question selection strategy-based SWOT analysis"""
    test_id = stats.get('test_id')
    answer_data = stats.get('answer_data', {})
    question_times = stats.get('question_times', {})
    
    if not test_id or test_id in ['qa1', 'qa2', 'qa3', 'qa4', 'varc1', 'varc2', 'varc3', 'lrdi1', 'lrdi2', 'lrdi3']:
        return generate_fallback_swot_analysis(stats)  # For non-full mock tests
    
    if not answer_data or not question_times:
        return generate_fallback_swot_analysis(stats)
    
    sections = stats.get('sections', [])
    
    swot = {
        'strengths': [],
        'weaknesses': [],
        'opportunities': [],
        'threats': []
    }
    
    # Section configurations with CSV paths
    sections_conf = get_sections_conf_for_test(test_id)
    
    try:
        overall_metrics = analyze_overall_question_selection(sections_conf, answer_data, question_times)
        section_analyses = []
        
        # Analyze each section
        for sec_idx, sec_conf in enumerate(sections_conf):
            section_metrics = analyze_section_question_selection(sec_conf, sec_idx, answer_data, question_times)
            section_analyses.append(section_metrics)
        
        # Generate SWOT based on overall analysis
        generate_overall_swot_items(swot, overall_metrics, section_analyses)
        
        # Generate section-wise insights
        for section_metrics in section_analyses:
            generate_section_swot_items(swot, section_metrics)
        
        # Ensure balanced SWOT (at least 1 item per category, max 3)
        ensure_balanced_swot(swot)
        
        return swot
        
    except Exception as e:
        return generate_fallback_swot_analysis(stats)

def analyze_overall_question_selection(sections_conf, answer_data, question_times):
    """Analyze overall question selection strategy across all sections"""
    total_easy = total_medium = total_hard = 0
    attempted_easy = attempted_medium = attempted_hard = 0
    easy_times = []
    hard_times = []
    
    for sec_idx, sec_conf in enumerate(sections_conf):
        try:
            path = app.static_folder + '/' + sec_conf['csv']
            rows = list(csv.DictReader(open(path, encoding='utf-8')))
            answers = answer_data.get(str(sec_idx), {})
            times = question_times.get(str(sec_idx), {})
            
            for q_idx, row in enumerate(rows):
                difficulty = row.get('DifficultyLevelPredicted', '').strip().lower()
                user_ans = answers.get(str(q_idx), {}).get('answer')
                q_time = times.get(str(q_idx))
                
                # Count total questions by difficulty
                if difficulty == 'easy':
                    total_easy += 1
                    if user_ans is not None:
                        attempted_easy += 1
                        if q_time:
                            easy_times.append(q_time)
                elif difficulty == 'medium':
                    total_medium += 1
                    if user_ans is not None:
                        attempted_medium += 1
                elif 'hard' in difficulty:
                    total_hard += 1
                    if user_ans is not None:
                        attempted_hard += 1
                        if q_time:
                            hard_times.append(q_time)
                            
        except FileNotFoundError:
            continue
    
    # Calculate percentages
    easy_attempt_pct = (attempted_easy / total_easy * 100) if total_easy > 0 else 0
    medium_attempt_pct = (attempted_medium / total_medium * 100) if total_medium > 0 else 0
    hard_attempt_pct = (attempted_hard / total_hard * 100) if total_hard > 0 else 0
    
    # Calculate average times
    avg_easy_time = sum(easy_times) / len(easy_times) if easy_times else 0
    avg_hard_time = sum(hard_times) / len(hard_times) if hard_times else 0
    
    return {
        'total_easy': total_easy,
        'total_medium': total_medium,
        'total_hard': total_hard,
        'attempted_easy': attempted_easy,
        'attempted_medium': attempted_medium,
        'attempted_hard': attempted_hard,
        'easy_attempt_pct': easy_attempt_pct,
        'medium_attempt_pct': medium_attempt_pct,
        'hard_attempt_pct': hard_attempt_pct,
        'avg_easy_time': avg_easy_time,
        'avg_hard_time': avg_hard_time,
        'time_priority_correct': avg_easy_time > 0 and avg_hard_time > 0 and avg_easy_time < avg_hard_time
    }

def analyze_section_question_selection(sec_conf, sec_idx, answer_data, question_times):
    """Analyze question selection strategy for a specific section"""
    try:
        path = app.static_folder + '/' + sec_conf['csv']
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
        answers = answer_data.get(str(sec_idx), {})
        times = question_times.get(str(sec_idx), {})
        
        section_name = sec_conf['name']
        short_name = sec_conf['short_name']
        
        easy_qs = []
        medium_qs = []
        hard_qs = []
        topic_performance = {}
        
        for q_idx, row in enumerate(rows):
            difficulty = row.get('DifficultyLevelPredicted', '').strip().lower()
            topic = row.get('Topic', 'Unknown Topic')
            subtopic = row.get('SubTopic', 'Unknown SubTopic')
            user_ans = answers.get(str(q_idx), {}).get('answer')
            correct_ans = row.get('CorrectAnswerValue')
            q_time = times.get(str(q_idx))
            
            # Track topic performance
            if topic not in topic_performance:
                topic_performance[topic] = {'total': 0, 'attempted': 0, 'correct': 0, 'easy_missed': 0}
            
            topic_performance[topic]['total'] += 1
            
            q_data = {
                'idx': q_idx,
                'topic': topic,
                'subtopic': subtopic,
                'attempted': user_ans is not None,
                'correct': str(user_ans) == str(correct_ans) if user_ans is not None else False,
                'time': q_time
            }
            
            if user_ans is not None:
                topic_performance[topic]['attempted'] += 1
                if str(user_ans) == str(correct_ans):
                    topic_performance[topic]['correct'] += 1
            
            # Categorize by difficulty
            if difficulty == 'easy':
                easy_qs.append(q_data)
                if user_ans is None:  # Easy question missed
                    topic_performance[topic]['easy_missed'] += 1
            elif difficulty == 'medium':
                medium_qs.append(q_data)
            elif 'hard' in difficulty:
                hard_qs.append(q_data)
        
        # Calculate metrics
        total_easy = len(easy_qs)
        attempted_easy = sum(1 for q in easy_qs if q['attempted'])
        total_medium = len(medium_qs)
        attempted_medium = sum(1 for q in medium_qs if q['attempted'])
        total_hard = len(hard_qs)
        attempted_hard = sum(1 for q in hard_qs if q['attempted'])
        
        easy_attempt_pct = (attempted_easy / total_easy * 100) if total_easy > 0 else 0
        medium_attempt_pct = (attempted_medium / total_medium * 100) if total_medium > 0 else 0
        
        # Find strongest topics (by accuracy among attempted questions)
        strong_topics = []
        for topic, perf in topic_performance.items():
            if perf['attempted'] >= 3:  # At least 3 questions attempted
                accuracy = (perf['correct'] / perf['attempted'] * 100)
                if accuracy >= 75:
                    strong_topics.append(topic)
        
        # Find topics with missed easy questions
        topics_with_missed_easy = []
        for topic, perf in topic_performance.items():
            if perf['easy_missed'] > 0:
                topics_with_missed_easy.append((topic, perf['easy_missed']))
        
        return {
            'section_name': section_name,
            'short_name': short_name,
            'total_easy': total_easy,
            'total_medium': total_medium,
            'total_hard': total_hard,
            'attempted_easy': attempted_easy,
            'attempted_medium': attempted_medium,
            'attempted_hard': attempted_hard,
            'easy_attempt_pct': easy_attempt_pct,
            'medium_attempt_pct': medium_attempt_pct,
            'unattempted_easy': total_easy - attempted_easy,
            'strong_topics': strong_topics,
            'topics_with_missed_easy': topics_with_missed_easy,
            'topic_performance': topic_performance
        }
        
    except FileNotFoundError:
        return None

def generate_overall_swot_items(swot, overall_metrics, section_analyses):
    """Generate SWOT items based on overall question selection strategy"""
    easy_pct = overall_metrics['easy_attempt_pct']
    medium_pct = overall_metrics['medium_attempt_pct']
    time_priority = overall_metrics['time_priority_correct']
    unattempted_easy = overall_metrics['total_easy'] - overall_metrics['attempted_easy']
    
    # Find topics with most missed easy/medium questions across sections
    missed_easy_topics = []
    for section_analysis in section_analyses:
        if section_analysis and section_analysis.get('topics_with_missed_easy'):
            for topic, count in section_analysis['topics_with_missed_easy']:
                missed_easy_topics.append(f"{topic} ({section_analysis['short_name']})")
    
    # OVERALL ANALYSIS - Good Strategy (PRD compliant)
    if (easy_pct >= 85 and medium_pct >= 70 and time_priority):
        if missed_easy_topics:
            topics_str = ", ".join(missed_easy_topics[:2])  # Show top 2
            description = f"good: your overall question selection was effective, prioritizing easier questions. however, {unattempted_easy} easy/medium questions in {topics_str} were missed. refine scanning to catch all low-hanging fruit."
        else:
            description = f"good: your overall question selection was excellent, prioritizing easier questions with {easy_pct:.0f}% of easy questions and {medium_pct:.0f}% of medium questions attempted."
        
        swot['strengths'].append({
            'title': '🎯 Overall Question Selection Strategy',
            'description': description,
            'tags': ['strategy', 'time management', 'question selection']
        })
    
    # OVERALL ANALYSIS - Average Strategy (PRD compliant)
    elif (easy_pct >= 70 and medium_pct >= 50):
        swot['opportunities'].append({
            'title': '🧭 Overall Question Selection Strategy',
            'description': f"average: you attempted a reasonable mix of questions. focus on identifying and attempting all easy questions first, and be cautious about getting stuck on difficult ones too early.",
            'tags': ['strategy', 'question selection']
        })
    
    # OVERALL ANALYSIS - Needs Improvement (PRD compliant)
    elif (easy_pct < 70 or unattempted_easy >= 0.30 * overall_metrics['total_easy']):
        swot['weaknesses'].append({
            'title': '🎯 Overall Question Selection Strategy',
            'description': f"needs improvement: your strategy could be enhanced. {unattempted_easy} easy questions were left unattempted, while significant time may have been spent on harder ones. prioritize easy and medium questions across all topics first.",
            'tags': ['strategy', 'question selection', 'time management']
        })

def generate_section_swot_items(swot, section_metrics):
    """Generate SWOT items for individual sections"""
    if not section_metrics:
        return
        
    section_name = section_metrics['section_name']
    short_name = section_metrics['short_name']
    easy_pct = section_metrics['easy_attempt_pct']
    unattempted_easy = section_metrics['unattempted_easy']
    strong_topics = section_metrics['strong_topics']
    topics_with_missed_easy = section_metrics['topics_with_missed_easy']
    attempted_hard = section_metrics['attempted_hard']
    total_easy = section_metrics['total_easy']
    
    # SECTION-WISE Good Performance (PRD compliant)
    # Rule: IF (Percentage of Attempted Easy [Section] Questions / Total Easy [Section] Qs >= 0.80) 
    # AND (Percentage of Attempted [Section] Questions from [Student's Top 2 Strongest Topics] >= 0.75)
    if (easy_pct >= 80 and len(strong_topics) >= 2):
        topic_names = strong_topics[:2]
        swot['strengths'].append({
            'title': f'🎯 {short_name}',
            'description': f'good: your selection in {short_name.lower()} was efficient, focusing on easier questions and your strengths in {" and ".join(topic_names)}.',
            'tags': [short_name.lower(), 'strategy', 'topic mastery']
        })
    
    # SECTION-WISE Needs Improvement (PRD compliant)
    # Rule: IF (Number of Unattempted Easy [Section] Questions / Total Easy [Section] Qs >= 0.25) 
    # AND (Number of Attempted Hard [Section] Questions before attempting at least 75% of Easy [Section] Questions >= 1)
    elif (unattempted_easy >= 0.25 * total_easy and attempted_hard >= 1):
        swot['weaknesses'].append({
            'title': f'🎯 {short_name}',
            'description': f'needs improvement: in {short_name.lower()}, {unattempted_easy} easy questions were missed while time was invested in harder ones. ensure all easier questions are scanned and attempted first within this section.',
            'tags': [short_name.lower(), 'strategy', 'prioritization']
        })
    
    # ACTIONABLE TIPS (PRD compliant)
    # Triggered if "Good" but easy ones missed: "refine your initial scan..."
    if easy_pct >= 80 and topics_with_missed_easy and len(strong_topics) > 0:
        for topic, missed_count in topics_with_missed_easy[:1]:  # Focus on one topic
            if topic in strong_topics:
                swot['opportunities'].append({
                    'title': f'💡 {short_name}',
                    'description': f'refine your initial scan in {short_name.lower()} to ensure no easy questions, especially in {topic}, are overlooked.',
                    'tags': [short_name.lower(), topic.lower().replace(' ', '_'), 'scanning']
                })
                break
    
    # Triggered if "Needs Improvement": "practice a 'first pass'..."
    elif unattempted_easy >= 3:
        swot['opportunities'].append({
            'title': f'💡 {short_name}',
            'description': f'practice a "first pass" for {short_name.lower()}: quickly scan all questions, solve obvious easy ones, mark medium, and skip hard for later.',
            'tags': [short_name.lower(), 'first pass', 'strategy']
        })

def ensure_balanced_swot(swot):
    """Ensure each SWOT category has at least 1 item and max 3 items"""
    
    # Add fallback items if categories are empty
    if not swot['strengths']:
        swot['strengths'].append({
            'title': 'Test Completion Commitment',
            'description': 'You completed the mock test, demonstrating dedication to systematic CAT preparation.',
            'tags': ['commitment', 'practice']
        })
    
    if not swot['weaknesses']:
        swot['weaknesses'].append({
            'title': 'Strategic Awareness Development',
            'description': 'Building more awareness around question selection timing can enhance your test-taking efficiency.',
            'tags': ['strategy', 'awareness']
        })
    
    if not swot['opportunities']:
        swot['opportunities'].append({
            'title': 'Question Selection Mastery',
            'description': 'Developing a systematic first-pass strategy can significantly improve your score by ensuring easy wins.',
            'tags': ['strategy', 'systematic approach']
        })
    
    if not swot['threats']:
        swot['threats'].append({
            'title': 'Time Pressure Under Exam Conditions',
            'description': 'Real exam pressure might affect question selection decisions. Practice maintaining strategic discipline.',
            'tags': ['exam pressure', 'strategy maintenance']
        })
    
    # Limit to 3 items per category
    for category in swot:
        swot[category] = swot[category][:3]

def check_test_session_state(test_id):
    """Helper function to check test session state and prevent back navigation"""
    # Check if user wants to retake a test
    retake = request.args.get('retake', '').lower() == 'true'
    
    # First check if user has already taken this test (stored in database)
    if current_user.is_authenticated and not retake:
        existing_result = TestResult.get_user_test_result(current_user.id, test_id)
        if existing_result:
            # User has already taken this test, redirect to their results
            session.clear()  # Clear any existing session data
            session['results'] = existing_result.to_dict()
            session['test_submitted'] = True
            session['current_test_id'] = test_id
            flash(f'You have already taken this test on {existing_result.created_at.strftime("%B %d, %Y")}. Here are your results. <a href="?retake=true" class="alert-link">Click here to retake (your previous score will be replaced)</a>.', 'info')
            return redirect(url_for('results_page'))
    
    current_test_id = session.get('current_test_id')
    
    # If user is trying to access the same test they just submitted in this session, prevent it
    if ('test_submitted' in session and 
        'current_test_id' in session and 
        str(current_test_id) == str(test_id) and 
        not retake):
        flash('You have already submitted this test. Your results are available below.', 'warning')
        return redirect(url_for('results_page'))
    
    # If user is starting a new test or retake, clear previous session data
    session.clear()  # Clear all previous test data
    print(f"DEBUG: Starting {'retake' if retake else 'new'} full mock test {test_id} for user {current_user.id if current_user.is_authenticated else 'anonymous'}")
    
    # Mark new test as in progress
    session['test_in_progress'] = True
    session['current_test_id'] = test_id
    
    return None

def check_sectional_test_state(test_id):
    """Helper function to check sectional test state"""
    # Check if user wants to retake a test
    retake = request.args.get('retake', '').lower() == 'true'
    
    # First check if user has already taken this sectional test (stored in database)
    if current_user.is_authenticated and not retake:
        existing_result = TestResult.get_user_test_result(current_user.id, test_id)
        if existing_result:
            # User has already taken this test, redirect to their results
            session.clear()  # Clear any existing session data
            session['results'] = existing_result.to_dict()
            session['test_submitted'] = True
            session['current_test_id'] = test_id
            flash(f'You have already taken this sectional test on {existing_result.created_at.strftime("%B %d, %Y")}. Here are your results. <a href="?retake=true" class="alert-link">Click here to retake (your previous score will be replaced)</a>.', 'info')
            return redirect(url_for('results_page'))
    
    # Clear any previous session data for new test or retake
    session.clear()
    print(f"DEBUG: Starting {'retake' if retake else 'new'} sectional test {test_id} for user {current_user.id if current_user.is_authenticated else 'anonymous'}")
    session['test_in_progress'] = True
    session['current_test_id'] = test_id
    
    return None

def generate_fallback_swot_analysis(stats):
    """Fallback SWOT analysis for sectional tests or when detailed analysis fails"""
    # This is a simplified version for non-full mock tests
    sections = stats.get('sections', [])
    swot = {
        'strengths': [],
        'weaknesses': [],
        'opportunities': [],
        'threats': []
    }
    
    # Calculate overall metrics for fallback
    total_correct = sum(s['correct'] for s in sections) if sections else stats.get('correct', 0)
    total_wrong = sum(s['wrong'] for s in sections) if sections else stats.get('wrong', 0)
    total_attempted = total_correct + total_wrong
    overall_accuracy = (total_correct / total_attempted * 100) if total_attempted > 0 else 0
    
    # Basic analysis based on accuracy
    if overall_accuracy >= 75:
        swot['strengths'].append({
            'title': 'Strong Performance Accuracy',
            'description': f'Your accuracy of {overall_accuracy:.0f}% demonstrates solid conceptual understanding.',
            'tags': ['accuracy', 'concepts']
        })
    elif overall_accuracy < 50:
        swot['weaknesses'].append({
            'title': 'Accuracy Enhancement Required',
            'description': f'Accuracy of {overall_accuracy:.0f}% suggests need for more focused preparation.',
            'tags': ['accuracy', 'preparation']
        })
    
    # Add default items
    ensure_balanced_swot(swot)
    
    return swot

def generate_sectional_swot_analysis(stats):
    """Generate question selection strategy-based SWOT analysis for sectional tests"""
    test_id = stats.get('test_id')
    answer_data = stats.get('answer_data', {})
    question_times = stats.get('question_times', {})
    section_name = stats.get('section_name', 'this section')
    
    swot = {
        'strengths': [],
        'weaknesses': [],
        'opportunities': [],
        'threats': []
    }
    
    # Determine section configuration based on test_id
    section_conf_map = {
        'qa1': { 'name': "Quantitative Aptitude", 'csv': 'QA_16.csv', 'short_name': 'QA' },
        'qa2': { 'name': "Quantitative Aptitude", 'csv': 'QA_17.csv', 'short_name': 'QA' },
        'qa3': { 'name': "Quantitative Aptitude", 'csv': 'QA_18.csv', 'short_name': 'QA' },
        'qa4': { 'name': "Quantitative Aptitude", 'csv': 'QA_19.csv', 'short_name': 'QA' },
        'varc1': { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#16.csv', 'short_name': 'VARC' },
        'varc2': { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#17.csv', 'short_name': 'VARC' },
        'varc3': { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#18.csv', 'short_name': 'VARC' },
        'lrdi1': { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#16.csv', 'short_name': 'LRDI' },
        'lrdi2': { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#17.csv', 'short_name': 'LRDI' },
        'lrdi3': { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#18.csv', 'short_name': 'LRDI' }
    }
    
    if test_id not in section_conf_map:
        return generate_fallback_swot_analysis(stats)
    
    section_conf = section_conf_map[test_id]
    
    try:
        # Analyze the sectional question selection
        section_metrics = analyze_sectional_question_selection(section_conf, answer_data, question_times, stats)
        
        if not section_metrics:
            return generate_fallback_swot_analysis(stats)
        
        # Generate SWOT based on sectional analysis
        generate_sectional_strategy_swot_items(swot, section_metrics, stats)
        
        # Ensure balanced SWOT
        ensure_balanced_swot(swot)
        
        return swot
        
    except Exception as e:
        print(f"Error in sectional SWOT analysis: {e}")
        return generate_fallback_swot_analysis(stats)

def analyze_sectional_question_selection(section_conf, answer_data, question_times, stats):
    """Analyze question selection strategy for a sectional test"""
    try:
        path = app.static_folder + '/' + section_conf['csv']
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
        answers = answer_data.get('0', {})  # Sectional tests only have one section (index 0)
        times = question_times.get('0', {})
        
        section_name = section_conf['name']
        short_name = section_conf['short_name']
        
        easy_qs = []
        medium_qs = []
        hard_qs = []
        topic_performance = {}
        
        for q_idx, row in enumerate(rows):
            difficulty = row.get('DifficultyLevelPredicted', '').strip().lower()
            topic = row.get('Topic', 'Unknown Topic')
            subtopic = row.get('SubTopic', 'Unknown SubTopic')
            user_ans = answers.get(str(q_idx), {}).get('answer')
            correct_ans = row.get('CorrectAnswerValue')
            q_time = times.get(str(q_idx))
            
            # Track topic performance
            if topic not in topic_performance:
                topic_performance[topic] = {'total': 0, 'attempted': 0, 'correct': 0, 'easy_missed': 0}
            
            topic_performance[topic]['total'] += 1
            
            q_data = {
                'idx': q_idx,
                'topic': topic,
                'subtopic': subtopic,
                'attempted': user_ans is not None,
                'correct': str(user_ans) == str(correct_ans) if user_ans is not None else False,
                'time': q_time
            }
            
            if user_ans is not None:
                topic_performance[topic]['attempted'] += 1
                if str(user_ans) == str(correct_ans):
                    topic_performance[topic]['correct'] += 1
            
            # Categorize by difficulty
            if difficulty == 'easy':
                easy_qs.append(q_data)
                if user_ans is None:  # Easy question missed
                    topic_performance[topic]['easy_missed'] += 1
            elif difficulty == 'medium':
                medium_qs.append(q_data)
            elif 'hard' in difficulty:
                hard_qs.append(q_data)
        
        # Calculate metrics
        total_easy = len(easy_qs)
        attempted_easy = sum(1 for q in easy_qs if q['attempted'])
        total_medium = len(medium_qs)
        attempted_medium = sum(1 for q in medium_qs if q['attempted'])
        total_hard = len(hard_qs)
        attempted_hard = sum(1 for q in hard_qs if q['attempted'])
        
        easy_attempt_pct = (attempted_easy / total_easy * 100) if total_easy > 0 else 0
        medium_attempt_pct = (attempted_medium / total_medium * 100) if total_medium > 0 else 0
        
        # Find strongest topics (by accuracy among attempted questions)
        strong_topics = []
        for topic, perf in topic_performance.items():
            if perf['attempted'] >= 2:  # At least 2 questions attempted (lower threshold for sectional)
                accuracy = (perf['correct'] / perf['attempted'] * 100)
                if accuracy >= 70:  # Slightly lower threshold for sectional
                    strong_topics.append(topic)
        
        # Find topics with missed easy questions
        topics_with_missed_easy = []
        for topic, perf in topic_performance.items():
            if perf['easy_missed'] > 0:
                topics_with_missed_easy.append((topic, perf['easy_missed']))
        
        return {
            'section_name': section_name,
            'short_name': short_name,
            'total_easy': total_easy,
            'total_medium': total_medium,
            'total_hard': total_hard,
            'attempted_easy': attempted_easy,
            'attempted_medium': attempted_medium,
            'attempted_hard': attempted_hard,
            'easy_attempt_pct': easy_attempt_pct,
            'medium_attempt_pct': medium_attempt_pct,
            'unattempted_easy': total_easy - attempted_easy,
            'strong_topics': strong_topics,
            'topics_with_missed_easy': topics_with_missed_easy,
            'topic_performance': topic_performance
        }
        
    except FileNotFoundError:
        return None

def generate_sectional_strategy_swot_items(swot, section_metrics, stats):
    """Generate SWOT items based on sectional question selection strategy"""
    section_name = section_metrics['section_name']
    short_name = section_metrics['short_name']
    easy_pct = section_metrics['easy_attempt_pct']
    medium_pct = section_metrics['medium_attempt_pct']
    unattempted_easy = section_metrics['unattempted_easy']
    strong_topics = section_metrics['strong_topics']
    topics_with_missed_easy = section_metrics['topics_with_missed_easy']
    
    # Get overall performance metrics
    accuracy = stats.get('accuracy', 0)
    correct = stats.get('correct', 0)
    wrong = stats.get('wrong', 0)
    skipped = stats.get('skipped', 0)
    
    # SECTIONAL OVERALL ANALYSIS - Good Strategy
    if (easy_pct >= 85 and medium_pct >= 70):
        swot['strengths'].append({
            'title': f'🎯 Excellent {short_name} Question Selection',
            'description': f'Your strategy was outstanding - {easy_pct:.0f}% of easy questions and {medium_pct:.0f}% of medium questions attempted, showing smart prioritization.',
            'tags': [short_name.lower(), 'strategy', 'question selection']
        })
    
    # Good performance with strong topics
    elif (easy_pct >= 75 and len(strong_topics) >= 2):
        topic_names = strong_topics[:2]
        swot['strengths'].append({
            'title': f'🎯 Strategic {short_name} Topic Selection',
            'description': f'Effective focus on easier questions and strong performance in {" and ".join(topic_names)}.',
            'tags': [short_name.lower(), 'strategy', 'topic mastery']
        })
    
    # SECTIONAL OVERALL ANALYSIS - Average Strategy  
    elif (easy_pct >= 70 and medium_pct >= 50):
        swot['opportunities'].append({
            'title': f'🧭 {short_name} Strategy Refinement',
            'description': f'Reasonable selection pattern ({easy_pct:.0f}% easy, {medium_pct:.0f}% medium). Focus on catching all easy questions first in {short_name}.',
            'tags': [short_name.lower(), 'strategy', 'refinement']
        })
    
    # SECTIONAL OVERALL ANALYSIS - Needs Improvement
    elif (easy_pct < 70 or unattempted_easy >= 0.25 * section_metrics['total_easy']):
        swot['weaknesses'].append({
            'title': f'🎯 {short_name} Selection Strategy Enhancement Needed',
            'description': f'Strategy needs improvement - {unattempted_easy} easy questions left unattempted. Prioritize scanning all easy questions first.',
            'tags': [short_name.lower(), 'strategy', 'prioritization']
        })
    
    # ACTIONABLE TIPS - based on missed easy questions in strong topics
    if topics_with_missed_easy and len(strong_topics) > 0:
        for topic, missed_count in topics_with_missed_easy[:1]:  # Focus on one topic
            if topic in strong_topics:
                swot['opportunities'].append({
                    'title': f'💡 Refine {short_name} Scanning in {topic}',
                    'description': f'Despite strength in {topic}, {missed_count} easy questions were missed. Improve initial scanning to catch all easy wins.',
                    'tags': [short_name.lower(), topic.lower().replace(' ', '_'), 'scanning']
                })
                break
    
    # ACTIONABLE TIPS - General improvement for sections needing work
    elif unattempted_easy >= 3:
        swot['opportunities'].append({
            'title': f'💡 Implement {short_name} Two-Pass Strategy',
            'description': f'Practice a systematic approach: First pass for all easy questions, second pass for medium, then hard questions if time permits.',
            'tags': [short_name.lower(), 'two pass', 'systematic']
        })
    
    # Performance-based insights
    if accuracy >= 80 and easy_pct >= 75:
        swot['strengths'].append({
            'title': f'🎯 High {short_name} Accuracy with Good Strategy',
            'description': f'Excellent {accuracy}% accuracy combined with smart question selection shows strong {short_name} preparation.',
            'tags': [short_name.lower(), 'accuracy', 'preparation']
        })
    
    # Time management insights for sectional
    total_questions = correct + wrong + skipped
    attempt_rate = ((correct + wrong) / total_questions * 100) if total_questions > 0 else 0
    
    if attempt_rate < 60:
        swot['threats'].append({
            'title': f'⚠️ {short_name} Time Management Pressure',
            'description': f'Only {attempt_rate:.0f}% questions attempted suggests time pressure. Practice pacing and quick question scanning.',
            'tags': [short_name.lower(), 'time management', 'pacing']
        })
    elif attempt_rate >= 85 and accuracy >= 70:
        swot['strengths'].append({
            'title': f'🎯 Excellent {short_name} Time Management',
            'description': f'High attempt rate ({attempt_rate:.0f}%) with good accuracy shows effective time management in {short_name}.',
            'tags': [short_name.lower(), 'time management', 'efficiency']
        })

def reconstruct_detailed_sections(stats):
    """Reconstruct detailed sections with questions from stored answer data"""
    if 'detailed_sections' in stats:
        return stats['detailed_sections']  # Already reconstructed
    
    test_id = stats.get('test_id')
    
    if not test_id or test_id in ['qa1', 'qa2', 'qa3', 'qa4', 'varc1', 'varc2', 'varc3', 'lrdi1', 'lrdi2', 'lrdi3']:
        return []  # Not a full mock test
    
    answer_data = stats.get('answer_data', {})
    question_times = stats.get('question_times', {})
    
    sections_conf = get_sections_conf_for_test(test_id)
    
    detailed_sections = []
    
    for sec_idx, sec_conf in enumerate(sections_conf):
        path = app.static_folder + '/' + sec_conf['csv']
        
        try:
            rows = list(csv.DictReader(open(path, encoding='utf-8')))
        except FileNotFoundError as e:
            continue
        except Exception as e:
            continue
        
        answers = answer_data.get(str(sec_idx), {})
        detailed_questions = []
        current_section_q_times = question_times.get(str(sec_idx), {})
        
        for q_idx, row in enumerate(rows):
            user_ans = answers.get(str(q_idx), {}).get('answer')
            actual = row.get('CorrectAnswerValue')
            time_spent = current_section_q_times.get(str(q_idx))
            
            if user_ans is None:
                status = 'skipped'
                combined = 'status-skipped'
            else:
                # Handle both MCQ and TITA type questions
                question_type = row.get('QuestionType', 'MCQ')
                is_correct = False
                
                if question_type == 'TITA':
                    # For TITA questions, compare numerical values with tolerance
                    try:
                        user_val = float(user_ans)
                        correct_val = float(actual)
                        # Allow small tolerance for floating point comparison
                        tolerance = 0.001
                        is_correct = abs(user_val - correct_val) <= tolerance
                    except (ValueError, TypeError):
                        is_correct = False
                else:
                    # For MCQ questions, exact string match
                    is_correct = str(user_ans) == str(actual)
                
                if is_correct:
                    status = 'correct'
                    if time_spent and time_spent <= sec_conf.get('optimal_time_correct', 90):
                        combined = 'status-optimal-correct'
                    else:
                        combined = 'status-longer-correct'
                else:
                    status = 'incorrect'
                    if time_spent and time_spent <= sec_conf.get('quick_time_incorrect', 60):
                        combined = 'status-quick-incorrect'
                    else:
                        combined = 'status-long-incorrect'
            
            # Add options to the question
            question_options = []
            for letter in ['A', 'B', 'C', 'D', 'E']:
                option_text = row.get(f'Option{letter}Text', '')
                option_value = row.get(f'Option{letter}Value', letter)
                if option_text:
                    question_options.append({
                        'text': option_text,
                        'value': option_value
                    })
            
            detailed_questions.append({
                'number': q_idx+1,
                'status': status,
                'combined_status_class': combined,
                'corner_icon_char': '✓' if status == 'correct' else ('✗' if status=='incorrect' else '–'),
                'time_spent_on_question_formatted': format_seconds_to_str(time_spent),
                'prompt': row.get('QuestionPrompt', ''),
                'passage_content': row.get('PassageOrSetContent', ''),
                'options': question_options,
                'correct_answer': actual,
                'user_answer': user_ans,
                'solution': row.get('SolutionExplanation', ''),
                'question_type': row.get('QuestionType', 'MCQ')
            })
        
        detailed_sections.append({
            'name': sec_conf['name'],
            'questions': detailed_questions
        })
    
    return detailed_sections

def reconstruct_sectional_questions(stats):
    """Reconstruct detailed questions for sectional tests from stored answer data"""
    if 'detailed_questions' in stats:
        return stats['detailed_questions']  # Already reconstructed
    
    test_id = stats.get('test_id')
    if not test_id or test_id not in ['qa1', 'qa2', 'qa3', 'qa4', 'varc1', 'varc2', 'varc3', 'lrdi1', 'lrdi2', 'lrdi3']:
        return []  # Not a sectional test
    
    answer_data = stats.get('answer_data', {})
    question_times = stats.get('question_times', {})
    
    # Determine section configuration based on test_id - MUST match process_sectional_data mapping
    if test_id == 'qa1':
        section_conf = {
            'name': "Quantitative Aptitude",
            'csv': 'QA_16.csv',
            'optimal_time_correct': 75,
            'quick_time_incorrect': 50
        }
    elif test_id == 'qa2':
        section_conf = {
            'name': "Quantitative Aptitude",
            'csv': 'QA_17.csv',
            'optimal_time_correct': 75,
            'quick_time_incorrect': 50
        }
    elif test_id == 'qa3':
        section_conf = {
            'name': "Quantitative Aptitude",
            'csv': 'QA_18.csv',
            'optimal_time_correct': 75,
            'quick_time_incorrect': 50
        }
    elif test_id == 'qa4':
        section_conf = {
            'name': "Quantitative Aptitude",
            'csv': 'QA_19.csv',
            'optimal_time_correct': 75,
            'quick_time_incorrect': 50
        }
    elif test_id == 'varc1':
        section_conf = {
            'name': "Verbal Ability and Reading Comprehension",
            'csv': 'VARC_#16.csv',
            'optimal_time_correct': 60,
            'quick_time_incorrect': 40
        }
    elif test_id == 'varc2':
        section_conf = {
            'name': "Verbal Ability and Reading Comprehension",
            'csv': 'VARC_#17.csv',
            'optimal_time_correct': 60,
            'quick_time_incorrect': 40
        }
    elif test_id == 'varc3':
        section_conf = {
            'name': "Verbal Ability and Reading Comprehension",
            'csv': 'VARC_#18.csv',
            'optimal_time_correct': 60,
            'quick_time_incorrect': 40
        }
    elif test_id == 'lrdi1':
        section_conf = {
            'name': "Data Interpretation & Logical Reasoning",
            'csv': 'LRDI_#16.csv',
            'optimal_time_correct': 90,
            'quick_time_incorrect': 60
        }
    elif test_id == 'lrdi2':
        section_conf = {
            'name': "Data Interpretation & Logical Reasoning",
            'csv': 'LRDI_#17.csv',
            'optimal_time_correct': 90,
            'quick_time_incorrect': 60
        }
    elif test_id == 'lrdi3':
        section_conf = {
            'name': "Data Interpretation & Logical Reasoning",
            'csv': 'LRDI_#18.csv',
            'optimal_time_correct': 90,
            'quick_time_incorrect': 60
        }
    else:
        return []
    
    # Load questions from CSV
    path = app.static_folder + '/' + section_conf['csv']
    try:
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
    except FileNotFoundError:
        return []
    
    # Process answers and calculate stats
    answers = answer_data.get('0', {})  # Sectional tests only have one section (index 0)
    detailed_questions = []
    current_section_q_times = question_times.get('0', {})
    
    for q_idx, row in enumerate(rows):
        user_ans = answers.get(str(q_idx), {}).get('answer')
        actual = row.get('CorrectAnswerValue')
        time_spent = current_section_q_times.get(str(q_idx))
        
        if user_ans is None:
            status = 'skipped'
            combined = 'status-skipped'
        else:
            # Handle both MCQ and TITA type questions
            question_type = row.get('QuestionType', 'MCQ')
            is_correct = False
            
            if question_type == 'TITA':
                # For TITA questions, compare numerical values with tolerance
                try:
                    user_val = float(user_ans)
                    correct_val = float(actual)
                    # Allow small tolerance for floating point comparison
                    tolerance = 0.001
                    is_correct = abs(user_val - correct_val) <= tolerance
                except (ValueError, TypeError):
                    is_correct = False
            else:
                # For MCQ questions, exact string match
                is_correct = str(user_ans) == str(actual)
            
            if is_correct:
                status = 'correct'
                if time_spent and time_spent <= section_conf['optimal_time_correct']:
                    combined = 'status-optimal-correct'
                else:
                    combined = 'status-longer-correct'
            else:
                status = 'incorrect'
                if time_spent and time_spent <= section_conf['quick_time_incorrect']:
                    combined = 'status-quick-incorrect'
                else:
                    combined = 'status-long-incorrect'
        
        # Add options to the question
        question_options = []
        for letter in ['A', 'B', 'C', 'D', 'E']:
            option_text = row.get(f'Option{letter}Text', '')
            option_value = row.get(f'Option{letter}Value', letter)
            if option_text:
                question_options.append({
                    'text': option_text,
                    'value': option_value
                })
        
        detailed_questions.append({
            'number': q_idx + 1,
            'status': status,
            'combined_status_class': combined,
            'time_spent_on_question_formatted': format_seconds_to_str(time_spent),
            'prompt': row.get('QuestionPrompt', ''),
            'passage_content': row.get('PassageOrSetContent', ''),
            'options': question_options,
            'correct_answer': actual,
            'user_answer': user_ans,
            'solution': row.get('SolutionExplanation', ''),
            'question_type': row.get('QuestionType', 'MCQ')
        })
    
    return detailed_questions

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/work-in-progress')
def work_in_progress():
    return render_template('work_in_progress.html')

@app.route('/mock-tests')
@login_required
def mock_tests_page():
    print(f"DEBUG: mock_tests_page accessed")
    print(f"DEBUG: current_user.is_authenticated = {current_user.is_authenticated}")
    print(f"DEBUG: current_user = {current_user}")
    if hasattr(current_user, 'id'):
        print(f"DEBUG: current_user.id = {current_user.id}")
    
    # Show helpful message if user has completed a test
    if 'test_submitted' in session:
        flash('Test completed! You can view your results or start a new test.', 'info')
    
    return render_template('mock_tests.html')

@app.route('/take-test')
@login_required
def take_test_page():
    test_id = 1
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/1')
@login_required
def mock_test_1():
    test_id = 1
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/2')
@login_required
def mock_test_2():
    test_id = 2
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/3')
@login_required
def mock_test_3():
    test_id = 3
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/4')
@login_required
def mock_test_4():
    test_id = 4
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/5')
@login_required
def mock_test_5():
    test_id = 5
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/6')
@login_required
def mock_test_6():
    test_id = 6
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/7')
@login_required
def mock_test_7():
    test_id = 7
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/8')
@login_required
def mock_test_8():
    test_id = 8
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/9')
@login_required
def mock_test_9():
    test_id = 9
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/10')
@login_required
def mock_test_10():
    test_id = 10
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/11')
@login_required
def mock_test_11():
    test_id = 11
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/12')
@login_required
def mock_test_12():
    test_id = 12
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/13')
@login_required
def mock_test_13():
    test_id = 13
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/14')
@login_required
def mock_test_14():
    test_id = 14
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/mock-test/15')
@login_required
def mock_test_15():
    test_id = 15
    redirect_response = check_test_session_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/1')
@login_required
def qa_sectional_1():
    test_id = 'qa1'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/2')
@login_required
def qa_sectional_2():
    test_id = 'qa2'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/3')
@login_required
def qa_sectional_3():
    test_id = 'qa3'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/4')
@login_required
def qa_sectional_4():
    test_id = 'qa4'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/1')
@login_required
def varc_sectional_1():
    test_id = 'varc1'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/2')
@login_required
def varc_sectional_2():
    test_id = 'varc2'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/3')
@login_required
def varc_sectional_3():
    test_id = 'varc3'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/1')
@login_required
def lrdi_sectional_1():
    test_id = 'lrdi1'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/2')
@login_required
def lrdi_sectional_2():
    test_id = 'lrdi2'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/3')
@login_required
def lrdi_sectional_3():
    test_id = 'lrdi3'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/4')
@login_required
def lrdi_sectional_4():
    test_id = 'lrdi4'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/5')
@login_required
def lrdi_sectional_5():
    test_id = 'lrdi5'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/6')
@login_required
def lrdi_sectional_6():
    test_id = 'lrdi6'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/7')
@login_required
def lrdi_sectional_7():
    test_id = 'lrdi7'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/8')
@login_required
def lrdi_sectional_8():
    test_id = 'lrdi8'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/9')
@login_required
def lrdi_sectional_9():
    test_id = 'lrdi9'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/lrdi/10')
@login_required
def lrdi_sectional_10():
    test_id = 'lrdi10'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/5')
@login_required
def qa_sectional_5():
    test_id = 'qa5'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/6')
@login_required
def qa_sectional_6():
    test_id = 'qa6'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/7')
@login_required
def qa_sectional_7():
    test_id = 'qa7'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/8')
@login_required
def qa_sectional_8():
    test_id = 'qa8'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/9')
@login_required
def qa_sectional_9():
    test_id = 'qa9'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/qa/10')
@login_required
def qa_sectional_10():
    test_id = 'qa10'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/4')
@login_required
def varc_sectional_4():
    test_id = 'varc4'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/5')
@login_required
def varc_sectional_5():
    test_id = 'varc5'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/6')
@login_required
def varc_sectional_6():
    test_id = 'varc6'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/7')
@login_required
def varc_sectional_7():
    test_id = 'varc7'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/8')
@login_required
def varc_sectional_8():
    test_id = 'varc8'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/9')
@login_required
def varc_sectional_9():
    test_id = 'varc9'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/sectional/varc/10')
@login_required
def varc_sectional_10():
    test_id = 'varc10'
    redirect_response = check_sectional_test_state(test_id)
    if redirect_response:
        return redirect_response
    return render_template('take_test.html', test_id=test_id)

@app.route('/submit-test', methods=['POST'])
@login_required
def submit_test():
    data = request.get_json() or {}
    test_id = data.get('test_id')
    
    # DEBUG: Print what we're receiving
    print("=" * 60)
    print("DEBUG: Submit test data:")
    print(f"test_id received: '{test_id}' (type: {type(test_id)})")
    print(f"test_id in sectional list: {test_id in ['qa1', 'varc1', 'lrdi1']}")
    print(f"Full data keys: {list(data.keys())}")
    print("=" * 60)
    
    if test_id in ['qa1', 'qa2', 'qa3', 'qa4', 'qa5', 'qa6', 'qa7', 'qa8', 'qa9', 'qa10', 
                   'varc1', 'varc2', 'varc3', 'varc4', 'varc5', 'varc6', 'varc7', 'varc8', 'varc9', 'varc10',
                   'lrdi1', 'lrdi2', 'lrdi3', 'lrdi4', 'lrdi5', 'lrdi6', 'lrdi7', 'lrdi8', 'lrdi9', 'lrdi10']:  # Sectional tests
        print("DEBUG: Taking SECTIONAL path")
        # CLEAR session completely before processing sectional test
        session.clear()
        section_stats = process_sectional_data(data)
        session['results'] = section_stats
        
        # Mark test as submitted to prevent back navigation
        session['test_submitted'] = True
        session['current_test_id'] = test_id
        session.pop('test_in_progress', None)
        
        print(f"DEBUG: Set sectional session data with test_name: '{section_stats.get('test_name')}'")
        
        # Save test result to database
        if current_user.is_authenticated:
            try:
                # Use safer create_or_update method for retakes
                test_result, is_update = TestResult.create_or_update_test_result(current_user.id, test_id, section_stats)
                
                if not is_update:
                    db.session.add(test_result)
                
                db.session.commit()
                
                # Set appropriate message for retake
                if is_update:
                    session['retake_success'] = True
                    
                print(f"DEBUG: Successfully {'updated' if is_update else 'created'} sectional test result for user {current_user.id}, test {test_id}")
            except Exception as e:
                print(f"ERROR: Failed to save sectional test result: {str(e)}")
                print(f"ERROR: Exception details: {type(e).__name__}: {e}")
                db.session.rollback()
                # Continue anyway - user still sees their current session results
        
        return ('', 204)
    else:  # Full mock tests
        print("DEBUG: Taking FULL MOCK path")
        # CLEAR session completely before processing full mock test
        session.clear()
        
        # 1) Unpack
        answer_data = data.get('answers', {})
        section_times = data.get('times', [])
        question_times = data.get('question_times', {})

        # 2) Your section configs
        sections_conf = get_sections_conf_for_test(test_id)

        processed_section_stats = []
        total_questions = 0

        # 3) Build each section's stats
        for sec_idx, sec_conf in enumerate(sections_conf):
            path = app.static_folder + '/' + sec_conf['csv']
            try:
                rows = list(csv.DictReader(open(path, encoding='utf-8')))
            except FileNotFoundError:
                continue

            answers = answer_data.get(str(sec_idx), {})
            correct = wrong = skipped = 0
            detailed = []
            current_section_q_times = question_times.get(str(sec_idx), {})
            
            for q_idx, row in enumerate(rows):
                total_questions += 1
                user_ans = answers.get(str(q_idx), {}).get('answer')
                actual = row.get('CorrectAnswerValue')
                
                # Get time spent on this question
                time_spent = current_section_q_times.get(str(q_idx))
                
                if user_ans is None:
                    skipped += 1
                    status = 'skipped'
                    combined = 'status-skipped'
                else:
                    # Handle both MCQ and TITA type questions
                    question_type = row.get('QuestionType', 'MCQ')
                    is_correct = False
                    
                    if question_type == 'TITA':
                        # For TITA questions, compare numerical values with tolerance
                        try:
                            user_val = float(user_ans)
                            correct_val = float(actual)
                            # Allow small tolerance for floating point comparison
                            tolerance = 0.001
                            is_correct = abs(user_val - correct_val) <= tolerance
                        except (ValueError, TypeError):
                            is_correct = False
                    else:
                        # For MCQ questions, exact string match
                        is_correct = str(user_ans) == str(actual)
                    
                    if is_correct:
                        correct += 1
                        status = 'correct'
                        # Determine if time was optimal based on section config
                        if time_spent and time_spent <= sec_conf.get('optimal_time_correct', 90):
                            combined = 'status-optimal-correct'
                        else:
                            combined = 'status-longer-correct'
                    else:
                        wrong += 1
                        status = 'incorrect'
                        # Determine if time was quick based on section config
                        if time_spent and time_spent <= sec_conf.get('quick_time_incorrect', 60):
                            combined = 'status-quick-incorrect'
                        else:
                            combined = 'status-long-incorrect'
                    
                detailed.append({
                    'number': q_idx+1,
                    'status': status,
                    'combined_status_class': combined,
                    'corner_icon_char': '✓' if status == 'correct' else ('✗' if status=='incorrect' else '–'),
                    'time_spent_on_question_formatted': format_seconds_to_str(time_spent),
                    'prompt': row.get('QuestionPrompt', ''),
                    'passage_content': row.get('PassageOrSetContent', ''),
                    'options': [],
                    'correct_answer': actual,
                    'user_answer': user_ans,
                    'solution': row.get('SolutionExplanation', ''),
                    'question_type': row.get('QuestionType', 'MCQ')
                })

                # Add options to the question
                question_options = []
                for letter in ['A', 'B', 'C', 'D', 'E']:
                    option_text = row.get(f'Option{letter}Text', '')
                    option_value = row.get(f'Option{letter}Value', letter)
                    if option_text:
                        question_options.append({
                            'text': option_text,
                            'value': option_value
                        })
                detailed[-1]['options'] = question_options

            # Calculate score with different rules for MCQ vs TITA
            mcq_correct = mcq_wrong = tita_correct = tita_wrong = 0
            
            for q_idx, row in enumerate(rows):
                user_ans = answers.get(str(q_idx), {}).get('answer')
                actual = row.get('CorrectAnswerValue')
                question_type = row.get('QuestionType', 'MCQ')
                
                if user_ans is not None:
                    # Handle both MCQ and TITA type questions
                    is_correct = False
                    
                    if question_type == 'TITA':
                        # For TITA questions, compare numerical values with tolerance
                        try:
                            user_val = float(user_ans)
                            correct_val = float(actual)
                            # Allow small tolerance for floating point comparison
                            tolerance = 0.001
                            is_correct = abs(user_val - correct_val) <= tolerance
                        except (ValueError, TypeError):
                            is_correct = False
                    else:
                        # For MCQ questions, exact string match
                        is_correct = str(user_ans) == str(actual)
                    
                    if question_type == 'TITA':
                        if is_correct:
                            tita_correct += 1
                        else:
                            tita_wrong += 1
                    else:  # MCQ
                        if is_correct:
                            mcq_correct += 1
                        else:
                            mcq_wrong += 1
            
            # Calculate score: MCQ has negative marking, TITA doesn't
            score = (mcq_correct * 3) - (mcq_wrong * 1) + (tita_correct * 3)

            secs_spent = None
            if sec_idx < len(section_times) and isinstance(section_times[sec_idx], (int, float)):
                secs_spent = section_times[sec_idx]
            section_time_str = format_seconds_to_str(secs_spent)

            processed_section_stats.append({
                'name':      sec_conf['name'],
                'score':     score,
                'correct':   correct,
                'wrong':     wrong,
                'skipped':   skipped,
                'time_spent':section_time_str,
                'questions': detailed
            })

        # 4) Overall totals
        total_score = sum(s['score'] for s in processed_section_stats)
        total_possible = total_questions * 3
        total_secs = sum(t for t in section_times if isinstance(t, (int,float)))
        total_time_str = format_seconds_to_str(total_secs)

        # Generate insights based on performance data
        temp_stats = {
            'test_id': test_id,  # Add test_id for proper analysis
            'answer_data': answer_data,  # Add answer data for detailed analysis
            'question_times': question_times,  # Add question times for strategy analysis
            'sections': [
                {
                    'name': sec['name'],
                    'score': sec['score'],
                    'correct': sec['correct'],
                    'wrong': sec['wrong'],
                    'skipped': sec['skipped'],
                    'time_spent': sec['time_spent']
                } for sec in processed_section_stats
            ]
        }
        
        # Generate dynamic missed opportunities, time wasters, and SWOT analysis
        missed_ops = generate_missed_opportunities(temp_stats, is_sectional=False)
        time_wasters = generate_time_wasters(temp_stats, is_sectional=False)
        swot_analysis = generate_swot_analysis(temp_stats)

        # 6) Save into session - STORE ONLY ESSENTIAL DATA (not detailed questions)
        session['results'] = {
          'test_name': 'Full Mock Test',
          'test_id': test_id,  # Store test_id to reconstruct data later
          'total_score': total_score,
          'total_possible': total_possible,
          'time_spent': total_time_str,
          'sections': [
              {
                  'name': sec['name'],
                  'score': sec['score'],
                  'correct': sec['correct'],
                  'wrong': sec['wrong'],
                  'skipped': sec['skipped'],
                  'time_spent': sec['time_spent']
              } for sec in processed_section_stats
          ],
          'missed_opportunities': missed_ops,
          'time_wasters': time_wasters,
          'swot_analysis': swot_analysis,
          # Store answer data to reconstruct detailed questions when needed
          'answer_data': answer_data,
          'question_times': question_times,
          'section_times': section_times
        }
        
        # Mark test as submitted to prevent back navigation
        session['test_submitted'] = True
        session['current_test_id'] = test_id
        session.pop('test_in_progress', None)

        print(f"DEBUG: Set full mock session data with test_name: '{session['results'].get('test_name')}'")
        print(f"DEBUG: Session sections count: {len(session['results'].get('sections', []))}")
        print(f"DEBUG: Session data keys: {list(session['results'].keys())}")

        # Save test result to database
        if current_user.is_authenticated:
            try:
                # Use safer create_or_update method for retakes
                test_result, is_update = TestResult.create_or_update_test_result(current_user.id, test_id, session['results'])
                
                if not is_update:
                    db.session.add(test_result)
                
                db.session.commit()
                
                # Set appropriate message for retake
                if is_update:
                    session['retake_success'] = True
                    
                print(f"DEBUG: Successfully {'updated' if is_update else 'created'} full mock test result for user {current_user.id}, test {test_id}")
            except Exception as e:
                print(f"ERROR: Failed to save full mock test result: {str(e)}")
                print(f"ERROR: Exception details: {type(e).__name__}: {e}")
                db.session.rollback()
                # Continue anyway - user still sees their current session results

        return ('', 204)

@app.route('/results')
@login_required
def results_page():
    stats = session.get('results')
    if not stats:
        return redirect(url_for('mock_tests_page'))
    
    # Check if user has actually submitted a test (prevent direct URL access)
    if 'test_submitted' not in session:
        flash('Please complete a test to view results.', 'warning')
        return redirect(url_for('mock_tests_page'))
    
    # Show retake success message if applicable
    if session.pop('retake_success', False):
        flash('Test retaken successfully! Your previous score has been replaced with this new result.', 'success')
    

    
    try:
        # Determine test type based on test_name field (same logic as review_answers)
        test_name = stats.get('test_name', '')
        is_sectional = test_name.startswith('Sectional Mock')
        
        print(f"DEBUG: test_name = '{test_name}'")
        print(f"DEBUG: is_sectional = {is_sectional}")
        
        if is_sectional:  # Sectional test
            print("DEBUG: Rendering sectional_results.html")
            # Ensure all required fields are present for sectional results
            if 'accuracy' not in stats:
                total_attempted = stats.get('correct', 0) + stats.get('wrong', 0)
                stats['accuracy'] = round((stats.get('correct', 0) / total_attempted * 100) if total_attempted > 0 else 0)
            
            if 'avg_time_per_question' not in stats:
                stats['avg_time_per_question'] = '1m 30s'  # Default value
            
            if 'topic_analysis' not in stats:
                stats['topic_analysis'] = []
            
            if 'improvement_areas' not in stats:
                stats['improvement_areas'] = []
            
            if 'time_analysis' not in stats:
                stats['time_analysis'] = {
                    'optimal_count': 0,
                    'longer_count': 0,
                    'avg_time_correct': '1m 30s',
                    'avg_time_incorrect': '2m 00s'
                }
            
            return render_template('sectional_results.html', stats=stats)
        else:  # Full mock test
            print("DEBUG: Rendering results.html")
            # Ensure all required fields are present for full mock tests
            if not test_name or test_name.startswith('Sectional Mock'):
                stats['test_name'] = 'Full Mock Test'
            
            # Remove any conflicting section_name field for full mock tests
            if 'section_name' in stats:
                del stats['section_name']
                print("DEBUG: Removed section_name from stats")
            
            return render_template('results.html', stats=stats)
    except Exception as e:
        print(f"ERROR in results_page: {str(e)}")
        print(f"Stats structure: {stats}")
        # Return a simple error page or redirect
        return f"Error loading results: {str(e)}", 500

@app.route('/clear-session')
@login_required
def clear_session():
    session.clear()
    flash('Session cleared. You can now start a new test.', 'success')
    return redirect(url_for('mock_tests_page'))

@app.route('/test-history')
@login_required
def test_history():
    """Show user's test history"""
    user_results = TestResult.query.filter_by(user_id=current_user.id).order_by(TestResult.created_at.desc()).all()
    
    # Group results by test type
    full_mock_results = [result for result in user_results if result.test_type == 'full_mock']
    sectional_results = [result for result in user_results if result.test_type == 'sectional']
    
    return render_template('test_history.html', 
                         full_mock_results=full_mock_results,
                         sectional_results=sectional_results)

@app.route('/view-result/<int:result_id>')
@login_required
def view_result(result_id):
    """View a specific test result by ID"""
    test_result = TestResult.query.filter_by(id=result_id, user_id=current_user.id).first()
    
    if not test_result:
        flash('Test result not found or access denied.', 'error')
        return redirect(url_for('test_history'))
    
    # Clear any existing session data to prevent conflicts
    session.clear()
    
    # Load fresh result data into session for viewing
    print(f"DEBUG: Loading test result ID {result_id} for user {current_user.id}")
    session['results'] = test_result.to_dict()
    session['test_submitted'] = True
    session['current_test_id'] = test_result.test_id
    
    return redirect(url_for('results_page'))

@app.route('/review-answers')
@login_required
def review_answers():
    stats = session.get('results')
    if not stats:
        return redirect(url_for('mock_tests_page'))
    
    # Check if user has actually submitted a test (prevent direct URL access)
    if 'test_submitted' not in session:
        flash('Please complete a test to view answers.', 'warning')
        return redirect(url_for('mock_tests_page'))
    
    try:
        # Determine test type based on test_name field (more reliable than section_name)
        test_name = stats.get('test_name', '')
        is_sectional = test_name.startswith('Sectional Mock')
        
        # Ensure required data is present
        if is_sectional:
            # Sectional test - ensure detailed_questions exists
            if 'detailed_questions' not in stats:
                stats['detailed_questions'] = reconstruct_sectional_questions(stats)
        else:
            # Full mock test - ensure detailed_sections exists and no conflicting section_name
            if 'detailed_sections' not in stats:
                # Reconstruct detailed_sections from stored answer data
                stats['detailed_sections'] = reconstruct_detailed_sections(stats)
            
            # Ensure proper test_name for full mock tests
            if not test_name or test_name.startswith('Sectional Mock'):
                stats['test_name'] = 'Full Mock Test'
                is_sectional = False
            
            # Remove any conflicting section_name field for full mock tests
            if 'section_name' in stats:
                del stats['section_name']
        
        return render_template('answer_review.html', stats=stats, is_sectional=is_sectional)
    except Exception as e:
        print(f"ERROR in review_answers: {str(e)}")
        print(f"Stats structure: {stats}")
        return f"Error loading answer review: {str(e)}", 500

def process_sectional_data(data):
    # Extract data from request
    answer_data = data.get('answers', {})
    section_times = data.get('times', [])
    question_times = data.get('question_times', {})
    test_id = data.get('test_id')

    # Determine section configuration based on test_id
    section_conf_map = {
        'qa1': {
            'name': "Quantitative Aptitude",
            'csv': 'QA_16.csv',
            'optimal_time_correct': 75,
            'quick_time_incorrect': 50
        },
        'qa2': {
            'name': "Quantitative Aptitude",
            'csv': 'QA_17.csv',
            'optimal_time_correct': 75,
            'quick_time_incorrect': 50
        },
        'qa3': {
            'name': "Quantitative Aptitude",
            'csv': 'QA_18.csv',
            'optimal_time_correct': 75,
            'quick_time_incorrect': 50
        },
        'qa4': {
            'name': "Quantitative Aptitude",
            'csv': 'QA_19.csv',
            'optimal_time_correct': 75,
            'quick_time_incorrect': 50
        },
        'varc1': {
            'name': "Verbal Ability and Reading Comprehension",
            'csv': 'VARC_#16.csv',
            'optimal_time_correct': 60,
            'quick_time_incorrect': 40
        },
        'varc2': {
            'name': "Verbal Ability and Reading Comprehension",
            'csv': 'VARC_#17.csv',
            'optimal_time_correct': 60,
            'quick_time_incorrect': 40
        },
        'varc3': {
            'name': "Verbal Ability and Reading Comprehension",
            'csv': 'VARC_#18.csv',
            'optimal_time_correct': 60,
            'quick_time_incorrect': 40
        },
        'lrdi1': {
            'name': "Data Interpretation & Logical Reasoning",
            'csv': 'LRDI_#16.csv',
            'optimal_time_correct': 90,
            'quick_time_incorrect': 60
        },
        'lrdi2': {
            'name': "Data Interpretation & Logical Reasoning",
            'csv': 'LRDI_#17.csv',
            'optimal_time_correct': 90,
            'quick_time_incorrect': 60
        },
        'lrdi3': {
            'name': "Data Interpretation & Logical Reasoning",
            'csv': 'LRDI_#18.csv',
            'optimal_time_correct': 90,
            'quick_time_incorrect': 60
        }
    }
    
    section_conf = section_conf_map.get(test_id)
    if not section_conf:
        return {'error': 'Invalid test ID'}

    # Load questions from CSV
    path = app.static_folder + '/' + section_conf['csv']
    try:
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
    except FileNotFoundError:
        return {'error': 'Question set not found'}

    # Process answers and calculate stats
    answers = answer_data.get('0', {})  # Sectional tests only have one section (index 0)
    correct = wrong = skipped = 0
    current_section_q_times = question_times.get('0', {})

    for q_idx, row in enumerate(rows):
        user_ans = answers.get(str(q_idx), {}).get('answer')
        actual = row.get('CorrectAnswerValue')

        if user_ans is None:
            skipped += 1
        else:
            # Handle both MCQ and TITA type questions
            question_type = row.get('QuestionType', 'MCQ')
            is_correct = False
            
            if question_type == 'TITA':
                # For TITA questions, compare numerical values with tolerance
                try:
                    user_val = float(user_ans)
                    correct_val = float(actual)
                    # Allow small tolerance for floating point comparison
                    tolerance = 0.001
                    is_correct = abs(user_val - correct_val) <= tolerance
                except (ValueError, TypeError):
                    is_correct = False
            else:
                # For MCQ questions, exact string match
                is_correct = str(user_ans) == str(actual)
            
            if is_correct:
                correct += 1
            else:
                wrong += 1

    # Calculate section time
    section_time = section_times[0] if section_times else None
    section_time_str = format_seconds_to_str(section_time)

    # Calculate score with different rules for MCQ vs TITA
    mcq_correct = mcq_wrong = tita_correct = tita_wrong = 0
    
    for q_idx, row in enumerate(rows):
        user_ans = answers.get(str(q_idx), {}).get('answer')
        actual = row.get('CorrectAnswerValue')
        question_type = row.get('QuestionType', 'MCQ')
        
        if user_ans is not None:
            # Handle both MCQ and TITA type questions
            is_correct = False
            
            if question_type == 'TITA':
                # For TITA questions, compare numerical values with tolerance
                try:
                    user_val = float(user_ans)
                    correct_val = float(actual)
                    # Allow small tolerance for floating point comparison
                    tolerance = 0.001
                    is_correct = abs(user_val - correct_val) <= tolerance
                except (ValueError, TypeError):
                    is_correct = False
            else:
                # For MCQ questions, exact string match
                is_correct = str(user_ans) == str(actual)
            
            if question_type == 'TITA':
                if is_correct:
                    tita_correct += 1
                else:
                    tita_wrong += 1
            else:  # MCQ
                if is_correct:
                    mcq_correct += 1
                else:
                    mcq_wrong += 1
    
    # Calculate score: MCQ has negative marking, TITA doesn't
    score = (mcq_correct * 3) - (mcq_wrong * 1) + (tita_correct * 3)
    total_attempted = correct + wrong
    accuracy = round((correct / total_attempted * 100) if total_attempted > 0 else 0)
    

    # Calculate average time per question
    total_time = sum(t for t in current_section_q_times.values() if t is not None)
    avg_time = total_time / len(rows) if rows else 0
    avg_time_str = format_seconds_to_str(avg_time)

    # Prepare stats for SWOT analysis and final return
    sectional_stats = {
        'test_name': f"Sectional Mock - {section_conf['name']}",
        'test_id': test_id,  # Store test_id to reconstruct data later
        'section_name': section_conf['name'],
        'score': score,
        'total_possible': len(rows) * 3,
        'time_spent': section_time_str,
        'accuracy': accuracy,
        'correct': correct,
        'wrong': wrong,
        'skipped': skipped,
        'avg_time_per_question': avg_time_str,
        'topic_analysis': [
            {
                'name': 'Topic 1',  # You can add actual topic analysis here
                'total_questions': 10,
                'correct': 8,
                'accuracy': 80,
                'avg_time': '1:45'
            }
        ],
        'improvement_areas': [
            {
                'icon': '⚡',
                'title': 'Speed in Calculations',
                'description': 'Work on improving your speed while maintaining accuracy',
                'action_items': [
                    'Practice more timed questions',
                    'Learn shortcut methods'
                ]
            }
        ],
        'time_analysis': {
            'optimal_count': 0,  # Will be calculated when detailed questions are reconstructed
            'longer_count': 0,   # Will be calculated when detailed questions are reconstructed
            'avg_time_correct': avg_time_str,
            'avg_time_incorrect': avg_time_str
        },
        # Store answer data to reconstruct detailed questions when needed
        'answer_data': answer_data,
        'question_times': question_times,
        'section_times': section_times
    }

    # Generate SWOT analysis for sectional test
    swot_analysis = generate_sectional_swot_analysis(sectional_stats)
    sectional_stats['swot_analysis'] = swot_analysis

    # Generate missed opportunities and time wasters for sectional test
    missed_ops = generate_missed_opportunities(sectional_stats, is_sectional=True)
    time_wasters = generate_time_wasters(sectional_stats, is_sectional=True)
    sectional_stats['missed_opportunities'] = missed_ops
    sectional_stats['time_wasters'] = time_wasters

    # Return formatted stats for sectional results - STORE ONLY ESSENTIAL DATA
    return sectional_stats

def generate_missed_opportunities(stats, is_sectional=False):
    """Generate topic-wise missed opportunities based on performance data"""
    missed_ops = []
    
    if is_sectional:
        # For sectional tests - get detailed topic analysis
        test_id = stats.get('test_id')
        answer_data = stats.get('answer_data', {})
        question_times = stats.get('question_times', {})
        
        # Determine section configuration based on test_id
        section_conf_map = {
            'qa1': { 'name': "Quantitative Aptitude", 'csv': 'QA_16.csv', 'short_name': 'QA' },
            'qa2': { 'name': "Quantitative Aptitude", 'csv': 'QA_17.csv', 'short_name': 'QA' },
            'qa3': { 'name': "Quantitative Aptitude", 'csv': 'QA_18.csv', 'short_name': 'QA' },
            'qa4': { 'name': "Quantitative Aptitude", 'csv': 'QA_19.csv', 'short_name': 'QA' },
            'varc1': { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#16.csv', 'short_name': 'VARC' },
            'varc2': { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#17.csv', 'short_name': 'VARC' },
            'varc3': { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#18.csv', 'short_name': 'VARC' },
            'lrdi1': { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#16.csv', 'short_name': 'LRDI' },
            'lrdi2': { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#17.csv', 'short_name': 'LRDI' },
            'lrdi3': { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#18.csv', 'short_name': 'LRDI' }
        }
        
        if test_id in section_conf_map:
            section_conf = section_conf_map[test_id]
            section_analysis = analyze_sectional_question_selection(section_conf, answer_data, question_times, stats)
            
            if section_analysis:
                # Get topic-wise missed opportunities
                for topic, perf in section_analysis['topic_performance'].items():
                    if perf['easy_missed'] > 0:
                        # Get subtopics for this topic from CSV
                        subtopics = get_subtopics_for_topic(section_conf['csv'], topic, answer_data.get('0', {}))
                        main_subtopic = subtopics[0] if subtopics else topic
                        
                        missed_ops.append({
                            'section': section_conf['short_name'],
                            'topic': topic,
                            'subtopic': main_subtopic,
                            'count': perf['easy_missed'],
                            'difficulty': 'Easy',
                            'efficiency': 'Low Efficiency' if perf['easy_missed'] >= 2 else 'Medium Efficiency'
                        })
        
        # Enhanced fallback with better topic analysis
        if not missed_ops:
            test_id = stats.get('test_id')
            if test_id in section_conf_map:
                section_conf = section_conf_map[test_id]
                # Get actual topics from CSV even if no questions were attempted
                missed_ops = generate_fallback_missed_opportunities(section_conf, stats)
            
            # Basic fallback if nothing else works
            if not missed_ops:
                skipped = stats.get('skipped', 0)
                section_name = stats.get('section_name', 'this section')
                if skipped > 0:
                    missed_ops.append({
                        'section': section_name.split()[-1],
                        'topic': 'General',
                        'subtopic': 'Multiple Topics',
                        'count': min(skipped, 3),
                        'difficulty': 'Easy',
                        'efficiency': 'Low Efficiency'
                    })
                        
    else:
        # For full mock tests - analyze each section
        sections = stats.get('sections', [])
        answer_data = stats.get('answer_data', {})
        question_times = stats.get('question_times', {})
        test_id = stats.get('test_id')
        
        # Mock test configurations
        mock_test_configs = {
            1: [
                { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#1.csv', 'short_name': 'VARC' },
                { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#1.csv', 'short_name': 'LRDI' },
                { 'name': "Quantitative Aptitude", 'csv': 'QA_1.csv', 'short_name': 'QA' }
            ],
            2: [
                { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#2.csv', 'short_name': 'VARC' },
                { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#2.csv', 'short_name': 'LRDI' },
                { 'name': "Quantitative Aptitude", 'csv': 'QA_2.csv', 'short_name': 'QA' }
            ],
            3: [
                { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#3.csv', 'short_name': 'VARC' },
                { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#3.csv', 'short_name': 'LRDI' },
                { 'name': "Quantitative Aptitude", 'csv': 'QA_3.csv', 'short_name': 'QA' }
            ]
            # Add more as needed
        }
        
        sections_conf = mock_test_configs.get(test_id, [])
        
        for sec_idx, sec in enumerate(sections):
            if sec_idx < len(sections_conf) and sec['skipped'] > 2:
                section_conf = sections_conf[sec_idx]
                section_analysis = analyze_section_question_selection(section_conf, sec_idx, answer_data, question_times)
                
                if section_analysis:
                    # Get top 2 topics with missed opportunities
                    sorted_topics = sorted(section_analysis['topic_performance'].items(), 
                                         key=lambda x: x[1]['easy_missed'], reverse=True)
                    
                    for topic, perf in sorted_topics[:2]:
                        if perf['easy_missed'] > 0:
                            subtopics = get_subtopics_for_topic(section_conf['csv'], topic, answer_data.get(str(sec_idx), {}))
                            main_subtopic = subtopics[0] if subtopics else topic
                            
                            missed_ops.append({
                                'section': section_conf['short_name'],
                                'topic': topic,
                                'subtopic': main_subtopic,
                                'count': perf['easy_missed'],
                                'difficulty': 'Easy',
                                'efficiency': 'Low Efficiency' if perf['easy_missed'] >= 2 else 'Medium Efficiency'
                            })
    
    # Sort by count (highest first) and limit to top 6
    missed_ops.sort(key=lambda x: x['count'], reverse=True)
    
    # Ensure we always have diverse sections represented
    if not is_sectional:
        diverse_missed, diverse_time = generate_diverse_fallback_data(stats)
        
        # Check what sections we already have
        existing_sections = set(op['section'] for op in missed_ops)
        target_sections = {'QA', 'VARC', 'LRDI'}
        missing_sections = target_sections - existing_sections
        
        # Add diverse data for missing sections
        for div_op in diverse_missed:
            if div_op['section'] in missing_sections:
                missed_ops.append(div_op)
                missing_sections.discard(div_op['section'])
    
    return missed_ops[:6]

def generate_time_wasters(stats, is_sectional=False):
    """Generate topic-wise time wasters based on performance data"""
    time_wasters = []
    
    if is_sectional:
        # For sectional tests - get detailed topic analysis
        test_id = stats.get('test_id')
        answer_data = stats.get('answer_data', {})
        question_times = stats.get('question_times', {})
        
        # Determine section configuration
        section_conf_map = {
            'qa1': { 'name': "Quantitative Aptitude", 'csv': 'QA_16.csv', 'short_name': 'QA' },
            'qa2': { 'name': "Quantitative Aptitude", 'csv': 'QA_17.csv', 'short_name': 'QA' },
            'qa3': { 'name': "Quantitative Aptitude", 'csv': 'QA_18.csv', 'short_name': 'QA' },
            'qa4': { 'name': "Quantitative Aptitude", 'csv': 'QA_19.csv', 'short_name': 'QA' },
            'varc1': { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#16.csv', 'short_name': 'VARC' },
            'varc2': { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#17.csv', 'short_name': 'VARC' },
            'varc3': { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#18.csv', 'short_name': 'VARC' },
            'lrdi1': { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#16.csv', 'short_name': 'LRDI' },
            'lrdi2': { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#17.csv', 'short_name': 'LRDI' },
            'lrdi3': { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#18.csv', 'short_name': 'LRDI' }
        }
        
        if test_id in section_conf_map:
            section_conf = section_conf_map[test_id]
            # Analyze time spent per topic
            topic_time_analysis = analyze_topic_time_consumption(section_conf['csv'], answer_data.get('0', {}), question_times.get('0', {}))
            
            for topic_data in topic_time_analysis:
                if topic_data['avg_time_seconds'] > topic_data['optimal_time']:
                    time_wasters.append({
                        'section': section_conf['short_name'],
                        'topic': topic_data['topic'],
                        'subtopic': topic_data['main_subtopic'],
                        'time_spent': format_seconds_to_mm_ss(topic_data['avg_time_seconds']),
                        'difficulty': topic_data['difficulty'],
                        'efficiency': topic_data['efficiency']
                    })
        
        # Enhanced fallback with better topic analysis
        if not time_wasters:
            test_id = stats.get('test_id')
            if test_id in section_conf_map:
                section_conf = section_conf_map[test_id]
                # Get actual topics from CSV even if no questions were attempted
                time_wasters = generate_fallback_time_wasters(section_conf, stats)
            
            # Basic fallback if nothing else works
            if not time_wasters:
                accuracy = stats.get('accuracy', 0)
                if accuracy < 50:
                    time_wasters.append({
                        'section': stats.get('section_name', 'Section').split()[-1],
                        'topic': 'General',
                        'subtopic': 'Multiple Topics',
                        'time_spent': '4:30',
                        'difficulty': 'Medium',
                        'efficiency': 'Low Efficiency'
                    })
                        
    else:
        # For full mock tests - analyze each section
        sections = stats.get('sections', [])
        answer_data = stats.get('answer_data', {})
        question_times = stats.get('question_times', {})
        test_id = stats.get('test_id')
        
        mock_test_configs = {
            1: [
                { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#1.csv', 'short_name': 'VARC' },
                { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#1.csv', 'short_name': 'LRDI' },
                { 'name': "Quantitative Aptitude", 'csv': 'QA_1.csv', 'short_name': 'QA' }
            ],
            2: [
                { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#2.csv', 'short_name': 'VARC' },
                { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#2.csv', 'short_name': 'LRDI' },
                { 'name': "Quantitative Aptitude", 'csv': 'QA_2.csv', 'short_name': 'QA' }
            ],
            3: [
                { 'name': "Verbal Ability and Reading Comprehension", 'csv': 'VARC_#3.csv', 'short_name': 'VARC' },
                { 'name': "Data Interpretation & Logical Reasoning", 'csv': 'LRDI_#3.csv', 'short_name': 'LRDI' },
                { 'name': "Quantitative Aptitude", 'csv': 'QA_3.csv', 'short_name': 'QA' }
            ]
            # Add more as needed
        }
        
        sections_conf = mock_test_configs.get(test_id, [])
        
        for sec_idx, sec in enumerate(sections):
            if sec_idx < len(sections_conf):
                section_conf = sections_conf[sec_idx]
                topic_time_analysis = analyze_topic_time_consumption(section_conf['csv'], 
                                                                   answer_data.get(str(sec_idx), {}), 
                                                                   question_times.get(str(sec_idx), {}))
                
                # Get top 2 time-consuming topics from this section
                sorted_topics = sorted(topic_time_analysis, key=lambda x: x['avg_time_seconds'], reverse=True)
                
                for topic_data in sorted_topics[:2]:
                    if topic_data['avg_time_seconds'] > topic_data['optimal_time']:
                        time_wasters.append({
                            'section': section_conf['short_name'],
                            'topic': topic_data['topic'],
                            'subtopic': topic_data['main_subtopic'],
                            'time_spent': format_seconds_to_mm_ss(topic_data['avg_time_seconds']),
                            'difficulty': topic_data['difficulty'],
                            'efficiency': topic_data['efficiency']
                        })
    
    # Sort by time spent (highest first) and limit to top 6
    time_wasters.sort(key=lambda x: time_to_seconds(x['time_spent']), reverse=True)
    
    # Ensure we always have diverse sections represented
    if not is_sectional:
        diverse_missed, diverse_time = generate_diverse_fallback_data(stats)
        
        # Check what sections we already have
        existing_sections = set(tw['section'] for tw in time_wasters)
        target_sections = {'QA', 'VARC', 'LRDI'}
        missing_sections = target_sections - existing_sections
        
        # Add diverse data for missing sections
        for div_tw in diverse_time:
            if div_tw['section'] in missing_sections:
                time_wasters.append(div_tw)
                missing_sections.discard(div_tw['section'])
    
    return time_wasters[:6]

def get_subtopics_for_topic(csv_filename, topic_name, answer_data):
    """Get subtopics for a given topic from CSV"""
    try:
        path = app.static_folder + '/' + csv_filename
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
        
        subtopics = []
        for q_idx, row in enumerate(rows):
            if row.get('Topic', '') == topic_name:
                subtopic = row.get('SubTopic', 'Unknown SubTopic')
                user_ans = answer_data.get(str(q_idx), {}).get('answer')
                # Prioritize subtopics of unattempted questions
                if user_ans is None and subtopic not in subtopics:
                    subtopics.insert(0, subtopic)
                elif subtopic not in subtopics:
                    subtopics.append(subtopic)
                    
        return subtopics[:3]  # Return top 3 subtopics
    except FileNotFoundError:
        return [topic_name]

def analyze_topic_time_consumption(csv_filename, answer_data, question_times):
    """Analyze time consumption per topic"""
    try:
        path = app.static_folder + '/' + csv_filename
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
        
        topic_times = {}
        
        for q_idx, row in enumerate(rows):
            topic = row.get('Topic', 'Unknown Topic')
            subtopic = row.get('SubTopic', 'Unknown SubTopic')
            difficulty = row.get('DifficultyLevelPredicted', '').strip().lower()
            user_ans = answer_data.get(str(q_idx), {}).get('answer')
            q_time = question_times.get(str(q_idx), 0)
            
            if user_ans is not None and q_time > 0:  # Only consider attempted questions
                if topic not in topic_times:
                    topic_times[topic] = {
                        'total_time': 0,
                        'question_count': 0,
                        'subtopics': [],
                        'difficulties': [],
                        'correct_count': 0
                    }
                
                topic_times[topic]['total_time'] += q_time
                topic_times[topic]['question_count'] += 1
                
                if subtopic not in topic_times[topic]['subtopics']:
                    topic_times[topic]['subtopics'].append(subtopic)
                if difficulty not in topic_times[topic]['difficulties']:
                    topic_times[topic]['difficulties'].append(difficulty)
                
                # Check if answer is correct
                correct_ans = row.get('CorrectAnswerValue')
                if str(user_ans) == str(correct_ans):
                    topic_times[topic]['correct_count'] += 1
        
        # Convert to analysis format
        topic_analysis = []
        for topic, data in topic_times.items():
            if data['question_count'] > 0:
                avg_time = data['total_time'] / data['question_count']
                accuracy = (data['correct_count'] / data['question_count']) * 100
                
                # Determine optimal time based on difficulty
                main_difficulty = data['difficulties'][0] if data['difficulties'] else 'medium'
                if main_difficulty == 'easy':
                    optimal_time = 45
                elif main_difficulty == 'hard':
                    optimal_time = 120
                else:
                    optimal_time = 75
                
                # Determine efficiency
                if avg_time > optimal_time * 1.5:
                    efficiency = 'Low Efficiency'
                elif avg_time > optimal_time * 1.2:
                    efficiency = 'Medium Efficiency'
                else:
                    efficiency = 'High Efficiency'
                
                topic_analysis.append({
                    'topic': topic,
                    'main_subtopic': data['subtopics'][0] if data['subtopics'] else topic,
                    'avg_time_seconds': avg_time,
                    'optimal_time': optimal_time,
                    'difficulty': main_difficulty.title(),
                    'efficiency': efficiency,
                    'accuracy': accuracy
                })
        
        return topic_analysis
    except FileNotFoundError:
        return []

def format_seconds_to_mm_ss(seconds):
    """Convert seconds to MM:SS format"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

def time_to_seconds(time_str):
    """Convert MM:SS format to seconds"""
    try:
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except:
        return 0

def generate_fallback_missed_opportunities(section_conf, stats):
    """Generate fallback missed opportunities using actual CSV topic data"""
    try:
        path = app.static_folder + '/' + section_conf['csv']
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
        
        # Get topics from CSV
        topics_found = {}
        for row in rows:
            topic = row.get('Topic', 'Unknown Topic')
            subtopic = row.get('SubTopic', 'Unknown SubTopic')
            difficulty = row.get('DifficultyLevelPredicted', '').strip().lower()
            
            if difficulty == 'easy' and topic not in topics_found:
                topics_found[topic] = subtopic
                
        # Create missed opportunities from actual topics
        missed_ops = []
        for i, (topic, subtopic) in enumerate(list(topics_found.items())[:3]):
            missed_ops.append({
                'section': section_conf['short_name'],
                'topic': topic,
                'subtopic': subtopic,
                'count': 3 - i,  # Decreasing count
                'difficulty': 'Easy',
                'efficiency': 'Low Efficiency'
            })
            
        return missed_ops
    except FileNotFoundError:
        return []

def generate_diverse_fallback_data(stats):
    """Generate diverse fallback data across all sections"""
    all_missed_ops = []
    all_time_wasters = []
    
    # Sample data for different sections
    section_configs = [
        { 'short_name': 'QA', 'csv': 'QA_16.csv' },
        { 'short_name': 'VARC', 'csv': 'VARC_#16.csv' },
        { 'short_name': 'LRDI', 'csv': 'LRDI_#16.csv' }
    ]
    
    for i, config in enumerate(section_configs):
        # Try to get real data first
        real_missed = generate_fallback_missed_opportunities(config, stats)
        real_time_wasters = generate_fallback_time_wasters(config, stats)
        
        if real_missed:
            all_missed_ops.extend(real_missed[:1])  # Take only 1 from each section
        else:
            # Fallback with section-specific data
            section_topics = {
                'QA': [('Arithmetic', 'Percentages'), ('Algebra', 'Linear Equations'), ('Geometry', 'Coordinate Geometry')],
                'VARC': [('Reading Comprehension', 'Science Passages'), ('Para Jumbles', 'Sentence Ordering'), ('Vocabulary', 'Synonyms')],
                'LRDI': [('Data Interpretation', 'Tables'), ('Logical Reasoning', 'Arrangements'), ('Puzzles', 'Grid Based')]
            }
            
            topics = section_topics.get(config['short_name'], [('General Topic', 'Multiple Subtopics')])
            topic, subtopic = topics[i % len(topics)]
            
            all_missed_ops.append({
                'section': config['short_name'],
                'topic': topic,
                'subtopic': subtopic,
                'count': 3 - i,
                'difficulty': 'Easy',
                'efficiency': 'Low Efficiency'
            })
        
        if real_time_wasters:
            all_time_wasters.extend(real_time_wasters[:1])  # Take only 1 from each section
        else:
            # Fallback with section-specific data
            section_topics = {
                'QA': [('Arithmetic', 'Percentages'), ('Algebra', 'Quadratic Equations'), ('Geometry', 'Mensuration')],
                'VARC': [('Reading Comprehension', 'Philosophy Passages'), ('Critical Reasoning', 'Assumptions'), ('Grammar', 'Error Detection')],
                'LRDI': [('Data Interpretation', 'Graphs'), ('Logical Reasoning', 'Blood Relations'), ('Puzzles', 'Scheduling')]
            }
            
            topics = section_topics.get(config['short_name'], [('General Topic', 'Multiple Subtopics')])
            topic, subtopic = topics[i % len(topics)]
            times = ['4:30', '3:45', '5:15']
            difficulties = ['Medium', 'Hard', 'Medium']
            
            all_time_wasters.append({
                'section': config['short_name'],
                'topic': topic,
                'subtopic': subtopic,
                'time_spent': times[i],
                'difficulty': difficulties[i],
                'efficiency': 'Low Efficiency'
            })
    
    return all_missed_ops, all_time_wasters

def generate_fallback_time_wasters(section_conf, stats):
    """Generate fallback time wasters using actual CSV topic data"""
    try:
        path = app.static_folder + '/' + section_conf['csv']
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
        
        # Get topics from CSV
        topics_found = {}
        for row in rows:
            topic = row.get('Topic', 'Unknown Topic')
            subtopic = row.get('SubTopic', 'Unknown SubTopic')
            difficulty = row.get('DifficultyLevelPredicted', '').strip().lower()
            
            if difficulty in ['medium', 'hard'] and topic not in topics_found:
                topics_found[topic] = {'subtopic': subtopic, 'difficulty': difficulty}
                
        # Create time wasters from actual topics
        time_wasters = []
        times = ['4:30', '3:45', '5:15']
        efficiencies = ['Low Efficiency', 'Medium Efficiency', 'Low Efficiency']
        
        for i, (topic, data) in enumerate(list(topics_found.items())[:3]):
            time_wasters.append({
                'section': section_conf['short_name'],
                'topic': topic,
                'subtopic': data['subtopic'],
                'time_spent': times[i],
                'difficulty': data['difficulty'].title(),
                'efficiency': efficiencies[i]
            })
            
        return time_wasters
    except FileNotFoundError:
        return []

if __name__ == '__main__':
    # Initialize database tables
    init_db()
    
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)