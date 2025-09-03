from wordcloud import WordCloud
import matplotlib.pyplot as plt
import io
import base64

def generate_wordcloud(text):
    if not text.strip():
        return ''
    wordcloud = WordCloud(width=400, height=200, background_color='white').generate(text)
    img = io.BytesIO()
    plt.figure(figsize=(4, 2))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    plt.tight_layout()
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()