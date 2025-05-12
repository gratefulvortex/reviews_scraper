from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from config import Config
from functools import wraps
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import io
import base64
import re
from core import scrape_amazon_reviews
from influenster import scrape_reviews as scrape_influenster_reviews
from flask_cors import CORS
from utils.text_processing import count_sentences, count_words
from utils.visualization import generate_wordcloud
import os
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
CORS(app, supports_credentials=True)
app.secret_key = '436e393f66a2da1e51c01388be6b25cace91dcf7eaf53db5b63bae2ba2f15e12'

# Initialize VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print('user in session:', 'user' in session)
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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'csv'

# Routes
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('select_products'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if email in Config.VALID_CREDENTIALS and Config.VALID_CREDENTIALS[email] == password:
            session['user'] = email
            return redirect(url_for('select_products'))
        else:
            flash('Invalid email or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/select_products', methods=['GET', 'POST'])
@login_required
def select_products():
    if request.method == 'POST':
        products = []
        for i in range(1, 3):
            name = request.form.get(f'product{i}')
            url = request.form.get(f'url{i}')
            file = request.files.get(f'csv{i}')
            data = None
            csv_path = None
            
            if file and file.filename.endswith('.csv'):
                # Save uploaded CSV file
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                csv_path = os.path.join('csvlist', f'uploaded_{timestamp}_{file.filename}')
                os.makedirs('csvlist', exist_ok=True)
                file.save(csv_path)
                df = pd.read_csv(csv_path)
                data = df.to_dict(orient='records')
            elif url:
                if 'amazon' in url:
                    data = scrape_amazon_reviews(url)
                    if data:
                        # Save Amazon reviews to CSV
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        csv_path = os.path.join('csvlist', f'amazon_reviews_{timestamp}.csv')
                        os.makedirs('csvlist', exist_ok=True)
                        df = pd.DataFrame(data)
                        df.to_csv(csv_path, index=False)
                elif 'influenster' in url:
                    data = scrape_influenster_reviews(url)
                    if data:
                        # Save Influenster reviews to CSV
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        csv_path = os.path.join('csvlist', f'influenster_reviews_{timestamp}.csv')
                        os.makedirs('csvlist', exist_ok=True)
                        df = pd.DataFrame(data)
                        df.to_csv(csv_path, index=False)
            
            if name and data:
                products.append({
                    'name': name,
                    'data': data,
                    'csv_path': csv_path
                })
        
        session['products'] = products
        return redirect(url_for('view_csv'))
    return render_template('select_products.html')

@app.route('/view_csv', methods=['GET', 'POST'])
@login_required
def view_csv():
    products = session.get('products', [])
    if not products:
        return redirect(url_for('select_products'))
    if request.method == 'POST':
        return redirect(url_for('sentiment_analysis'))
    # Show the first product's CSV by default, allow switching
    idx = int(request.args.get('idx', 0))
    product = products[idx]
    rows = product['data']
    columns = rows[0].keys() if rows else []
    return render_template('view_csv.html', products=products, product=product, columns=columns, rows=rows, idx=idx)

@app.route('/sentiment_analysis', methods=['GET', 'POST'])
@login_required
def sentiment_analysis():
    products = session.get('products', [])
    for product in products:
        rows = product['data']
        pos, neg = 0, 0
        for row in rows:
            text = row.get('review_text', '') or row.get('text', '')
            score = analyzer.polarity_scores(str(text))['compound']
            if score >= 0.05:
                pos += 1
            else:
                neg += 1
        product['sentiment'] = {'positive': pos, 'negative': neg}
    if request.method == 'POST':
        return redirect(url_for('word_cloud'))
    return render_template('sentiment_analysis.html', products=products)

@app.route('/word_cloud', methods=['GET', 'POST'])
@login_required
def word_cloud():
    products = session.get('products', [])
    for product in products:
        rows = product['data']
        texts = [str(row.get('review_text', '') or row.get('text', '')) for row in rows]
        product['wordcloud'] = generate_wordcloud(' '.join(texts))
    if request.method == 'POST':
        flash('Analysis complete!')
        return redirect(url_for('select_products'))
    return render_template('word_cloud.html', products=products)

@app.route('/set_model', methods=['POST'])
def set_model():
    session['llm_model'] = request.form.get('llm_model')
    return redirect(request.referrer or url_for('select_products'))

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/download_csv/<path:path>')
@login_required
def download_csv(path):
    try:
        return send_file(path, as_attachment=True)
    except Exception as e:
        flash(f'Error downloading file: {str(e)}')
        return redirect(url_for('view_csv'))

if __name__ == '__main__':
    app.run(debug=True)