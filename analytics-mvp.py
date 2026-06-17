import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine
from datetime import date

# Connexion PostgreSQL
engine = create_engine("postgresql://USER@localhost:5432/DATABASE")

# Télécharger les données
df = yf.download("AAPL MSFT GOOGL", start="2024-01-01", end=date.today(), threads=False)
df.to_sql("stock_prices_raw", engine, if_exists="replace", index=True)