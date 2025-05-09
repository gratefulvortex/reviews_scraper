from flask import Flask, render_template, request, redirect, url_for, flash, session
from config import Config
from functools import wraps
from flask_cors import CORS
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import io
import base64
from collections import Counter
import re

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialize VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def clean_text(text):
    if not isinstance(text, str):
        return ''
    text = re.sub(r'[^\w\s]', '', text.lower())
    return text

def generate_word_cloud(text, title):
    if not text.strip():
        return None
    wordcloud = WordCloud(width=800, height=400, background_color='white', min_font_size=10).generate(text)
    plt.figure(figsize=(8, 4))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    plt.title(title)
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()
    return f'data:image/png;base64,{img_str}'

# Routes
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if email in Config.VALID_CREDENTIALS and Config.VALID_CREDENTIALS[email] == password:
            session['user'] = email
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Invalid file format. Please upload a CSV file.'}), 400

    try:
        # Read CSV
        df = pd.read_csv(file)
        
        # Clean data
        df = df.dropna(subset=['review_text', 'rating'])
        df['review_text'] = df['review_text'].astype(str)
        
        # Sentiment analysis
        df['sentiment'] = df['review_text'].apply(lambda x: 
            'positive' if analyzer.polarity_scores(x)['compound'] >= 0.05 else 'negative')
        
        # Analysis results
        results = analyze_reviews(df)
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def analyze_reviews(df):
    # Rating pie chart data
    rating_counts = df['rating'].value_counts().reset_index()
    rating_pie_chart_data = [
        {'name': f'Rating {int(row["rating"])}', 'value': int(row["count"])}
        for _, row in rating_counts.iterrows()
    ]
    
    # Sentiment pie chart data
    sentiment_counts = df['sentiment'].value_counts().reset_index()
    sentiment_pie_chart_data = [
        {'name': row['sentiment'].capitalize(), 'value': int(row["count"])}
        for _, row in sentiment_counts.iterrows()
    ]
    
    # Summary statistics
    total_reviews = len(df)
    positive_reviews = df[df['sentiment'] == 'positive'].shape[0]
    
    # Word clouds
    positive_text = ' '.join(df[df['sentiment'] == 'positive']['review_text'].apply(clean_text))
    negative_text = ' '.join(df[df['sentiment'] == 'negative']['review_text'].apply(clean_text))
    
    return {
        'ratingPieChartData': rating_pie_chart_data,
        'sentimentPieChartData': sentiment_pie_chart_data,
        'summary': {
            'positive': f'{positive_reviews} reviews ({positive_reviews/total_reviews*100:.1f}%)',
            'negative': f'{total_reviews-positive_reviews} reviews ({(total_reviews-positive_reviews)/total_reviews*100:.1f}%)'
        },
        'wordClouds': {
            'positive': generate_word_cloud(positive_text, 'Positive Reviews'),
            'negative': generate_word_cloud(negative_text, 'Negative Reviews')
        }
    }

@app.route('/test', methods=['GET'])
@login_required
def test():
    return jsonify({'message': 'Flask server is running'})

if __name__ == '__main__':
    app.run(debug=True)