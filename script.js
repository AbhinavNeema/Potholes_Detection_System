document.addEventListener('DOMContentLoaded', () => {
    // General UI elements
    const initialChoice = document.getElementById('initial-choice');
    const statusMessage = document.getElementById('status-message');
    // NEW: Get the report section
    const reportSection = document.getElementById('report-section');

    // --- Upload Section Elements ---
    const showUploadBtn = document.getElementById('show-upload-btn');
    const uploadSection = document.getElementById('upload-section');
    const videoUpload = document.getElementById('video-upload');
    const locationPicker = document.getElementById('location-picker');
    const mapContainer = document.getElementById('map');
    const submitUploadBtn = document.getElementById('submit-upload-btn');
    let map;
    let marker;
    let uploadedFile = null;

    // --- Record Section Elements ---
    const showRecordBtn = document.getElementById('show-record-btn');
    const recordSection = document.getElementById('record-section');
    const videoPlayer = document.getElementById('video-player');
    const startRecordBtn = document.getElementById('start-record-btn');
    const stopRecordBtn = document.getElementById('stop-record-btn');
    const submitRecordBtn = document.getElementById('submit-record-btn');
    let mediaRecorder;
    let recordedChunks = [];
    let liveGpsLocation = null;
    let recordedVideoBlob = null;


    // --- UI Logic ---
    showUploadBtn.addEventListener('click', () => {
        initialChoice.classList.add('hidden');
        uploadSection.classList.remove('hidden');
    });

    showRecordBtn.addEventListener('click', () => {
        initialChoice.classList.add('hidden');
        recordSection.classList.remove('hidden');
    });


    // --- UPLOAD VIDEO LOGIC ---
    videoUpload.addEventListener('change', (event) => {
        uploadedFile = event.target.files[0];
        if (uploadedFile) {
            locationPicker.classList.remove('hidden');
            initializeMap();
        }
    });

    function initializeMap() {
        if (map) return; // Initialize map only once
        map = L.map(mapContainer).setView([26.8467, 80.9462], 13); // Default: Lucknow

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);

        marker = L.marker(map.getCenter(), { draggable: true }).addTo(map);
        map.on('click', (e) => marker.setLatLng(e.latlng));
    }

    submitUploadBtn.addEventListener('click', () => {
        const location = marker.getLatLng();
        if (!uploadedFile || !location) {
            statusMessage.textContent = 'Please upload a video and pin a location.';
            statusMessage.style.color = '#dc3545';
            return;
        }

        const formData = new FormData();
        formData.append('video', uploadedFile);
        formData.append('latitude', location.lat);
        formData.append('longitude', location.lng);

        statusMessage.textContent = 'Uploading and processing... This may take a moment.';
        statusMessage.style.color = '#007bff';

        fetch('http://127.0.0.1:5001/api/report', {
            method: 'POST',
            body: formData
        })
        .then(response => {
             if (!response.ok) {
                throw new Error(`Server error: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            console.log('Success:', data);
            // MODIFIED: Call the new function to display the report
            displayReport(data);
        })
        .catch(error => {
            console.error('Error:', error);
            statusMessage.textContent = `Submission failed: ${error.message}`;
            statusMessage.style.color = '#dc3545';
        });
    });


    // --- RECORD LIVE VIDEO LOGIC ---
    startRecordBtn.addEventListener('click', async () => {
        statusMessage.textContent = '';
        if (!('geolocation' in navigator)) {
            statusMessage.textContent = 'Geolocation is not available on your browser.';
            return;
        }
        
        statusMessage.textContent = 'Requesting location...';
        navigator.geolocation.getCurrentPosition(position => {
            liveGpsLocation = {
                lat: position.coords.latitude,
                lng: position.coords.longitude
            };
            statusMessage.textContent = `Location captured. Starting camera...`;
            startCamera();
        }, () => {
            statusMessage.textContent = 'Could not get location. Please enable location services.';
            statusMessage.style.color = '#dc3545';
        });
    });

    async function startCamera() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            videoPlayer.srcObject = stream;
            
            recordedChunks = [];
            mediaRecorder = new MediaRecorder(stream);

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) recordedChunks.push(event.data);
            };

            mediaRecorder.onstop = () => {
                recordedVideoBlob = new Blob(recordedChunks, { type: 'video/webm' });
                const videoUrl = URL.createObjectURL(recordedVideoBlob);
                videoPlayer.srcObject = null;
                videoPlayer.src = videoUrl;
                videoPlayer.controls = true;
                videoPlayer.muted = false;
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            startRecordBtn.disabled = true;
            stopRecordBtn.disabled = false;
            submitRecordBtn.classList.add('hidden');
            statusMessage.textContent = 'Recording...';

        } catch (error) {
            console.error('Error accessing media devices.', error);
            statusMessage.textContent = 'Could not access camera. Please grant permission.';
            statusMessage.style.color = '#dc3545';
        }
    }

    stopRecordBtn.addEventListener('click', () => {
        if (mediaRecorder) mediaRecorder.stop();
        stopRecordBtn.disabled = true;
        submitRecordBtn.classList.remove('hidden');
        statusMessage.textContent = 'Recording stopped. Review and submit.';
    });
    
    submitRecordBtn.addEventListener('click', () => {
        if (!recordedVideoBlob || !liveGpsLocation) {
            statusMessage.textContent = 'No video recorded or location captured.';
            statusMessage.style.color = '#dc3545';
            return;
        }

        const formData = new FormData();
        formData.append('video', recordedVideoBlob, `live-recording-${Date.now()}.webm`);
        formData.append('latitude', liveGpsLocation.lat);
        formData.append('longitude', liveGpsLocation.lng);

        statusMessage.textContent = 'Uploading and processing... This may take a moment.';
        statusMessage.style.color = '#007bff';

        // CORRECTED PORT to 5001
        fetch('http://127.0.0.1:5001/api/report', {
            method: 'POST',
            body: formData
        })
        .then(response => {
             if (!response.ok) {
                throw new Error(`Server error: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            console.log('Success:', data);
            // MODIFIED: Call the new function to display the report
            displayReport(data);
        })
        .catch(error => {
            console.error('Error:', error);
            statusMessage.textContent = `Submission failed: ${error.message}`;
            statusMessage.style.color = '#dc3545';
        });
    });

    // --- NEW FUNCTION TO DISPLAY THE REPORT ---
    function displayReport(data) {
        // Hide all other sections
        initialChoice.classList.add('hidden');
        uploadSection.classList.add('hidden');
        recordSection.classList.add('hidden');

        // Show the report section
        reportSection.classList.remove('hidden');
        const reportContent = document.getElementById('report-content');
        reportContent.innerHTML = ''; // Clear any previous report

        statusMessage.textContent = `Analysis Complete for: ${data.filename}`;
        statusMessage.style.color = '#28a745';

        if (!data.report_details || data.potholes_found === 0) {
            reportContent.innerHTML = '<p>No potholes were detected in the video. Thank you for your submission.</p>';
            return;
        }

        const summary = document.createElement('h3');
        summary.textContent = `Detected ${data.potholes_found} pothole(s):`;
        reportContent.appendChild(summary);

        // Loop through each detected pothole and create a card for it
        data.report_details.forEach(pothole => {
            const card = document.createElement('div');
            card.className = 'report-card'; // Add a class for styling

            const image = document.createElement('img');
            // The server returns a relative path, so we build the full URL
            image.src = `http://127.0.0.1:5001/${pothole.image_path}`;
            image.alt = 'Detected pothole';

            const details = document.createElement('p');
            details.textContent = `Severity: ${pothole.severity}`;

            card.appendChild(image);
            card.appendChild(details);
            reportContent.appendChild(card);
        });
    }
});