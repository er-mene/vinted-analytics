import sqlite3
import pandas as pd
from database import DB_NAME

def get_brand_analytics(brand_name: str):
    conn = sqlite3.connect(DB_NAME)
    
    # SQL Query: "Give me everything where the brand name contains X"
    query = f"SELECT * FROM listings WHERE brand LIKE '%{brand_name}%'"
    
    # Load into Pandas DataFrame (Think of it as a programmable Excel sheet)
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return None

    # --- THE MATH SECTION ---
    
    # 1. Clean the data (remove crazy outliers, e.g., price = 0 or price = 1,000,000)
    # This filters out "Joke" listings
    df = df[(df['price'] > 5) & (df['price'] < 100000)]
    
    # 2. Basic Stats
    stats = {
        "brand_analyzed": brand_name,
        "total_listings_tracked": int(len(df)), # Convert to int for JSON compatibility
        "average_price": round(df['price'].mean(), 2),
        "median_price": round(df['price'].median(), 2),
        "min_price": df['price'].min(),
        "max_price": df['price'].max(),

    }
    
    # 3. Advanced Insight: "Volatility"
    # Standard Deviation tells us if prices are stable or crazy
    stats["price_volatility"] = round(df['price'].std(), 2)
    
    return stats