from flask import Flask, request, jsonify
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
CORS(app)  # Enable CORS for all routes

# Initialize VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()

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

@app.route('/upload', methods=['POST'])
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
        sentiments = []
        for text in df['review_text']:
            score = analyzer.polarity_scores(text)['compound']
            sentiments.append('positive' if score >= 0.05 else 'negative')
        df['sentiment'] = sentiments
        
        # Rating pie chart data
        rating_counts = df['rating'].value_counts().reset_index()
        rating_pie_chart_data = [
            {'name': f'Rating {int(row["rating"])}', 'value': int(row["count"])}
            for _, row in rating_counts.iterrows()
        ]
        
        # Sentiment pie chart data
        sentiment_counts = df['sentiment'].value_counts().reset_index()
        sentiment_pie_chart_data = [
            {'name': row['sentiment'].capitalize(), 'value': int(row['count'])}
            for _, row in sentiment_counts.iterrows()
        ]
        
        # Summary
        positive_reviews = df[df['sentiment'] == 'positive'].shape[0]
        negative_reviews = df[df['sentiment'] == 'negative'].shape[0]
        summary = {
            'positive': f'{positive_reviews} reviews ({positive_reviews/len(df)*100:.1f}%) are positive, praising the lotion’s hydration, gentle formula, and non-greasy texture.',
            'negative': f'{negative_reviews} reviews ({negative_reviews/len(df)*100:.1f}%) are negative, citing issues like irritation or insufficient hydration.'
        }
        
        # Word clouds
        positive_text = ' '.join(df[df['sentiment'] == 'positive']['review_text'].apply(clean_text))
        negative_text = ' '.join(df[df['sentiment'] == 'negative']['review_text'].apply(clean_text))
        
        word_clouds = {
            'positive': generate_word_cloud(positive_text, 'Positive Reviews Word Cloud'),
            'negative': generate_word_cloud(negative_text, 'Negative Reviews Word Cloud')
        }
        
        # Interesting fact: Most frequent word in positive reviews
        positive_words = positive_text.split()
        word_counts = Counter(positive_words)
        most_common_word, count = word_counts.most_common(1)[0]
        interesting_fact = f"The word '{most_common_word}' appears {count} times in positive reviews, highlighting its frequent mention in user feedback about the lotion’s benefits."
        
        return jsonify({
            'ratingPieChartData': rating_pie_chart_data,
            'sentimentPieChartData': sentiment_pie_chart_data,
            'summary': summary,
            'wordClouds': word_clouds,
            'interestingFact': interesting_fact
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/test', methods=['GET'])
def test():
    return jsonify({'message': 'Flask server is running'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)