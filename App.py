import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

st.set_page_config(page_title="Equity Portfolio Paolo", layout="wide")

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
                except: continue
    except: return None
    if not data: return None
    df = pd.DataFrame(data)
    df = df.groupby('date')['pnl'].sum().reset_index()
    df = df.sort_values('date')
    df['equity'] = df['pnl'].cumsum()
    return df

st.markdown("### Equity Portfolio Interattivo – Paolo")

uploaded_files = st.file_uploader("1. Carica i file TXT", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = set()
    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.update(df['date'])

    # --- SELEZIONE STRATEGIE (Sostituisce il click sulla legenda) ---
    st.sidebar.header("Selezione Strategie")
    selected_names = []
    for name in raw_data.keys():
        if st.sidebar.checkbox(name, value=True):
            selected_names.append(name)

    if not selected_names:
        st.warning("Seleziona almeno una strategia dalla barra laterale.")
    else:
        # Costruzione DataFrame filtrato
        df_port = pd.DataFrame({'date': sorted(list(all_dates))})
        for name in selected_names:
            df = raw_data[name]
            df_port = df_port.merge(df[['date', 'equity', 'pnl']].rename(
                columns={'equity': name, 'pnl': name + '_pnl'}), on='date', how='left')

        # Riempimento e calcoli dinamici
        pnl_cols = [n + '_pnl' for n in selected_names]
        df_port[selected_names] = df_port[selected_names].ffill().fillna(0)
        df_port[pnl_cols] = df_port[pnl_cols].fillna(0)
        
        df_port['EQUITY_TOTALE'] = df_port[selected_names].sum(axis=1)
        df_port['drawdown'] = df_port['EQUITY_TOTALE'] - df_port['EQUITY_TOTALE'].cummax()

        # Filtro Date
        col_d1, col_d2 = st.columns(2)
        start_d = col_d1.date_input("Inizio", df_port['date'].min())
        end_d = col_d2.date_input("Fine", df_port['date'].max())
        df_plot = df_port[(df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)]

        # Grafici
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, 
                           row_heights=[0.7, 0.3], subplot_titles=("Equity Curves", "Drawdown Totale (€)"))
        
        # Equity Totale LIME
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['EQUITY_TOTALE'], 
                                 name='TOTALE', line=dict(color='#00FF00', width=4)), row=1, col=1)
        
        for n in selected_names:
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[n], name=n, line=dict(width=1.5)), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['drawdown'], name='Drawdown', 
                                 fill='tozeroy', line=dict(color='red')), row=2, col=1)

        fig.update_layout(template="plotly_dark", height=700, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # Tabella PnL Annuale
        st.markdown("### PnL Netto Anno per Anno")
        df_port['Year'] = df_port['date'].dt.year
        annual_pnl = pd.DataFrame()
        for n in selected_names:
            annual_pnl[n + ' PnL'] = df_port.groupby('Year')[n + '_pnl'].sum().round(0).astype(int)
        
        annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)
        totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
        annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

        st.table(annual_pnl_with_total.style.apply(lambda x: ['background-color: #d1e7dd; color: black' 
                if x.name == 'TOTALE STORICO' else '' for _ in x], axis=1).format("{:,}"))
