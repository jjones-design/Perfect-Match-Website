from flask import Flask, request, jsonify, render_template
from datetime import datetime
import cv2
import numpy as np
import os
import requests
import mysql.connector  # Ensure mysql-connector-python is installed

app = Flask(__name__)

UPLOAD_FOLDER = 'static/uploads'
RESULT_FOLDER = 'static/results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# Database Connection Function
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="perfectmatch_db"
    )

def create_bar(height, width, color):
    """Creates a color bar for visualization"""
    bar = np.zeros((height, width, 3), np.uint8)
    bar[:] = color
    return bar

def rgb_to_hex(color):
    """Convert a BGR color to HEX format"""
    return "#{:02x}{:02x}{:02x}".format(int(color[2]), int(color[1]), int(color[0]))

@app.route('/')
def index():
    """Render the HTML page"""
    return render_template('index.html')

@app.route('/process-image', methods=['POST'])
def process_image():
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image uploaded"}), 400

        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        # Save the uploaded image
        image_path = os.path.join(UPLOAD_FOLDER, 'uploaded.jpg')
        image_file.save(image_path)

        # Load and process image
        img = cv2.imread(image_path)
        height, width, _ = np.shape(img)

        # Reshape image data for clustering
        data = np.reshape(img, (height * width, 3))
        data = np.float32(data)

        # K-Means clustering for dominant colors
        number_clusters = 3
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(data, number_clusters, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

        # Convert BGR to HEX
        hex_colors = [rgb_to_hex(color) for color in centers]

        return jsonify({
            "message": "Processing successful",
            "uploaded_image": f"/{UPLOAD_FOLDER}/uploaded.jpg",
            "colors": hex_colors  # Send extracted colors to frontend
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Inserts data in detected_colors table
@app.route('/save-color', methods=['POST'])
def save_color():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        hex_code = data.get('hex_code')

        if not hex_code:
            return jsonify({"error": "Missing required hex_code field"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert into detected_colors table
        cursor.execute("INSERT INTO detected_colors (hex_code) VALUES (%s)", (hex_code,))

        # Commit the transaction
        conn.commit()

        return jsonify({"message": "Color saved successfully!"})

    except mysql.connector.Error as err:
        if conn:
            conn.rollback()  # Rollback the transaction in case of error
        return jsonify({"error": str(err)})

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_detected_color():
    """Retrieve the last detected color from the database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Retrieve the latest detected color
        cursor.execute("SELECT hex_code FROM detected_colors ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        return result['hex_code'] if result else None
    except Exception as e:
        return None

@app.route('/get_color', methods=['GET'])
def get_color():
    detected_color = get_detected_color()
    if detected_color:
        return jsonify({"hex_code": detected_color})
    else:
        return jsonify({"error": "No detected color found"}), 404

def hex_to_rgb(hex_color):
    """Convert HEX to RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def color_distance(rgb1, rgb2):
    """Calculate Euclidean distance between two RGB colors"""
    return ((rgb1[0] - rgb2[0]) ** 2 + (rgb1[1] - rgb2[1]) ** 2 + (rgb1[2] - rgb2[2]) ** 2) ** 0.5

@app.route('/find-match', methods=['GET'])
def find_match():
    """Retrieve the closest foundation shade match"""
    try:
        detected_color = get_detected_color()
        if not detected_color:
            return jsonify({"error": "No detected color found"}), 404

        detected_rgb = hex_to_rgb(detected_color)

        # Fetch foundation shades from the database
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, brand, hex_code FROM foundation_shades")
        shades = cursor.fetchall()
        cursor.close()
        conn.close()

        if not shades:
            return jsonify({"error": "No foundation shades available"}), 404

        # Find the closest match
        closest_match = None
        min_distance = float('inf')

        for shade in shades:
            shade_rgb = hex_to_rgb(shade['hex_code'])
            distance = color_distance(detected_rgb, shade_rgb)

            if distance < min_distance:
                min_distance = distance
                closest_match = shade

        if closest_match:
            return jsonify({
                "match": closest_match['name'],
                "brand": closest_match['brand'],
                "hex": closest_match['hex_code']
            })
        else:
            return jsonify({"error": "No match found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# //Inserts data into user_results table
@app.route('/save-shade', methods=['POST'])   
def save_shade():
    try:
        data = request.get_json()  # Get data from the request
        user_id = data.get('user_id')
        brand_name = data.get('brand_name')
        shade_name = data.get('shade_name')

        if not all([user_id, brand_name, shade_name]):  
            return jsonify({"error": "Missing required fields"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert into user_results table
        query = "INSERT INTO user_results (user_id, brand_name, shade_name, created_at) VALUES (%s, %s, %s, %s)"
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        values = (user_id, brand_name, shade_name, created_at)

        cursor.execute(query, values)
        conn.commit()
        
        return jsonify({"message": "Shade saved successfully!"}), 200
    except mysql.connector.Error as err:
        conn.rollback()  # Rollback on error
        return jsonify({"error": str(err)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)