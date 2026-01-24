import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date

# --- DATABASE MARGINI INITIAL (Valori base modificabili dall'utente) ---
if 'margin_db' not in st.session_state:
    st.session_state.margin_db = {
        "NQ": 18480.0, "MNQ": 1848.0,
        "ES": 12320.0, "MES": 1232.0,
        "YM": 8200.0,  "MYM": 1637.0,
        "GC": 8500.0,  "MGC": 850.0,
        "CL": 7200.0,  "MCL": 720.0,
        "HG": 2750.0,  "SI": 9500.0,
        "DAX": 28500.0, "DXM": 5700.0,
        "ZC": 2050.0,  "ZS": 2400.0
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

st.markdown("# 📈 Equity & Margin Control Panel")

# --- SEZIONE OVERRIDE MARGINI ---
with st.expander("⚙️ Configurazione Margini (Modifica qui se i valori IBKR cambiano)"):
    cols = st.columns(4)
    for i, (ticker, val) in enumerate(st.session_state.margin_db.items()):
        new_val = cols[i % 4].number_input(f"Margine {ticker}", value=float(val), step=100.0)
        st.session_state.margin_db[ticker] = new_val

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
        st.sidebar.header("💰 Analisi Margini")
        margine_totale = 0
        dettaglio_margini = []

        st.write("### 🛠️ Selezione Strategie")
        selected_names = []
        cols = st.columns(min(len(raw_data), 4))
        
        for i, name in enumerate(sorted(raw_data.keys())):
            valore_m = 0
            ticker_ref = "N/A"
            for t in st.session_state.margin_db:
                if t in name.upper():
                    valore_m = st.session_state.margin_db[t]
                    ticker_ref = t
                    break
            
            with cols[i % 4]:
                if st.checkbox(f"{name} (${valore_m:,})", value=True, key=name):
                    selected_names.append(name)
                    margine_totale += valore_m
                    if valore_m > 0:
                        dettaglio_margini.append({"Ticker": ticker_ref, "Strategia": name, "Margine": valore_m})

        if selected_names:
            st.sidebar.metric("Margine Totale Impegnato", f"${margine_totale:,}")
            
            # Grafico e Tabelle
            df_port = pd.DataFrame({'date': sorted(list(set(all_dates)))})
            for name in selected_names:
                df_port = df_port.merge(raw_data[name][['date', 'pnl']].rename(columns={'pnl': name + '_pnl'}), on='date', how='left')
            
            df_port.fillna(0, inplace=True)
            
            # Filtro Date con Reset a Zero
            start_d = st.sidebar.date_input("Inizio", min(all_dates).date())
            end_d = st.sidebar.date_input("Fine", max(all_dates).date())
            mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
            df_plot = df_port[mask].copy()

            for n in selected_names:
                df_plot[n] = df_plot[n + '_pnl'].cumsum()
            
            df_plot['TOTALE'] = df_plot[selected_names].sum(axis=1)
            df_plot['DD'] = df_plot['TOTALE'] - df_plot['TOTALE'].cummax()

            # Plotly Chart
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['TOTALE'], name='TOTAL', line=dict(color='black', width=3)), row=1, col=1)
            for n in selected_names:
                fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[n], name=n, line=dict(width=1), opacity=0.3), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['DD'], name='Drawdown', fill='tozeroy', line=dict(color='red')), row=2, col=1)
            
            fig.update_layout(plot_bgcolor='white', height=700, uirevision='constant', hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # Tabella Finale con ROE
            st.write("### 📊 Risultati Annuali e ROE")
            df_plot['Year'] = df_plot['date'].dt.year
            res = df_plot.groupby('Year')[[n + '_pnl' for n in selected_names]].sum().round(0)
            res['TOTALE PnL'] = res.sum(axis=1)
            if margine_totale > 0:
                res['ROE %'] = (res['TOTALE PnL'] / margine_totale * 100).round(2)
            
            st.dataframe(res.style.format("{:,}"), use_container_width=True)

else:
    st.info("Trascina i file TXT da Titan per analizzare il portafoglio.")
