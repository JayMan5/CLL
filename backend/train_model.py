import os
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
MODEL_PATH = os.path.join(DATA_DIR, "delay_model.joblib")
ENCODERS_PATH = os.path.join(DATA_DIR, "label_encoders.joblib")

DATASET_PATH = os.path.join(DATA_DIR, "courtlog_delay_dataset.csv")

def train_and_save():
    print("Loading generated Nigerian court case dataset...")
    df = pd.read_csv(DATASET_PATH)
    
    # Create binary target (High risk = 1)
    df["stalled"] = (df["delay_risk"] == "High").astype(int)
    
    # Initialize encoders
    le_case_type = LabelEncoder()
    le_court = LabelEncoder()
    
    # Fit and transform categorical columns
    df["case_type_encoded"] = le_case_type.fit_transform(df["case_type"])
    df["court_encoded"] = le_court.fit_transform(df["court"])
    
    # Features & target
    X = df[["adjournment_count", "days_since_filing", "case_type_encoded", "court_encoded"]]
    y = df["stalled"]
    
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Train Logistic Regression
    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    print("\n=== Model Training Evaluation ===")
    print(classification_report(y_test, y_pred))
    print(f"ROC AUC Score: {roc_auc_score(y_test, y_prob):.4f}")
    
    print("\n=== Model Coefficients (Interpretability Map) ===")
    features = X.columns
    for feat, coef in zip(features, model.coef_[0]):
        print(f"Feature: {feat:<22} | Coefficient: {coef:.4f}")
    print(f"Intercept: {model.intercept_[0]:.4f}")
    
    # Save the model and label encoders
    os.makedirs(DATA_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    joblib.dump({
        "case_type": le_case_type,
        "court": le_court,
        # Save class mappings for reference
        "case_type_classes": le_case_type.classes_.tolist(),
        "court_classes": le_court.classes_.tolist()
    }, ENCODERS_PATH)
    
    print(f"\nModel saved successfully to {MODEL_PATH}")
    print(f"Encoders saved successfully to {ENCODERS_PATH}")

if __name__ == "__main__":
    train_and_save()
