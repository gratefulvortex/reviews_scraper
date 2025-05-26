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
from utils.visualization import generate_wordcloud, generate_sentiment_chart
import os
from datetime import datetime
import csv
import json

app = Flask(__name__)
app.config.from_object(Config)
CORS(app, supports_credentials=True)
app.secret_key = '436e393f66a2da1e51c01388be6b25cace91dcf7eaf53db5b63bae2ba2f15e12'

# Create data directory if it doesn't exist
os.makedirs('data', exist_ok=True)

def save_session_data(user_id, data):
    """Save session data to a file"""
    filename = os.path.join('data', f'session_{user_id}.json')
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f)

def load_session_data(user_id):
    """Load session data from a file"""
    filename = os.path.join('data', f'session_{user_id}.json')
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def clear_session_data(user_id):
    """Clear session data file"""
    filename = os.path.join('data', f'session_{user_id}.json')
    if os.path.exists(filename):
        os.remove(filename)

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

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'csv'

# Routes
@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('select_products'))
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
    if 'user' in session:
        clear_session_data(session['user'])
    session.clear()
    return redirect(url_for('login'))

@app.route('/select_products', methods=['GET', 'POST'])
@login_required
def select_products():
    user_id = session.get('user')
    if not user_id:
        flash('User not logged in.')
        return redirect(url_for('login'))
        
    session_data = load_session_data(user_id)
    products = session_data.get('products', []) if session_data else []
    selected_industry = request.args.get('industry', '')

    if request.method == 'POST':
        new_products = []
        name = request.form.get('product_name')
        url = request.form.get('product_url')
        industry = request.form.get('industry')
        
        if not industry:
            flash('Please select an industry first.')
            return redirect(url_for('select_products'))
        
        data = None
        csv_path = None
        product_image = None

        if url:
            try:
                if 'amazon' in url:
                    flash(f'Scraping Amazon URL: {url}')
                    data = scrape_amazon_reviews(url)
                    if data:
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        csv_path = os.path.join('csvlist', f'amazon_reviews_{timestamp}.csv')
                        os.makedirs('csvlist', exist_ok=True)
                        df = pd.DataFrame(data)
                        df.to_csv(csv_path, index=False)
                        flash(f'Successfully scraped {len(data)} reviews from Amazon.')
                    else:
                        flash(f'Failed to scrape reviews from Amazon URL: {url}')
                elif 'influenster' in url:
                    flash(f'Scraping Influenster URL: {url}')
                    result = scrape_influenster_reviews(url)
                    if result:
                        data = result['reviews']
                        product_image = result['product_image']
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        csv_path = os.path.join('csvlist', f'influenster_reviews_{timestamp}.csv')
                        os.makedirs('csvlist', exist_ok=True)
                        df = pd.DataFrame(data)
                        df.to_csv(csv_path, index=False)
                        flash(f'Successfully scraped {len(data)} reviews from Influenster.')
                    else:
                        flash(f'Failed to scrape reviews from Influenster URL: {url}')
                else:
                    flash(f'Unsupported URL: {url}. Please provide an Amazon or Influenster URL.')
            except Exception as e:
                flash(f'Error during scraping: {str(e)}')
                return redirect(url_for('select_products'))

        if name and data:
            new_products.append({
                'name': name,
                'data': data,
                'csv_path': csv_path,
                'image_url': product_image,
                'industry': industry,
                'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
        products.extend(new_products)

        if products:
            save_session_data(user_id, {'products': products})
            return redirect(url_for('view_csv', idx=len(products)-1 if new_products else 0))
        else:
            flash('No valid products were added. Please try again.')
            return redirect(url_for('select_products'))

    # Filter products by industry if selected
    if selected_industry:
        products = [p for p in products if p.get('industry') == selected_industry]
        # Sort products by most recently scraped
        products.sort(key=lambda x: x.get('scraped_at', ''), reverse=True)

    return render_template('select_products.html', 
                         products=products,
                         selected_industry=selected_industry)

@app.route('/view_csv', methods=['GET', 'POST'])
@login_required
def view_csv():
    # Load products from session file
    session_data = load_session_data(session['user'])
    if not session_data or 'products' not in session_data:
        flash('No product data found. Please add products first.')
        return redirect(url_for('select_products'))
    
    products = session_data['products']
    if not products:
        flash('No products available. Please add products first.')
        return redirect(url_for('select_products'))
    
    idx = request.args.get('idx', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Number of reviews per page
    
    if idx is None or idx >= len(products):
        idx = 0
    
    product = products[idx]
    rows = []
    columns = []
    
    if product['csv_path'] and os.path.exists(product['csv_path']):
        try:
            with open(product['csv_path'], 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                columns = [col for col in reader.fieldnames if col != 'content_hash']  # Remove content_hash from columns
                rows = []
                for row in reader:
                    # Create a new row without content_hash
                    filtered_row = {k: v for k, v in row.items() if k != 'content_hash'}
                    rows.append(filtered_row)
        except Exception as e:
            flash(f'Error reading CSV file: {str(e)}')
            return redirect(url_for('select_products'))
    
    # Calculate statistics
    total_reviews = len(rows)
    
    # Calculate average rating
    ratings = [float(row['rating']) for row in rows if 'rating' in row and row['rating']]
    average_rating = sum(ratings) / len(ratings) if ratings else 0
    
    # Calculate rating distribution
    rating_distribution = {}
    for rating in range(1, 6):
        count = sum(1 for row in rows if 'rating' in row and float(row['rating']) == rating)
        rating_distribution[rating] = count
    
    # Calculate date range
    dates = []
    for row in rows:
        if 'date' in row and row['date']:
            try:
                date = datetime.strptime(row['date'], '%Y-%m-%d')
                dates.append(date)
            except ValueError:
                continue
    
    date_range = {
        'start': min(dates).strftime('%Y-%m-%d') if dates else 'N/A',
        'end': max(dates).strftime('%Y-%m-%d') if dates else 'N/A'
    }
    
    # Calculate pagination
    total_pages = (total_reviews + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_rows = rows[start_idx:end_idx]
    
    return render_template('view_csv.html', 
                         products=products,
                         idx=idx,
                         product=product,
                         columns=columns,
                         rows=rows,
                         paginated_rows=paginated_rows,
                         current_page=page,
                         total_pages=total_pages,
                         total_reviews=total_reviews,
                         average_rating=average_rating,
                         rating_distribution=rating_distribution,
                         date_range=date_range)

@app.route('/sentiment_analysis', methods=['GET', 'POST'])
@login_required
def sentiment_analysis():
    session_data = load_session_data(session['user'])
    if not session_data or 'products' not in session_data:
        flash('No product data found. Please add products first.')
        return redirect(url_for('select_products'))
    
    products = session_data['products']
    selected_idx = request.args.get('idx', type=int, default=0)
    
    if selected_idx >= len(products):
        selected_idx = 0
    
    selected_product = products[selected_idx]
    
    # Process sentiment analysis for selected product only
    rows = selected_product['data']
    pos, neg = 0, 0
    for row in rows:
        text = row.get('review_text', '') or row.get('text', '')
        score = analyzer.polarity_scores(str(text))['compound']
        if score >= 0.05:
            pos += 1
        else:
            neg += 1
    
    selected_product['sentiment'] = {'positive': pos, 'negative': neg}
    selected_product['sentiment_chart'] = generate_sentiment_chart(pos, neg)
    
    if request.method == 'POST':
        if request.form.get('from_view_csv'):
            return render_template('sentiment_analysis.html', 
                                products=products,
                                selected_product=selected_product,
                                selected_idx=selected_idx)
        return redirect(url_for('word_cloud', idx=selected_idx))
    
    return render_template('sentiment_analysis.html', 
                         products=products,
                         selected_product=selected_product,
                         selected_idx=selected_idx)

@app.route('/word_cloud', methods=['GET', 'POST'])
@login_required
def word_cloud():
    session_data = load_session_data(session['user'])
    if not session_data or 'products' not in session_data:
        flash('No product data found. Please add products first.')
        return redirect(url_for('select_products'))
    
    products = session_data['products']
    selected_idx = request.args.get('idx', type=int, default=0)
    
    if selected_idx >= len(products):
        selected_idx = 0
    
    selected_product = products[selected_idx]
    
    # Generate word cloud for selected product only
    rows = selected_product['data']
    texts = [str(row.get('review_text', '') or row.get('text', '')) for row in rows]
    selected_product['wordcloud'] = generate_wordcloud(' '.join(texts), title=selected_product['name'])
    
    if request.method == 'POST':
        if request.form.get('from_sentiment'):
            return render_template('word_cloud.html', 
                                products=products,
                                selected_product=selected_product,
                                selected_idx=selected_idx)
        flash('Analysis complete!')
        return redirect(url_for('select_products'))
    
    return render_template('word_cloud.html', 
                         products=products,
                         selected_product=selected_product,
                         selected_idx=selected_idx)

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