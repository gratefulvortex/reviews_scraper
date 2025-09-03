import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import io
import base64

def generate_wordcloud(text, title=None):
    if not text.strip():
        return None
    
    # Create word cloud
    wordcloud = WordCloud(
        width=800,
        height=400,
        background_color='white',
        min_font_size=10,
        max_words=100,
        colormap='viridis'
    ).generate(text)
    
    # Create figure with specific size
    plt.figure(figsize=(10, 5))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    if title:
        plt.title(title, pad=20)
    
    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.1)
    buf.seek(0)
    img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()
    
    return f'data:image/png;base64,{img_str}'

def generate_sentiment_chart(positive, negative):
    # Create figure with specific size
    plt.figure(figsize=(8, 4))
    
    # Create pie chart
    labels = ['Positive', 'Negative']
    sizes = [positive, negative]
    colors = ['#059669', '#DC2626']
    explode = (0.1, 0)  # explode the 1st slice (Positive)
    
    plt.pie(sizes, explode=explode, labels=labels, colors=colors,
            autopct='%1.1f%%', shadow=True, startangle=90)
    plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
    
    # Save to buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.1)
    buf.seek(0)
    img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
    plt.close()
    
    return f'data:image/png;base64,{img_str}'