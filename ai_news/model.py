"""Deterministic, inspectable topic classifier and extractive summarizer."""
import re
from html.parser import HTMLParser

TOPICS = {
    'Models & research': ('llm', 'model', 'research', 'benchmark', 'reasoning', 'gpt', 'claude', 'gemini'),
    'Products & tools': ('agent', 'assistant', 'app', 'tool', 'copilot', 'chatbot', 'chatgpt'),
    'Business': ('funding', 'investment', 'acquisition', 'startup', 'revenue', 'billion', 'raises', 'raised', 'valuation'),
    'Policy & safety': ('regulation', 'safety', 'copyright', 'policy', 'lawsuit', 'risk', 'ban', 'banning', 'legislation', 'senator', 'government'),
    'Hardware': ('chip', 'gpu', 'nvidia', 'datacenter', 'data center', 'semiconductor'),
}
AI = re.compile(r'\b(ai|artificial intelligence|machine learning|llms?|openai|anthropic|chatgpt|deepmind|generative|gpt|claude|gemini)\b', re.I)

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden:
            self.parts.append(' ')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

def plain_text(html):
    parser = PlainText()
    parser.feed(html)
    return re.sub(r'\s+', ' ', ''.join(parser.parts)).strip()

def classify(title, content):
    text = (title + ' ' + title + ' ' + content).lower()
    scores = {topic: sum(len(re.findall(r'\b' + re.escape(term) + r's?\b', text)) for term in terms)
              for topic, terms in TOPICS.items()}
    return max(scores, key=scores.get) if any(scores.values()) else 'AI overview'

def summarize(content, limit=360):
    protected = re.sub(r'\b(Mr|Mrs|Ms|Dr|Sen|Rep|Gov|Prof|Sept|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Oct|Nov|Dec)\.', lambda m: m[0][:-1] + '\u2024', content)
    sentences = re.split(r'(?<=[.!?])\s+', protected)
    summary = ' '.join(sentences[:2]).replace('\u2024', '.')
    return summary if len(summary) <= limit else summary[:limit].rsplit(' ', 1)[0] + '…'
