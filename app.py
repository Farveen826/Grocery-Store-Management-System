from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime, date
from decimal import Decimal
import os

app = Flask(__name__)
CORS(app)

# Database setup
def init_db():
    conn = sqlite3.connect('grocery_store.db')
    cursor = conn.cursor()
    
    # Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            reorder_level INTEGER DEFAULT 10,
            supplier TEXT,
            barcode TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Sales table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    
    # Customers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert sample data
    cursor.execute('SELECT COUNT(*) FROM products')
    if cursor.fetchone()[0] == 0:
        sample_products = [
            ('Apples', 'Fruits', 2.99, 100, 20, 'Fresh Farms', '1234567890'),
            ('Bananas', 'Fruits', 1.99, 150, 30, 'Tropical Supply', '1234567891'),
            ('Milk', 'Dairy', 3.49, 50, 10, 'Dairy Co', '1234567892'),
            ('Bread', 'Bakery', 2.49, 75, 15, 'Local Bakery', '1234567893'),
            ('Eggs', 'Dairy', 4.99, 60, 12, 'Farm Fresh', '1234567894'),
            ('Rice', 'Grains', 5.99, 80, 20, 'Grain Supply', '1234567895'),
            ('Chicken Breast', 'Meat', 8.99, 40, 8, 'Meat Market', '1234567896'),
            ('Tomatoes', 'Vegetables', 3.99, 90, 18, 'Garden Fresh', '1234567897'),
        ]
        
        cursor.executemany('''
            INSERT INTO products (name, category, price, quantity, reorder_level, supplier, barcode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', sample_products)
    
    conn.commit()
    conn.close()

# Helper function to get database connection
def get_db_connection():
    conn = sqlite3.connect('grocery_store.db')
    conn.row_factory = sqlite3.Row
    return conn

# Products endpoints
@app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products ORDER BY name').fetchall()
    conn.close()
    
    return jsonify([dict(product) for product in products])

@app.route('/api/products', methods=['POST'])
def add_product():
    data = request.json
    conn = get_db_connection()
    
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO products (name, category, price, quantity, reorder_level, supplier, barcode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'], data['category'], data['price'], 
            data['quantity'], data.get('reorder_level', 10), 
            data.get('supplier', ''), data.get('barcode', '')
        ))
        conn.commit()
        product_id = cursor.lastrowid
        conn.close()
        
        return jsonify({'message': 'Product added successfully', 'id': product_id}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Product with this barcode already exists'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    data = request.json
    conn = get_db_connection()
    
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE products 
        SET name=?, category=?, price=?, quantity=?, reorder_level=?, supplier=?, barcode=?
        WHERE id=?
    ''', (
        data['name'], data['category'], data['price'], 
        data['quantity'], data.get('reorder_level', 10), 
        data.get('supplier', ''), data.get('barcode', ''), product_id
    ))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Product not found'}), 404
    
    conn.commit()
    conn.close()
    return jsonify({'message': 'Product updated successfully'})

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id=?', (product_id,))
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Product not found'}), 404
    
    conn.commit()
    conn.close()
    return jsonify({'message': 'Product deleted successfully'})

# Sales endpoints
@app.route('/api/sales', methods=['POST'])
def make_sale():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if product exists and has enough quantity
        product = cursor.execute('SELECT * FROM products WHERE id=?', (data['product_id'],)).fetchone()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        if product['quantity'] < data['quantity']:
            return jsonify({'error': 'Insufficient quantity in stock'}), 400
        
        # Calculate total price
        total_price = product['price'] * data['quantity']
        
        # Record sale
        cursor.execute('''
            INSERT INTO sales (product_id, quantity, total_price)
            VALUES (?, ?, ?)
        ''', (data['product_id'], data['quantity'], total_price))
        
        # Update product quantity
        new_quantity = product['quantity'] - data['quantity']
        cursor.execute('UPDATE products SET quantity=? WHERE id=?', (new_quantity, data['product_id']))
        
        conn.commit()
        sale_id = cursor.lastrowid
        conn.close()
        
        return jsonify({
            'message': 'Sale completed successfully',
            'sale_id': sale_id,
            'total_price': total_price
        }), 201
        
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sales', methods=['GET'])
def get_sales():
    conn = get_db_connection()
    sales = conn.execute('''
        SELECT s.*, p.name as product_name, p.price as unit_price
        FROM sales s
        JOIN products p ON s.product_id = p.id
        ORDER BY s.sale_date DESC
        LIMIT 100
    ''').fetchall()
    conn.close()
    
    return jsonify([dict(sale) for sale in sales])

# Analytics endpoints
@app.route('/api/analytics/low-stock', methods=['GET'])
def get_low_stock():
    conn = get_db_connection()
    low_stock = conn.execute('''
        SELECT * FROM products 
        WHERE quantity <= reorder_level
        ORDER BY quantity ASC
    ''').fetchall()
    conn.close()
    
    return jsonify([dict(product) for product in low_stock])

@app.route('/api/analytics/sales-summary', methods=['GET'])
def get_sales_summary():
    conn = get_db_connection()
    
    # Today's sales
    today_sales = conn.execute('''
        SELECT SUM(total_price) as total, COUNT(*) as count
        FROM sales
        WHERE DATE(sale_date) = DATE('now')
    ''').fetchone()
    
    # This month's sales
    month_sales = conn.execute('''
        SELECT SUM(total_price) as total, COUNT(*) as count
        FROM sales
        WHERE strftime('%Y-%m', sale_date) = strftime('%Y-%m', 'now')
    ''').fetchone()
    
    # Top selling products
    top_products = conn.execute('''
        SELECT p.name, SUM(s.quantity) as total_sold, SUM(s.total_price) as revenue
        FROM sales s
        JOIN products p ON s.product_id = p.id
        WHERE strftime('%Y-%m', s.sale_date) = strftime('%Y-%m', 'now')
        GROUP BY p.id, p.name
        ORDER BY total_sold DESC
        LIMIT 5
    ''').fetchall()
    
    conn.close()
    
    return jsonify({
        'today': {
            'total': today_sales['total'] or 0,
            'count': today_sales['count'] or 0
        },
        'month': {
            'total': month_sales['total'] or 0,
            'count': month_sales['count'] or 0
        },
        'top_products': [dict(product) for product in top_products]
    })

# Main route to serve the frontend
@app.route('/')
def index():
    return render_template_string(open('templates/index.html').read())

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Run the app
    app.run(debug=True, host='0.0.0.0', port=5000)