# main.py - Pothole Detector Web Server

# --- 1. INITIAL SETUP ---
import os
import cv2
import time
import datetime
import certifi
import threading
from queue import Queue
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from ultralytics import YOLO
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client.pothole_db
potholes_collection = db.potholes
print("Successfully connected to MongoDB Atlas.")

# Load the YOLO model
model = YOLO('best.pt')

# Configure Flask App
app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

# Configure upload folders
UPLOAD_FOLDER = 'pothole_videos'
IMAGE_FOLDER = 'pothole_images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# A queue to hold data for the background database worker
data_queue = Queue()


# --- 2. DATABASE WORKER THREAD ---
# This function runs in a background thread to handle all database operations.
def database_worker():
    while True:
        # Get data from the queue sent by the video processor
        lat, lon, severity, frame, box_coords = data_queue.get()
        
        # Temporarily disabled the duplicate check for testing purposes
        # if not is_duplicate_mongo(lon, lat):
        
        image_path = save_pothole_image(frame, box_coords)
        save_to_database_mongo(lat, lon, severity, image_path)
        
        data_queue.task_done()


# --- 3. HELPER FUNCTIONS ---
def get_pothole_severity(box_w, box_h, frame_w, frame_h):
    """Calculates pothole severity based on its size relative to the frame."""
    pothole_area_ratio = (box_w * box_h) / (frame_w * frame_h)
    if pothole_area_ratio > 0.05: return "Large"
    if pothole_area_ratio > 0.01: return "Medium"
    return "Small"

def is_duplicate_mongo(lon, lat, max_distance_meters=10):
    """Checks for nearby potholes using MongoDB's geospatial query."""
    nearby_pothole = potholes_collection.find_one({
        "location": {
            "$nearSphere": {
                "$geometry": {"type": "Point", "coordinates": [lon, lat]},
                "$maxDistance": max_distance_meters
            }
        }
    })
    return nearby_pothole is not None

def save_pothole_image(frame, box_coords):
    """Crops the pothole from the frame and saves it as an image."""
    x1, y1, x2, y2 = box_coords
    pothole_img = frame[y1:y2, x1:x2]
    timestamp_str = time.strftime("%Y%m%d-%H%M%S")
    image_name = f"pothole_{timestamp_str}_{threading.get_ident()}.jpg"
    image_path = os.path.join(IMAGE_FOLDER, image_name)
    cv2.imwrite(image_path, pothole_img)
    return image_path

def save_to_database_mongo(lat, lon, severity, image_path):
    """Saves the pothole's data to MongoDB, including a public URL for the image."""
    image_filename = os.path.basename(image_path)
    
    # IMPORTANT: If deploying, change '127.0.0.1' to your server's public IP or domain.
    image_url = f"http://127.0.0.1:5001/images/{image_filename}"
    
    pothole_document = {
        "severity": severity,
        "image_path": image_path,    # The local path on the server
        "image_url": image_url,      # The public URL for the dashboard
        "location": {"type": "Point", "coordinates": [lon, lat]},
        "timestamp": datetime.datetime.now(datetime.UTC)
    }
    potholes_collection.insert_one(pothole_document)
    print(f"BACKGROUND SAVE: New {severity} pothole at ({lat}, {lon}) saved to MongoDB.")


# --- 4. VIDEO PROCESSING FUNCTION ---
def process_video_and_detect(video_path, latitude, longitude):
    """
    Opens a video file, runs pothole detection, and puts found potholes
    into the data_queue for the database worker.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file: {video_path}")
        return

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    last_queued_time = 0

    print(f"Starting detection on {video_path} for location ({latitude}, {longitude})...")

    while True:
        success, frame = cap.read()
        if not success:
            break # Video finished

        results = model(frame)

        for result in results:
            for box in result.boxes:
                # Throttle DB checks to every 5 seconds to avoid spamming
                if box.conf[0] > 0.6 and time.time() - last_queued_time > 5:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    severity = get_pothole_severity(x2 - x1, y2 - y1, frame_w, frame_h)
                    
                    # Add the detected pothole to the queue for processing
                    data_queue.put((latitude, longitude, severity, frame.copy(), (x1, y1, x2, y2)))
                    print(f"Detection: Found a potential {severity} pothole. Queued for database check.")
                    last_queued_time = time.time()

    cap.release()
    print(f"Finished processing video: {video_path}")


# --- 5. FLASK API ROUTES ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/api/report', methods=['POST'])
def handle_report():
    """Handles video upload and starts the detection process in a new thread."""
    if 'video' not in request.files:
        return jsonify({"error": "No video file part"}), 400
    
    file = request.files['video']
    latitude = float(request.form.get('latitude'))
    longitude = float(request.form.get('longitude'))
    
    if file.filename == '' or not latitude or not longitude:
        return jsonify({"error": "Missing file or location data"}), 400

    if file:
        filename = secure_filename(file.filename)
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(video_path)
        
        # Start video processing in a background thread to keep the API responsive
        processing_thread = threading.Thread(
            target=process_video_and_detect,
            args=(video_path, latitude, longitude)
        )
        processing_thread.start()
        
        print(f"Received report. Starting analysis for {filename} in the background.")
        
        return jsonify({
            "message": "Video uploaded successfully! Processing has started in the background.",
            "filename": filename
        }), 202

@app.route('/images/<path:filename>')
def get_image(filename):
    """Serves an image from the IMAGE_FOLDER."""
    return send_from_directory(IMAGE_FOLDER, filename)


# --- 6. START THE APPLICATION ---
if __name__ == "__main__":
    # Start the background database worker thread
    db_worker_thread = threading.Thread(target=database_worker, daemon=True)
    db_worker_thread.start()
    
    # Start the Flask web server
    # Use host='0.0.0.0' to make it accessible on your local network
    app.run(host='0.0.0.0', port=5001, debug=True)