from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
import os
import requests
from dotenv import load_dotenv

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Change this to a random secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Load environment variables
load_dotenv()

# Set up OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    itineraries = db.relationship('Itinerary', backref='user', lazy=True)

class Itinerary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(100), nullable=False)
    days = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def get_image_url(query):
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=3"
    response = requests.get(url)
    data = response.json()
    if data['hits']:
        return data['hits'][0]['webformatURL']
    return None

def get_travel_itinerary(location, days):
    prompt = f"""
    Create a detailed {days}-day itinerary for a vacation in {location}. For each day, provide:
    1. A brief description of the day's theme or focus.
    2. 3-4 activities or attractions to visit, with short descriptions.
    3. Suggested local restaurants or cuisine to try.
    4. Any travel tips or cultural insights specific to that day's activities.

    Format the response as follows:

    Day 1: [Theme of the day]
    - Morning: [Activity 1] - [Brief description]
    - Afternoon: [Activity 2] - [Brief description]
    - Evening: [Activity 3] - [Brief description]
    - Dining: [Restaurant or cuisine suggestion]
    - Tip: [Travel tip or cultural insight]

    Day 2: [Theme of the day]
    ...

    Provide exactly {days} day(s) in the itinerary, no more and no less.
    """

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a knowledgeable travel guide providing detailed and engaging itineraries for various destinations around the world."},
            {"role": "user", "content": prompt}
        ]
    )

    itinerary = response.choices[0].message.content
    days_data = []

    for day in itinerary.split("Day")[1:]:
        day_info = day.strip().split("\n", 1)
        day_number = day_info[0].split(":")[0].strip()
        day_content = day_info[1].strip()
        
        # Get the first activity of the day for the image query
        activity = day_content.split("-")[1].split(":")[1].strip()
        image_url = get_image_url(f"{location} {activity}")
        
        days_data.append({
            "day": day_number,
            "content": day_content,
            "image_url": image_url
        })

    return days_data[:int(days)]

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists')
            return redirect(url_for('register'))
        new_user = User(username=username, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        flash(f'Welcome, {username}! You have successfully registered and logged in.')
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash(f'Welcome back, {username}!')
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/save_itinerary', methods=['POST'])
@login_required
def save_itinerary():
    data = request.json
    existing_itinerary = Itinerary.query.filter_by(user_id=current_user.id, location=data['location'], days=data['days']).first()
    
    if existing_itinerary:
        existing_itinerary.content = data['itinerary']
        message = "Itinerary updated successfully"
    else:
        new_itinerary = Itinerary(
            location=data['location'],
            days=int(data['days']),
            content=data['itinerary'],
            user_id=current_user.id
        )
        db.session.add(new_itinerary)
        message = "Itinerary saved successfully"
    
    db.session.commit()
    return jsonify({"message": message})

@app.route('/my_itineraries')
@login_required
def my_itineraries():
    itineraries = Itinerary.query.filter_by(user_id=current_user.id).all()
    return render_template('my_itineraries.html', itineraries=itineraries)

@app.route('/generate_itinerary', methods=['POST'])
@login_required
def generate_itinerary():
    data = request.json
    location = data.get('location')
    days = data.get('days')
    
    if not location or not days:
        return jsonify({"error": "Missing location or days"}), 400
    
    itinerary = get_travel_itinerary(location, int(days))
    return jsonify({"itinerary": itinerary})

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)