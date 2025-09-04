import os
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv
from bson.objectid import ObjectId


st.set_page_config(page_title="Pothole Dashboard", page_icon="📡", layout="wide")


load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    st.error("MONGO_URI environment variable not found! Please create a .env file with your connection string.")
    st.stop()


@st.cache_resource
def init_connection():
    try:
        client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        return client.pothole_db
    except Exception as e:
        st.error(f"Could not connect to MongoDB: {e}")
        return None

db = init_connection()


@st.cache_data(ttl=600)
def get_data_from_db():
    if db is None:
        return pd.DataFrame()

    try:
        potholes_collection = db.potholes
        potholes = list(potholes_collection.find().sort("timestamp", -1))
        
        if not potholes:
            return pd.DataFrame()

        df = pd.DataFrame(potholes)
        
        
        if '_id' in df.columns:
            df['_id'] = df['_id'].astype(str)

        
        if 'location' in df.columns:
            df['longitude'] = df['location'].apply(lambda x: x['coordinates'][0] if x else None)
            df['latitude'] = df['location'].apply(lambda x: x['coordinates'][1] if x else None)
        
        return df
        
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()


st.title("📡 Live Pothole Detection Dashboard")


if st.button("🔄 Refresh Data"):
    
    get_data_from_db.clear()
    st.rerun()

pothole_data = get_data_from_db()

if pothole_data.empty:
    st.warning("No potholes have been detected yet. Run the main application to start collecting data!")
else:
    
    st.header("Overall Summary")
    
    
    verified_data = pothole_data[pothole_data['status'] == 'confirmed']
    if verified_data.empty:
        total_verified = 0
        most_common_sev = "N/A"
    else:
        total_verified = len(verified_data)
        most_common_sev = verified_data['severity'].mode()[0]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Potholes Confirmed", total_verified)
    col2.metric("Most Common Severity", most_common_sev)
    last_seen_time = pd.to_datetime(pothole_data['timestamp'].iloc[0]).strftime("%d %b %Y, %I:%M %p")
    col3.metric("Last Seen (Any Status)", last_seen_time)

    st.markdown("---")

   
    st.header("Map of Detected Potholes")
   
    if not verified_data.empty:
        map_center = [verified_data['latitude'].mean(), verified_data['longitude'].mean()]
        m = folium.Map(location=map_center, zoom_start=14, tiles="CartoDB positron")
        color_map = {'Small': 'green', 'Medium': 'orange', 'Large': 'red'}

        for _, row in verified_data.iterrows():
            html = f"""
            <b>Severity:</b> {row['severity']}<br>
            <img src="{row['image_url']}" width="150">
            """
            popup = folium.Popup(html, max_width=200)
            folium.Marker(
                location=[row['latitude'], row['longitude']],
                popup=popup,
                icon=folium.Icon(color=color_map.get(row['severity'], 'blue'))
            ).add_to(m)
        st_folium(m, width=1200, height=500)
    else:
        st.info("No confirmed potholes to display on the map yet.")


    
    st.markdown("---")
    st.header("Verification Queue")

    pothole_to_verify = potholes_collection.find_one({"status": "unverified"})

    if not pothole_to_verify:
        st.success("🎉 No more potholes to verify! Great work.")
    else:
        st.write(f"Verifying Pothole ID: `{str(pothole_to_verify['_id'])}`")
        st.image(pothole_to_verify['image_url'], caption=f"Severity: {pothole_to_verify['severity']}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Confirm Pothole", use_container_width=True, type="primary"):
                potholes_collection.update_one(
                    {"_id": ObjectId(pothole_to_verify['_id'])},
                    {"$set": {"status": "confirmed"}}
                )
                get_data_from_db.clear() # Clear cache after updating
                st.rerun()
        with col2:
            if st.button("Reject (Not a Pothole)", use_container_width=True):
                potholes_collection.update_one(
                    {"_id": ObjectId(pothole_to_verify['_id'])},
                    {"$set": {"status": "rejected"}}
                )
                get_data_from_db.clear() 
                st.rerun()

    
    st.markdown("---")
    st.header("Live Pothole Data Log (All Statuses)")
    st.dataframe(pothole_data, column_config={
        "image_url": st.column_config.ImageColumn("Pothole Image", width="medium"),
        "timestamp": st.column_config.DatetimeColumn("Timestamp", format="D MMM YYYY, h:mm A"),
        "_id": None, "location": None, "image_path": None, 
    })
