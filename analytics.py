import matplotlib
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np

matplotlib.use('Agg')

def save_graph(title, items):
    df = pd.DataFrame(items)
    show_price_likes_correlation(title, items)
    show_price_distribution(title, items)
    show_listings_volume(title, df)
    show_price_trends(title, df)
    show_time_to_sell(title, df)

def show_listings_volume(monitor_name, df):
    if df.empty: return
    df['listed_at'] = pd.to_datetime(df['listed_at'])
    daily_volume = df.groupby(df['listed_at'].dt.date).size()
    
    plt.figure(figsize=(10, 6))
    daily_volume.plot(kind='bar', color='skyblue')
    plt.title(f'{monitor_name} - Listings Volume Over Time')
    plt.xlabel('Date')
    plt.ylabel('Number of Listings')
    plt.tight_layout()
    plt.savefig(f"{monitor_name}_volume.png", dpi=300)
    plt.close()

def show_price_trends(monitor_name, df):
    if df.empty: return
    df['listed_at'] = pd.to_datetime(df['listed_at'])
    daily_price = df.groupby(df['listed_at'].dt.date)['price'].mean()
    
    plt.figure(figsize=(10, 6))
    daily_price.plot(kind='line', marker='o', color='green')
    plt.title(f'{monitor_name} - Average Price Trend')
    plt.xlabel('Date')
    plt.ylabel('Average Price (€)')
    plt.tight_layout()
    plt.savefig(f"{monitor_name}_price_trend.png", dpi=300)
    plt.close()

def show_time_to_sell(monitor_name, df):
    if df.empty: return
    df['listed_at'] = pd.to_datetime(df['listed_at'])
    df['sold_at'] = pd.to_datetime(df['sold_at'])
    
    sold_items = df[df['sold_at'].notnull()].copy()
    if sold_items.empty: return
    sold_items['time_to_sell'] = (sold_items['sold_at'] - sold_items['listed_at']).dt.days
    
    plt.figure(figsize=(10, 6))
    sns.histplot(sold_items['time_to_sell'], bins=30, kde=True, color='purple')
    plt.title(f'{monitor_name} - Time to Sell (Days)')
    plt.xlabel('Days')
    plt.ylabel('Number of Items')
    plt.tight_layout()
    plt.savefig(f"{monitor_name}_time_to_sell.png", dpi=300)
    plt.close()

def show_price_distribution(title, items):
    # 1. Extract and prepare data
    prices = [item['price'] for item in items]
    
    # 2. Set the visual style
    sns.set_theme(style="whitegrid")
    plt.figure(figsize=(10, 6))

    # 3. Create the plot
    # bins=100 gives you those "fine" columns
    # kde=True adds the smooth curve
    ax = sns.histplot(prices, bins=100, kde=True, color='blue', edgecolor='white', linewidth=0.5)

    # 4. Add statistical "Precision" lines (Mean and Median)
    mean_val = np.mean(prices)
    median_val = np.median(prices)
    
    plt.axvline(mean_val, color='red', linestyle='--', label=f'Mean: {mean_val:.2f}')
    plt.axvline(median_val, color='green', linestyle='-', label=f'Median: {median_val:.2f}')

    # 5. Labeling
    plt.title(f'{title} Price Distribution', fontsize=15)
    plt.xlabel('Price (€)', fontsize=12)
    plt.ylabel('Number of Ads', fontsize=12)
    plt.legend()

    # 6. Save and clear
    plt.tight_layout()
    plt.savefig(f"{title}_price_distr.png", dpi=300) # Higher DPI for a crisp image
    plt.close()

def show_price_likes_correlation(title, items):
    df = pd.DataFrame(items)
    
    # Filtriamo l'outlier a 400$ per zoomare sulla zona interessante
    limit = df['price'].quantile(0.95)
    df_filtered = df[df['price'] <= limit]

    sns.set_theme(style="white")

    # Il 'jointplot' crea il grafico a dispersione + gli istogrammi sui lati
    g = sns.jointplot(
        data=df_filtered, 
        x='price', 
        y='likes',
        kind="scatter", # Mostra i punti
        color="#34495e",
        alpha=0.4,
        marginal_kws=dict(bins=25, fill=True) # Gli istogrammi sopra e a destra
    )

    # Aggiungiamo una 'sfumatura' di densità (KDE) sopra i punti
    # per evidenziare l'area con più "traffico"
    g.plot_joint(sns.kdeplot, color="r", zorder=0, levels=6, alpha=0.5)

    g.set_axis_labels('Prezzo (€)', 'Numero di Like')
    plt.title(f"{title} price vs likes")
    plt.xlim(0, None)
    plt.ylim(0, None)

    plt.savefig(f"{title}_price_likes_density.png", dpi=300, bbox_inches='tight')
    plt.close()