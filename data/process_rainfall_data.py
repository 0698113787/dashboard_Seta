import pandas as pd
import requests
import json
from datetime import datetime
import os

class RainfallDataProcessor:
    """Process and combine South African rainfall data"""
    
    def __init__(self, data_folder='data'):
        self.data_folder = data_folder
        self.combined_data = None
        
    def download_rainfall_data(self, url, filename):
        """Download rainfall CSV from URL"""
        print(f"📥 Downloading {filename}...")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            filepath = os.path.join(self.data_folder, filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Downloaded {filename} ({len(response.content)/1024/1024:.2f} MB)")
            return filepath
        
        except Exception as e:
            print(f"❌ Error downloading {filename}: {e}")
            return None
    
    def load_and_merge_data(self):
        """Load both datasets and merge them"""
        print("\n🔄 Loading and merging datasets...")
        
        # URLs from your JSON metadata
        full_url = "https://data.humdata.org/dataset/20978b3b-74bd-4746-9517-ae0fb35c02b3/resource/f3c9c76f-5eb0-42a2-a61b-9466862fab82/download/zaf-rainfall-subnat-full.csv"
        recent_url = "https://data.humdata.org/dataset/20978b3b-74bd-4746-9517-ae0fb35c02b3/resource/2dd325e3-ae69-484e-9faa-befeb80ead94/download/zaf-rainfall-subnat-5ytd.csv"
        
        # Download data
        full_path = self.download_rainfall_data(full_url, 'rainfall_full.csv')
        recent_path = self.download_rainfall_data(recent_url, 'rainfall_5ytd.csv')
        
        if not full_path or not recent_path:
            print("❌ Failed to download data files")
            return None
        
        # Load CSVs
        df_full = pd.read_csv(full_path)
        df_recent = pd.read_csv(recent_path)
        
        print(f"📊 Full dataset: {len(df_full):,} rows")
        print(f"📊 Recent dataset: {len(df_recent):,} rows")
        
        # Combine and remove duplicates
        combined = pd.concat([df_full, df_recent], ignore_index=True)
        combined = combined.drop_duplicates()
        
        print(f"📊 Combined dataset: {len(combined):,} rows")
        
        self.combined_data = combined
        return combined
    
    def process_for_training(self, location_filter=None):
        """Process data for ML training"""
        if self.combined_data is None:
            print("⚠️ No data loaded. Call load_and_merge_data() first")
            return None
        
        print("\n🔧 Processing data for ML training...")
        
        df = self.combined_data.copy()
        
        # Convert date column
        date_col = None
        for col in df.columns:
            if 'date' in col.lower() or 'time' in col.lower():
                date_col = col
                break
        
        if date_col:
            df['date'] = pd.to_datetime(df[date_col], errors='coerce')
            df = df.dropna(subset=['date'])
            df = df.sort_values('date')
        
        # Filter by location if specified (e.g., Johannesburg, Durban)
        if location_filter and any('location' in col.lower() or 'region' in col.lower() for col in df.columns):
            location_col = [col for col in df.columns if 'location' in col.lower() or 'region' in col.lower()][0]
            df = df[df[location_col].str.contains(location_filter, case=False, na=False)]
            print(f"📍 Filtered to location: {location_filter} ({len(df):,} rows)")
        
        # Extract features
        if 'date' in df.columns:
            df['year'] = df['date'].dt.year
            df['month'] = df['date'].dt.month
            df['day'] = df['date'].dt.day
            df['day_of_year'] = df['date'].dt.dayofyear
            df['week'] = df['date'].dt.isocalendar().week
            df['quarter'] = df['date'].dt.quarter
        
        # Find rainfall column
        rainfall_col = None
        for col in df.columns:
            if 'rainfall' in col.lower() or 'precip' in col.lower():
                rainfall_col = col
                break
        
        if rainfall_col:
            df['rainfall_mm'] = pd.to_numeric(df[rainfall_col], errors='coerce')
            
            # Create rolling averages
            df['rainfall_7day_avg'] = df['rainfall_mm'].rolling(window=7, min_periods=1).mean()
            df['rainfall_30day_avg'] = df['rainfall_mm'].rolling(window=30, min_periods=1).mean()
            
            # Create cumulative rainfall
            df['rainfall_cumulative'] = df['rainfall_mm'].cumsum()
        
        # Drop rows with missing critical values
        df = df.dropna(subset=['rainfall_mm'])
        
        # Save processed data
        output_path = os.path.join(self.data_folder, 'rainfall_processed.csv')
        df.to_csv(output_path, index=False)
        
        print(f"✅ Processed data saved to {output_path}")
        print(f"📊 Final dataset: {len(df):,} rows, {len(df.columns)} columns")
        print(f"📅 Date range: {df['date'].min()} to {df['date'].max()}")
        
        return df
    
    def get_statistics(self):
        """Get dataset statistics"""
        if self.combined_data is None:
            return None
        
        stats = {
            'total_rows': len(self.combined_data),
            'total_columns': len(self.combined_data.columns),
            'columns': list(self.combined_data.columns),
            'memory_usage_mb': self.combined_data.memory_usage(deep=True).sum() / 1024 / 1024,
            'missing_values': self.combined_data.isnull().sum().to_dict()
        }
        
        return stats

def main():
    """Main processing function"""
    print("=" * 60)
    print("🌧️  SOUTH AFRICAN RAINFALL DATA PROCESSOR")
    print("=" * 60)
    
    processor = RainfallDataProcessor()
    
    # Load and merge data
    combined = processor.load_and_merge_data()
    
    if combined is not None:
        # Get statistics
        stats = processor.get_statistics()
        print(f"\n📈 Dataset Statistics:")
        print(f"   Total Rows: {stats['total_rows']:,}")
        print(f"   Total Columns: {stats['total_columns']}")
        print(f"   Memory Usage: {stats['memory_usage_mb']:.2f} MB")
        print(f"   Columns: {', '.join(stats['columns'][:5])}...")
        
        # Process for training (you can specify location like 'Gauteng' or 'Durban')
        processed = processor.process_for_training(location_filter='Gauteng')
        
        print("\n✅ Data processing complete!")
        print("📁 Files created:")
        print("   - data/rainfall_full.csv")
        print("   - data/rainfall_5ytd.csv")
        print("   - data/rainfall_processed.csv")
    
    return processor

if __name__ == '__main__':
    main()