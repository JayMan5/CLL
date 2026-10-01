# Project Walkthrough: CourtLog 2.0

CourtLog 2.0 is a lightweight, low-overhead GovTech file tracking and predictive delay-risk compliance registry dashboard designed for Nigerian courts. It features real-time barcode/QR-based custody tracking, courtroom logging, automated notifications, post-judgment execution monitoring, and machine-learning-driven delay risk prediction.

---

## Technical Stack & Dependencies

### 1. Frontend
A premium Single Page Application (SPA) designed with a modern dark-mode glassmorphic aesthetic.
* **HTML5 & Vanilla JavaScript**: Core structure and client-side logic ([index.html](file:///c:/Users/salman%20yusuf/Documents/couch%20project/frontend/index.html), [app.js](file:///c:/Users/salman%20yusuf/Documents/couch%20project/frontend/app.js)).
* **Tailwind CSS**: Utility-first CSS styling via CDN.
* **Chart.js**: Render interactive visual data distributions of case delay risk.
* **FontAwesome**: UI iconography.
* **Google Fonts**: Modern typography featuring *Outfit* and *Plus Jakarta Sans*.

### 2. Backend
A robust, high-performance asynchronous REST API service.
* **FastAPI (Python)**: Modern web API framework for routing and JSON serialization ([main.py](file:///c:/Users/salman%20yusuf/Documents/couch%20project/backend/main.py)).
* **Pydantic**: Data validation and schema settings.
* **Requests**: Interfacing with the external WhatsApp simulation webhook endpoint.
* **Uvicorn**: ASGI server container.

### 3. Database & Storage Layer
Dual-mode storage model ensuring flexible deployment.
* **Firebase Firestore**: Real connection using `firebase-admin` client ([database.py](file:///c:/Users/salman%20yusuf/Documents/couch%20project/backend/database.py)) when credentials (`firebase_creds.json`) are present.
* **Mock JSON DB**: Fallback to local file-based database ([cases.json](file:///c:/Users/salman%20yusuf/Documents/couch%20project/data/cases.json)).

### 4. Machine Learning
Predictive analysis for stalling risk based on synthetic Nigerian court timelines.
* **Scikit-Learn**: Logistic Regression model (`delay_model.joblib`) and category encoding (`label_encoders.joblib`) ([train_model.py](file:///c:/Users/salman%20yusuf/Documents/couch%20project/backend/train_model.py)).
* **Joblib**: Model serialization and persistence.
* **Pandas & NumPy**: Training data manipulation and synthetic cohort generation.

### 5. Messaging & Integration
* **Meta WhatsApp Business API Simulation**: Triggers templates (`court_adjournment_alert`) for automated registry notifications upon hearing adjournments ([whatsapp.py](file:///c:/Users/salman%20yusuf/Documents/couch%20project/backend/whatsapp.py)).

### 6. Testing & Quality Assurance
* **Unittest & FastAPI TestClient**: Core integration test cases to validate API routes, QR scan outcomes, and webhook execution logs ([test_api.py](file:///c:/Users/salman%20yusuf/Documents/couch%20project/backend/test_api.py)).
