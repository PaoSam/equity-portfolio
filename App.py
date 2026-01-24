import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import requests

st.set_page_config(page_title="Equity & Capital Management", layout="wide")

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
                    val_raw = str(row['Overnight Initial']).replace('$', '').replace('€', '').replace(',', '').strip()
                    try: margin_dict[ticker] = float(val_raw)
                    except: continue
        return margin_dict
    except: return {}

st.markdown("# 📈 Analisi Equity & Capital Management")

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
                    data.append({'date': datetime.strptime(parts[0], '%d/%m/%Y'), 'pnl': float(parts[1])})
            return pd.DataFrame(data).groupby('date')['pnl'].sum().reset_index().sort_values('date')
        except: return None

    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())

    if raw_data:
        # --- CALCOLO MARGINI ---
        margine_totale = 0
        ticker_attivi = {}
        selected_names = []
        
        st.write("### 🛠️ Selezione Strategie")
        cols = st.columns(min(len(raw_data), 4))
        for i, name in enumerate(sorted(raw_data.keys())):
            ticker = name.split('_')[0].upper().strip()
            m_val = live_margins.get(ticker, 0)
            with cols[i % 4]:
                if st.checkbox(f"{name} (${m_val:,.0f})", value=True, key=name):
                    selected_names.append(name)
                    margine_totale += m_val
                    if m_val > 0: ticker_attivi[ticker] = m_val

        if selected_names:
            # --- ELABORAZIONE DATI ---
            df_port = pd.DataFrame({'date': sorted(list(set(all_dates)))})
            for name in selected_names:
                df_port = df_port.merge(raw_data[name][['date', 'pnl']].rename(columns={'pnl': name + '_pnl'}), on='date', how='left')
            df_port.fillna(0, inplace=True)
            
            mask = (df_port['date'].dt.date >= st.sidebar.date_input("Inizio", min(all_dates).date())) & \
                   (df_port['date'].dt.date <= st.sidebar.date_input("Fine", max(all_dates).date()))
            df_plot = df_port[mask].copy()

            for n in selected_names: df_plot[n] = df_plot[n + '_pnl'].cumsum()
            df_plot['TOTALE'] = df_plot[selected_names].sum(axis=1)
            df_plot['DD'] = df_plot['TOTALE'] - df_plot['TOTALE'].cummax()
            
            max_dd = abs(df_plot['DD'].min())

            # --- SIDEBAR: GESTIONE CAPITALE ---
            st.sidebar.header("💰 Gestione Capitale")
            capitale_minimo = margine_totale + max_dd
            capitale_prudenziale = margine_totale + (max_dd * 1.5)
            
            st.sidebar.metric("Margine Totale", f"${margine_totale:,.0f}")
            st.sidebar.metric("Max Drawdown Storico", f"-${max_dd:,.0f}")
            st.sidebar.subheader("Capitale Suggerito")
            st.sidebar.info(f"**Minimo:** ${capitale_minimo:,.0f}\n\n**Prudenziale:** ${capitale_prudenziale:,.0f}")

            if ticker_attivi:
                st.sidebar.write("---")
                st.sidebar.table(pd.DataFrame([{"Ticker": k, "Margine": v} for k, v in ticker_attivi.items()]))

            # --- GRAFICO E TABELLE ---
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['TOTALE'], name='PORTAFOGLIO', line=dict(color='black', width=3)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['DD'], name='Drawdown', fill='tozeroy', line=dict(color='red')), row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # Performance Table
            st.write("### 📊 Performance & ROE")
            df_plot['Year'] = df_plot['date'].dt.year
            res = df_plot.groupby('Year')[[n + '_pnl' for n in selected_names]].sum().round(0)
            res['PnL TOTALE'] = res.sum(axis=1)
            if capitale_minimo > 0:
                res['ROE % (Cap. Min)'] = (res['PnL TOTALE'] / capitale_minimo * 100).round(2)
            
            st.dataframe(res.style.format("{:,.0f}"), use_container_width=True)
