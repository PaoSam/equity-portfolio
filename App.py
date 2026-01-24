import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# Configurazione Pagina
st.set_page_config(page_title="Equity Portfolio Analyzer", layout="wide")

st.title("📊 Equity Portfolio & Drawdown Analyzer")
st.markdown("Analisi delle performance e del rischio basata su dati Yahoo Finance.")

# --- SIDEBAR PER INPUT ---
st.sidebar.header("Impostazioni Portafoglio")

# Input Ticker (separati da virgola)
tickers_input = st.sidebar.text_input("Inserisci i Ticker (es: AAPL, MSFT, GOOGL, TSLA)", "AAPL, MSFT, GOOGL")
tickers = [t.strip().upper() for t in tickers_input.split(",")]

# Selezione Date
col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input("Data Inizio", datetime.now() - timedelta(days=365*2))
with col2:
    end_date = st.date_input("Data Fine", datetime.now())

# Bottone per avviare l'analisi
if st.sidebar.button("Genera Analisi"):
    try:
        # 1. Download Dati
        with st.spinner('Scaricamento dati in corso...'):
            data = yf.download(tickers, start=start_date, end=end_date)['Adj Close']
        
        if data.empty:
            st.error("Nessun dato trovato per i ticker inseriti.")
        else:
            # 2. Calcoli Finanziari
            # Rendimenti logaritmici e normalizzazione
            returns = data.pct_change()
            # Equity curve del portafoglio (equipesato)
            portfolio_returns = returns.mean(axis=1)
            equity_curve = (1 + portfolio_returns).cumprod()
            
            # Calcolo Drawdown
            rolling_max = equity_curve.cummax()
            drawdown = (equity_curve - rolling_max) / rolling_max
            
            # Pulizia dati per Plotly (previene l'errore ValueError)
            equity_curve = equity_curve.fillna(1.0)
            drawdown = drawdown.fillna(0.0)

            # --- GRAFICO PLOTLY ---
            fig = make_subplots(rows=2, cols=1, 
                                shared_xaxes=True, 
                                vertical_spacing=0.1,
                                subplot_titles=("Equity Curve (Normalizzata)", "Drawdown (%)"),
                                row_heights=[0.7, 0.3])

            # Traccia Equity Curve
            fig.add_trace(
                go.Scatter(x=equity_curve.index, y=equity_curve, name="Portfolio Equity",
                           line=dict(color='royalblue', width=2), fill='tozeroy'),
                row=1, col=1
            )

            # Traccia Drawdown
            fig.add_trace(
                go.Scatter(x=drawdown.index, y=drawdown * 100, name="Drawdown",
                           line=dict(color='red', width=1), fill='tozeroy'),
                row=2, col=1
            )

            # Update Layout (Sistemato per evitare errori)
            fig.update_layout(
                height=700,
                showlegend=False,
                title_text="Analisi Performance Portafoglio",
                title_x=0.5,
                template="plotly_white"
            )
            
            fig.update_yaxes(title_text="Moltiplicatore", row=1, col=1)
            fig.update_yaxes(title_text="Drawdown %", row=2, col=1)

            # Visualizzazione Grafico
            st.plotly_chart(fig, use_container_width=True)

            # --- METRICHE ---
            st.subheader("Metriche Principali")
            m1, m2, m3 = st.columns(3)
            
            total_return = (equity_curve.iloc[-1] - 1) * 100
            max_drawdown = drawdown.min() * 100
            volatility = portfolio_returns.std() * np.sqrt(252) * 100

            m1.metric("Rendimento Totale", f"{total_return:.2f}%")
            m2.metric("Max Drawdown", f"{max_drawdown:.2f}%")
            m3.metric("Volatilità Annualizzata", f"{volatility:.2f}%")

            # Visualizzazione dati grezzi
            with st.expander("Visualizza Dati Storici"):
                st.dataframe(data.tail(10))

    except Exception as e:
        st.error(f"Si è verificato un errore: {e}")
else:
    st.info("Configura i ticker nella barra laterale e clicca su 'Genera Analisi'.")
