"""
routes/dashboard.py
===================
Page routes for the Smart Drain System dashboard.
Registered as a Flask Blueprint in app.py (no url_prefix — serves from /).

Routes
------
  GET  /                   → main dashboard
  GET  /overview           → alias for main dashboard
  GET  /water-level        → water level detail page (renders same template, section pre-selected)
  GET  /rainfall           → rainfall analysis page
  GET  /predictions        → ML predictions page
  GET  /alerts             → alerts management page
  GET  /system             → system status page
  GET  /health             → simple JSON health-check (used by uptime monitors)
"""

from flask import Blueprint, render_template, jsonify, redirect, url_for
from datetime import datetime

from models import (
    db,
    SensorReading,
    Alert,
    SystemStatus,
    ModelMetrics,
    RainfallData,
    DatasetInfo,
)

dashboard_bp = Blueprint('dashboard', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _base_context(active_section: str = 'overview') -> dict:
    """
    Build the template context dict shared by every dashboard page.
    Contains summary stats injected at render time so the page has data
    even before JavaScript/SocketIO fires.
    """
    # Latest sensor reading
    latest = SensorReading.query.order_by(SensorReading.timestamp.desc()).first()

    # Unacknowledged alert counts
    critical_count = Alert.query.filter_by(severity='CRITICAL', acknowledged=False).count()
    warning_count  = Alert.query.filter_by(severity='WARNING',  acknowledged=False).count()

    # System online flag
    status       = SystemStatus.query.order_by(SystemStatus.last_update.desc()).first()
    system_ok    = status.esp32_online if status else False
    battery      = status.battery_level if status else None

    # Active ML model
    model        = ModelMetrics.query.filter_by(is_active=True).first()

    # Dataset record count
    dataset_info = DatasetInfo.query.order_by(DatasetInfo.last_updated.desc()).first()
    dataset_records = (
        dataset_info.total_records if dataset_info
        else db.session.query(db.func.count(RainfallData.id)).scalar() or 0
    )

    return {
        'active_section':   active_section,
        'now':              datetime.utcnow(),

        # Sensor
        'water_level':      latest.water_level_cm if latest else None,
        'valve_status':     latest.valve_status   if latest else 'UNKNOWN',
        'last_reading':     latest.timestamp      if latest else None,

        # Alerts
        'critical_alerts':  critical_count,
        'warning_alerts':   warning_count,

        # System
        'system_online':    system_ok,
        'battery_level':    battery,

        # ML model
        'model_name':       model.model_name if model else 'Not trained',
        'model_r2':         model.r2_score   if model else None,
        'model_rmse':       model.rmse        if model else None,

        # Dataset
        'dataset_records':  dataset_records,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page Routes
# ─────────────────────────────────────────────────────────────────────────────

@dashboard_bp.route('/')
def index():
    """Main dashboard — overview section."""
    ctx = _base_context('overview')
    return render_template('dashboard.html', **ctx)


@dashboard_bp.route('/overview')
def overview():
    """Alias for the root dashboard."""
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/water-level')
def water_level():
    """Water level detail view — same template, water section pre-selected."""
    ctx = _base_context('water')
    return render_template('dashboard.html', **ctx)


@dashboard_bp.route('/rainfall')
def rainfall():
    """Rainfall analysis page."""
    ctx = _base_context('rainfall')
    return render_template('dashboard.html', **ctx)


@dashboard_bp.route('/predictions')
def predictions():
    """ML predictions page."""
    ctx = _base_context('predictions')
    return render_template('dashboard.html', **ctx)


@dashboard_bp.route('/alerts')
def alerts():
    """Alerts management page."""
    ctx = _base_context('alerts')
    return render_template('dashboard.html', **ctx)


@dashboard_bp.route('/system')
def system():
    """System status and hardware diagnostics page."""
    ctx = _base_context('system')
    return render_template('dashboard.html', **ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────

@dashboard_bp.route('/health')
def health():
    """
    Lightweight JSON health-check endpoint.
    Returns 200 when the app and database are reachable.
    """
    try:
        db.session.execute(db.text('SELECT 1'))
        db_ok = True
    except Exception:
        db_ok = False

    status = SystemStatus.query.order_by(SystemStatus.last_update.desc()).first()

    payload = {
        'status':       'ok' if db_ok else 'degraded',
        'database':     'ok' if db_ok else 'error',
        'timestamp':    datetime.utcnow().isoformat(),
        'esp32_online': status.esp32_online if status else False,
        'battery':      status.battery_level if status else None,
    }
    http_code = 200 if db_ok else 503
    return jsonify(payload), http_code