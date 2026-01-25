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
            
            # --- CALCOLO STATISTICHE AVANZATE ---
            stats_list = []
            risk_free_rate = 0.0 # Assunto 0 per semplicità

            for name in selected_names:
                ticker = ticker_map[name]
                temp_df = raw_data[name].copy().rename(columns={'pnl': f'pnl_{name}', 'pos': f'pos_{name}'})
                df_master = df_master.merge(temp_df[['date', f'pnl_{name}', f'pos_{name}']], on='date', how='left').fillna(0)
                
                # Filtro date per la singola strategia
                df_strat = temp_df[(temp_df['date'].dt.date >= start_date) & (temp_df['date'].dt.date <= end_date)].copy()
                
                # Calcolo Rendimenti e Rischio
                pnl_daily = df_strat[f'pnl_{name}']
                avg_ann_pnl = pnl_daily.mean() * 252
                std_ann = pnl_daily.std() * np.sqrt(252)
                
                # Sharpe Ratio
                sharpe = (avg_ann_pnl / std_ann) if std_ann != 0 else 0
                
                # Sortino Ratio
                downside_std = pnl_daily[pnl_daily < 0].std() * np.sqrt(252)
                sortino = (avg_ann_pnl / downside_std) if downside_std != 0 else 0
                
                # MAR Ratio
                cum_eq = pnl_daily.cumsum()
                max_dd_strat = abs((cum_eq - cum_eq.cummax()).min())
                mar_ratio = (avg_ann_pnl / max_dd_strat) if max_dd_strat != 0 else 0

                # Trade Detection
                df_strat['is_active'] = df_strat[f'pos_{name}'] != 0
                df_strat['trade_id'] = (df_strat['is_active'] != df_strat['is_active'].shift()).cumsum()
                trades = df_strat[df_strat['is_active']].groupby('trade_id')[f'pnl_{name}'].sum()
                
                if not trades.empty:
                    stats_list.append({
                        "Strategia": name,
                        "Total Trades": len(trades),
                        "Win Rate %": (len(trades[trades > 0]) / len(trades)) * 100,
                        "Profit Factor": abs(trades[trades > 0].sum() / trades[trades <= 0].sum()) if trades[trades <= 0].sum() != 0 else np.inf,
                        "Sharpe Ratio": sharpe,
                        "Sortino Ratio": sortino,
                        "MAR Ratio": mar_ratio,
                        "Avg Trade ($)": trades.mean()
                    })

            # --- GRAFICI PRINCIPALI ---
            pnl_cols = [f'pnl_{n}' for n in selected_names]
            df_master['Equity_Totale'] = df_master[pnl_cols].sum(axis=1).cumsum()
            df_master['DD'] = df_master['Equity_Totale'] - df_master['Equity_Totale'].cummax()
            
            # Calcolo Netting Margine
            net_exposure = {d: {t: 0 for t in strumenti_caricati} for d in dates_set}
            for name in selected_names:
                for d in dates_set:
                    net_exposure[d][ticker_map[name]] += df_master.loc[df_master['date']==d, f'pos_{name}'].values[0]
            
            m_giornaliero = [sum(abs(pos) * live_margins.get(t, 0) for t, pos in net_exposure[d].items()) for d in dates_set]
            
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.5, 0.25, 0.25])
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Equity_Totale'], name='Portafoglio', line=dict(color='black', width=3)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['DD'], name='Drawdown', fill='tozeroy', line=dict(color='red')), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_master['date'], y=m_giornaliero, name='Margine', fill='tozeroy', line=dict(color='orange')), row=3, col=1)
            fig.update_layout(height=800, template="plotly_white", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            # --- TABELLA STATISTICHE PROFESSIONALI ---
            st.write("---")
            st.write("### 📊 Analisi Statistica e Rendimento/Rischio")
            if stats_list:
                df_stats = pd.DataFrame(stats_list)
                st.dataframe(df_stats.style.format({
                    "Win Rate %": "{:.1f}%",
                    "Profit Factor": "{:.2f}",
                    "Sharpe Ratio": "{:.2f}",
                    "Sortino Ratio": "{:.2f}",
                    "MAR Ratio": "{:.2f}",
                    "Avg Trade ($)": "{:,.0f}"
                }), use_container_width=True, hide_index=True)

            # --- CORRELAZIONE ---
            st.write("---")
            st.write("### 🧬 Correlazione Rendimenti")
            corr = df_master[pnl_cols].corr()
            corr.columns = [c.replace('pnl_', '') for c in corr.columns]
            corr.index = [c.replace('pnl_', '') for c in corr.index]
            st.plotly_chart(px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r', zmin=-1, zmax=1), use_container_width=True)

            # --- RENDIMENTI ANNUALI ---
            st.write("---")
            st.write("### 📅 Performance e Efficienza Capitale")
            df_master['Year'] = df_master['date'].dt.year
            res = df_master.groupby('Year')[pnl_cols].sum().round(0)
            res['PnL Totale'] = res.sum(axis=1)
            
            max_m, max_dd = max(m_giornaliero), abs(df_master['DD'].min())
            cap_pru = max_m + (max_dd * 1.5)
            
            res['ROE %'] = (res['PnL Totale'] / cap_pru * 100).round(2)
            st.dataframe(res.style.format("{:,.0f}"), use_container_width=True)
            
            st.sidebar.write("---")
            st.sidebar.metric("MAR Ratio Portafoglio", f"{((res['PnL Totale'].mean()) / max_dd):.2f}")
