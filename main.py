import os
import cv2
import time
import datetime
import certifi
import threading
from deep_sort_realtime.deepsort_tracker import DeepSort
from queue import Queue
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from ultralytics import YOLO
from pymongo import MongoClient
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor


load_dotenv()


MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set!")
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = client.pothole_db
potholes_collection = db.potholes
print("✅ Successfully connected to MongoDB Atlas.")


try:
    potholes_collection.create_index([("location", "2dsphere")])
    print("✅ Ensured 2dsphere index exists on 'location' field.")
except Exception as e:
    print(f"⚠️ Could not create 2dsphere index: {e}")


model = YOLO('best.pt')
app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

UPLOAD_FOLDER = 'pothole_videos'
IMAGE_FOLDER = 'pothole_images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

data_queue = Queue()

executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 2)


def database_worker():
    """Pulls processed data from the queue and saves it to MongoDB."""
    while True:
        lat, lon, severity, image_path = data_queue.get()
        save_to_database_mongo(lat, lon, severity, image_path)
        data_queue.task_done()


def get_pothole_severity(box_coords, frame_shape):
    """
    Calculates pothole severity by adjusting its pixel area based on its
    vertical position in the frame to account for perspective.
    """
    PERSPECTIVE_MULTIPLIER = 2.5 
    LARGE_THRESHOLD = 40000
    MEDIUM_THRESHOLD = 15000
    frame_h, frame_w = frame_shape
    x1, y1, x2, y2 = box_coords
    box_w = x2 - x1
    box_h = y2 - y1
    pixel_area = box_w * box_h
    box_bottom_y = y2
    perspective_factor = 1.0 + ((frame_h - box_bottom_y) / frame_h) * PERSPECTIVE_MULTIPLIER
    adjusted_area = pixel_area * perspective_factor
    
    if adjusted_area > LARGE_THRESHOLD:
        return "Large"
    if adjusted_area > MEDIUM_THRESHOLD:
        return "Medium"
    return "Small"

def save_pothole_image(frame, box_coords):
    """
    Crops the detected pothole with added padding for better context
    and saves it as a JPEG image.
    """
    PADDING_PIXELS = 75 
    frame_h, frame_w, _ = frame.shape
    x1, y1, x2, y2 = box_coords
    new_x1 = x1 - PADDING_PIXELS
    new_y1 = y1 - PADDING_PIXELS
    new_x2 = x2 + PADDING_PIXELS
    new_y2 = y2 + PADDING_PIXELS
    safe_x1 = max(0, new_x1)
    safe_y1 = max(0, new_y1)
    safe_x2 = min(frame_w, new_x2)
    safe_y2 = min(frame_h, new_y2)
    pothole_img = frame[safe_y1:safe_y2, safe_x1:safe_x2]
    timestamp_str = time.strftime("%Y%m%d-%H%M%S")
    image_name = f"pothole_{timestamp_str}_{threading.get_ident()}.jpg"
    image_path = os.path.join(IMAGE_FOLDER, image_name)
    cv2.imwrite(image_path, pothole_img)
    return image_path

def save_to_database_mongo(lat, lon, severity, image_path):
    """Constructs and inserts the pothole document into MongoDB."""
    image_filename = os.path.basename(image_path)
    image_url = f"http://127.0.0.1:5001/images/{image_filename}"
    
    pothole_document = {
        "severity": severity,
        "image_url": image_url,
        "location": {"type": "Point", "coordinates": [lon, lat]},
        "timestamp": datetime.datetime.now(datetime.UTC),
        "status": "unverified"  # NEW: Add this default status
    }
    potholes_collection.insert_one(pothole_document)
    print(f"💾 BACKGROUND SAVE: New {severity} pothole at ({lat}, {lon}) saved.")


def process_video_and_detect(video_path, latitude, longitude, debug=False):
    """
    Main video processing function with a finely-tuned object tracker
    that prioritizes motion (IoU) over appearance to handle perspective changes.
    """
    
    CONFIDENCE_THRESHOLD = 0.6
    
    MIN_BOX_WIDTH = 20
    MIN_BOX_HEIGHT = 20
    
    FRAME_SKIP = 3

    
    tracker = DeepSort(
        max_age=60,             # Reduced memory slightly, as we are more confident in matches
        n_init=3,               # Lowered init, as confidence is higher
        # This is the most important change:
        # We make the position-based matching (IoU) much stricter.
        max_iou_distance=0.5,
        # We make the appearance-based matching more lenient, telling it to not give up so easily.
        max_cosine_distance=0.5
    )

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Error: Could not open video file: {video_path}")
        return

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) # Use float for more accurate timing
    
    if fps == 0:
        fps = 30 
    frame_count = 0
    saved_pothole_ids = set()

    output_video = None
    if debug:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        output_video = cv2.VideoWriter('debug_output.mp4', fourcc, fps / FRAME_SKIP, (frame_w, frame_h))
        print("🕵️  DEBUG MODE: An output video named 'debug_output.mp4' will be created.")

    print(f"🚀 Starting detection with FINAL tracking on {video_path}...")
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
                if not track.is_confirmed():
                    continue

                track_id = track.track_id
                ltrb = track.to_ltrb()
                x1, y1, x2, y2 = map(int, ltrb)

                if debug:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"ID: {track_id}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                if track_id not in saved_pothole_ids:
                    severity = get_pothole_severity((x1, y1, x2, y2), (frame_h, frame_w))
                    image_path = save_pothole_image(frame, (x1, y1, x2, y2))
                    data_queue.put((latitude, longitude, severity, image_path))
                    print(f"✅ New pothole detected! ID: {track_id}, Severity: {severity}.")
                    saved_pothole_ids.add(track_id)

            if debug and output_video:
                output_video.write(frame)

        frame_count += 1

    cap.release()
    if debug and output_video:
        output_video.release()
    print(f"🏁 Finished processing video: {video_path}. Found {len(saved_pothole_ids)} unique potholes.")
@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/api/report', methods=['POST'])
def handle_report():
    """Handles video uploads and submits them to the processing pool."""
    if 'video' not in request.files:
        return jsonify({"error": "No video file part"}), 400
    
    file = request.files['video']
    try:
        latitude = float(request.form.get('latitude'))
        longitude = float(request.form.get('longitude'))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid or missing location data"}), 400
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(video_path)
    
    # NEW WAY
    executor.submit(process_video_and_detect, video_path, latitude, longitude, debug=False)
    
    print(f"📥 Received report. Submitted {filename} to the processing pool.")
    return jsonify({
        "message": "Video uploaded successfully! Processing has started.",
        "filename": filename
    }), 202

@app.route('/images/<path:filename>')
def get_image(filename):
    """Serves a detected pothole image from the image folder."""
    return send_from_directory(IMAGE_FOLDER, filename)


if __name__ == "__main__":
    db_worker_thread = threading.Thread(target=database_worker, daemon=True)
    db_worker_thread.start()
    
    app.run(host='0.0.0.0', port=5001, debug=False)
