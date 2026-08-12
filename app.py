import os
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

PORT = int(os.environ.get("PORT", 5000))

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ====== ROUTES ======

@app.route('/')
def index():
    """Halaman setup (masukin API Key)"""
    return render_template('index.html')

@app.route('/chat')
def chat():
    """Halaman chat"""
    return render_template('chat.html')

@app.route('/api/chat', methods=['POST'])
def chat_api():
    """Chat pake OpenRouter API (API Key dari frontend)"""
    data = request.get_json()
    api_key = data.get('api_key', '').strip()
    model = data.get('model', 'mistralai/mistral-7b-instruct:free')
    message = data.get('message', '').strip()
    history = data.get('history', [])

    if not api_key:
        return jsonify({'error': 'API Key diperlukan'}), 400

    if not message:
        return jsonify({'error': 'Pesan tidak boleh kosong'}), 400

    # Build messages
    messages = [
        {"role": "system", "content": "Kamu adalah CobaltAI, asisten AI yang cerdas dan membantu. Jawab dengan bahasa Indonesia yang baik."}
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

    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        ai_response = result['choices'][0]['message']['content']
        
        return jsonify({
            'success': True,
            'response': ai_response
        })
        
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request timeout, coba lagi'}), 504
    except requests.exceptions.RequestException as e:
        print(f"OpenRouter error: {e}")
        return jsonify({'error': 'Gagal menghubungi OpenRouter. Cek API Key.'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    return jsonify({'status': 'online', 'version': '3.0.0'})

if __name__ == '__main__':
    print("🚀 CobaltAI running on http://0.0.0.0:" + str(PORT))
    app.run(host='0.0.0.0', port=PORT, debug=False)
