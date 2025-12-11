# 📈 Vinted Market Intelligence Engine

![Status](https://img.shields.io/badge/Status-Active_Development-yellow) ![Python](https://img.shields.io/badge/Python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-green)

> **Note:** This project is currently under active development as part of a portfolio initiative to engineer real-time market analytics tools.

## 💡 Overview

The **Vinted Market Intelligence Engine** is a backend data engineering tool designed to aggregate, store, and analyze secondary market data. Unlike standard keyword search, this tool persists historical listing data to identify **arbitrage opportunities**, calculate **price volatility**, and track **supply velocity** for specific high-value assets (e.g., luxury watches, electronics).

It solves the problem of ephemeral market data by building a local data warehouse of listings, allowing for longitudinal analysis and "Deal Scoring" based on historical medians rather than current asking prices.

## 🏗️ Architecture

The system follows a classic ETL (Extract, Transform, Load) pipeline pattern:

```mermaid
graph LR
    A[Vinted API] -->|TLS Fingerprint Spoofing| B(Ingestion Engine)
    B -->|Raw JSON| C{Data Processor}
    C -->|Clean Data| D[(SQLite Data Warehouse)]
    D -->|Historical Data| E[Analytics Engine]
    E -->|JSON Responses| F[FastAPI Endpoints]
    F -->|Insights| G[Client / Dashboard]