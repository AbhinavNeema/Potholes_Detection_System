# dashboard.py - Live Pothole Dashboard with MongoDB

# --- 1. SETUP ---
import os
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

# Page configuration
st.set_page_config(page_title="Live Pothole Dashboard", page_icon="📡", layout="wide")

# Load environment variables from a .env file
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

# Verify that the MONGO_URI was loaded before continuing
if not MONGO_URI:
    st.error("MONGO_URI environment variable not found! Please create a .env file with your connection string.")
    st.stop()


# --- 2. HELPER FUNCTIONS ---

# Connects to MongoDB and fetches the pothole data.
def get_data_from_db():
    try:
        # The tlsCAFile parameter is crucial for connecting to MongoDB Atlas
        client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        db = client.pothole_db
        potholes_collection = db.potholes
        
        # Fetch all documents and sort by the newest first
        potholes = list(potholes_collection.find().sort("timestamp", -1))
        client.close()
        
        df = pd.DataFrame(potholes)
        
        # Exit early if the dataframe is empty to prevent errors
        if df.empty:
            return pd.DataFrame()

        # Extract latitude and longitude from the GeoJSON 'location' field
        if 'location' in df.columns:
            df['longitude'] = df['location'].apply(lambda x: x['coordinates'][0])
            df['latitude'] = df['location'].apply(lambda x: x['coordinates'][1])
        
        # Ensure the image_url column exists to avoid errors later
        if 'image_url' not in df.columns:
            df['image_url'] = None
        
        return df
        
    except Exception as e:
        st.error(f"Could not connect to MongoDB: {e}")
        return pd.DataFrame()

# --- 3. DASHBOARD UI ---
st.title("📡 Live Pothole Detection Dashboard")
st.write("This dashboard displays live data collected from the pothole detection system.")

# Load the data
pothole_data = get_data_from_db()

# If there's no data, show a message and stop.
if pothole_data.empty:
    st.warning("No potholes have been detected yet. Run the main application to start collecting data!")
else:
    # --- Overall Summary Metrics ---
    st.header("Overall Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Potholes Found", len(pothole_data))
    col2.metric("Most Common Severity", pothole_data['severity'].mode()[0])
    last_seen_time = pd.to_datetime(pothole_data['timestamp'].iloc[0]).strftime("%d %b %Y, %I:%M %p")
    col3.metric("Last Seen", last_seen_time)

    st.markdown("---")

    # --- Interactive Map ---
    st.header("Map of Detected Potholes")
    map_center = [pothole_data['latitude'].mean(), pothole_data['longitude'].mean()]
    m = folium.Map(location=map_center, zoom_start=14, tiles="CartoDB positron")

    # Define a color scheme for pothole severity
    color_map = {'Small': 'green', 'Medium': 'orange', 'Large': 'red'}

    # Add a marker for each pothole
    for _, row in pothole_data.iterrows():
        # Create a popup with pothole image and severity
        if pd.notna(row['image_url']):
            html = f"""
            <b>Severity:</b> {row['severity']}<br>
            <img src="{row['image_url']}" width="150">
            """
            popup = folium.Popup(html, max_width=200)
        else:
            popup = f"<b>Severity:</b> {row['severity']}<br>(Image not available)"

        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=popup,
            icon=folium.Icon(color=color_map.get(row['severity'], 'blue'))
        ).add_to(m)

    st_folium(m, width=1200, height=500)

    st.markdown("---")

    # --- Live Data Table ---
    st.header("Live Pothole Data Log")
    st.dataframe(pothole_data, column_config={
        "image_url": st.column_config.ImageColumn("Pothole Image", width="medium"),
        "timestamp": st.column_config.DatetimeColumn("Timestamp", format="D MMM YYYY, h:mm A"),
        "_id": None, # Hide the MongoDB ID column
        "location": None, # Hide the raw location object column
        "image_path": None, # Hide the old local file path column
    })

    # A button to manually refresh the data
    if st.button("Refresh Data"):
        st.rerun()