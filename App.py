import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import requests

st.set_page_config(page_title="Professional Portfolio Analysis", layout="wide")

# --- 1. RECUPERO MARGINI LIVE ---
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

st.markdown("# 📈 Analisi Professionale con Equity, Drawdown e Margini")

url_ibkr = "https://www.interactivebrokers.com/en/trading/margin-futures-fops.php"
with st.spinner('Sincronizzazione margini con IBKR...'):
    live_margins = get_ibkr_margins(url_ibkr)

uploaded_files = st.file_uploader("Carica file Titan (.txt)", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = []
    
    def load_equity(uploaded_file):
        try:
            content = uploaded_file.getvalue().decode("utf-8")
            data = []
            for line in content.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3:
                    data.append({
                        'date': datetime.strptime(parts[0], '%d/%m/%Y'), 
                        'pnl': float(parts[1]),
                        'pos': int(float(parts[2]))
                    })
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
        ticker_attivi_margini = {}

        st.write("### 🛠️ Strategie in Analisi")
        cols = st.columns(min(len(raw_data), 4))
        for i, name in enumerate(sorted(raw_data.keys())):
            ticker = name.split('_')[0].upper().strip()
            ticker_map[name] = ticker
            m_unitario = live_margins.get(ticker, 0.0)
            
            with cols[i % 4]:
                if st.checkbox(f"{name}", value=True, key=name):
                    selected_names.append(name)
                    if m_unitario > 0:
                        ticker_attivi_margini[ticker] = m_unitario

        if selected_names:
            dates_set = sorted(list(set(all_dates)))
            df_master = pd.DataFrame({'date': dates_set})
            net_exposure = {d: {} for d in dates_set}
            
            for name in selected_names:
                ticker = ticker_map[name]
                temp_df = raw_data[name].copy().rename(columns={'pnl': f'pnl_{name}'}).set_index('date')
                df_master = df_master.merge(temp_df[[f'pnl_{name}', 'pos']], on='date', how='left').fillna(0)
                
                for d in dates_set:
                    pos_val = df_master.loc[df_master['date'] == d, 'pos'].values[0]
                    net_exposure[d][ticker] = net_exposure[d].get(ticker, 0) + pos_val
                
                df_master[f'eq_{name}'] = df_master[f'pnl_{name}'].cumsum()
                df_master.drop('pos', axis=1, inplace=True)

            m_giornaliero = [sum(abs(pos) * live_margins.get(t, 0) for t, pos in net_exposure[d].items()) for d in dates_set]
            
            df_master['Margine_Reale'] = m_giornaliero
            pnl_cols = [f'pnl_{n}' for n in selected_names]
            df_master['Equity_Totale'] = df_master[pnl_cols].sum(axis=1).cumsum()
            df_master['DD'] = df_master['Equity_Totale'] - df_master['Equity_Totale'].cummax()

            max_m = df_master['Margine_Reale'].max()
            max_dd = abs(df_master['DD'].min())
            cap_prudenziale = max_m + (max_dd * 1.5)
            
            # --- SIDEBAR ---
            st.sidebar.header("💰 Gestione Capitale")
            st.sidebar.metric("Picco Margine Netto", f"${max_m:,.0f}")
            st.sidebar.metric("Max Drawdown", f"-${max_dd:,.0f}")
            st.sidebar.info(f"**Capitale Prudenziale:** ${cap_prudenziale:,.0f}")

            if ticker_attivi_margini:
                st.sidebar.write("---")
                st.sidebar.subheader("📌 Margini IBKR")
                st.sidebar.table(pd.DataFrame([{"Asset": k, "Margine": v} for k, v in ticker_attivi_margini.items()]))

            # --- GRAFICO A 3 LIVELLI (EQUITY, DD, MARGINE) ---
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, 
                               row_heights=[0.5, 0.25, 0.25],
                               subplot_titles=("Equity (Totale e Singole)", "Drawdown Portafoglio ($)", "Margine Netto ($)"))
            
            # 1. Equity
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Equity_Totale'], name='PORTAFOGLIO', line=dict(color='black', width=3)), row=1, col=1)
            for name in selected_names:
                fig.add_trace(go.Scatter(x=df_master['date'], y=df_master[f'eq_{name}'], name=name, line=dict(width=1), opacity=0.4), row=1, col=1)
            
            # 2. Drawdown
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['DD'], name='Drawdown', fill='tozeroy', line=dict(color='red')), row=2, col=1)
            
            # 3. Margine
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Margine_Reale'], name='Margine', fill='tozeroy', line=dict(color='orange')), row=3, col=1)
            
            fig.update_layout(height=950, template="plotly_white", hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # Performance
            st.write("### 📊 Risultati Annuali")
            df_master['Year'] = df_master['date'].dt.year
            res = df_master.groupby('Year')[pnl_cols].sum().round(0)
            res['PnL Totale'] = res.sum(axis=1)
            res['ROE %'] = (res['PnL Totale'] / cap_prudenziale * 100).round(2)
            st.dataframe(res.style.format("{:,.0f}"), use_container_width=True)
