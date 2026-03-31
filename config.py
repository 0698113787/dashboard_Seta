import os
from datetime import timedelta

class Config:
    """Application configuration"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    DEBUG = True
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///smart_drain.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload folders
    UPLOAD_FOLDER = 'static/uploads'
    DATA_FOLDER = 'data'
    MODEL_FOLDER = 'ml/models'
    
    # Rainfall data URLs
    RAINFALL_FULL_URL = "https://data.humdata.org/dataset/20978b3b-74bd-4746-9517-ae0fb35c02b3/resource/f3c9c76f-5eb0-42a2-a61b-9466862fab82/download/zaf-rainfall-subnat-full.csv"
    RAINFALL_5Y_URL = "https://data.humdata.org/dataset/20978b3b-74bd-4746-9517-ae0fb35c02b3/resource/2dd325e3-ae69-484e-9faa-befeb80ead94/download/zaf-rainfall-subnat-5ytd.csv"
    
    # Sensor thresholds (in cm from ultrasonic sensor)
    CRITICAL_WATER_LEVEL = 10  # Emergency valve opens
    WARNING_WATER_LEVEL = 15   # Warning alert
    SAFE_WATER_LEVEL = 20      # Emergency valve closes
    NORMAL_WATER_LEVEL = 30    # Normal operation
    
    # ML Model settings
    MODEL_RETRAIN_DAYS = 7  # Retrain model every 7 days
    PREDICTION_HOURS = 24   # Predict next 24 hours
    
    # SocketIO
    SOCKETIO_MESSAGE_QUEUE = None
    SOCKETIO_ASYNC_MODE = 'eventlet'
    
    # Create necessary folders
    @staticmethod
    def init_app(app):
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.DATA_FOLDER, exist_ok=True)
        os.makedirs(Config.MODEL_FOLDER, exist_ok=True)