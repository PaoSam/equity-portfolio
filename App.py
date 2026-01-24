import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date

# --- DATABASE MARGINI OVERNIGHT INITIAL (Aggiornato IBKR) ---
DATABASE_MARGINI = {
    "NQ": 18480, "MNQ": 1848,
    "ES": 12320, "MES": 1232,
    "GC": 8500,  "MGC": 850,
    "HG": 2750,  "CL": 7200,
    "MYM": 1637, "YM": 8200,
    "DAX": 28500, "MINIDAX": 5700,
    "ZC": 2050,  "ZS": 2400,
    "SI": 9500,  "SIL": 1900
}

st.set_page_config(page_title="Equity Portfolio Paolo", layout="wide")

def load_equity(uploaded_file):
    data = []
    try:
        content = uploaded_file.getvalue().decode("utf-8")
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) == 6:
                try:
                    date_obj = datetime.strptime(parts[0], '%d/%m/%Y')
                    pnl = float(parts[1])
                    data.append({'date': date_obj, 'pnl': pnl})
                except: continue
    except: return None
    if not data: return None
    df = pd.DataFrame(data)
    df = df.groupby('date')['pnl'].sum().reset_index()
    df = df.sort_values('date')
    return df

st.markdown("# 📈 Analisi Equity & Margini IBKR")

uploaded_files = st.file_uploader("Carica i file TXT da Titan", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = []
    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())

    if raw_data:
        # --- LOGICA MARGINI ---
        st.sidebar.header("💰 Analisi Margini")
        margine_totale_portafoglio = 0
        lista_margini_singoli = []

        st.write("### 🛠️ Selezione Strategie")
        selected_names = []
        chk_cols = st.columns(min(len(raw_data), 4))
        
        for i, name in enumerate(sorted(raw_data.keys())):
            margine_strumento = 0
            ticker_trovato = "N/A"
            # Cerchiamo il ticker nel nome del file
            for ticker in DATABASE_MARGINI:
                if ticker in name.upper():
                    margine_strumento = DATABASE_MARGINI[ticker]
                    ticker_trovato = ticker
                    break
            
            with chk_cols[i % 4]:
                if st.checkbox(f"{name} (${margine_strumento:,})", value=True, key=name):
                    selected_names.append(name)
                    margine_totale_portafoglio += margine_strumento
                    if margine_strumento > 0:
                        lista_margini_singoli.append({"Strumento": ticker_trovato, "Strategia": name, "Margine ($)": margine_strumento})

        if selected_names:
            # --- SIDEBAR: DETTAGLIO MARGINI ---
            st.sidebar.metric("Margine Totale Impegnato", f"${margine_totale_portafoglio:,}")
            
            if lista_margini_singoli:
                st.sidebar.write("**Dettaglio per Strumento:**")
                df_margini_side = pd.DataFrame(lista_margini_singoli)
                st.sidebar.dataframe(df_margini_side[["Strumento", "Margine ($)"]], hide_index=True)

            # --- RANGE TEMPORALE ---
            data_min_assoluta = min(all_dates).date()
            data_max_assoluta = max(all_dates).date()
            start_d = st.sidebar.date_input("Inizio Analisi", value=data_min_assoluta)
            end_d = st.sidebar.date_input("Fine Analisi", value=data_max_assoluta)

            # Costruzione DataFrame
            df_port = pd.DataFrame({'date': sorted(list(set(all_dates)))})
            for name in selected_names:
                df_port = df_port.merge(raw_data[name][['date', 'pnl']].rename(columns={'pnl': name + '_pnl'}), on='date', how='left')
            
            df_port.fillna(0, inplace=True)
            mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
            df_periodo = df_port[mask].copy()

            if not df_periodo.empty:
                # Ricalcolo Equity
                for name in selected_names:
                    df_periodo[name] = df_periodo[name + '_pnl'].cumsum()
                
                df_periodo['EQUITY_TOTALE'] = df_periodo[selected_names].sum(axis=1)
                df_periodo['drawdown'] = df_periodo['EQUITY_TOTALE'] - df_periodo['EQUITY_TOTALE'].cummax()

                # --- GRAFICO (RITORNO DELLE SINGOLE EQUITY) ---
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])

                # 1. Equity Totale (Nera)
                fig.add_trace(go.Scatter(x=df_periodo['date'], y=df_periodo['EQUITY_TOTALE'], 
                                         name='EQUITY TOTALE', line=dict(color='black', width=3.5)), row=1, col=1)
                
                # 2. Singole Equity (Colorate e sottili)
                for n in selected_names:
                    fig.add_trace(go.Scatter(x=df_periodo['date'], y=df_periodo[n], 
                                             name=n, line=dict(width=1.1), opacity=0.6), row=1, col=1)
                
                # 3. Drawdown
                fig.add_trace(go.Scatter(x=df_periodo['date'], y=df_periodo['drawdown'], name='Drawdown', 
                                         fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.2)',
                                         line=dict(color='#e74c3c', width=1.5)), row=2, col=1)

                fig.update_yaxes(autorange=True, fixedrange=False, gridcolor='#f0f0f0', row=1, col=1)
                fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', height=800, hovermode="x unified", uirevision='constant',
                                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                
                st.plotly_chart(fig, use_container_width=True)

                # --- TABELLA E ROE ---
                st.write("### 📊 Performance & Efficienza Capitale")
                df_periodo['Year'] = df_periodo['date'].dt.year
                annual_pnl = pd.DataFrame()
                for n in selected_names:
                    annual_pnl[n] = df_periodo.groupby('Year')[n + '_pnl'].sum().round(0).astype(int)
                
                annual_pnl['EQUITY TOTALE'] = annual_pnl.sum(axis=1).astype(int)
                
                if margine_totale_portafoglio > 0:
                    annual_pnl['ROE % (su Margine)'] = ((annual_pnl['EQUITY TOTALE'] / margine_totale_portafoglio) * 100).round(2)
                
                st.dataframe(annual_pnl.style.format("{:,}"), use_container_width=True)

else:
    st.info("👋 Carica i file TXT per visualizzare Equity, Margini e ROE.")
