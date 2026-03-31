import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import joblib
import os
from datetime import datetime
import json

class WaterLevelPredictor:
    """Train ML model to predict water levels based on rainfall"""
    
    def __init__(self, model_folder='ml/models'):
        self.model_folder = model_folder
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        self.metrics = {}
        
        os.makedirs(model_folder, exist_ok=True)
    
    def load_rainfall_data(self, filepath='data/rainfall_processed.csv'):
        """Load processed rainfall data"""
        print(f"📂 Loading data from {filepath}...")
        
        df = pd.read_csv(filepath)
        print(f"✅ Loaded {len(df):,} rows")
        
        return df
    
    def engineer_features(self, df):
        """Create features for prediction"""
        print("\n🔧 Engineering features...")
        
        df = df.copy()
        
        # Ensure date column exists
        if 'date' not in df.columns:
            date_col = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()][0]
            df['date'] = pd.to_datetime(df[date_col], errors='coerce')
        
        # Time-based features
        df['year'] = pd.to_datetime(df['date']).dt.year
        df['month'] = pd.to_datetime(df['date']).dt.month
        df['day'] = pd.to_datetime(df['date']).dt.day
        df['day_of_year'] = pd.to_datetime(df['date']).dt.dayofyear
        df['week'] = pd.to_datetime(df['date']).dt.isocalendar().week
        df['quarter'] = pd.to_datetime(df['date']).dt.quarter
        df['is_weekend'] = pd.to_datetime(df['date']).dt.dayofweek.isin([5, 6]).astype(int)
        
        # Cyclical encoding for month and day
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
        df['day_sin'] = np.sin(2 * np.pi * df['day'] / 31)
        df['day_cos'] = np.cos(2 * np.pi * df['day'] / 31)
        
        # Rainfall features
        if 'rainfall_mm' in df.columns:
            # Lagged features (previous days)
            df['rainfall_lag_1'] = df['rainfall_mm'].shift(1)
            df['rainfall_lag_3'] = df['rainfall_mm'].shift(3)
            df['rainfall_lag_7'] = df['rainfall_mm'].shift(7)
            
            # Rolling statistics
            df['rainfall_7day_avg'] = df['rainfall_mm'].rolling(window=7, min_periods=1).mean()
            df['rainfall_7day_max'] = df['rainfall_mm'].rolling(window=7, min_periods=1).max()
            df['rainfall_7day_std'] = df['rainfall_mm'].rolling(window=7, min_periods=1).std()
            
            df['rainfall_30day_avg'] = df['rainfall_mm'].rolling(window=30, min_periods=1).mean()
            df['rainfall_30day_max'] = df['rainfall_mm'].rolling(window=30, min_periods=1).max()
            
            # Cumulative rainfall (last 7 days)
            df['rainfall_7day_sum'] = df['rainfall_mm'].rolling(window=7, min_periods=1).sum()
            
            # Rate of change
            df['rainfall_change'] = df['rainfall_mm'].diff()
            df['rainfall_change_rate'] = df['rainfall_change'] / (df['rainfall_lag_1'] + 1)
        
        # Create target variable: estimated water level
        # Water level = f(recent rainfall, cumulative rainfall, drainage rate)
        # Simplified model: water_level proportional to recent rainfall
        
        # Simulate realistic water levels (0-100 cm)
        if 'rainfall_mm' in df.columns:
            # Base level from recent rainfall
            base_level = df['rainfall_7day_sum'] * 0.5  # Scale factor
            
            # Add seasonal effects
            seasonal_factor = 1 + 0.3 * df['month_sin']  # Higher in summer
            
            # Add noise for realism
            noise = np.random.normal(0, 5, len(df))
            
            df['water_level_cm'] = (base_level * seasonal_factor + noise).clip(0, 100)
        
        # Drop rows with NaN values
        df = df.dropna()
        
        print(f"✅ Feature engineering complete: {len(df):,} rows, {len(df.columns)} features")
        
        return df
    
    def prepare_training_data(self, df, target_col='water_level_cm'):
        """Prepare X and y for training"""
        print("\n📊 Preparing training data...")
        
        # Select feature columns
        exclude_cols = ['date', target_col, 'rainfall_mm']
        feature_cols = [col for col in df.columns if col not in exclude_cols]
        
        X = df[feature_cols]
        y = df[target_col]
        
        self.feature_names = feature_cols
        
        print(f"   Features: {len(feature_cols)}")
        print(f"   Samples: {len(X):,}")
        print(f"   Target: {target_col}")
        print(f"   Target range: {y.min():.2f} - {y.max():.2f} cm")
        
        return X, y
    
    def train(self, X, y, test_size=0.2, random_state=42):
        """Train the model"""
        print("\n🎯 Training model...")
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, shuffle=False
        )
        
        print(f"   Training set: {len(X_train):,} samples")
        print(f"   Test set: {len(X_test):,} samples")
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Try multiple models
        models = {
            'Random Forest': RandomForestRegressor(
                n_estimators=100,
                max_depth=15,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=random_state,
                n_jobs=-1
            ),
            'Gradient Boosting': GradientBoostingRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=random_state
            )
        }
        
        best_model = None
        best_score = -np.inf
        
        for name, model in models.items():
            print(f"\n   Training {name}...")
            model.fit(X_train_scaled, y_train)
            
            # Evaluate
            y_pred = model.predict(X_test_scaled)
            
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            mae = mean_absolute_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)
            
            print(f"      RMSE: {rmse:.2f} cm")
            print(f"      MAE: {mae:.2f} cm")
            print(f"      R²: {r2:.4f}")
            
            if r2 > best_score:
                best_score = r2
                best_model = model
                self.model = model
                
                self.metrics = {
                    'model_name': name,
                    'rmse': float(rmse),
                    'mae': float(mae),
                    'r2': float(r2),
                    'train_samples': len(X_train),
                    'test_samples': len(X_test),
                    'features': len(self.feature_names),
                    'trained_at': datetime.now().isoformat()
                }
        
        print(f"\n✅ Best model: {self.metrics['model_name']}")
        print(f"   R² Score: {self.metrics['r2']:.4f}")
        
        # Feature importance
        if hasattr(self.model, 'feature_importances_'):
            importances = pd.DataFrame({
                'feature': self.feature_names,
                'importance': self.model.feature_importances_
            }).sort_values('importance', ascending=False)
            
            print(f"\n📊 Top 10 Important Features:")
            for idx, row in importances.head(10).iterrows():
                print(f"   {row['feature']}: {row['importance']:.4f}")
            
            self.metrics['feature_importances'] = importances.to_dict('records')
    
    def save_model(self):
        """Save trained model"""
        if self.model is None:
            print("❌ No model to save")
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save model
        model_path = os.path.join(self.model_folder, f'water_level_model_{timestamp}.pkl')
        joblib.dump(self.model, model_path)
        
        # Save scaler
        scaler_path = os.path.join(self.model_folder, f'scaler_{timestamp}.pkl')
        joblib.dump(self.scaler, scaler_path)
        
        # Save metadata
        metadata = {
            'model_path': model_path,
            'scaler_path': scaler_path,
            'feature_names': self.feature_names,
            'metrics': self.metrics
        }
        
        metadata_path = os.path.join(self.model_folder, f'metadata_{timestamp}.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Save as latest
        latest_model = os.path.join(self.model_folder, 'water_level_model_latest.pkl')
        latest_scaler = os.path.join(self.model_folder, 'scaler_latest.pkl')
        latest_metadata = os.path.join(self.model_folder, 'metadata_latest.json')
        
        joblib.dump(self.model, latest_model)
        joblib.dump(self.scaler, latest_scaler)
        with open(latest_metadata, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"\n💾 Model saved:")
        print(f"   {model_path}")
        print(f"   {scaler_path}")
        print(f"   {metadata_path}")
    
    def load_model(self, model_path=None):
        """Load trained model"""
        if model_path is None:
            model_path = os.path.join(self.model_folder, 'water_level_model_latest.pkl')
        
        scaler_path = model_path.replace('water_level_model', 'scaler')
        metadata_path = model_path.replace('water_level_model', 'metadata').replace('.pkl', '.json')
        
        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
            self.feature_names = metadata['feature_names']
            self.metrics = metadata['metrics']
        
        print(f"✅ Model loaded from {model_path}")
        return self.model

def main():
    """Main training pipeline"""
    print("=" * 60)
    print("🤖  WATER LEVEL PREDICTION MODEL TRAINING")
    print("=" * 60)
    
    predictor = WaterLevelPredictor()
    
    # Load data
    df = predictor.load_rainfall_data()
    
    # Engineer features
    df = predictor.engineer_features(df)
    
    # Prepare training data
    X, y = predictor.prepare_training_data(df)
    
    # Train model
    predictor.train(X, y)
    
    # Save model
    predictor.save_model()
    
    print("\n" + "=" * 60)
    print("✅ Training complete!")
    print("=" * 60)
    print(f"\n📊 Model Performance:")
    print(f"   Algorithm: {predictor.metrics['model_name']}")
    print(f"   R² Score: {predictor.metrics['r2']:.4f}")
    print(f"   RMSE: {predictor.metrics['rmse']:.2f} cm")
    print(f"   MAE: {predictor.metrics['mae']:.2f} cm")
    print(f"   Training Samples: {predictor.metrics['train_samples']:,}")
    print(f"   Features Used: {predictor.metrics['features']}")
    
    return predictor

if __name__ == '__main__':
    main()