from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from transformers import BartTokenizer, pipeline
from keybert import KeyBERT
from gensim import corpora
from gensim.models.ldamodel import LdaModel
from nltk.corpus import stopwords
from nltk import download
from PyPDF2 import PdfReader
from fpdf import FPDF
import os

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = './uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SECRET_KEY'] = 'your_secret_key_here'
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Download stopwords for nltk
download('stopwords')

# Load models
tokenizer = BartTokenizer.from_pretrained('sshleifer/distilbart-cnn-12-6')
summarizer = pipeline('summarization', model='sshleifer/distilbart-cnn-12-6')
sentiment_analyzer = pipeline('sentiment-analysis', model='distilbert-base-uncased-finetuned-sst-2-english')
kw_model = KeyBERT()

# User model for database with first_name, last_name, email
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(150), nullable=False)
    last_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    chat_history = db.relationship('ChatHistory', backref='user', lazy=True)

# ChatHistory model for storing user-specific chat
class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chat_summary = db.Column(db.Text, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Helper functions for AI functionalities
def chunk_text(text, max_tokens=512):
    tokens = tokenizer(text, return_tensors="pt", truncation=False)['input_ids'][0]
    chunks = [tokens[i:i + max_tokens] for i in range(0, len(tokens), max_tokens)]
    return [tokenizer.decode(chunk, skip_special_tokens=True) for chunk in chunks]

def summarize_text(text):
    word_count = len(text.split())

    # Handle too short inputs
    if word_count < 40:
        return "The text is too short for summarization. Please enter at least 40 words."
    elif 40 <= word_count <= 60:
        summary = summarizer(text, max_length=30, min_length=20, num_beams=4, early_stopping=True)[0]['summary_text']
    elif 60 < word_count <= 100:
        summary = summarizer(text, max_length=50, min_length=30, num_beams=4, early_stopping=True)[0]['summary_text']
    elif 100 < word_count <= 200:
        summary = summarizer(text, max_length=100, min_length=50, num_beams=4, early_stopping=True)[0]['summary_text']
    else:
        summary = summarizer(text, max_length=150, min_length=100, num_beams=4, early_stopping=True)[0]['summary_text']

    return summary.strip()

def extract_keywords(text):
    keywords = kw_model.extract_keywords(text, keyphrase_ngram_range=(1, 2), stop_words='english', top_n=5)
    return [kw[0] for kw in keywords]

def perform_topic_modeling(text):
    tokens = [word for word in text.lower().split() if word not in stopwords.words('english')]
    word_count = len(tokens)
    if word_count <= 200:
        num_topics = 1
    elif word_count <= 500:
        num_topics = 2
    else:
        num_topics = 3
    dictionary = corpora.Dictionary([tokens])
    corpus = [dictionary.doc2bow(tokens)]
    lda_model = LdaModel(corpus, num_topics=num_topics, id2word=dictionary, passes=15)
    topics = lda_model.show_topics(num_topics=num_topics, num_words=6, formatted=False)
    topic_keywords = []
    for topic in topics:
        keywords = set(word for word, _ in topic[1])
        topic_keywords.append(", ".join(keywords))
    return topic_keywords

def analyze_sentiment(text):
    sentiment = sentiment_analyzer(text)[0]
    return sentiment['label'], sentiment['score']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ''
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
        return text if text else None
    except Exception as e:
        print("Error reading PDF:", e)
        return None

# Route for home page
@app.route('/')
def index():
    if current_user.is_authenticated:
        chat_history = ChatHistory.query.filter_by(user_id=current_user.id).all()
        return render_template('index.html', chat_history=chat_history)
    return render_template('index.html')

# Route for signup
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if password and confirm password match
        if password != confirm_password:
            flash('Passwords do not match. Please try again.')
            return redirect(url_for('signup'))

        # Check if the username or email already exists
        existing_user = User.query.filter_by(username=username).first()
        existing_email = User.query.filter_by(email=email).first()
        if existing_user or existing_email:
            flash('Username or email already exists. Please choose another.')
            return redirect(url_for('signup'))

        # Hash the password using pbkdf2:sha256
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Create new user
        new_user = User(username=username, password=hashed_password, email=email, first_name=first_name, last_name=last_name)
        db.session.add(new_user)
        db.session.commit()

        flash('Signup successful, please login.')
        return redirect(url_for('login'))

    return render_template('signup.html')

# Route for login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Login failed. Check username and password.')

    return render_template('login.html')

# Route for logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            extracted_text = extract_text_from_pdf(file_path)

            if extracted_text is None:
                return jsonify({'error': 'Failed to extract text from PDF'}), 400

            summary = summarize_text(extracted_text)
            summary_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], 'summary.pdf')
            
            # Generate the summarized PDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, summary)
            pdf.output(summary_pdf_path)
            
            return send_file(summary_pdf_path, as_attachment=True, download_name='summarized_output.pdf')
        except Exception as e:
            print("Error during file processing:", e)
            return jsonify({'error': 'An error occurred during file processing.'}), 500

    return jsonify({'error': 'File type not allowed'}), 400

# Route for analyzing text
@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    text = data.get('text', '')

    if not text:
        return jsonify({'error': 'No text provided'}), 400

    summary = summarize_text(text)
    keywords = extract_keywords(text)
    topics = perform_topic_modeling(text)
    sentiment_label, sentiment_score = analyze_sentiment(text)

    # Save chat history
    if current_user.is_authenticated:
            chat_history = ChatHistory(user_id=current_user.id, chat_summary=summary)
            db.session.add(chat_history)
            db.session.commit()

    return jsonify({
        'summary': summary,
        'keywords': keywords,
        'topics': topics,
        'sentiment': f"{sentiment_label} ({sentiment_score:.2f})"
    })

# Run the Flask app
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(debug= False)
