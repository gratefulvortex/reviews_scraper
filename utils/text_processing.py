import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()

def clean_text(text):
    if not isinstance(text, str):
        return ''
    text = re.sub(r'[^\w\s]', '', text.lower())
    return text

def perform_sentiment_analysis(text):
    score = analyzer.polarity_scores(text)['compound']
    return 'positive' if score >= 0.05 else 'negative'

def count_sentences(text):
    return len(re.findall(r'[.!?]+', str(text) or ''))

def count_words(text):
    return len((str(text) or '').split())