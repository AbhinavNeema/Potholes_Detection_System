import os
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv
import requests
from PIL import Image
import io
import streamlit as st 


def export_data_for_training(potholes_collection):
    """
    Fetches confirmed pothole data, downloads images, and creates
    YOLO-formatted label files for retraining.
    """
    if potholes_collection is None:
        st.error("Database connection not available.")
        return

    print("Fetching confirmed potholes for export...")
    confirmed_potholes = list(potholes_collection.find({"status": "confirmed"}))

    if not confirmed_potholes:
        st.warning("No confirmed potholes found to export.")
        return

    
    dataset_path = "retraining_dataset"
    images_path = os.path.join(dataset_path, "images")
    labels_path = os.path.join(dataset_path, "labels")
    os.makedirs(images_path, exist_ok=True)
    os.makedirs(labels_path, exist_ok=True)

    st.write(f"Found {len(confirmed_potholes)} confirmed potholes. Starting export...")
    progress_bar = st.progress(0)

    for i, pothole in enumerate(confirmed_potholes):
        try:
            image_url = pothole["image_url"]
            image_id = str(pothole["_id"])
            
            
            response = requests.get(image_url)
            if response.status_code != 200:
                print(f"Failed to download image: {image_url}")
                continue
            
            image = Image.open(io.BytesIO(response.content))
            img_w, img_h = image.size
            image_filename = os.path.join(images_path, f"{image_id}.jpg")
            image.save(image_filename)

            
            padding = 75 
            
            original_box_w = img_w - (2 * padding)
            original_box_h = img_h - (2 * padding)

            norm_w = original_box_w / img_w
            norm_h = original_box_h / img_h
            
            norm_x_center = 0.5
            norm_y_center = 0.5
            
            label_filename = os.path.join(labels_path, f"{image_id}.txt")
            with open(label_filename, "w") as f:
                f.write(f"0 {norm_x_center:.6f} {norm_y_center:.6f} {norm_w:.6f} {norm_h:.6f}\n")
            
        except Exception as e:
            print(f"Error processing pothole {pothole['_id']}: {e}")
        
        progress_bar.progress((i + 1) / len(confirmed_potholes))

    st.success(f"Export complete! Dataset saved to '{dataset_path}' folder.")

