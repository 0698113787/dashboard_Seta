"""
models.py
=========
SQLAlchemy database models for the Smart Drain System.
All tables used by app.py, the dashboard, and the ML pipeline live here.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# ── Sensor Readings ───────────────────────────────────────────────────────────

class SensorReading(db.Model):
    """Real-time readings pushed from the ESP32 ultrasonic sensor."""
    __tablename__ = 'sensor_readings'

    id             = db.Column(db.Integer,     primary_key=True)
    water_level_cm = db.Column(db.Float,       nullable=False)   # cm from sensor floor
    valve_status   = db.Column(db.String(10),  nullable=False)   # OPEN / CLOSED
    rainfall_mm    = db.Column(db.Float,       nullable=True)    # live rain if available
    temperature_c  = db.Column(db.Float,       nullable=True)    # optional temp sensor
    humidity_pct   = db.Column(db.Float,       nullable=True)    # optional humidity
    timestamp      = db.Column(db.DateTime,    default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id':             self.id,
            'water_level_cm': self.water_level_cm,
            'valve_status':   self.valve_status,
            'rainfall_mm':    self.rainfall_mm,
            'temperature_c':  self.temperature_c,
            'humidity_pct':   self.humidity_pct,
            'timestamp':      self.timestamp.isoformat(),
        }

    def __repr__(self):
        return f'<SensorReading {self.timestamp} level={self.water_level_cm}cm>'


# ── Rainfall Data ─────────────────────────────────────────────────────────────

class RainfallData(db.Model):
    """
    Historical and real-time rainfall records.
    Populated by data/process_rainfall_data.py (HDX dataset) and live sensors.
    """
    __tablename__ = 'rainfall_data'

    id          = db.Column(db.Integer,     primary_key=True)
    date        = db.Column(db.Date,        nullable=False, index=True)
    location    = db.Column(db.String(100), nullable=True)   # Province / station name
    rainfall_mm = db.Column(db.Float,       nullable=False)
    source      = db.Column(db.String(50),  nullable=True)   # 'hdx_full', 'hdx_5ytd', 'sensor', 'seed'
    timestamp   = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':          self.id,
            'date':        self.date.isoformat(),
            'location':    self.location,
            'rainfall_mm': self.rainfall_mm,
            'source':      self.source,
            'timestamp':   self.timestamp.isoformat(),
        }

    def __repr__(self):
        return f'<RainfallData {self.date} {self.location} {self.rainfall_mm}mm>'


# ── Aggregated Rainfall Stats ─────────────────────────────────────────────────

class RainfallStat(db.Model):
    """
    Pre-aggregated monthly/annual rainfall stats per province.
    Written by data/process_rainfall_data.py after ingestion.
    Used by /api/rainfall/stats and the province bar chart.
    """
    __tablename__ = 'rainfall_stats'

    id           = db.Column(db.Integer,     primary_key=True)
    period       = db.Column(db.String(7),   nullable=False, index=True)  # 'YYYY-MM' or 'YYYY'
    period_type  = db.Column(db.String(10),  nullable=False)              # 'monthly' | 'annual'
    location     = db.Column(db.String(100), nullable=True)
    total_mm     = db.Column(db.Float,       nullable=False)
    avg_mm       = db.Column(db.Float,       nullable=False)
    max_mm       = db.Column(db.Float,       nullable=True)
    min_mm       = db.Column(db.Float,       nullable=True)
    record_count = db.Column(db.Integer,     nullable=False, default=0)
    computed_at  = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':           self.id,
            'period':       self.period,
            'period_type':  self.period_type,
            'location':     self.location,
            'total_mm':     self.total_mm,
            'avg_mm':       self.avg_mm,
            'max_mm':       self.max_mm,
            'min_mm':       self.min_mm,
            'record_count': self.record_count,
            'computed_at':  self.computed_at.isoformat(),
        }

    def __repr__(self):
        return f'<RainfallStat {self.period} {self.location} avg={self.avg_mm}mm>'


# ── ML Predictions ────────────────────────────────────────────────────────────

class Prediction(db.Model):
    """ML model water-level predictions (single point or 24-h forecast)."""
    __tablename__ = 'predictions'

    id                 = db.Column(db.Integer,    primary_key=True)
    predicted_level_cm = db.Column(db.Float,      nullable=False)
    confidence_lower   = db.Column(db.Float,      nullable=True)
    confidence_upper   = db.Column(db.Float,      nullable=True)
    confidence_std     = db.Column(db.Float,      nullable=True)
    risk_level         = db.Column(db.String(20), nullable=True)   # SAFE | WARNING | CRITICAL
    prediction_for     = db.Column(db.DateTime,   nullable=False, index=True)
    created_at         = db.Column(db.DateTime,   default=datetime.utcnow, index=True)
    model_version      = db.Column(db.String(50), nullable=True)
    input_rainfall_mm  = db.Column(db.Float,      nullable=True)   # rainfall used as input

    def to_dict(self):
        return {
            'id':                 self.id,
            'predicted_level_cm': self.predicted_level_cm,
            'confidence_lower':   self.confidence_lower,
            'confidence_upper':   self.confidence_upper,
            'confidence_std':     self.confidence_std,
            'risk_level':         self.risk_level,
            'prediction_for':     self.prediction_for.isoformat(),
            'created_at':         self.created_at.isoformat(),
            'model_version':      self.model_version,
            'input_rainfall_mm':  self.input_rainfall_mm,
        }

    def __repr__(self):
        return f'<Prediction {self.prediction_for} {self.predicted_level_cm}cm {self.risk_level}>'


# ── Alerts ────────────────────────────────────────────────────────────────────

class Alert(db.Model):
    """System alerts generated by threshold breaches or prediction warnings."""
    __tablename__ = 'alerts'

    id              = db.Column(db.Integer,  primary_key=True)
    alert_type      = db.Column(db.String(20), nullable=False)  # SENSOR | PREDICTION | SYSTEM | CAMERA
    severity        = db.Column(db.String(20), nullable=False)  # INFO | WARNING | CRITICAL
    message         = db.Column(db.Text,       nullable=False)
    water_level     = db.Column(db.Float,      nullable=True)
    acknowledged    = db.Column(db.Boolean,    default=False,   nullable=False)
    acknowledged_at = db.Column(db.DateTime,   nullable=True)
    acknowledged_by = db.Column(db.String(50), nullable=True)   # user / system
    timestamp       = db.Column(db.DateTime,   default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id':              self.id,
            'alert_type':      self.alert_type,
            'severity':        self.severity,
            'message':         self.message,
            'water_level':     self.water_level,
            'acknowledged':    self.acknowledged,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'acknowledged_by': self.acknowledged_by,
            'timestamp':       self.timestamp.isoformat(),
        }

    def __repr__(self):
        return f'<Alert [{self.severity}] {self.message[:40]}>'


# ── Camera Captures ───────────────────────────────────────────────────────────

class CameraCapture(db.Model):
    """Images captured by the ESP32-CAM and their CV analysis results."""
    __tablename__ = 'camera_captures'

    id                 = db.Column(db.Integer,  primary_key=True)
    image_path         = db.Column(db.String(255), nullable=False)
    image_url          = db.Column(db.String(500), nullable=True)   # optional public URL
    trash_detected     = db.Column(db.Boolean,  default=False)
    blockage_detected  = db.Column(db.Boolean,  default=False)
    water_visible      = db.Column(db.Boolean,  default=False)
    confidence         = db.Column(db.Float,    nullable=True)
    analysis_data      = db.Column(db.JSON,     nullable=True)      # bounding boxes, labels
    notes              = db.Column(db.Text,     nullable=True)
    timestamp          = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id':                self.id,
            'image_path':        self.image_path,
            'image_url':         self.image_url,
            'trash_detected':    self.trash_detected,
            'blockage_detected': self.blockage_detected,
            'water_visible':     self.water_visible,
            'confidence':        self.confidence,
            'analysis_data':     self.analysis_data,
            'notes':             self.notes,
            'timestamp':         self.timestamp.isoformat(),
        }

    def __repr__(self):
        return f'<CameraCapture {self.timestamp} trash={self.trash_detected}>'


# ── System Status ─────────────────────────────────────────────────────────────

class SystemStatus(db.Model):
    """
    Single-row table tracking hardware connectivity.
    app.py upserts this record every sensor cycle.
    """
    __tablename__ = 'system_status'

    id                  = db.Column(db.Integer, primary_key=True)
    esp32_online        = db.Column(db.Boolean, default=False)
    esp32_cam_online    = db.Column(db.Boolean, default=False)
    raspberry_pi_online = db.Column(db.Boolean, default=False)
    battery_level       = db.Column(db.Float,   nullable=True)   # 0–100 %
    solar_charging      = db.Column(db.Boolean, default=False)
    wifi_rssi           = db.Column(db.Integer, nullable=True)   # dBm
    uptime_seconds      = db.Column(db.Integer, nullable=True)
    last_update         = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':                  self.id,
            'esp32_online':        self.esp32_online,
            'esp32_cam_online':    self.esp32_cam_online,
            'raspberry_pi_online': self.raspberry_pi_online,
            'battery_level':       self.battery_level,
            'solar_charging':      self.solar_charging,
            'wifi_rssi':           self.wifi_rssi,
            'uptime_seconds':      self.uptime_seconds,
            'last_update':         self.last_update.isoformat(),
        }

    def __repr__(self):
        return f'<SystemStatus batt={self.battery_level}% solar={self.solar_charging}>'


# ── ML Model Metrics ──────────────────────────────────────────────────────────

class ModelMetrics(db.Model):
    """
    Performance metrics written by ml/train_model.py after each training run.
    The dashboard reads the row where is_active=True for the KPI card.
    """
    __tablename__ = 'model_metrics'

    id               = db.Column(db.Integer,     primary_key=True)
    model_name       = db.Column(db.String(100),  nullable=False)   # e.g. 'Random Forest'
    algorithm        = db.Column(db.String(100),  nullable=True)    # full sklearn class name
    r2_score         = db.Column(db.Float,        nullable=True)
    cv_r2_mean       = db.Column(db.Float,        nullable=True)    # 5-fold CV mean
    cv_r2_std        = db.Column(db.Float,        nullable=True)    # 5-fold CV std
    rmse             = db.Column(db.Float,        nullable=True)
    mae              = db.Column(db.Float,        nullable=True)
    training_samples = db.Column(db.Integer,      nullable=True)
    test_samples     = db.Column(db.Integer,      nullable=True)
    features_count   = db.Column(db.Integer,      nullable=True)
    dataset_records  = db.Column(db.Integer,      nullable=True)    # total rows in training CSV
    is_active        = db.Column(db.Boolean,      default=False,    nullable=False)
    model_path       = db.Column(db.String(255),  nullable=True)    # path to .pkl file
    trained_at       = db.Column(db.DateTime,     default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':               self.id,
            'model_name':       self.model_name,
            'algorithm':        self.algorithm,
            'r2_score':         self.r2_score,
            'cv_r2_mean':       self.cv_r2_mean,
            'cv_r2_std':        self.cv_r2_std,
            'rmse':             self.rmse,
            'mae':              self.mae,
            'training_samples': self.training_samples,
            'test_samples':     self.test_samples,
            'features_count':   self.features_count,
            'dataset_records':  self.dataset_records,
            'is_active':        self.is_active,
            'model_path':       self.model_path,
            'trained_at':       self.trained_at.isoformat(),
        }

    def __repr__(self):
        return f'<ModelMetrics {self.model_name} R²={self.r2_score} active={self.is_active}>'


# ── Dataset Info ──────────────────────────────────────────────────────────────

class DatasetInfo(db.Model):
    """
    Metadata about the loaded HDX rainfall dataset.
    Written once by data/process_rainfall_data.py.
    Read by /api/dataset/info to populate the dashboard panel.
    """
    __tablename__ = 'dataset_info'

    id              = db.Column(db.Integer,     primary_key=True)
    source_name     = db.Column(db.String(200), nullable=False)
    total_records   = db.Column(db.Integer,     nullable=False, default=0)
    earliest_date   = db.Column(db.Date,        nullable=True)
    latest_date     = db.Column(db.Date,        nullable=True)
    provinces       = db.Column(db.JSON,        nullable=True)   # list of province names
    full_size_mb    = db.Column(db.Float,       nullable=True)
    recent_size_mb  = db.Column(db.Float,       nullable=True)
    columns_list    = db.Column(db.JSON,        nullable=True)   # column names in CSV
    last_updated    = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':             self.id,
            'source':         self.source_name,
            'total_records':  self.total_records,
            'earliest_date':  self.earliest_date.isoformat() if self.earliest_date else None,
            'latest_date':    self.latest_date.isoformat()   if self.latest_date   else None,
            'provinces':      self.provinces,
            'full_size_mb':   self.full_size_mb,
            'recent_size_mb': self.recent_size_mb,
            'columns':        self.columns_list,
            'last_updated':   self.last_updated.isoformat(),
        }

    def __repr__(self):
        return f'<DatasetInfo {self.total_records} records {self.earliest_date}→{self.latest_date}>'