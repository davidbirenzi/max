# Stock Management System

A simple, modern web application for managing product inventory across multiple locations.

## Features
- User authentication with workplace registration
- Add products with name, type, and quantity
- Automatic stock reduction on sales
- Real-time stock updates across all locations
- Multi-location visibility
- Clean, intuitive interface

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open browser and navigate to:
```
http://127.0.0.1:5000
```

## Usage

1. Register a new account with your workplace location
2. Login with your credentials
3. Add products to your inventory
4. View stock across all locations in real-time
5. Record sales by entering quantity and clicking "Sell"
6. Stock updates automatically across all users

## Security Note
Change the `secret_key` in app.py before production deployment.

By: Mucyo Jean de Dieu