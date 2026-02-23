# PinPoint

PinPoint is a community-focused local discovery web app where users can explore small businesses, read and leave reviews, save favorites, and browse active deals.

## Tech Stack

### Frontend

- HTML templates with Jinja2 (`pinpoint/templates`)
- Vanilla JavaScript for page logic and API calls (`pinpoint/static/js/main.js`)
- Custom CSS for styling and responsive UI (`pinpoint/static/css/style.css`)

### Backend

- Python
- Flask web framework (`pinpoint/app.py`)
- SQLite database (`pinpoint/pinpoint.db`)
- Werkzeug security utilities for password hashing (`generate_password_hash`, `check_password_hash`)

## Key Features

- Explore page with category filtering and sorting (newest, highest rated, most reviewed)
- Business detail pages with ratings, address/phone info, and review history
- Review submission flow with a lightweight math captcha
- User authentication (sign up, log in, log out, session-based auth)
- Saved businesses (bookmarks) per logged-in user
- Deals page with active/all deal views, coupon code copy, and expiry handling
- Seeded demo data for businesses, reviews, and deals

## Project Structure

- `pinpoint/app.py`: Flask app, API routes, auth, DB initialization/seeding
- `pinpoint/templates/`: Server-rendered page templates
- `pinpoint/static/js/main.js`: Frontend behaviors and API integration
- `pinpoint/static/css/style.css`: Styles for all pages/components
- `pinpoint/pinpoint.db`: SQLite database file
- `pinpoint/requirements.txt`: Python dependencies

## Getting Started

1. Create and activate a Python virtual environment.
2. Install dependencies:
   - `pip install -r pinpoint/requirements.txt`
3. Run the app:
   - `python pinpoint/app.py`
4. Open:
   - `http://127.0.0.1:5000`

## Demo Login

The app seeds a demo account on startup:

- Username: `demo`
- Password: `demo123`
