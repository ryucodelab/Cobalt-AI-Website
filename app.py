import os
import re
import bcrypt
import jwt
import psycopg2
import psycopg2.extras
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Konfigurasi
app.secret_key = os.environ.get("JWT_SECRET", "default-secret-key-ganti-di-vercel")

# Environment variables
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Model default
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "mistralai/mistral-7b-instruct:free")

def get_db_connection():
    """Koneksi ke Neon PostgreSQL"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def hash_password(password):
    """Hash password pake bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password, hashed):
    """Verifikasi password"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_token(user_id, username):
    """Generate JWT token"""
    payload = {
        'user_id': user_id,
        'username': username,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, app.secret_key, algorithm='HS256')

def decode_token(token):
    """Decode JWT token"""
    try:
        payload = jwt.decode(token, app.secret_key, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_user_from_token(token):
    """Ambil user dari token"""
    payload = decode_token(token)
    if not payload:
        return None
    
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id, username FROM users WHERE id = %s", (payload['user_id'],))
        user = cur.fetchone()
        cur.close()
        conn.close()
        return dict(user) if user else None
    except Exception as e:
        print(f"Error getting user: {e}")
        return None

def call_openrouter(user_message, history=None):
    """Panggil OpenRouter API"""
    if not OPENROUTER_API_KEY:
        return "OpenRouter API key tidak dikonfigurasi. Mohon set di environment variables."
    
    messages = []
    
    # System prompt
    messages.append({
        "role": "system",
        "content": "Kamu adalah CobaltAI, asisten AI yang cerdas, kreatif, dan membantu. Berikan jawaban yang informatif, akurat, dan mudah dipahami. Gunakan bahasa Indonesia yang baik dan benar."
    })
    
    # History (jika ada)
    if history:
        for h in history:
            messages.append({"role": h['role'], "content": h['content']})
    
    # Pesan user
    messages.append({"role": "user", "content": user_message})
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://cobaltai.vercel.app",
        "X-Title": "CobaltAI"
    }
    
    data = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048
    }
    
    try:
        response = requests.post(OPENROUTER_URL, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except requests.exceptions.Timeout:
        return "Maaf, waktu permintaan habis. Silakan coba lagi."
    except requests.exceptions.RequestException as e:
        print(f"OpenRouter error: {e}")
        return "Maaf, terjadi kesalahan saat menghubungi AI. Silakan coba lagi."
    except Exception as e:
        print(f"Error: {e}")
        return "Maaf, terjadi kesalahan. Silakan coba lagi."

# ==================== ROUTES ====================

@app.route('/')
def index():
    """Halaman utama"""
    return render_template('index.html')

@app.route('/api/health')
def health():
    """Cek status server"""
    return jsonify({
        'status': 'online',
        'version': '2.0.0',
        'database': 'connected' if get_db_connection() else 'disconnected',
        'openrouter': 'configured' if OPENROUTER_API_KEY else 'not configured'
    })

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register user baru"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'error': 'Username dan password wajib diisi'}), 400
    
    if len(username) < 3 or len(username) > 50:
        return jsonify({'error': 'Username minimal 3 dan maksimal 50 karakter'}), 400
    
    if len(password) < 6:
        return jsonify({'error': 'Password minimal 6 karakter'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database tidak terhubung'}), 500
    
    try:
        cur = conn.cursor()
        
        # Cek username udah dipake
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Username sudah digunakan'}), 400
        
        # Insert user
        hashed = hash_password(password)
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, hashed)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        
        # Generate token
        token = generate_token(user_id, username)
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {'id': user_id, 'username': username}
        })
        
    except Exception as e:
        print(f"Register error: {e}")
        return jsonify({'error': 'Terjadi kesalahan'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'error': 'Username dan password wajib diisi'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database tidak terhubung'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if not user:
            return jsonify({'error': 'Username atau password salah'}), 401
        
        if not verify_password(password, user['password_hash']):
            return jsonify({'error': 'Username atau password salah'}), 401
        
        token = generate_token(user['id'], user['username'])
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {'id': user['id'], 'username': user['username']}
        })
        
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Terjadi kesalahan'}), 500

@app.route('/api/auth/me', methods=['GET'])
def me():
    """Cek user saat ini"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token tidak ditemukan'}), 401
    
    user = get_user_from_token(token)
    if not user:
        return jsonify({'error': 'Token tidak valid'}), 401
    
    return jsonify({'user': user})

@app.route('/api/chat', methods=['POST'])
def chat():
    """Kirim pesan ke AI"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token tidak ditemukan'}), 401
    
    user = get_user_from_token(token)
    if not user:
        return jsonify({'error': 'Token tidak valid'}), 401
    
    data = request.get_json()
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'error': 'Pesan tidak boleh kosong'}), 400
    
    # Ambil history dari DB (5 chat terakhir)
    conn = get_db_connection()
    history = []
    if conn:
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(
                "SELECT role, content FROM history WHERE user_id = %s ORDER BY created_at DESC LIMIT 10",
                (user['id'],)
            )
            rows = cur.fetchall()
            history = [dict(row) for row in reversed(rows)]  # Balik urutan
            cur.close()
            conn.close()
        except Exception as e:
            print(f"History error: {e}")
    
    # Panggil AI
    ai_response = call_openrouter(message, history)
    
    # Simpan ke database
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO history (user_id, role, content) VALUES (%s, %s, %s)",
                (user['id'], 'user', message)
            )
            cur.execute(
                "INSERT INTO history (user_id, role, content) VALUES (%s, %s, %s)",
                (user['id'], 'assistant', ai_response)
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Save history error: {e}")
    
    return jsonify({
        'success': True,
        'response': ai_response
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    """Ambil history chat user"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token tidak ditemukan'}), 401
    
    user = get_user_from_token(token)
    if not user:
        return jsonify({'error': 'Token tidak valid'}), 401
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database tidak terhubung'}), 500
    
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "SELECT id, role, content, created_at FROM history WHERE user_id = %s ORDER BY created_at DESC LIMIT 50",
            (user['id'],)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        history = []
        for row in rows:
            history.append({
                'id': row['id'],
                'role': row['role'],
                'content': row['content'],
                'created_at': row['created_at'].isoformat()
            })
        
        return jsonify({'history': history})
        
    except Exception as e:
        print(f"History error: {e}")
        return jsonify({'error': 'Terjadi kesalahan'}), 500

@app.route('/api/history/<int:history_id>', methods=['DELETE'])
def delete_history(history_id):
    """Hapus satu history"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token tidak ditemukan'}), 401
    
    user = get_user_from_token(token)
    if not user:
        return jsonify({'error': 'Token tidak valid'}), 401
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database tidak terhubung'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM history WHERE id = %s AND user_id = %s",
            (history_id, user['id'])
        )
        conn.commit()
        affected = cur.rowcount
        cur.close()
        conn.close()
        
        if affected == 0:
            return jsonify({'error': 'History tidak ditemukan'}), 404
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Delete history error: {e}")
        return jsonify({'error': 'Terjadi kesalahan'}), 500

@app.route('/api/history/clear', methods=['DELETE'])
def clear_history():
    """Hapus semua history user"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token tidak ditemukan'}), 401
    
    user = get_user_from_token(token)
    if not user:
        return jsonify({'error': 'Token tidak valid'}), 401
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database tidak terhubung'}), 500
    
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM history WHERE user_id = %s", (user['id'],))
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Clear history error: {e}")
        return jsonify({'error': 'Terjadi kesalahan'}), 500

# ==================== MAIN ====================

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 CobaltAI - Backend")
    print("=" * 50)
    print(f"📍 Running on: http://0.0.0.0:{os.environ.get('PORT', 5000)}")
    print(f"🔑 OpenRouter: {'✅ Configured' if OPENROUTER_API_KEY else '❌ NOT SET'}")
    print(f"💾 Database: {'✅ Connected' if get_db_connection() else '❌ NOT CONNECTED'}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
