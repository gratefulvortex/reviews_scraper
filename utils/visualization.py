# from wordcloud import WordCloud
# import matplotlib.pyplot as plt
# import io
# import base64

# def generate_word_cloud(text, title):
#     if not text.strip():
#         return None
#     wordcloud = WordCloud(width=800, height=400, background_color='white', min_font_size=10).generate(text)
#     plt.figure(figsize=(8, 4))
#     plt.imshow(wordcloud, interpolation='bilinear')
#     plt.axis('off')
#     plt.title(title)
#     buf = io.BytesIO()
#     plt.savefig(buf, format='png')
#     buf.seek(0)
#     img_str = base64.b64encode(buf.getvalue()).decode('utf-8')
#     plt.close()
#     return f'data:image/png;base64,{img_str}'