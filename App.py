import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
            # Pulizia nome file
            clean_name = uploaded_file.name.replace('.txt', '').replace('#', '').strip()
            equity_dfs[clean_name] = df
            all_dates.update(df['date'])

    if not equity_dfs:
        st.warning("Nessun dato valido estratto dai file.")
    else:
        # --- SELETTORE DINAMICO STRATEGIE ---
        st.sidebar.header("Filtri Portafoglio")
        selected_strategies = st.sidebar.multiselect(
            "Seleziona le strategie da includere nel Totale:",
            options=list(equity_dfs.keys()),
            default=list(equity_dfs.keys())
        )

        if not selected_strategies:
            st.error("Seleziona almeno una strategia per vedere i calcoli.")
        else:
            # Creazione DataFrame base
            df_port = pd.DataFrame({'date': sorted(list(all_dates))})
            
            for name in selected_strategies:
                df = equity_dfs[name]
                df_port = df_port.merge(
                    df.rename(columns={'equity': name, 'pnl': name + '_pnl'}),
                    on='date', how='left'
                )

            # Riempimento buchi
            pnl_cols = [c + '_pnl' for c in selected_strategies]
            df_port[pnl_cols] = df_port[pnl_cols].fillna(0)
            df_port[selected_strategies] = df_port[selected_strategies].ffill().fillna(0)

            # --- RICALCOLO DINAMICO EQUITY E DRAWDOWN ---
            df_port['EQUITY_TOTALE'] = df_port[selected_strategies].sum(axis=1)
            
            # Calcolo Drawdown Dinamico
            rolling_max = df_port['EQUITY_TOTALE'].cummax()
            df_port['drawdown'] = df_port['EQUITY_TOTALE'] - rolling_max

            # --- GRAFICI ---
            st.subheader("Analisi Grafica Dinamica")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                start_d = st.date_input("Inizio", value=df_port['date'].min())
            with col_d2:
                end_d = st.date_input("Fine", value=df_port['date'].max())

            mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
            df_plot = df_port.loc[mask]

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                               vertical_spacing=0.05, row_heights=[0.7, 0.3],
                               subplot_titles=("Equity Curves", "Portfolio Drawdown (€)"))

            # Equity Totale LIME
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['EQUITY_TOTALE'], 
                                     name='EQUITY_TOTALE', 
                                     line=dict(color='#00FF00', width=4)), row=1, col=1)

            # Singole Equity selezionate
            for col in selected_strategies:
                fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[col], 
                                         name=col, line=dict(width=1.5), opacity=0.5), row=1, col=1)

            # Drawdown dinamico
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['drawdown'], 
                                     name='Drawdown Totale', fill='tozeroy',
                                     line=dict(color='red', width=1)), row=2, col=1)

            fig.update_layout(template="plotly_dark", height=800, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # --- TABELLA PnL ANNUALE ---
            st.markdown("### PnL netto prodotto anno per anno")
            df_port['Year'] = df_port['date'].dt.year
            annual_pnl = pd.DataFrame()

            for col in selected_strategies:
                pnl_col_name = col + '_pnl'
                yearly_pnl = df_port.groupby('Year')[pnl_col_name].sum().round(0).astype(int)
                annual_pnl[col + ' PnL'] = yearly_pnl

            annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)
            totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
            annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

            def style_df(df):
                def make_pretty(row):
                    if row.name == 'TOTALE STORICO':
                        return ['background-color: #d1e7dd; color: black; font-weight: bold'] * len(row)
                    return [''] * len(row)
                return df.style.apply(make_pretty, axis=1).format("{:,}")

            st.table(style_df(annual_pnl_with_total))

else:
    st.info("Trascina i file .txt per iniziare.")
