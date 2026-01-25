import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime
import requests

st.set_page_config(page_title="Professional Titan Analyzer", layout="wide")

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

st.markdown("# 📈 Analisi Avanzata Portafoglio Titan")

url_ibkr = "https://www.interactivebrokers.com/en/trading/margin-futures-fops.php"
with st.spinner('Sincronizzazione margini live...'):
    live_margins = get_ibkr_margins(url_ibkr)

uploaded_files = st.file_uploader("Carica file Titan (.txt)", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = []
    strumenti_caricati = set()
    
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
        ticker = name.split('_')[0].upper().strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())
            strumenti_caricati.add(ticker)

    if raw_data:
        selected_names = []
        ticker_map = {}
        
        # --- SIDEBAR ---
        st.sidebar.header("🗓️ Filtri Temporali")
        abs_min_date, abs_max_date = min(all_dates).date(), max(all_dates).date()
        start_date = st.sidebar.date_input("Data Inizio", value=abs_min_date, min_value=abs_min_date, max_value=abs_max_date)
        end_date = st.sidebar.date_input("Data Fine", value=abs_max_date, min_value=abs_min_date, max_value=abs_max_date)

        st.sidebar.write("---")
        st.sidebar.header("🛠️ Strategie")
        for name in sorted(raw_data.keys()):
            ticker_map[name] = name.split('_')[0].upper().strip()
            if st.sidebar.checkbox(f"{name}", value=True, key=name):
                selected_names.append(name)

        st.sidebar.write("---")
        st.sidebar.subheader("📌 Margini IBKR")
        margini_filtrati = [{"Asset": s, "Margine ($)": live_margins[s]} for s in strumenti_caricati if s in live_margins]
        if margini_filtrati:
            st.sidebar.table(pd.DataFrame(margini_filtrati).set_index("Asset"))

        if selected_names:
            dates_set = sorted([d for d in list(set(all_dates)) if start_date <= d.date() <= end_date])
            df_master = pd.DataFrame({'date': dates_set})
            
            # --- CALCOLO STATISTICHE DEI TRADE PER OGNI STRATEGIA ---
            stats_list = []
            
            for name in selected_names:
                ticker = ticker_map[name]
                temp_df = raw_data[name].copy().rename(columns={'pnl': f'pnl_{name}', 'pos': f'pos_{name}'})
                df_master = df_master.merge(temp_df[['date', f'pnl_{name}', f'pos_{name}']], on='date', how='left').fillna(0)
                
                # Logica rilevamento Trade (quando pos cambia da 0 a != 0 o cambia segno)
                df_strat = temp_df[(temp_df['date'].dt.date >= start_date) & (temp_df['date'].dt.date <= end_date)].copy()
                df_strat['trade_pnl'] = df_strat[f'pnl_{name}']
                
                # Identifichiamo i singoli trade raggruppando i periodi in cui la posizione è diversa da 0
                df_strat['is_active'] = df_strat[f'pos_{name}'] != 0
                df_strat['trade_id'] = (df_strat['is_active'] != df_strat['is_active'].shift()).cumsum()
                trades = df_strat[df_strat['is_active']].groupby('trade_id')['trade_pnl'].sum()
                
                if not trades.empty:
                    wins = trades[trades > 0]
                    losses = trades[trades <= 0]
                    win_rate = (len(wins) / len(trades)) * 100
                    p_factor = abs(wins.sum() / losses.sum()) if losses.sum() != 0 else np.inf
                    avg_trade = trades.mean()
                    
                    stats_list.append({
                        "Strategia": name,
                        "Total Trades": len(trades),
                        "Win Rate %": win_rate,
                        "Profit Factor": p_factor,
                        "Avg Trade ($)": avg_trade,
                        "Max Win ($)": wins.max() if not wins.empty else 0,
                        "Max Loss ($)": losses.min() if not losses.empty else 0
                    })

            # --- DASHBOARD PRINCIPALE ---
            pnl_cols = [f'pnl_{n}' for n in selected_names]
            df_master['Equity_Totale'] = df_master[pnl_cols].sum(axis=1).cumsum()
            df_master['DD'] = df_master['Equity_Totale'] - df_master['Equity_Totale'].cummax()
            
            # Grafici Equity/Margine
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.5, 0.25, 0.25])
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Equity_Totale'], name='TOTALE', line=dict(color='black', width=3)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['DD'], name='Drawdown', fill='tozeroy', line=dict(color='red')), row=2, col=1)
            
            # Calcolo Margine Reale (Netting)
            net_exposure = {d: {t: 0 for t in strumenti_caricati} for d in dates_set}
            for name in selected_names:
                for d in dates_set:
                    val = df_master.loc[df_master['date']==d, f'pos_{name}'].values[0]
                    net_exposure[d][ticker_map[name]] += val
            
            m_giornaliero = [sum(abs(pos) * live_margins.get(t, 0) for t, pos in net_exposure[d].items()) for d in dates_set]
            fig.add_trace(go.Scatter(x=df_master['date'], y=m_giornaliero, name='Margine', fill='tozeroy', line=dict(color='orange')), row=3, col=1)
            
            fig.update_layout(height=800, template="plotly_white", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            # --- SEZIONE STATISTICHE TRADE ---
            st.write("---")
            st.write("### 📊 Analisi Statistica dei Trade")
            if stats_list:
                df_stats = pd.DataFrame(stats_list)
                st.dataframe(df_stats.style.format({
                    "Win Rate %": "{:.2f}%",
                    "Profit Factor": "{:.2f}",
                    "Avg Trade ($)": "{:,.2f}",
                    "Max Win ($)": "{:,.2f}",
                    "Max Loss ($)": "{:,.2f}"
                }), use_container_width=True, hide_index=True)
            
            # --- CORRELAZIONE ---
            st.write("---")
            st.write("### 🧬 Matrice di Correlazione")
            corr = df_master[pnl_cols].corr()
            corr.columns = [c.replace('pnl_', '') for c in corr.columns]
            corr.index = [c.replace('pnl_', '') for c in corr.index]
            st.plotly_chart(px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r', zmin=-1, zmax=1), use_container_width=True)

            # Risultati Annuali
            st.write("---")
            st.write("### 📅 Performance Annuale e ROE")
            df_master['Year'] = df_master['date'].dt.year
            res = df_master.groupby('Year')[pnl_cols].sum().round(0)
            res['PnL Totale'] = res.sum(axis=1)
            
            max_m = max(m_giornaliero)
            max_dd = abs(df_master['DD'].min())
            cap_pru = max_m + (max_dd * 1.5)
            
            res['ROE %'] = (res['PnL Totale'] / cap_pru * 100).round(2)
            st.dataframe(res.style.format("{:,.0f}"), use_container_width=True)
