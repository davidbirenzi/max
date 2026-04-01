from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stock.db')
ALLOWED_PRODUCTS = {
    'mintice',
    'blue berry ice',
    'strawberry watermelon',
    'grape ice',
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_product_name(name):
    return (name or '').strip().lower()

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        workplace TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0
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
        request_type TEXT DEFAULT 'stock_add',
        product_id INTEGER,
        product_name TEXT NOT NULL,
        product_type TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        seller_id INTEGER NOT NULL,
        seller_name TEXT NOT NULL,
        workplace TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    request_columns = {row['name'] for row in conn.execute("PRAGMA table_info(requests)").fetchall()}
    if 'request_type' not in request_columns:
        conn.execute("ALTER TABLE requests ADD COLUMN request_type TEXT DEFAULT 'stock_add'")
    if 'product_id' not in request_columns:
        conn.execute("ALTER TABLE requests ADD COLUMN product_id INTEGER")
    conn.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        seller_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
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
            session['is_admin'] = bool(user['is_admin'])
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    conn = get_db()
    try:
        conn.execute('INSERT INTO users (username, password, workplace, is_admin) VALUES (?, ?, ?, 0)',
                    (data['username'], data['password'], data['workplace']))
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
    role = 'manager' if session['is_admin'] else 'seller'
    return jsonify({'id': session['user_id'], 'username': session['username'], 'workplace': session['workplace'], 'is_admin': session['is_admin'], 'role': role})

@app.route('/api/products', methods=['GET'])
@login_required
def get_products():
    conn = get_db()
    if not session['is_admin']:
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
    if not session['is_admin']:
        return jsonify({'success': False, 'message': 'Only admins can add products'}), 403
    data = request.json
    name = normalize_product_name(data.get('name'))
    try:
        quantity = int(data['quantity'])
    except (TypeError, ValueError, KeyError):
        return jsonify({'success': False, 'message': 'Invalid quantity'}), 400
    if name not in ALLOWED_PRODUCTS:
        return jsonify({'success': False, 'message': 'Invalid product'}), 400
    if quantity < 0:
        return jsonify({'success': False, 'message': 'Invalid quantity'}), 400
    conn = get_db()
    conn.execute('INSERT INTO products (name, type, quantity, workplace, user_id) VALUES (?, ?, ?, ?, ?)',
                (name, '', quantity, session['workplace'], session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/products/add-for-user', methods=['POST'])
@login_required
def add_product_for_user():
    if not session['is_admin']:
        return jsonify({'success': False}), 403
    
    data = request.json
    name = normalize_product_name(data.get('name'))
    try:
        quantity = int(data['quantity'])
    except (TypeError, ValueError, KeyError):
        return jsonify({'success': False, 'message': 'Invalid quantity'}), 400
    if name not in ALLOWED_PRODUCTS:
        return jsonify({'success': False, 'message': 'Invalid product'}), 400
    if quantity < 0:
        return jsonify({'success': False, 'message': 'Invalid quantity'}), 400
    conn = get_db()
    user = conn.execute('SELECT workplace FROM users WHERE id = ?', (data['user_id'],)).fetchone()
    if user:
        conn.execute('INSERT INTO products (name, type, quantity, workplace, user_id) VALUES (?, ?, ?, ?, ?)',
                    (name, '', quantity, user['workplace'], data['user_id']))
        conn.commit()
    conn.close()
    return jsonify({'success': True})

def _can_manage_product(product_row):
    if not product_row:
        return False
    if session['is_admin']:
        return True
    return product_row['user_id'] == session['user_id']


@app.route('/api/products/<int:id>/purchase', methods=['POST'])
@login_required
def purchase_product(id):
    data = request.json or {}
    try:
        qty = int(data['quantity'])
    except (TypeError, ValueError, KeyError):
        return jsonify({'success': False, 'message': 'Invalid quantity'}), 400
    if qty <= 0:
        return jsonify({'success': False, 'message': 'Invalid quantity'}), 400
    conn = get_db()
    product = conn.execute('SELECT quantity, user_id FROM products WHERE id = ?', (id,)).fetchone()

    if not product or not _can_manage_product(product):
        conn.close()
        return jsonify({'success': False, 'message': 'Not found or forbidden'}), 403

    if product['quantity'] < qty:
        conn.close()
        return jsonify({'success': False, 'message': 'Insufficient stock'}), 400

    if session['is_admin']:
        conn.execute('UPDATE products SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (qty, id))
        conn.execute('INSERT INTO sales (product_id, seller_id, quantity) VALUES (?, ?, ?)', (id, product['user_id'], qty))
    else:
        product_info = conn.execute('SELECT name, type, workplace FROM products WHERE id = ?', (id,)).fetchone()
        conn.execute(
            '''INSERT INTO requests
               (request_type, product_id, product_name, product_type, quantity, seller_id, seller_name, workplace)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            ('sale', id, product_info['name'], product_info['type'], qty, session['user_id'], session['username'], product_info['workplace'])
        )
    conn.commit()
    conn.close()
    if session['is_admin']:
        return jsonify({'success': True, 'mode': 'completed'})
    return jsonify({'success': True, 'mode': 'requested', 'message': 'Sale request sent for approval'})


@app.route('/api/products/batch-purchase', methods=['POST'])
@login_required
def batch_purchase():
    raw = (request.json or {}).get('items') or []
    items = []
    for it in raw:
        try:
            pid = int(it['id'])
            q = int(it['quantity'])
            if q > 0:
                items.append((pid, q))
        except (TypeError, ValueError, KeyError):
            return jsonify({'success': False, 'message': 'Invalid item payload'}), 400
    if not items:
        return jsonify({'success': False, 'message': 'No line items with quantity > 0'}), 400

    merged = {}
    for pid, q in items:
        merged[pid] = merged.get(pid, 0) + q
    items = list(merged.items())

    conn = get_db()
    updates = []
    for pid, qty in items:
        product = conn.execute('SELECT quantity, user_id FROM products WHERE id = ?', (pid,)).fetchone()
        if not product or not _can_manage_product(product):
            conn.close()
            return jsonify({'success': False, 'message': 'Not found or forbidden'}), 403
        if product['quantity'] < qty:
            conn.close()
            return jsonify({'success': False, 'message': 'Insufficient stock on one or more products'}), 400
        updates.append((qty, pid, product['user_id']))

    if session['is_admin']:
        for qty, pid, seller_id in updates:
            conn.execute(
                'UPDATE products SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (qty, pid),
            )
            conn.execute(
                'INSERT INTO sales (product_id, seller_id, quantity) VALUES (?, ?, ?)',
                (pid, seller_id, qty),
            )
    else:
        for qty, pid, seller_id in updates:
            product_info = conn.execute('SELECT name, type, workplace FROM products WHERE id = ?', (pid,)).fetchone()
            conn.execute(
                '''INSERT INTO requests
                   (request_type, product_id, product_name, product_type, quantity, seller_id, seller_name, workplace)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                ('sale', pid, product_info['name'], product_info['type'], qty, seller_id, session['username'], product_info['workplace'])
            )
    conn.commit()
    conn.close()
    if session['is_admin']:
        return jsonify({'success': True, 'mode': 'completed'})
    return jsonify({'success': True, 'mode': 'requested', 'message': 'Sale requests sent for approval'})


@app.route('/api/products/<int:id>/quantity', methods=['PATCH'])
@login_required
def set_product_quantity(id):
    if not session['is_admin']:
        return jsonify({'success': False, 'message': 'Only admins can change stock quantities'}), 403
    data = request.json or {}
    try:
        new_qty = int(data['quantity'])
    except (TypeError, ValueError, KeyError):
        return jsonify({'success': False, 'message': 'quantity required'}), 400
    if new_qty < 0:
        return jsonify({'success': False, 'message': 'Quantity cannot be negative'}), 400

    conn = get_db()
    product = conn.execute('SELECT user_id FROM products WHERE id = ?', (id,)).fetchone()
    if not product or not _can_manage_product(product):
        conn.close()
        return jsonify({'success': False, 'message': 'Not found or forbidden'}), 403

    conn.execute('UPDATE products SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (new_qty, id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/products/<int:id>', methods=['DELETE'])
@login_required
def delete_product(id):
    if not session['is_admin']:
        return jsonify({'success': False, 'message': 'Only stock managers can delete products'}), 403
    conn = get_db()
    product = conn.execute('SELECT id FROM products WHERE id = ?', (id,)).fetchone()
    if not product:
        conn.close()
        return jsonify({'success': False, 'message': 'Not found'}), 404
    conn.execute('DELETE FROM products WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/requests', methods=['GET'])
@login_required
def get_requests():
    conn = get_db()
    if session['is_admin']:
        requests = conn.execute('SELECT * FROM requests WHERE status = "pending" ORDER BY created_at DESC').fetchall()
    else:
        requests = conn.execute('SELECT * FROM requests WHERE seller_id = ? ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in requests])

@app.route('/api/requests', methods=['POST'])
@login_required
def create_request():
    data = request.json
    name = normalize_product_name(data.get('name'))
    try:
        quantity = int(data['quantity'])
    except (TypeError, ValueError, KeyError):
        return jsonify({'success': False, 'message': 'Invalid quantity'}), 400
    if name not in ALLOWED_PRODUCTS:
        return jsonify({'success': False, 'message': 'Invalid product'}), 400
    if quantity < 0:
        return jsonify({'success': False, 'message': 'Invalid quantity'}), 400
    conn = get_db()
    conn.execute(
        '''INSERT INTO requests
           (request_type, product_id, product_name, product_type, quantity, seller_id, seller_name, workplace)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        ('stock_add', None, name, '', quantity, session['user_id'], session['username'], session['workplace'])
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/requests/<int:id>/approve', methods=['POST'])
@login_required
def approve_request(id):
    if not session['is_admin']:
        return jsonify({'success': False}), 403
    
    conn = get_db()
    req = conn.execute('SELECT * FROM requests WHERE id = ?', (id,)).fetchone()
    if req:
        if req['request_type'] == 'sale':
            product = conn.execute('SELECT id, quantity, user_id FROM products WHERE id = ?', (req['product_id'],)).fetchone()
            if not product or product['user_id'] != req['seller_id']:
                conn.close()
                return jsonify({'success': False, 'message': 'Product no longer exists for this seller'}), 400
            if product['quantity'] < req['quantity']:
                conn.close()
                return jsonify({'success': False, 'message': 'Insufficient stock to approve this sale'}), 400
            conn.execute(
                'UPDATE products SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (req['quantity'], req['product_id'])
            )
            conn.execute(
                'INSERT INTO sales (product_id, seller_id, quantity) VALUES (?, ?, ?)',
                (req['product_id'], req['seller_id'], req['quantity'])
            )
        else:
            conn.execute('INSERT INTO products (name, type, quantity, workplace, user_id) VALUES (?, ?, ?, ?, ?)',
                        (req['product_name'], req['product_type'], req['quantity'], req['workplace'], req['seller_id']))
        conn.execute('UPDATE requests SET status = "approved" WHERE id = ?', (id,))
        conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/requests/<int:id>/reject', methods=['POST'])
@login_required
def reject_request(id):
    if not session['is_admin']:
        return jsonify({'success': False}), 403
    
    conn = get_db()
    conn.execute('UPDATE requests SET status = "rejected" WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    if not session['is_admin']:
        return jsonify({'success': False}), 403
    
    conn = get_db()
    users = conn.execute('SELECT id, username, is_admin, workplace FROM users ORDER BY is_admin DESC, username').fetchall()
    conn.close()
    out = []
    for u in users:
        d = dict(u)
        d['role'] = 'manager' if d['is_admin'] else 'seller'
        out.append(d)
    return jsonify(out)

@app.route('/api/users/<int:id>', methods=['DELETE'])
@login_required
def delete_user(id):
    if not session['is_admin']:
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
    if not session['is_admin']:
        return jsonify({'success': False}), 403
    
    conn = get_db()
    
    total_products = conn.execute('SELECT SUM(quantity) as total FROM products').fetchone()['total'] or 0
    total_sellers = conn.execute('SELECT COUNT(*) as count FROM users WHERE is_admin = 0').fetchone()['count']
    low_stock_items = conn.execute('SELECT COUNT(*) as count FROM products WHERE quantity < 10').fetchone()['count']
    pending_requests = conn.execute('SELECT COUNT(*) as count FROM requests WHERE status = "pending"').fetchone()['count']
    
    top_sellers = conn.execute('''SELECT u.id, u.username as seller, 
                                   COALESCE(SUM(s.quantity), 0) as total_sales,
                                   COUNT(DISTINCT p.id) as product_count,
                                   COALESCE(SUM(p.quantity), 0) as current_stock
                                   FROM users u
                                   LEFT JOIN products p ON u.id = p.user_id
                                   LEFT JOIN sales s ON u.id = s.seller_id
                                   WHERE u.is_admin = 0
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

@app.route('/setup-admin', methods=['GET', 'POST'])
def setup_admin():
    conn = get_db()
    admin_exists = conn.execute('SELECT COUNT(*) as count FROM users WHERE is_admin = 1').fetchone()['count']
    if admin_exists:
        conn.close()
        return 'Admin already exists.', 403
    if request.method == 'POST':
        data = request.form
        try:
            conn.execute('INSERT INTO users (username, password, workplace, is_admin) VALUES (?, ?, ?, 1)',
                        (data['username'], data['password'], data['workplace']))
            conn.commit()
            conn.close()
            return 'Admin created successfully. Delete or disable this route now.'
        except sqlite3.IntegrityError:
            conn.close()
            return 'Username already exists.', 400
    conn.close()
    return '''
        <form method="post">
            Username: <input name="username"><br>
            Password: <input name="password" type="password"><br>
            Workplace: <input name="workplace"><br>
            <button type="submit">Create Admin</button>
        </form>
    '''

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
