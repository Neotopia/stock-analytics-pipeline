import yfinance as yf
import pandas as pd
from sqlalchemy import create_engine
from datetime import date

# Connexion PostgreSQL (couche Bronze)
engine = create_engine("postgresql://USER@localhost:5432/DATABASE")

# Télécharger les données yfinance
# threads=False évite le conflit sur le cache SQLite interne de yfinance
df = yf.download("AAPL MSFT GOOGL", start="2024-01-01", end=date.today(), threads=False)

# Charger dans PostgreSQL — remplace la table à chaque exécution
df.to_sql("stock_prices_raw", engine, if_exists="replace", index=True)

print(f"✅ Données chargées jusqu'au {date.today()}")