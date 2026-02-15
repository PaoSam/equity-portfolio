import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime
import requests
import re

st.set_page_config(page_title="Titan Portfolio Professional", layout="wide")

# --- 1. RECUPERO MARGINI LIVE (VERSIONE STABILE) ---
@st.cache_data(ttl=3600)
def get_ibkr_margins():
    url = "https://www.interactivebrokers.com/en/trading/margin-futures-fops.php?hm=eu&ex=us&rgt=0&rsk=1&pm=1"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9"
        }

        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        tables = pd.read_html(response.text, flavor="lxml")

        margin_dict = {}

        for df in tables:
            df.columns = [str(c).strip().lower() for c in df.columns]

            underlying_cols = [c for c in df.columns if "underlying" in c or "symbol" in c]
            overnight_cols = [c for c in df.columns if "overnight" in c and "initial" in c]
            exchange_cols = [c for c in df.columns if "exchange" in c]

            if not underlying_cols or not overnight_cols:
                continue

            underlying_col = underlying_cols[0]
            overnight_col = overnight_cols[0]

            if exchange_cols:
                exchange_col = exchange_cols[0]
                df = df[df[exchange_col].astype(str).str.contains(
                    "CME|NYMEX|CBOT|COMEX", case=False, na=False
                )]

            for _, row in df.iterrows():
                ticker = str(row[underlying_col]).strip().upper()

                raw_val = str(row[overnight_col])
                raw_val = re.sub(r"[^\d.]", "", raw_val)

                try:
                    value = float(raw_val)
                    if value > 0:
                        margin_dict[ticker] = value
                except:
                    continue

        return margin_dict

    except Exception as e:
        print("Errore recupero margini IBKR:", e)
        return {}

st.markdown("# 📈 Analisi Avanzata Portafoglio Titan")

with st.spinner('Sincronizzazione margini live...'):
    live_margins = get_ibkr_margins()

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
        except:
            return None

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
        
        st.sidebar.header("🗓️ Filtri Temporali")
        abs_min_date, abs_max_date = min(all_dates).date(), max(all_dates).date()
        start_date = st.sidebar.date_input("Data Inizio", value=abs_min_date, min_value=abs_min_date, max_value=abs_max_date)
        end_date = st.sidebar.date_input("Data Fine", value=abs_max_date, min_value=abs_min_date, max_value=abs_max_date)

        st.sidebar.write("---")
        st.sidebar.header("🎲 Parametri Monte Carlo")
        n_sim = st.sidebar.slider("Numero Simulazioni", 100, 5000, 1000)
        n_giorni = st.sidebar.number_input("Giorni Proiezione", value=252)

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
            
            stats_list = []
            active_info = {d: [] for d in dates_set}
            
            for name in selected_names:
                ticker = ticker_map[name]
                temp_df = raw_data[name].copy().rename(columns={'pnl': f'pnl_{name}', 'pos': f'pos_{name}'})
                df_master = df_master.merge(temp_df[['date', f'pnl_{name}', f'pos_{name}']], on='date', how='left').fillna(0)
                df_master[f'eq_{name}'] = df_master[f'pnl_{name}'].cumsum()
                
                df_strat = temp_df[(temp_df['date'].dt.date >= start_date) & (temp_df['date'].dt.date <= end_date)].copy()
                df_strat['is_active'] = df_strat[f'pos_{name}'] != 0
                df_strat['trade_id'] = (df_strat['is_active'] != df_strat['is_active'].shift()).cumsum()
                trades = df_strat[df_strat['is_active']].groupby('trade_id')[f'pnl_{name}'].sum()
                
                for d in dates_set:
                    pos_val = df_master.loc[df_master['date'] == d, f'pos_{name}'].values[0]
                    if pos_val != 0:
                        active_info[d].append(f"{name}({'L' if pos_val==1 else 'S'})")

                if not trades.empty:
                    wins = trades[trades > 0]
                    losses = trades[trades <= 0]
                    daily_returns = df_strat[f'pnl_{name}']
                    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() != 0 else 0
                    equity_curve = daily_returns.cumsum()
                    max_dd_strat = abs((equity_curve - equity_curve.cummax()).min())
                    days_diff = (end_date - start_date).days
                    cagr = (daily_returns.sum() / days_diff * 365) if days_diff > 0 else 0

                    stats_list.append({
                        "Strategia": name,
                        "Trades": len(trades),
                        "Win Rate": f"{(len(wins)/len(trades)*100):.1f}%",
                        "Profit Factor": round(abs(wins.sum()/losses.sum()), 2) if losses.sum() != 0 else np.inf,
                        "Sharpe": round(sharpe, 2),
                        "MAR": round(cagr/max_dd_strat, 2) if max_dd_strat != 0 else 0,
                        "Avg Trade ($)": round(trades.mean(), 2)
                    })

            pnl_cols = [f'pnl_{n}' for n in selected_names]
            df_master['Equity_Totale'] = df_master[pnl_cols].sum(axis=1).cumsum()
            df_master['DD'] = df_master['Equity_Totale'] - df_master['Equity_Totale'].cummax()

            net_exposure = {d: {t: 0 for t in strumenti_caricati} for d in dates_set}
            for name in selected_names:
                for d in dates_set:
                    net_exposure[d][ticker_map[name]] += df_master.loc[df_master['date']==d, f'pos_{name}'].values[0]
            m_giornaliero = [sum(abs(pos) * live_margins.get(t, 0) for t, pos in net_exposure[d].items()) for d in dates_set]

            # (Il resto del codice grafici, Monte Carlo, performance annuale rimane IDENTICO al tuo originale)
