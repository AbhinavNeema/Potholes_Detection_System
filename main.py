import os
import cv2
import time
import datetime
import certifi
import threading
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from ultralytics import YOLO
from pymongo import MongoClient
from dotenv import load_dotenv
from deep_sort_realtime.deepsort_tracker import DeepSort

load_dotenv()


MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client.pothole_db
potholes_collection = db.potholes
print("Successfully connected to MongoDB Atlas.")

try:
    potholes_collection.create_index([("location", "2dsphere")])
    print("✅ Ensured 2dsphere index exists on 'location' field.")
except Exception as e:
    print(f"⚠️ Could not create 2dsphere index: {e}")


model=YOLO('best.pt')
app=Flask(__name__, template_folder='.', static_folder='.')
CORS(app,resources={r"/api/*": {"origins": "*"}})


UPLOAD_FOLDER='pothole_videos'
IMAGE_FOLDER='pothole_images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER']=UPLOAD_FOLDER


def get_pothole_severity(box_coords, frame_shape):
    PERSPECTIVE_MULTIPLIER = 2.5
    LARGE_THRESHOLD = 40000
    MEDIUM_THRESHOLD = 15000
    frame_h, frame_w = frame_shape
    x1, y1, x2, y2 = box_coords
    pixel_area = (x2 - x1) * (y2 - y1)
    perspective_factor = 1.0 + ((frame_h - y2) / frame_h) * PERSPECTIVE_MULTIPLIER
    adjusted_area = pixel_area * perspective_factor
    
    if adjusted_area > LARGE_THRESHOLD:
        return "Large"
    if adjusted_area > MEDIUM_THRESHOLD:
        return "Medium"
    return "Small"

def save_pothole_image(frame,box_coords):
    PADDING_PIXELS=75
    frame_h, frame_w, _=frame.shape
    x1, y1, x2, y2 = box_coords
    safe_x1 = max(0, x1 - PADDING_PIXELS)
    safe_y1 = max(0, y1 - PADDING_PIXELS)
    safe_x2 = min(frame_w, x2 + PADDING_PIXELS)
    safe_y2 = min(frame_h, y2 + PADDING_PIXELS)
    
    pothole_img = frame[safe_y1:safe_y2, safe_x1:safe_x2]
    
    image_name = f"pothole_{int(time.time() * 1000)}.jpg"
    image_path = os.path.join(IMAGE_FOLDER, image_name)
    cv2.imwrite(image_path, pothole_img)
    return image_path

def save_to_database_mongo(lat, lon, severity, image_path):
    
    image_filename = os.path.basename(image_path)
    host_url = os.getenv("FLASK_HOST_URL", "http://127.0.0.1:5001")
    image_url = f"{host_url}/images/{image_filename}"
    
    pothole_document = {
        "severity": severity,
        "image_url": image_url,
        "location": {"type": "Point", "coordinates": [lon, lat]},
        "timestamp": datetime.datetime.now(datetime.UTC),
        "status": "unverified"
    }
    potholes_collection.insert_one(pothole_document)
    return pothole_document

def process_video_and_detect(video_path, latitude, longitude):
    
    CONFIDENCE_THRESHOLD = 0.6
    MIN_BOX_WIDTH = 20
    MIN_BOX_HEIGHT = 20
    FRAME_SKIP = 3
    
    tracker = DeepSort(max_age=60, n_init=3, max_iou_distance=0.5, max_cosine_distance=0.5)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Error: Could not open video file: {video_path}")
        return []

    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    
    saved_pothole_ids = set()
    report_details = []
    frame_count = 0

    print(f"🚀 Starting detection on {os.path.basename(video_path)}...")
    while True:
        success, frame = cap.read()
        if not success:
            break

        if frame_count % FRAME_SKIP == 0:
            results = model(frame)
            detections = []
            for result in results:
                for box in result.boxes:
                    if box.conf[0] > CONFIDENCE_THRESHOLD:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        w, h = x2 - x1, y2 - y1
                        if w > MIN_BOX_WIDTH and h > MIN_BOX_HEIGHT:
                            detections.append(([x1, y1, w, h], box.conf[0], int(box.cls[0])))

            tracks = tracker.update_tracks(detections, frame=frame)

            for track in tracks:
                if not track.is_confirmed() or track.track_id in saved_pothole_ids:
                    continue

                track_id = track.track_id
                x1, y1, x2, y2 = map(int, track.to_ltrb())
                
                severity = get_pothole_severity((x1, y1, x2, y2), (frame_h, frame_w))
                image_path = save_pothole_image(frame, (x1, y1, x2, y2))
                
                pothole_doc = save_to_database_mongo(latitude, longitude, severity, image_path)
                report_details.append({
                    "severity": severity,
                    "image_url": pothole_doc['image_url']
                })
                saved_pothole_ids.add(track_id)

        frame_count += 1

    cap.release()
    print(f"🏁 Finished processing. Found {len(saved_pothole_ids)} unique potholes.")
    return report_details


@app.route('/')
def index():
    
    return render_template('index.html')

@app.route('/api/report', methods=['POST', 'OPTIONS'], strict_slashes=False)
def handle_report():
    
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200

    if 'video' not in request.files:
        return jsonify({"error": "No video file part"}), 400
    
    file = request.files['video']
    try:
        latitude = float(request.form.get('latitude'))
        longitude = float(request.form.get('longitude'))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid or missing location data"}), 400
    
    if file.filename=='':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(video_path)
    
    report = process_video_and_detect(video_path, latitude, longitude)
    
    print(f"📥 Report generated for {filename}.")
    return jsonify({
        "message": "Video processed successfully!",
        "filename": filename,
        "potholes_found": len(report),
        "report_details": report
    }), 200

@app.route('/images/<path:filename>')
def get_image(filename):
    return send_from_directory(IMAGE_FOLDER, filename)


if __name__ == "__main__":
    print("🚀 Starting Flask server in DEVELOPMENT mode...")
    app.run(host='0.0.0.0', port=5001, debug=True)

