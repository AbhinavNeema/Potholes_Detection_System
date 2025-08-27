#  pothole-detection-system
Project by- Abhinav Neema
# 🛣️ Real-Time Pothole Detection System

A complete web application that uses YOLOv8 to detect potholes from uploaded video streams and displays them on a live dashboard.



---

## ✨ Features

-   **AI-Powered Detection**: Utilizes a custom-trained **YOLOv8 model** to accurately identify potholes in real-time.
-   **Web-Based Video Upload**: A simple Flask interface to upload video files for analysis.
-   **Asynchronous Processing**: Uses background threading to process videos without blocking the user interface.
-   **Geospatial Database**: Stores pothole locations, severity, and image URLs in **MongoDB Atlas**.
-   **Duplicate Prevention**: Smartly checks for nearby potholes to avoid duplicate entries for the same location.
-   **Live Interactive Dashboard**: A **Streamlit** dashboard displays detected potholes on a Folium map with image popups and a live data log.

---

## 🛠️ Tech Stack

-   **Backend**: Python, Flask
-   **AI Model**: Ultralytics YOLOv8
-   **Database**: MongoDB Atlas
-   **Frontend/Dashboard**: Streamlit, Folium, Pandas
-   **Core Libraries**: OpenCV, PyMongo, Dotenv

---

## 📊 Model Performance

The custom-trained YOLOv8m model was evaluated on a validation dataset of 273 images. The performance benchmarks below, captured on an NVIDIA Tesla T4 GPU, demonstrate its effectiveness and efficiency for real-time detection.

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Precision** | 0.90 | 90% of predicted potholes were correct. |
| **Recall** | 0.78 | The model found 78% of all actual potholes. |
| **mAP@50** | 0.88 | 88% mean average precision at 50% IoU. |
| **Inference Speed** | 7.3ms / ~137 FPS | Average time per image on an NVIDIA Tesla T4 GPU. |

These metrics confirm the model's suitability for deployment in a real-time road monitoring application.

---

## 📂 Project Structure

.
├── pothole_images/         # Saved pothole images (ignored by git)
├── pothole_videos/         # Uploaded videos (ignored by git)
├── best.pt                 # The trained YOLOv8 model file
├── dashboard.py            # The Streamlit dashboard application
├── main.py                 # The Flask backend server for detection
├── index.html              # Simple frontend for video upload
├── .env                    # Environment variables (ignored by git)
├── .gitignore              # Specifies files for git to ignore
├── requirements.txt        # Python dependencies
└── README.md               # You are here!


---

## ⚙️ Setup and Installation

Follow these steps to get the project running locally.

1.  **Clone the Repository**
    ```bash
    git clone [https://github.com/AbhinavNeema/Pothole-detection-system.git](https://github.com/AbhinavNeema/Pothole-detection-system.git)
    cd Pothole-detection-system
    ```

2.  **Create a Virtual Environment**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set Up Environment Variables**
    -   Create a file named `.env` in the root directory.
    -   Add your MongoDB Atlas connection string to it:
        ```
        MONGO_URI="mongodb+srv://<username>:<password>@cluster..."
        ```

5.  **Download the Model**
    -   Make sure the `best.pt` model file is present in the root directory.

---

## 🚀 Usage

You need to run two components in separate terminals.

1.  **Run the Backend Server** (Handles detection and database saves)
    ```bash
    python main.py
    ```
    -   The server will be running at `http://127.0.0.1:5001`. You can visit this URL to upload a video.

2.  **Run the Streamlit Dashboard** (Visualizes the results)
    ```bash
    streamlit run dashboard.py
    ```
    -   The dashboard will open in your browser, typically at `http://localhost:8501`.

Once both are running, upload a video through the Flask app, and watch the results appear on the Streamlit dashboard!