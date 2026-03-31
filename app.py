"""
app.py
======
Main Flask application entry point for the Smart Drain System.

Responsibilities:
  - Create and configure the Flask app
  - Initialise extensions (SQLAlchemy, SocketIO, CORS)
  - Register Blueprints  (routes/dashboard.py, routes/api.py)
  - Run the background ESP32 sensor simulator thread
  - Seed the DB with sample data on first run
  - Expose the SocketIO server for real-time updates

Usage:
    python app.py
"""

import os
import random
import threading
import time
from datetime import datetime, timedelta

from flask import Flask
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from config import Config
from models import (
    db,
    SensorReading,
    RainfallData,
    Prediction,
    Alert,
    SystemStatus,
    ModelMetrics,
)

# ── App factory ───────────────────────────────────────────────────────────────

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    config_class.init_app(app)

    db.init_app(app)
    CORS(app)

    from routes.api       import api_bp
    from routes.dashboard import dashboard_bp

    app.register_blueprint(api_bp)        # /api/*
    app.register_blueprint(dashboard_bp)  # / and page routes

    return app


app      = create_app()
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')


# ── Background sensor simulator ───────────────────────────────────────────────

def simulate_sensor_data():
    """Simulates real-time ESP32 readings every 3 seconds."""
    water_level = 25.0

    while True:
        with app.app_context():
            try:
                delta       = random.uniform(-2.0, 2.5)
                water_level = round(max(5.0, min(50.0, water_level + delta)), 2)
                rainfall_now = round(max(0.0, random.gauss(5, 8)), 2)

                if water_level >= 40:
                    risk = 'CRITICAL'
                elif water_level >= 30:
                    risk = 'WARNING'
                else:
                    risk = 'SAFE'

                valve = 'OPEN' if water_level < 20 else 'CLOSED'

                reading = SensorReading(
                    water_level_cm=water_level,
                    valve_status=valve,
                    rainfall_mm=rainfall_now,
                )
                db.session.add(reading)

                predicted = round(water_level + random.uniform(-3, 3), 2)
                pred = Prediction(
                    predicted_level_cm=predicted,
                    confidence_lower=round(predicted - 4, 2),
                    confidence_upper=round(predicted + 4, 2),
                    confidence_std=round(abs(random.gauss(0, 2)), 2),
                    risk_level=risk,
                    prediction_for=datetime.utcnow() + timedelta(hours=1),
                    model_version='sim-v1.0',
                    input_rainfall_mm=rainfall_now,
                )
                db.session.add(pred)

                status = SystemStatus.query.first()
                if not status:
                    status = SystemStatus()
                    db.session.add(status)

                status.esp32_online        = True
                status.esp32_cam_online    = True
                status.raspberry_pi_online = True
                status.battery_level       = round(random.uniform(75, 95), 1)
                status.solar_charging      = True
                status.wifi_rssi           = random.randint(-70, -40)
                status.last_update         = datetime.utcnow()

                if risk == 'CRITICAL':
                    db.session.add(Alert(
                        alert_type='SENSOR',
                        severity='CRITICAL',
                        message=f'Warning: Critical water level detected: {water_level:.1f} cm',
                        water_level=water_level,
                    ))

                db.session.commit()

                socketio.emit('sensor_update', {
                    'water_level':     water_level,
                    'valve_status':    valve,
                    'risk_level':      risk,
                    'rainfall_now':    rainfall_now,
                    'predicted_level': predicted,
                    'battery':         status.battery_level,
                    'wifi_rssi':       status.wifi_rssi,
                    'timestamp':       datetime.utcnow().isoformat(),
                })

            except Exception as exc:
                print(f'[Simulator] Error: {exc}')
                db.session.rollback()

        time.sleep(3)


# ── SocketIO events ───────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    print('Client connected')
    emit('connected', {'msg': 'Connected to Smart Drain System'})


@socketio.on('disconnect')
def on_disconnect():
    print('Client disconnected')


# ── DB seed ───────────────────────────────────────────────────────────────────

def seed_rainfall_data():
    if RainfallData.query.count() > 0:
        return
    provinces = [
        'Gauteng', 'KwaZulu-Natal', 'Western Cape',
        'Limpopo', 'Mpumalanga', 'Eastern Cape',
        'North West', 'Free State', 'Northern Cape',
    ]
    base    = datetime.utcnow().date() - timedelta(days=365)
    records = []
    for i in range(365):
        d = base + timedelta(days=i)
        for prov in provinces:
            records.append(RainfallData(
                date=d,
                location=prov,
                rainfall_mm=round(max(0.0, random.gauss(8, 12)), 2),
                source='seed',
            ))
    db.session.bulk_save_objects(records)
    db.session.commit()
    print(f'Seeded {len(records):,} rainfall records')


def seed_model_metrics():
    if ModelMetrics.query.count() > 0:
        return
    db.session.add(ModelMetrics(
        model_name='Random Forest',
        algorithm='sklearn.ensemble.RandomForestRegressor',
        r2_score=0.0,
        rmse=0.0,
        mae=0.0,
        training_samples=0,
        features_count=24,
        is_active=True,
    ))
    db.session.commit()
    print('Seeded placeholder ModelMetrics row')


# ── Startup ───────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    seed_rainfall_data()
    seed_model_metrics()
    simulator = threading.Thread(target=simulate_sensor_data, daemon=True)
    simulator.start()
    print('Sensor simulator started')

if __name__ == '__main__':
    print('Smart Drain System - Starting on http://0.0.0.0:5000')
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)