from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

def get_db():
    conn = sqlite3.connect('stock.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        workplace TEXT NOT NULL,
        role TEXT DEFAULT 'manager'
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        workplace TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT NOT NULL,
        product_type TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        seller_id INTEGER NOT NULL,
        seller_name TEXT NOT NULL,
        workplace TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        seller_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Create default manager account if it doesn't exist
    manager_exists = conn.execute('SELECT COUNT(*) as count FROM users WHERE role = "manager"').fetchone()['count']
    if manager_exists == 0:
        conn.execute('INSERT INTO users (username, password, workplace, role) VALUES (?, ?, ?, ?)',
                    ('admin', 'admin123', 'Head Office', 'manager'))
    
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?',
                          (data['username'], data['password'])).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['workplace'] = user['workplace']
            session['role'] = user['role']
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    conn = get_db()
    try:
        # Force all registrations to be sellers only
        conn.execute('INSERT INTO users (username, password, workplace, role) VALUES (?, ?, ?, ?)',
                    (data['username'], data['password'], data['workplace'], 'seller'))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'message': 'Username already exists'}), 400

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/user', methods=['GET'])
@login_required
def get_user():
    return jsonify({'id': session['user_id'], 'username': session['username'], 'workplace': session['workplace'], 'role': session['role']})

@app.route('/api/products', methods=['GET'])
@login_required
def get_products():
    conn = get_db()
    if session['role'] == 'seller':
        products = conn.execute('SELECT * FROM products WHERE user_id = ? ORDER BY name', (session['user_id'],)).fetchall()
    else:
        products = conn.execute('''SELECT p.*, u.username as owner_name 
                                   FROM products p 
                                   JOIN users u ON p.user_id = u.id 
                                   ORDER BY p.workplace, p.name''').fetchall()
    conn.close()
    return jsonify([dict(p) for p in products])

@app.route('/api/products', methods=['POST'])
@login_required
def add_product():
    data = request.json
    conn = get_db()
    conn.execute('INSERT INTO products (name, type, quantity, workplace, user_id) VALUES (?, ?, ?, ?, ?)',
                (data['name'], data['type'], data['quantity'], session['workplace'], session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/products/add-for-user', methods=['POST'])
@login_required
def add_product_for_user():
    if session['role'] != 'manager':
        return jsonify({'success': False}), 403
    
    data = request.json
    conn = get_db()
    user = conn.execute('SELECT workplace FROM users WHERE id = ?', (data['user_id'],)).fetchone()
    if user:
        conn.execute('INSERT INTO products (name, type, quantity, workplace, user_id) VALUES (?, ?, ?, ?, ?)',
                    (data['name'], data['type'], data['quantity'], user['workplace'], data['user_id']))
        conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/products/<int:id>/purchase', methods=['POST'])
@login_required
def purchase_product(id):
    data = request.json
    qty = data['quantity']
    conn = get_db()
    product = conn.execute('SELECT quantity, user_id FROM products WHERE id = ?', (id,)).fetchone()
    
    if not product or product['quantity'] < qty:
        conn.close()
        return jsonify({'success': False, 'message': 'Insufficient stock'}), 400
    
    conn.execute('UPDATE products SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (qty, id))
    conn.execute('INSERT INTO sales (product_id, seller_id, quantity) VALUES (?, ?, ?)', (id, product['user_id'], qty))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/products/<int:id>', methods=['DELETE'])
@login_required
def delete_product(id):
    conn = get_db()
    conn.execute('DELETE FROM products WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/requests', methods=['GET'])
@login_required
def get_requests():
    conn = get_db()
    if session['role'] == 'manager':
        requests = conn.execute('SELECT * FROM requests WHERE status = "pending" ORDER BY created_at DESC').fetchall()
    else:
        requests = conn.execute('SELECT * FROM requests WHERE seller_id = ? ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in requests])

@app.route('/api/requests', methods=['POST'])
@login_required
def create_request():
    data = request.json
    conn = get_db()
    conn.execute('INSERT INTO requests (product_name, product_type, quantity, seller_id, seller_name, workplace) VALUES (?, ?, ?, ?, ?, ?)',
                (data['name'], data['type'], data['quantity'], session['user_id'], session['username'], session['workplace']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/requests/<int:id>/approve', methods=['POST'])
@login_required
def approve_request(id):
    if session['role'] != 'manager':
        return jsonify({'success': False}), 403
    
    conn = get_db()
    req = conn.execute('SELECT * FROM requests WHERE id = ?', (id,)).fetchone()
    if req:
        conn.execute('INSERT INTO products (name, type, quantity, workplace, user_id) VALUES (?, ?, ?, ?, ?)',
                    (req['product_name'], req['product_type'], req['quantity'], req['workplace'], req['seller_id']))
        conn.execute('UPDATE requests SET status = "approved" WHERE id = ?', (id,))
        conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/requests/<int:id>/reject', methods=['POST'])
@login_required
def reject_request(id):
    if session['role'] != 'manager':
        return jsonify({'success': False}), 403
    
    conn = get_db()
    conn.execute('UPDATE requests SET status = "rejected" WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    if session['role'] != 'manager':
        return jsonify({'success': False}), 403
    
    conn = get_db()
    users = conn.execute('SELECT id, username, role, workplace FROM users ORDER BY role, username').fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/users/<int:id>', methods=['DELETE'])
@login_required
def delete_user(id):
    if session['role'] != 'manager':
        return jsonify({'success': False}), 403
    
    conn = get_db()
    conn.execute('DELETE FROM products WHERE user_id = ?', (id,))
    conn.execute('DELETE FROM users WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/statistics', methods=['GET'])
@login_required
def get_statistics():
    if session['role'] != 'manager':
        return jsonify({'success': False}), 403
    
    conn = get_db()
    
    total_products = conn.execute('SELECT SUM(quantity) as total FROM products').fetchone()['total'] or 0
    total_sellers = conn.execute('SELECT COUNT(*) as count FROM users WHERE role = "seller"').fetchone()['count']
    low_stock_items = conn.execute('SELECT COUNT(*) as count FROM products WHERE quantity < 10').fetchone()['count']
    pending_requests = conn.execute('SELECT COUNT(*) as count FROM requests WHERE status = "pending"').fetchone()['count']
    
    top_sellers = conn.execute('''SELECT u.id, u.username as seller, 
                                   COALESCE(SUM(s.quantity), 0) as total_sales,
                                   COUNT(DISTINCT p.id) as product_count,
                                   COALESCE(SUM(p.quantity), 0) as current_stock
                                   FROM users u
                                   LEFT JOIN products p ON u.id = p.user_id
                                   LEFT JOIN sales s ON u.id = s.seller_id
                                   WHERE u.role = "seller"
                                   GROUP BY u.id, u.username
                                   ORDER BY total_sales DESC, u.username ASC''').fetchall()
    
    conn.close()
    
    return jsonify({
        'total_products': total_products,
        'total_sellers': total_sellers,
        'low_stock_items': low_stock_items,
        'pending_requests': pending_requests,
        'top_sellers': [dict(s) for s in top_sellers]
    })

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
