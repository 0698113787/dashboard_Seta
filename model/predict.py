import pandas as pd
import numpy as np
import joblib
import json
import os
from datetime import datetime, timedelta

class WaterLevelPredictor:
    """Make predictions using trained model"""
    
    def __init__(self, model_folder='ml/models'):
        self.model_folder = model_folder
        self.model = None
        self.scaler = None
        self.feature_names = []
        self.metadata = {}
        
        self.load_latest_model()
    
    def load_latest_model(self):
        """Load the latest trained model"""
        model_path = os.path.join(self.model_folder, 'water_level_model_latest.pkl')
        scaler_path = os.path.join(self.model_folder, 'scaler_latest.pkl')
        metadata_path = os.path.join(self.model_folder, 'metadata_latest.json')
        
        if not os.path.exists(model_path):
            print("⚠️  No trained model found. Please run train_model.py first.")
            return False
        
        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)
        
        with open(metadata_path, 'r') as f:
            self.metadata = json.load(f)
            self.feature_names = self.metadata['feature_names']
        
        print(f"✅ Loaded model: {self.metadata['metrics']['model_name']}")
        print(f"   R² Score: {self.metadata['metrics']['r2']:.4f}")
        print(f"   Trained: {self.metadata['metrics']['trained_at']}")
        
        return True
    
    def prepare_features(self, current_data):
        """
        Prepare features for prediction from current sensor data
        
        Args:
            current_data (dict): {
                'current_rainfall': float (mm),
                'rainfall_history': list of floats (last 30 days),
                'date': datetime or string
            }
        """
        if isinstance(current_data['date'], str):
            date = pd.to_datetime(current_data['date'])
        else:
            date = current_data['date']
        
        # Time-based features
        features = {
            'year': date.year,
            'month': date.month,
            'day': date.day,
            'day_of_year': date.timetuple().tm_yday,
            'week': date.isocalendar()[1],
            'quarter': (date.month - 1) // 3 + 1,
            'is_weekend': 1 if date.weekday() in [5, 6] else 0,
        }
        
        # Cyclical encoding
        features['month_sin'] = np.sin(2 * np.pi * date.month / 12)
        features['month_cos'] = np.cos(2 * np.pi * date.month / 12)
        features['day_sin'] = np.sin(2 * np.pi * date.day / 31)
        features['day_cos'] = np.cos(2 * np.pi * date.day / 31)
        
        # Rainfall features
        rainfall_history = current_data.get('rainfall_history', [])
        current_rainfall = current_data.get('current_rainfall', 0)
        
        # Ensure we have at least some history
        if len(rainfall_history) == 0:
            rainfall_history = [0] * 30
        
        rainfall_series = pd.Series(rainfall_history + [current_rainfall])
        
        # Lagged features
        features['rainfall_lag_1'] = rainfall_series.iloc[-2] if len(rainfall_series) > 1 else 0
        features['rainfall_lag_3'] = rainfall_series.iloc[-4] if len(rainfall_series) > 3 else 0
        features['rainfall_lag_7'] = rainfall_series.iloc[-8] if len(rainfall_series) > 7 else 0
        
        # Rolling statistics (last 7 days)
        last_7 = rainfall_series.tail(7)
        features['rainfall_7day_avg'] = last_7.mean()
        features['rainfall_7day_max'] = last_7.max()
        features['rainfall_7day_std'] = last_7.std() if len(last_7) > 1 else 0
        features['rainfall_7day_sum'] = last_7.sum()
        
        # Rolling statistics (last 30 days)
        last_30 = rainfall_series.tail(30)
        features['rainfall_30day_avg'] = last_30.mean()
        features['rainfall_30day_max'] = last_30.max()
        
        # Rate of change
        features['rainfall_change'] = current_rainfall - features['rainfall_lag_1']
        features['rainfall_change_rate'] = features['rainfall_change'] / (features['rainfall_lag_1'] + 1)
        
        # Create DataFrame with correct column order
        df = pd.DataFrame([features])
        
        # Ensure all required features are present
        for feat in self.feature_names:
            if feat not in df.columns:
                df[feat] = 0
        
        # Select only the features used in training
        df = df[self.feature_names]
        
        return df
    
    def predict(self, current_data):
        """
        Make a single prediction
        
        Returns:
            dict: {
                'predicted_water_level': float (cm),
                'confidence_interval': tuple (lower, upper),
                'risk_level': string ('SAFE', 'WARNING', 'CRITICAL')
            }
        """
        if self.model is None:
            return None
        
        # Prepare features
        X = self.prepare_features(current_data)
        
        # Scale features
        X_scaled = self.scaler.transform(X)
        
        # Predict
        prediction = self.model.predict(X_scaled)[0]
        
        # Estimate confidence interval (using model's estimators if Random Forest)
        if hasattr(self.model, 'estimators_'):
            predictions = [tree.predict(X_scaled)[0] for tree in self.model.estimators_]
            std = np.std(predictions)
            lower = prediction - 1.96 * std
            upper = prediction + 1.96 * std
        else:
            # Fallback to simple estimate
            std = prediction * 0.1
            lower = prediction - std
            upper = prediction + std
        
        # Determine risk level
        if prediction < 20:
            risk_level = 'SAFE'
        elif prediction < 30:
            risk_level = 'WARNING'
        else:
            risk_level = 'CRITICAL'
        
        result = {
            'predicted_water_level': float(prediction),
            'confidence_interval': (float(lower), float(upper)),
            'confidence_std': float(std),
            'risk_level': risk_level,
            'prediction_time': datetime.now().isoformat()
        }
        
        return result
    
    def predict_next_hours(self, current_data, hours=24):
        """
        Predict water levels for next N hours
        
        Args:
            current_data: Current sensor data
            hours: Number of hours to predict
            
        Returns:
            list of predictions
        """
        predictions = []
        
        # Get current date
        if isinstance(current_data['date'], str):
            current_date = pd.to_datetime(current_data['date'])
        else:
            current_date = current_data['date']
        
        # Make predictions for each hour
        for hour in range(1, hours + 1):
            future_date = current_date + timedelta(hours=hour)
            
            future_data = current_data.copy()
            future_data['date'] = future_date
            
            # Assume rainfall decreases gradually (simple model)
            # In production, you'd use weather forecast API
            decay_factor = 0.95 ** hour
            future_data['current_rainfall'] = current_data.get('current_rainfall', 0) * decay_factor
            
            pred = self.predict(future_data)
            pred['hour'] = hour
            pred['timestamp'] = future_date.isoformat()
            
            predictions.append(pred)
        
        return predictions
    
    def get_model_info(self):
        """Get information about loaded model"""
        return {
            'model_name': self.metadata.get('metrics', {}).get('model_name', 'Unknown'),
            'r2_score': self.metadata.get('metrics', {}).get('r2', 0),
            'rmse': self.metadata.get('metrics', {}).get('rmse', 0),
            'mae': self.metadata.get('metrics', {}).get('mae', 0),
            'trained_at': self.metadata.get('metrics', {}).get('trained_at', 'Unknown'),
            'features_count': len(self.feature_names),
            'training_samples': self.metadata.get('metrics', {}).get('train_samples', 0)
        }

# Example usage
def demo():
    """Demo prediction"""
    print("=" * 60)
    print("🔮  WATER LEVEL PREDICTION DEMO")
    print("=" * 60)
    
    predictor = WaterLevelPredictor()
    
    if predictor.model is None:
        print("\n❌ No model loaded. Run training first:")
        print("   python ml/train_model.py")
        return
    
    # Example current data (simulated from sensors)
    current_data = {
        'date': datetime.now(),
        'current_rainfall': 15.5,  # mm today
        'rainfall_history': [10, 5, 0, 0, 3, 8, 12, 20, 15, 5] + [0] * 20  # Last 30 days
    }
    
    # Single prediction
    print("\n📊 Current Prediction:")
    result = predictor.predict(current_data)
    
    print(f"   Water Level: {result['predicted_water_level']:.2f} cm")
    print(f"   Confidence Interval: {result['confidence_interval'][0]:.2f} - {result['confidence_interval'][1]:.2f} cm")
    print(f"   Risk Level: {result['risk_level']}")
    
    # 24-hour forecast
    print("\n📈 Next 24 Hours Forecast:")
    forecast = predictor.predict_next_hours(current_data, hours=24)
    
    for pred in forecast[::3]:  # Show every 3 hours
        print(f"   Hour {pred['hour']:2d}: {pred['predicted_water_level']:.2f} cm ({pred['risk_level']})")
    
    # Model info
    print("\n🤖 Model Information:")
    info = predictor.get_model_info()
    for key, value in info.items():
        print(f"   {key}: {value}")
    
    print("\n" + "=" * 60)

if __name__ == '__main__':
    demo()