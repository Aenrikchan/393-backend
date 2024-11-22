import yaml
from flask import Flask, request, jsonify
import openai
import requests
import logging
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

# Load configuration from file
def load_config(config_path="config.yaml"):
    try:
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        logging.error(f"Configuration file not found at {config_path}")
        return {}

config = load_config()

# Set API keys and other parameters
openai_api_key = os.getenv('OPENAI_API_KEY', '')
bing_api_key = os.getenv('BING_API_KEY', '')
MAX_TOKENS = config.get('max_tokens', 100)
SEARCH_RESULT_COUNT = config.get('search_result_count', 5)
SEARCH_RETRY_LIMIT = config.get('search_retry_limit', 3)

openai.api_key = openai_api_key

# Graceful fallback for missing keys
if not openai.api_key:
    logging.warning("OpenAI API key is missing. Summarization functionality will be disabled.")

if not bing_api_key:
    logging.warning("Bing API key is missing. Search functionality will be disabled.")

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def preprocess_text(text):
    return text.strip()

def summarize_text(text):
    try:
        response = openai.Completion.create(
            engine="gpt-4-turbo",  
            prompt=f"Summarize and analyze: {text}",
            max_tokens=MAX_TOKENS
        )
        summary = response.get('choices', [{}])[0].get('text', '').strip()
        if not summary:
            raise ValueError("Empty summary returned by GPT.")
        return summary
    except Exception as e:
        logging.error(f"GPT summarization error: {e}")
        raise

def search_alternative_sources(query, retry_count=0):
    if retry_count >= SEARCH_RETRY_LIMIT:
        logging.error(f"Search retry limit reached for query: {query}")
        return []

    search_url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": bing_api_key}
    params = {"q": query, "count": SEARCH_RESULT_COUNT, "safeSearch": "Strict"}

    try:
        response = requests.get(search_url, headers=headers, params=params)
        response.raise_for_status()
        search_results = response.json()

        links = [
            {
                "title": result.get("name"),
                "url": result.get("url"),
                "snippet": result.get("snippet")
            }
            for result in search_results.get("webPages", {}).get("value", [])
        ]

        unique_links = {link['url']: link for link in links}.values()
        return list(unique_links)

    except requests.RequestException as e:
        logging.warning(f"Search API request failed: {e}, retrying...")
        return search_alternative_sources(query, retry_count + 1)

@app.route('/analyze', methods=['POST'])
def analyze_content():
    try:
        data = request.json
        text = preprocess_text(data.get('content', ''))
        metadata = data.get('metadata', {})
        
        if not text:
            return jsonify({'error': 'No content provided'}), 400

        summary = summarize_text(text)
        alternative_sources = search_alternative_sources(summary)

        return jsonify({
            'summary': summary,
            'metadata': metadata,
            'alternative_sources': alternative_sources
        })

    except Exception as e:
        logging.error(f"Error in /analyze endpoint: {e}")
        return jsonify({'error': str(e)}), 500