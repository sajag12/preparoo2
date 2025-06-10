# CAT Prep App with Google OAuth

A comprehensive CAT (Common Admission Test) preparation application built with Flask, featuring Google OAuth authentication, mock tests, and detailed performance analytics.

## Features

- 🔐 **Google OAuth Authentication** - Secure login with Google accounts
- 📝 **Mock Tests** - Full-length CAT mock tests and sectional tests
- 📊 **Performance Analytics** - Detailed analysis with SWOT insights
- ⏱️ **Time Tracking** - Question-wise time analysis
- 🎯 **Question Selection Strategy** - AI-powered recommendations
- 📱 **Responsive Design** - Works on desktop and mobile devices

## Prerequisites

- Python 3.8 or higher
- Google Cloud Console account (for OAuth setup)
- Git

## Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd cat_prep_app
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Google OAuth Setup

1. **Create a Google Cloud Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one

2. **Enable Google+ API**
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google+ API" and enable it

3. **Create OAuth 2.0 Credentials**
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client IDs"
   - Choose "Web application"
   - Add authorized redirect URIs:
     - `http://localhost:5000/login/google/authorized` (for development)
     - `https://yourdomain.com/login/google/authorized` (for production)

4. **Download credentials**
   - Download the JSON file or copy the Client ID and Client Secret

## Environment Configuration

1. **Create a `.env` file** in the project root:
   ```env
   # Google OAuth Configuration
   GOOGLE_OAUTH_CLIENT_ID=your_google_client_id_here
   GOOGLE_OAUTH_CLIENT_SECRET=your_google_client_secret_here
   
   # Flask Configuration
   SECRET_KEY=your_super_secret_key_here_replace_this_with_a_real_secret_key
   DATABASE_URL=sqlite:///app.db
   ```

2. **Replace the placeholder values** with your actual Google OAuth credentials

## Database Setup

The application will automatically create the database tables on first run. The SQLite database will be created as `app.db` in your project directory.

## Running the Application

1. **Start the Flask development server**
   ```bash
   python app.py
   ```

2. **Access the application**
   - Open your browser and go to `http://localhost:5000`
   - Click "Login" and authenticate with Google
   - Start taking mock tests!

## Project Structure

```
cat_prep_app/
├── app.py                 # Main Flask application
├── config.py             # Configuration settings
├── models.py             # Database models
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── templates/           # HTML templates
│   ├── index.html       # Home page
│   ├── login.html       # Login page
│   ├── mock_tests.html  # Mock tests listing
│   ├── take_test.html   # Test interface
│   ├── results.html     # Test results
│   └── ...
├── static/              # Static files (CSS, JS, images)
│   ├── style.css
│   └── question sets/   # CSV files with questions
└── __pycache__/         # Python cache files
```

## Key Features Explained

### Authentication Flow
1. User clicks "Login with Google"
2. Redirected to Google OAuth consent screen
3. After approval, user data is stored in local database
4. Session management handles subsequent requests

### Test Taking Process
1. Authenticated users can access mock tests
2. Questions are loaded from CSV files
3. Time tracking for each question
4. Answers stored in session during test
5. Comprehensive analysis generated after submission

### Performance Analytics
- **SWOT Analysis**: Strengths, Weaknesses, Opportunities, Threats
- **Question Selection Strategy**: Analysis of difficulty-based selection
- **Time Management**: Optimal vs. longer time analysis
- **Topic-wise Performance**: Detailed breakdown by subjects

## Development

### Adding New Tests
1. Add question CSV files to `static/` directory
2. Update the section configurations in `app.py`
3. Add new routes for the test

### Customizing Analytics
- Modify functions in `app.py` starting with `generate_`
- Update thresholds and criteria in analysis functions
- Add new insight categories as needed

## Security Considerations

- **Environment Variables**: Never commit `.env` file to version control
- **Secret Key**: Use a strong, random secret key in production
- **HTTPS**: Always use HTTPS in production
- **OAuth Settings**: Set `OAUTHLIB_INSECURE_TRANSPORT=False` in production

## Deployment

### For Production:
1. Set `OAUTHLIB_INSECURE_TRANSPORT=False` in config
2. Use a production WSGI server (e.g., Gunicorn)
3. Set up proper database (PostgreSQL recommended)
4. Configure environment variables on your hosting platform
5. Update OAuth redirect URIs to production domain

### Example with Heroku:
```bash
# Set environment variables
heroku config:set GOOGLE_OAUTH_CLIENT_ID=your_client_id
heroku config:set GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret
heroku config:set SECRET_KEY=your_secret_key
```

## Troubleshooting

### Common Issues:

1. **OAuth Error: redirect_uri_mismatch**
   - Ensure redirect URI in Google Console matches exactly
   - Check for trailing slashes and http vs https

2. **Database Errors**
   - Delete `app.db` and restart to recreate tables
   - Check file permissions

3. **Import Errors**
   - Ensure virtual environment is activated
   - Reinstall requirements: `pip install -r requirements.txt`

4. **Session Issues**
   - Clear browser cookies
   - Check SECRET_KEY configuration

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
- Check the troubleshooting section above
- Create an issue in the GitHub repository
- Review Google OAuth documentation for authentication issues 