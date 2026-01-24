import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime

# Configurazione Pagina
st.set_page_config(page_title="Equity Portfolio Interattivo", layout="wide")

# =============================================
# FUNZIONE CARICAMENTO DATI
# =============================================
def load_equity(uploaded_file):
    data = []
    try:
        content = uploaded_file.getvalue().decode("utf-8")
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) == 6:
                try:
                    date = datetime.strptime(parts[0], '%d/%m/%Y')
                    pnl = float(parts[1])
                    data.append({'date': date, 'pnl': pnl})
                except:
                    continue
    except Exception as e:
        st.error(f"Errore lettura {uploaded_file.name}: {e}")
        return None

    if not data:
        return None

    df = pd.DataFrame(data)
    df = df.groupby('date')['pnl'].sum().reset_index()
    df = df.sort_values('date')
    df['equity'] = df['pnl'].cumsum()
    return df[['date', 'equity', 'pnl']]

# =============================================
# INTERFACCIA STREAMLIT
# =============================================
st.markdown("### Equity Portfolio Interattivo – Paolo")

uploaded_files = st.file_uploader("Carica i file TXT", type="txt", accept_multiple_files=True)

if uploaded_files:
    equity_dfs = {}
    all_dates = set()

    for uploaded_file in uploaded_files:
        df = load_equity(uploaded_file)
        if df is not None:
            equity_dfs[uploaded_file.name] = df
            all_dates.update(df['date'])

    if not equity_dfs:
        st.warning("Nessun dato valido estratto dai file.")
    else:
        df_port = pd.DataFrame({'date': sorted(list(all_dates))})
        equity_columns = []
        pnl_columns = []
        
        for name, df in equity_dfs.items():
            col_name = name.replace('.txt', '').replace('#', '').strip()
            df_port = df_port.merge(
                df.rename(columns={'equity': col_name, 'pnl': col_name + '_pnl'}),
                on='date', how='left'
            )
            equity_columns.append(col_name)
            pnl_columns.append(col_name + '_pnl')

        df_port[pnl_columns] = df_port[pnl_columns].fillna(0)
        df_port[equity_columns] = df_port[equity_columns].ffill().fillna(0)

        # Calcolo Equity Totale (Somma delle singole equity)
        df_port['EQUITY_TOTALE'] = df_port[equity_columns].sum(axis=1)

        # Calcolo Drawdown sull'Equity Totale
        rolling_max = df_port['EQUITY_TOTALE'].cummax()
        # Evitiamo divisioni per zero se l'equity parte da zero
        df_port['drawdown'] = (df_port['EQUITY_TOTALE'] - rolling_max)

        # Calcolo PnL Annuale
        df_port['Year'] = df_port['date'].dt.year
        years = sorted(df_port['Year'].unique())
        annual_pnl = pd.DataFrame(index=years)

        for col in equity_columns:
            pnl_col_name = col + '_pnl'
            yearly_pnl = df_port.groupby('Year')[pnl_col_name].sum().round(0).astype(int)
            annual_pnl[col + ' PnL'] = yearly_pnl

        annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)
        totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
        annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

        # GRAFICI (Equity + Drawdown)
        st.subheader("Analisi Grafica")
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_d = st.date_input("Inizio", value=df_port['date'].min())
        with col_d2:
            end_d = st.date_input("Fine", value=df_port['date'].max())

        mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
        df_plot = df_port.loc[mask]

        # Creazione Subplots: uno per l'Equity, uno per il Drawdown
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                           vertical_spacing=0.05, row_heights=[0.7, 0.3],
                           subplot_titles=("Equity Curves", "Portfolio Drawdown (€)"))

        # 1. Equity Totale - COLORE LIME (Verde acceso)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['EQUITY_TOTALE'], 
                                 name='EQUITY_TOTALE', 
                                 line=dict(color='#00FF00', width=4)), row=1, col=1)

        # 2. Singole Equity
        for col in equity_columns:
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[col], 
                                     name=col, line=dict(width=1.5), opacity=0.6), row=1, col=1)

        # 3. Drawdown Totale (Area Rossa)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['drawdown'], 
                                 name='Drawdown Totale', fill='tozeroy',
                                 line=dict(color='red', width=1)), row=2, col=1)

        fig.update_layout(template="plotly_dark", height=800, showlegend=True, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # TABELLA PnL
        st.markdown("### PnL netto prodotto anno per anno (non cumulativo)")
        
        def style_df(df):
            def make_pretty(row):
                if row.name == 'TOTALE STORICO':
                    return ['background-color: #d1e7dd; color: black; font-weight: bold'] * len(row)
                return [''] * len(row)
            return df.style.apply(make_pretty, axis=1).format("{:,}")

        st.table(style_df(annual_pnl_with_total))

else:
    st.info("Trascina i file .txt per iniziare l'analisi del portafoglio.")
