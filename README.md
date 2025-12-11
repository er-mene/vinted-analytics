# 📈 Vinted Market Intelligence Engine

![Status](https://img.shields.io/badge/Status-Active_Development-yellow) ![Python](https://img.shields.io/badge/Python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-green)

> **Note:** This project is currently under active development as part of a portfolio initiative to engineer real-time market analytics tools.

## 💡 Overview

The **Vinted Market Intelligence Engine** is a backend data engineering tool designed to aggregate, store, and analyze secondary market data. Unlike standard keyword search, this tool persists historical listing data to identify **arbitrage opportunities**, calculate **price volatility**, and track **supply velocity** for specific high-value assets (e.g., luxury watches, electronics).

It solves the problem of ephemeral market data by building a local data warehouse of listings, allowing for longitudinal analysis and "Deal Scoring" based on historical medians rather than current asking prices.

## 🚀 Key Features

* **Stealth Data Ingestion:** Implements `curl_cffi` to mimic browser TLS fingerprints (JA3), successfully bypassing Cloudflare 403/401 protections to access private API endpoints.
* **Idempotent Storage:** Custom SQLite persistence layer with primary key constraints to prevent data duplication during repeated scrape cycles.
* **Market Analytics:**
    * **Volatility Index:** Calculates standard deviation of prices to measure asset stability.
    * **Arbitrage Detection:** Automatically flags listings priced >30% below the historical market median.
* **Dynamic Monitoring:** "Cron-style" monitoring system to track specific brand/model combinations over time.

## 🛠️ Tech Stack

* **Core:** Python 3.x
* **API Framework:** FastAPI (Asynchronous, Type-safe)
* **Data Processing:** Pandas (Vectorized operations for price stats)
* **Database:** SQLite (Lightweight relational storage)
* **Networking:** curl_cffi (Advanced HTTP client for browser impersonation)

## ⚡ Quick Start

### Prerequisites
* Python 3.10+
* Virtual Environment (Recommended)

### Installation
1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/er-mene/vinted-analytics.git](https://github.com/YOUR_NEW_USERNAME/vinted-analytics.git)
    cd vinted-analytics
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Initialize the Database:**
    ```bash
    python -c "from database import init_db; init_db()"
    ```

4.  **Run the Server:**
    ```bash
    uvicorn main:app --reload
    ```

5.  **Explore the API:**
    Open your browser to `http://127.0.0.1:8000/docs` to see the Swagger UI.

## ⚖️ Disclaimer
This tool is developed for **educational purposes only** to demonstrate data engineering and API development skills. It is not intended for commercial scraping or to violate Vinted's Terms of Service.