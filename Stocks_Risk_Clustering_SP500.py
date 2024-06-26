import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from tqdm import tqdm
from sklearn.mixture import GaussianMixture
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import yfinance as yf
from datetime import datetime, timedelta
import random

# Function to fetch data from Yahoo Finance
def fetch_data(symbol, start_date, end_date):
    return yf.download(symbol, start=start_date, end=end_date)

# Calculate the beta of each stock against the market index
def calculate_beta(stock_returns, market_returns):
    if len(stock_returns) < 2 or len(market_returns) < 2:
        return np.nan, np.nan, np.nan
    covariance_matrix = np.cov(stock_returns, market_returns)
    beta = covariance_matrix[0, 1] / covariance_matrix[1, 1]
    return beta, covariance_matrix[0, 1], covariance_matrix[1, 1]  # Also return covariance and variance for debugging

# Calculate the R-squared value between two stock series
def calculate_r_squared(stock_returns, market_returns):
    if len(stock_returns) < 2 or len(market_returns) < 2:
        return np.nan
    correlation_matrix = np.corrcoef(stock_returns, market_returns)
    correlation_xy = correlation_matrix[0, 1]
    r_squared = correlation_xy ** 2
    return r_squared

# Determine the optimal number of clusters using BIC
def determine_optimal_clusters(data):
    bics = []
    n_clusters_range = range(3, 13)  # from 3 to 12 clusters

    for n_clusters in n_clusters_range:
        gmm = GaussianMixture(n_components=n_clusters, random_state=42)
        gmm.fit(data)
        bic = gmm.bic(data)
        bics.append((n_clusters, bic))

    optimal_clusters = min(bics, key=lambda x: x[1])[0]

    # Plot BIC scores
    plt.figure(figsize=(10, 6))
    plt.plot(n_clusters_range, [bic for _, bic in bics], marker='o')
    plt.title('BIC Scores for Different Numbers of Clusters')
    plt.xlabel('Number of clusters')
    plt.ylabel('BIC Score')
    plt.show()

    print(f"The optimal number of clusters determined by BIC is: {optimal_clusters}")
    return optimal_clusters

# Align stock and market data
def align_data(stock_data, index_data):
    aligned_data = stock_data.join(index_data, how='inner', lsuffix='_stock', rsuffix='_index')
    return aligned_data

# Determine the risk level of a stock based on beta value
def risk_level(beta):
    if beta < 0.5:
        return "Very Low Risk"
    elif beta < 1:
        return "Low Risk"
    elif beta < 1.5:
        return "Moderate Risk"
    elif beta < 2:
        return "High Risk"
    else:
        return "Very High Risk"

# Main function to process the data
def analyze_stocks(stocks_filepath, index_symbol, years=5):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)

    # Load the list of S&P 500 symbols from the CSV file
    stock_symbols_df = pd.read_csv(stocks_filepath)
    stock_symbols = stock_symbols_df['Symbol'].tolist()

    # Fetch market index data
    print(f"Fetching market index data for {index_symbol} from {start_date} to {end_date}")
    index_data = fetch_data(index_symbol, start_date, end_date)
    index_data = index_data['Close'].to_frame(name='Close_index')

    betas = {}
    r_squared_values = {}
    latest_close_values = {}
    symbols = {}
    valid_stocks_count = 0

    # Fetch stock data
    for symbol in tqdm(stock_symbols, desc="Fetching stock data and calculating metrics"):
        stock_data = fetch_data(symbol, start_date, end_date)
        stock_data = stock_data['Close'].to_frame(name='Close_stock')

        if not stock_data.empty:
            stock_returns = stock_data['Close_stock'].pct_change().dropna()
            market_returns = index_data['Close_index'].pct_change().dropna()

            aligned_data = align_data(stock_returns.to_frame(), market_returns.to_frame())

            if not aligned_data['Close_stock'].empty and not aligned_data['Close_index'].empty:
                beta, cov, var = calculate_beta(aligned_data['Close_stock'].dropna(), aligned_data['Close_index'].dropna())
                if np.isfinite(beta):
                    betas[symbol] = round(beta, 3)
                    r_squared_values[symbol] = round(calculate_r_squared(aligned_data['Close_stock'].dropna(), aligned_data['Close_index'].dropna()), 3)
                    latest_close_values[symbol] = round(stock_data['Close_stock'].iloc[-1], 3)
                    symbols[symbol] = symbol
                    valid_stocks_count += 1
                else:
                    print(f"Skipping {symbol} due to non-finite beta value")
            else:
                print(f"Skipping {symbol} due to empty aligned returns")

    results_df = pd.DataFrame({
        'Symbol': list(betas.keys()),
        'Name': [stock_symbols_df[stock_symbols_df['Symbol'] == symbol]['Name'].values[0] for symbol in betas.keys()],
        'Beta': list(betas.values()),
        'R-Squared': [r_squared_values[symbol] for symbol in betas.keys()],
        'Latest Close': [latest_close_values[symbol] for symbol in betas.keys()]
    }).sort_values(by='Beta')

    # Drop rows with NaN values
    results_df.dropna(inplace=True)


    # Use the original Beta and R-Squared values for clustering
    features = results_df[['Beta', 'R-Squared']].values

    scaler = StandardScaler()
    features = scaler.fit_transform(features)

    # Determine the optimal number of clusters
    optimal_clusters = determine_optimal_clusters(features)

    # Perform Gaussian Mixture Model clustering with the optimal number of clusters
    gmm = GaussianMixture(n_components=optimal_clusters, random_state=42)
    cluster_labels = gmm.fit_predict(features)
    results_df['Cluster'] = cluster_labels

    # Add risk level information
    results_df['Risk Level'] = results_df['Beta'].apply(risk_level)

    # Save the results to a CSV file
    results_df.to_csv('SP500_results.csv', index=False)

    # Generate random colors for each cluster
    custom_colors = []
    for _ in range(optimal_clusters):
        r = random.random()
        g = random.random()
        b = random.random()
        custom_colors.append(f'rgb({r}, {g}, {b})')

    # Create traces for each cluster
    traces = []
    cluster_probs = gmm.predict_proba(features)
    for cluster in sorted(results_df['Cluster'].unique()):
        cluster_df = results_df[results_df['Cluster'] == cluster]
        trace = go.Scatter(x=cluster_df['Beta'], y=cluster_df['R-Squared'],
                           mode='markers', marker=dict(size=cluster_df['Latest Close'],
                                                       sizeref=2. * max(cluster_df['Latest Close']) / (60. ** 2),
                                                       sizemode='area'),
                           hovertext=cluster_df['Symbol'] + '<br>' + cluster_df['Name'] + '<br>Beta: ' + cluster_df[
                               'Beta'].astype(str) + '<br>R-Squared: ' + cluster_df['R-Squared'].astype(
                               str) + '<br>Latest Close Price: ' + cluster_df['Latest Close'].astype(str) +
                                     '<br>Risk Level: ' + cluster_df['Risk Level'] +
                                     '<br>Cluster Prob: ' + cluster_probs[cluster_df.index, cluster].round(3).astype(str),
                           showlegend=False,  # Hide legend for clusters
                           marker_color=custom_colors[cluster % len(custom_colors)])
        traces.append(trace)



    # Create the layout
    layout = go.Layout(title=f'S&P500 Index Stock Clustering based on Beta and R-Squared',
                       xaxis=dict(title='β (Risk)', tickmode='linear', dtick=0.25),
                       yaxis=dict(title='R² (Market Dependency)'))

    # Create the figure
    fig = go.Figure(data=traces, layout=layout)

    # Add red lines at beta = 0 and beta = 1
    fig.add_trace(go.Scatter(x=[0, 0], y=[results_df['R-Squared'].min(), results_df['R-Squared'].max()],
                             mode="lines", line=dict(color="black", width=2), showlegend=False))
    fig.add_trace(go.Scatter(x=[1, 1], y=[results_df['R-Squared'].min(), results_df['R-Squared'].max()],
                             mode="lines", line=dict(color="black", width=2), showlegend=False))

    # Display the number of valid stocks and the latest date of data
    latest_date = end_date.strftime('%d/%m/%Y')
    fig.add_annotation(x=results_df['Beta'].max(), y=results_df['R-Squared'].max(),
                       text=f"Valid Stocks: {valid_stocks_count} | Date: {latest_date}",
                       showarrow=False, font=dict(size=14, color="black"))

    fig.show()

    print(f"Number of valid stocks: {valid_stocks_count}")

stocks_filepath = "SP500_stock_list_Jan-1-2024.csv"
index_symbol = "^GSPC"  # S&P 500 Index
analyze_stocks(stocks_filepath, index_symbol, years=5)
