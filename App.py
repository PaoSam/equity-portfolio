import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import requests

st.set_page_config(page_title="Margine Reale Asset-Based", layout="wide")

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

st.markdown("# 📈 Calcolo Margine Reale per Asset")

url_ibkr = "https://www.interactivebrokers.com/en/trading/margin-futures-fops.php"
with st.spinner('Lettura margini IBKR...'):
    live_margins = get_ibkr_margins(url_ibkr)

uploaded_files = st.file_uploader("Carica file Titan", type="txt", accept_multiple_files=True)

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
            return pd.DataFrame(data).sort_values('date')
        except: return None

    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())

    if raw_data:
        selected_names = []
        ticker_map = {}
        
        st.write("### 🛠️ Selezione Strategie")
        cols = st.columns(min(len(raw_data), 4))
        for i, name in enumerate(sorted(raw_data.keys())):
            ticker = name.split('_')[0].upper().strip()
            ticker_map[name] = ticker
            with cols[i % 4]:
                if st.checkbox(name, value=True):
                    selected_names.append(name)

        if selected_names:
            dates_set = sorted(list(set(all_dates)))
            df_master = pd.DataFrame({'date': dates_set})
            
            # Struttura per il calcolo netto: { data: { ticker: posizione_netta } }
            net_exposure = {d: {} for d in dates_set}
            total_pnl = pd.Series(0.0, index=dates_set)

            for name in selected_names:
                ticker = ticker_map[name]
                temp_df = raw_data[name].set_index('date')
                
                for d, row in temp_df.iterrows():
                    if d in net_exposure:
                        # Determiniamo la direzione dal PnL
                        # Se PnL > 0 assume Long (+1), se < 0 assume Short (-1)
                        direction = 1 if row['pnl'] > 0 else (-1 if row['pnl'] < 0 else 0)
                        net_exposure[d][ticker] = net_exposure[d].get(ticker, 0) + direction
                
                total_pnl = total_pnl.add(temp_df['pnl'], fill_value=0)

            # CALCOLO MARGINE REALE
            # Se hai 1 Long e 1 Short sullo stesso ticker, il margine è 0.
            # Se hai solo una delle due attiva, il margine è quello di 1 contratto.
            m_giornaliero = []
            for d in dates_set:
                day_m = 0
                for t, pos in net_exposure[d].items():
                    # Usiamo il valore assoluto della posizione netta (Netting)
                    day_m += abs(pos) * live_margins.get(t, 0)
                m_giornaliero.append(day_m)

            df_master['Margine_Reale'] = m_giornaliero
            df_master['Equity'] = total_pnl.cumsum().values
            df_master['DD'] = df_master['Equity'] - df_master['Equity'].cummax()

            # Metriche Dashboard
            max_m = df_master['Margine_Reale'].max()
            max_dd = abs(df_master['DD'].min())
            
            st.sidebar.header("🛡️ Gestione del Capitale")
            st.sidebar.metric("Picco Margine Netto", f"${max_m:,.0f}")
            st.sidebar.metric("Max Drawdown", f"${max_dd:,.0f}")
            
            capitale_reale = max_m + max_dd
            st.sidebar.success(f"**Capitale Necessario: ${capitale_reale:,.0f}**")
            
            st.sidebar.write("---")
            st.sidebar.write("**Logica applicata:**")
            st.sidebar.caption("1. Netting Long/Short sullo stesso asset.")
            st.sidebar.caption("2. Margine calcolato solo sulla posizione netta aperta.")

            # Grafici
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                               subplot_titles=("Equity Line Portafoglio", "Impegno Margine Reale ($)"))
            
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Equity'], name="Equity", line=dict(color="#2ca02c")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Margine_Reale'], name="Margine", fill='tozeroy', line=dict(color="#1f77b4")), row=2, col=1)
            
            fig.update_layout(height=800, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
