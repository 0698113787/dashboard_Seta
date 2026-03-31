"""
routes/api.py
=============
All /api/* REST endpoints for the Smart Drain System.
Registered as a Flask Blueprint in app.py with url_prefix='/api'.

Endpoints
---------
Sensor
  GET  /api/sensor/latest            → most recent ESP32 reading
  GET  /api/sensor/history           → readings over last N hours
  POST /api/sensor/reading           → ingest reading from ESP32

Rainfall
  GET  /api/rainfall                 → raw records for last N days
  GET  /api/rainfall/stats           → total / avg / max summary
  GET  /api/rainfall/province        → 30-day avg grouped by province
  GET  /api/rainfall/monthly         → monthly aggregates for chart

Predictions
  GET  /api/predictions              → recent ML predictions
  GET  /api/predictions/latest       → single latest prediction

Alerts
  GET  /api/alerts                   → recent alerts (paginated)
  POST /api/alerts/<id>/acknowledge  → mark alert as acknowledged
  GET  /api/alerts/summary           → counts by severity

System
  GET  /api/system/status            → hardware connectivity

Model
  GET  /api/model/metrics            → active ML model performance
  GET  /api/model/history            → all past training runs

Dataset
  GET  /api/dataset/info             → HDX dataset metadata
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta

from models import (
    db,
    SensorReading,
    RainfallData,
    RainfallStat,
    Prediction,
    Alert,
    SystemStatus,
    ModelMetrics,
    DatasetInfo,
    CameraCapture,
)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ─────────────────────────────────────────────────────────────────────────────
# SENSOR
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/sensor/latest', methods=['GET'])
def sensor_latest():
    """Return the single most recent sensor reading."""
    r = SensorReading.query.order_by(SensorReading.timestamp.desc()).first()
    if not r:
        return jsonify({'error': 'No sensor data yet'}), 404
    return jsonify(r.to_dict())


@api_bp.route('/sensor/history', methods=['GET'])
def sensor_history():
    """
    Return sensor readings over a window.
    Query params:
        hours  (int, default 24)  — look-back window
        limit  (int, default 500) — max rows returned
    """
    hours = int(request.args.get('hours', 24))
    limit = int(request.args.get('limit', 500))
    since = datetime.utcnow() - timedelta(hours=hours)

    readings = (
        SensorReading.query
        .filter(SensorReading.timestamp >= since)
        .order_by(SensorReading.timestamp.asc())
        .limit(limit)
        .all()
    )
    return jsonify([r.to_dict() for r in readings])


@api_bp.route('/sensor/reading', methods=['POST'])
def post_sensor_reading():
    """
    Ingest a reading posted by the ESP32.
    Expected JSON body:
        { "water_level_cm": float, "valve_status": "OPEN"|"CLOSED",
          "rainfall_mm": float (optional), "temperature_c": float (optional) }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    required = ['water_level_cm', 'valve_status']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing field: {field}'}), 422

    reading = SensorReading(
        water_level_cm=float(data['water_level_cm']),
        valve_status=str(data['valve_status']),
        rainfall_mm=data.get('rainfall_mm'),
        temperature_c=data.get('temperature_c'),
        humidity_pct=data.get('humidity_pct'),
    )
    db.session.add(reading)
    db.session.commit()
    return jsonify({'status': 'ok', 'id': reading.id}), 201


# ─────────────────────────────────────────────────────────────────────────────
# RAINFALL
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/rainfall', methods=['GET'])
def rainfall():
    """
    Raw rainfall records.
    Query params:
        days     (int, default 30)
        location (str, optional) — filter by province name
        limit    (int, default 2000)
    """
    days     = int(request.args.get('days', 30))
    location = request.args.get('location')
    limit    = int(request.args.get('limit', 2000))
    since    = datetime.utcnow().date() - timedelta(days=days)

    q = RainfallData.query.filter(RainfallData.date >= since)
    if location:
        q = q.filter(RainfallData.location.ilike(f'%{location}%'))

    records = q.order_by(RainfallData.date.asc()).limit(limit).all()
    return jsonify([r.to_dict() for r in records])


@api_bp.route('/rainfall/stats', methods=['GET'])
def rainfall_stats():
    """Overall rainfall summary across the whole dataset."""
    total = db.session.query(db.func.count(RainfallData.id)).scalar() or 0
    avg   = db.session.query(db.func.avg(RainfallData.rainfall_mm)).scalar() or 0
    max_r = db.session.query(db.func.max(RainfallData.rainfall_mm)).scalar() or 0
    min_r = db.session.query(db.func.min(RainfallData.rainfall_mm)).scalar() or 0
    return jsonify({
        'total_records': total,
        'average_mm':    round(float(avg),   2),
        'max_mm':        round(float(max_r), 2),
        'min_mm':        round(float(min_r), 2),
    })


@api_bp.route('/rainfall/province', methods=['GET'])
def rainfall_province():
    """
    Average & total rainfall per province over the last N days.
    Query params:
        days (int, default 30)
    """
    days  = int(request.args.get('days', 30))
    since = datetime.utcnow().date() - timedelta(days=days)

    rows = (
        db.session.query(
            RainfallData.location,
            db.func.avg(RainfallData.rainfall_mm).label('avg_mm'),
            db.func.sum(RainfallData.rainfall_mm).label('total_mm'),
            db.func.max(RainfallData.rainfall_mm).label('max_mm'),
            db.func.count(RainfallData.id).label('records'),
        )
        .filter(RainfallData.date >= since, RainfallData.location.isnot(None))
        .group_by(RainfallData.location)
        .order_by(db.func.avg(RainfallData.rainfall_mm).desc())
        .all()
    )
    return jsonify([{
        'location': r.location,
        'avg_mm':   round(float(r.avg_mm),   2),
        'total_mm': round(float(r.total_mm), 2),
        'max_mm':   round(float(r.max_mm),   2),
        'records':  r.records,
    } for r in rows])


@api_bp.route('/rainfall/monthly', methods=['GET'])
def rainfall_monthly():
    """
    Monthly average rainfall — used by the bar chart.
    Query params:
        months   (int, default 12)
        location (str, optional)
    """
    months   = int(request.args.get('months', 12))
    location = request.args.get('location')
    since    = datetime.utcnow().date() - timedelta(days=months * 31)

    q = RainfallData.query.filter(RainfallData.date >= since)
    if location:
        q = q.filter(RainfallData.location.ilike(f'%{location}%'))

    records = q.order_by(RainfallData.date.asc()).all()

    # Aggregate in Python so we stay DB-agnostic
    monthly: dict = {}
    for r in records:
        key = r.date.strftime('%Y-%m')
        if key not in monthly:
            monthly[key] = {'values': [], 'location': r.location}
        monthly[key]['values'].append(r.rainfall_mm)

    result = []
    for period in sorted(monthly.keys()):
        vals = monthly[period]['values']
        result.append({
            'period':   period,
            'avg_mm':   round(sum(vals) / len(vals), 2),
            'total_mm': round(sum(vals), 2),
            'max_mm':   round(max(vals), 2),
            'records':  len(vals),
        })

    return jsonify(result[-months:])


# ─────────────────────────────────────────────────────────────────────────────
# PREDICTIONS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/predictions', methods=['GET'])
def predictions():
    """
    Recent ML predictions.
    Query params:
        hours (int, default 24)
        limit (int, default 50)
    """
    hours = int(request.args.get('hours', 24))
    limit = int(request.args.get('limit', 50))
    since = datetime.utcnow() - timedelta(hours=hours)

    preds = (
        Prediction.query
        .filter(Prediction.created_at >= since)
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify([p.to_dict() for p in preds])


@api_bp.route('/predictions/latest', methods=['GET'])
def prediction_latest():
    """Return the single most recent ML prediction."""
    pred = Prediction.query.order_by(Prediction.created_at.desc()).first()
    if not pred:
        return jsonify({'error': 'No predictions yet'}), 404
    return jsonify(pred.to_dict())


# ─────────────────────────────────────────────────────────────────────────────
# ALERTS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/alerts', methods=['GET'])
def alerts():
    """
    Recent alerts.
    Query params:
        limit        (int,  default 20)
        severity     (str,  optional) — INFO | WARNING | CRITICAL
        acknowledged (bool, optional) — true | false
    """
    limit        = int(request.args.get('limit', 20))
    severity     = request.args.get('severity')
    ack_param    = request.args.get('acknowledged')

    q = Alert.query
    if severity:
        q = q.filter(Alert.severity == severity.upper())
    if ack_param is not None:
        q = q.filter(Alert.acknowledged == (ack_param.lower() == 'true'))

    items = q.order_by(Alert.timestamp.desc()).limit(limit).all()
    return jsonify([a.to_dict() for a in items])


@api_bp.route('/alerts/<int:alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    """Mark a single alert as acknowledged."""
    alert = Alert.query.get_or_404(alert_id)
    if alert.acknowledged:
        return jsonify({'status': 'already_acknowledged'})

    data = request.get_json(silent=True) or {}
    alert.acknowledged    = True
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by = data.get('by', 'dashboard_user')
    db.session.commit()
    return jsonify({'status': 'ok', 'acknowledged_at': alert.acknowledged_at.isoformat()})


@api_bp.route('/alerts/summary', methods=['GET'])
def alerts_summary():
    """Count of alerts in last 24 h grouped by severity."""
    since = datetime.utcnow() - timedelta(hours=24)
    rows = (
        db.session.query(Alert.severity, db.func.count(Alert.id))
        .filter(Alert.timestamp >= since)
        .group_by(Alert.severity)
        .all()
    )
    summary = {'INFO': 0, 'WARNING': 0, 'CRITICAL': 0, 'total': 0}
    for sev, cnt in rows:
        summary[sev] = cnt
        summary['total'] += cnt
    return jsonify(summary)


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM STATUS
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/system/status', methods=['GET'])
def system_status():
    """Return the latest hardware status row."""
    status = SystemStatus.query.order_by(SystemStatus.last_update.desc()).first()
    if not status:
        return jsonify({'error': 'No system status available'}), 404
    return jsonify(status.to_dict())


# ─────────────────────────────────────────────────────────────────────────────
# ML MODEL
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/model/metrics', methods=['GET'])
def model_metrics():
    """Return the currently active ML model metrics."""
    metrics = ModelMetrics.query.filter_by(is_active=True).first()
    if not metrics:
        # Return a placeholder until the first training run completes
        metrics = ModelMetrics(
            model_name='Random Forest',
            r2_score=0.0,
            rmse=0.0,
            mae=0.0,
            training_samples=0,
            features_count=24,
            is_active=True,
        )
        db.session.add(metrics)
        db.session.commit()
    return jsonify(metrics.to_dict())


@api_bp.route('/model/history', methods=['GET'])
def model_history():
    """Return all past model training runs, newest first."""
    runs = ModelMetrics.query.order_by(ModelMetrics.trained_at.desc()).all()
    return jsonify([m.to_dict() for m in runs])


# ─────────────────────────────────────────────────────────────────────────────
# DATASET
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/dataset/info', methods=['GET'])
def dataset_info():
    """
    Return metadata about the loaded HDX rainfall dataset.
    Prefers the DatasetInfo table (written by process_rainfall_data.py).
    Falls back to a live aggregate from RainfallData if table is empty.
    """
    info = DatasetInfo.query.order_by(DatasetInfo.last_updated.desc()).first()
    if info:
        return jsonify(info.to_dict())

    # Live fallback
    total    = db.session.query(db.func.count(RainfallData.id)).scalar() or 0
    earliest = db.session.query(db.func.min(RainfallData.date)).scalar()
    latest_d = db.session.query(db.func.max(RainfallData.date)).scalar()
    return jsonify({
        'source':         'OCHA HDX – South African Subnational Rainfall',
        'total_records':  total,
        'earliest_date':  str(earliest) if earliest else None,
        'latest_date':    str(latest_d) if latest_d else None,
        'full_size_mb':   11.7,
        'recent_size_mb': 1.1,
    })


# ─────────────────────────────────────────────────────────────────────────────
# CAMERA
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/camera/latest', methods=['GET'])
def camera_latest():
    """Return the most recent camera capture analysis."""
    cap = CameraCapture.query.order_by(CameraCapture.timestamp.desc()).first()
    if not cap:
        return jsonify({'error': 'No camera data yet'}), 404
    return jsonify(cap.to_dict())


@api_bp.route('/camera/captures', methods=['GET'])
def camera_captures():
    """
    Return recent camera captures.
    Query params:
        limit (int, default 10)
    """
    limit = int(request.args.get('limit', 10))
    caps  = CameraCapture.query.order_by(CameraCapture.timestamp.desc()).limit(limit).all()
    return jsonify([c.to_dict() for c in caps])