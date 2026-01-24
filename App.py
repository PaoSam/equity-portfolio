import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import requests

st.set_page_config(page_title="Margine Reale Contemporaneo", layout="wide")

@st.cache_data(ttl=3600)
def get_ibkr_margins(url):
    try:
        header = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=header, timeout=15)
        tables = pd.read_html(response.text, flavor='lxml')
        margin_dict = {}
        for df in tables:
            df.columns = [str(c).strip() for c in df.columns]
            if 'Underlying' in df.columns and 'Overnight Initial' in df.columns:
                for _, row in df.iterrows():
                    ticker = str(row['Underlying']).strip().upper()
                    val_raw = str(row['Overnight Initial']).replace('$', '').replace(',', '').strip()
                    try: margin_dict[ticker] = float(val_raw)
                    except: continue
        return margin_dict
    except: return {}

st.markdown("# 📈 Calcolo Margine Reale Contemporaneo")

url_ibkr = "https://www.interactivebrokers.com/en/trading/margin-futures-fops.php"
with st.spinner('Aggiornamento margini IBKR...'):
    live_margins = get_ibkr_margins(url_ibkr)

uploaded_files = st.file_uploader("Carica i file TXT da Titan", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = []
    
    def load_equity(uploaded_file):
        try:
            content = uploaded_file.getvalue().decode("utf-8")
            data = []
            for line in content.splitlines():
                parts = line.strip().split()
                if len(parts) == 6:
                    # Includiamo il PnL per capire se la strategia era attiva
                    data.append({'date': datetime.strptime(parts[0], '%d/%m/%Y'), 'pnl': float(parts[1])})
            return pd.DataFrame(data).sort_values('date')
        except: return None

    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())

    if raw_data:
        # Prepariamo il database dei margini per il calcolo
        selected_names = []
        ticker_map = {}
        
        st.write("### 🛠️ Strategie in Portafoglio")
        cols = st.columns(min(len(raw_data), 4))
        for i, name in enumerate(sorted(raw_data.keys())):
            ticker = name.split('_')[0].upper().strip()
            m_val = live_margins.get(ticker, 0)
            ticker_map[name] = m_val # Associa ogni file al suo margine
            with cols[i % 4]:
                if st.checkbox(f"{name} (${m_val:,.0f})", value=True, key=name):
                    selected_names.append(name)

        if selected_names:
            # --- CALCOLO MARGINE CONTEMPORANEO ---
            dates_set = sorted(list(set(all_dates)))
            df_master = pd.DataFrame({'date': dates_set})
            
            # Sommiamo i margini solo per le strategie che hanno PnL != 0 in quel giorno
            df_master['Margine_Giornaliero'] = 0.0
            df_master['Equity_Cumulata'] = 0.0

            for name in selected_names:
                m_cost = ticker_map[name]
                temp_df = raw_data[name].copy()
                # Se il PnL non è 0, consideriamo il margine impegnato
                temp_df['margine_attivo'] = temp_df['pnl'].apply(lambda x: m_cost if x != 0 else 0.0)
                
                df_master = df_master.merge(temp_df[['date', 'pnl', 'margine_attivo']], on='date', how='left').fillna(0)
                df_master['Margine_Giornaliero'] += df_master['margine_attivo']
                df_master['Equity_Cumulata'] += df_master['pnl'].cumsum()
                df_master.drop(['pnl', 'margine_attivo'], axis=1, inplace=True)

            # --- METRICHE DI CONTEMPORANEITÀ ---
            margine_di_picco = df_master['Margine_Giornaliero'].max()
            margine_medio = df_master[df_master['Margine_Giornaliero'] > 0]['Margine_Giornaliero'].mean()
            max_dd = abs((df_master['Equity_Cumulata'] - df_master['Equity_Cumulata'].cummax()).min())
            
            st.sidebar.header("📊 Analisi Reale")
            st.sidebar.metric("Picco Margine Reale", f"${margine_di_picco:,.0f}")
            st.sidebar.metric("Margine Medio Attivo", f"${margine_medio:,.0f}")
            st.sidebar.metric("Max Drawdown", f"${max_dd:,.0f}")
            
            capitale_necessario = margine_di_picco + max_dd
            st.sidebar.subheader("Capitale Reale Richiesto")
            st.sidebar.success(f"**${capitale_necessario:,.0f}**")
            st.sidebar.caption("Calcolato come: Picco Margine Storico + Max Drawdown")

            # --- GRAFICO ---
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, 
                               subplot_titles=("Equity Portafoglio", "Utilizzo Margine Contemporaneo ($)"))
            
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Equity_Cumulata'], name='Equity', line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Margine_Giornaliero'], name='Margine Reale', fill='tozeroy', line=dict(color='orange')), row=2, col=1)
            
            fig.update_layout(height=800, showlegend=False, plot_bgcolor='white')
            st.plotly_chart(fig, use_container_width=True)
