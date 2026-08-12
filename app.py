import os
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

PORT = int(os.environ.get("PORT", 5000))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat')
def chat():
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
def chat_api():
    try:
        data = request.get_json()
        
        api_key = data.get('api_key', '').strip()
        model = data.get('model', 'mistralai/mistral-7b-instruct:free')
        message = data.get('message', '').strip()
        history = data.get('history', [])

        if not api_key:
            return jsonify({'error': 'API Key diperlukan'}), 400

        if not message:
            return jsonify({'error': 'Pesan tidak boleh kosong'}), 400

        messages = [
            {"role": "system", "content": "Kamu adalah CobaltAI, asisten AI yang cerdas. Jawab dalam bahasa Indonesia."}
        ]
        
        for h in history:
            messages.append({"role": h['role'], "content": h['content']})
        
        messages.append({"role": "user", "content": message})

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2048
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            error_data = response.json() if response.text else {}
            error_msg = error_data.get('error', {}).get('message', 'Unknown error')
            return jsonify({'error': f'OpenRouter: {error_msg}'}), response.status_code
        
        result = response.json()
        ai_response = result['choices'][0]['message']['content']
        
        return jsonify({
            'success': True,
            'response': ai_response
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    return jsonify({'status': 'online', 'version': '3.0.0'})

if __name__ == '__main__':
    print("🚀 CobaltAI running on http://0.0.0.0:" + str(PORT))
    app.run(host='0.0.0.0', port=PORT, debug=False)
