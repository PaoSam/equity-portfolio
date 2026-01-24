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

st.markdown("### 📈 Equity Portfolio Interattivo – Paolo")

uploaded_files = st.file_uploader("1. Carica i file TXT delle strategie", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = set()
    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.update(df['date'])

    # --- NUOVA LEGENDA INTERATTIVA (Checkbox sopra il grafico) ---
    st.write("#### Selezione Strategie (attiva/disattiva per ricalcolare tutto):")
    # Creiamo una riga di colonne per le checkbox
    cols_check = st.columns(min(len(raw_data), 5)) 
    selected_names = []
    for i, name in enumerate(sorted(raw_data.keys())):
        with cols_check[i % 5]:
            if st.checkbox(name, value=True, key=f"check_{name}"):
                selected_names.append(name)

    if not selected_names:
        st.warning("⚠️ Seleziona almeno una strategia per visualizzare i dati.")
    else:
        # Costruzione DataFrame filtrato
        df_port = pd.DataFrame({'date': sorted(list(all_dates))})
        for name in selected_names:
            df = raw_data[name]
            df_port = df_port.merge(df[['date', 'equity', 'pnl']].rename(
                columns={'equity': name, 'pnl': name + '_pnl'}), on='date', how='left')

        # Riempimento e calcoli dinamici
        df_port[selected_names] = df_port[selected_names].ffill().fillna(0)
        pnl_cols = [n + '_pnl' for n in selected_names]
        df_port[pnl_cols] = df_port[pnl_cols].fillna(0)
        
        df_port['EQUITY_TOTALE'] = df_port[selected_names].sum(axis=1)
        df_port['drawdown'] = df_port['EQUITY_TOTALE'] - df_port['EQUITY_TOTALE'].cummax()

        # --- FILTRO DATE ---
        st.write("---")
        c1, c2 = st.columns([1, 1])
        start_d = c1.date_input("Inizio Analisi", df_port['date'].min())
        end_d = c2.date_input("Fine Analisi", df_port['date'].max())
        
        mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
        df_plot = df_port[mask].copy()

        # --- GRAFICI ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, 
                           row_heights=[0.7, 0.3], subplot_titles=("Curva Equity (Dinamica)", "Drawdown Portafoglio (€)"))
        
        # Equity Totale LIME (Spessa per visibilità)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['EQUITY_TOTALE'], 
                                 name='🎯 TOTALE SELEZIONATO', line=dict(color='#00FF00', width=4)), row=1, col=1)
        
        for n in selected_names:
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[n], name=n, line=dict(width=1.5), opacity=0.7), row=1, col=1)
        
        # Drawdown
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['drawdown'], name='Drawdown', 
                                 fill='tozeroy', line=dict(color='red', width=1)), row=2, col=1)

        # FIX APPIATTIMENTO: Autorange basato sui dati visibili
        fig.update_yaxes(autorange=True, fixedrange=False, row=1, col=1)
        fig.update_layout(
            template="plotly_dark", 
            height=750, 
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- TABELLA PnL ---
        st.markdown("### 📊 PnL Netto Anno per Anno")
        df_port['Year'] = df_port['date'].dt.year
        annual_pnl = pd.DataFrame()
        for n in selected_names:
            annual_pnl[n + ' PnL'] = df_port.groupby('Year')[n + '_pnl'].sum().round(0).astype(int)
        
        annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)
        totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
        annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

        st.table(annual_pnl_with_total.style.apply(lambda x: ['background-color: #1e4d3a; color: white; font-weight: bold' 
                if x.name == 'TOTALE STORICO' else '' for _ in x], axis=1).format("{:,}"))
