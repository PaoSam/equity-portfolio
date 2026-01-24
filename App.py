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

st.markdown("# 📈 Analisi Professionale Portafoglio Titan")

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

        # --- 2. SELEZIONE STRATEGIE E MAPPATURA MARGINI ---
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
            # --- 3. ELABORAZIONE DATI (NETTING & EQUITY) ---
            dates_set = sorted(list(set(all_dates)))
            df_master = pd.DataFrame({'date': dates_set})
            net_exposure = {d: {} for d in dates_set}
            
            # Per visualizzare le equity singole
            for name in selected_names:
                ticker = ticker_map[name]
                temp_df = raw_data[name].copy().rename(columns={'pnl': f'pnl_{name}'}).set_index('date')
                df_master = df_master.merge(temp_df[[f'pnl_{name}', 'pos']], on='date', how='left').fillna(0)
                
                # Calcolo posizione netta per asset
                for d in dates_set:
                    pos_val = df_master.loc[df_master['date'] == d, 'pos'].values[0]
                    net_exposure[d][ticker] = net_exposure[d].get(ticker, 0) + pos_val
                
                # Creazione Equity Cumulata Singola
                df_master[f'eq_{name}'] = df_master[f'pnl_{name}'].cumsum()
                df_master.drop('pos', axis=1, inplace=True)

            # Calcolo Margine Reale Giornaliero
            m_giornaliero = []
            for d in dates_set:
                day_m = sum(abs(pos) * live_margins.get(t, 0) for t, pos in net_exposure[d].items())
                m_giornaliero.append(day_m)
            
            df_master['Margine_Reale'] = m_giornaliero
            pnl_cols = [f'pnl_{n}' for n in selected_names]
            df_master['Equity_Totale'] = df_master[pnl_cols].sum(axis=1).cumsum()
            df_master['DD'] = df_master['Equity_Totale'] - df_master['Equity_Totale'].cummax()

            # --- 4. METRICHE PROFESSIONALI NELLA SIDEBAR ---
            max_m = df_master['Margine_Reale'].max()
            max_dd = abs(df_master['DD'].min())
            
            capitale_minimo = max_m + max_dd
            capitale_prudenziale = max_m + (max_dd * 1.5) # Metodo professionale 1.5x DD
            
            st.sidebar.header("💰 Gestione Capitale")
            st.sidebar.metric("Picco Margine Netto", f"${max_m:,.0f}")
            st.sidebar.metric("Max Drawdown Storico", f"-${max_dd:,.0f}")
            
            st.sidebar.subheader("Allocazione Suggerita")
            st.sidebar.info(f"**Capitale Minimo:** ${capitale_minimo:,.0f}\n\n**Capitale Prudenziale:** ${capitale_prudenziale:,.0f}")

            # Tabella Margini Rilevati
            if ticker_attivi_margini:
                st.sidebar.write("---")
                st.sidebar.subheader("📌 Margini IBKR Rilevati")
                df_m_info = pd.DataFrame([{"Strumento": k, "Margine ($)": v} for k, v in ticker_attivi_margini.items()])
                st.sidebar.table(df_m_info.style.format({"Margine ($)": "{:,.2f}"}))

            # --- 5. GRAFICO PROFESSIONALE ---
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, 
                               row_heights=[0.7, 0.3],
                               subplot_titles=("Equity Line (Totale e Singole)", "Impegno Margine Reale ($)"))
            
            # Linea Totale (Nera)
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Equity_Totale'], 
                                     name='PORTAFOGLIO', line=dict(color='black', width=4)), row=1, col=1)
            
            # Linee Singole (Sottili)
            for name in selected_names:
                fig.add_trace(go.Scatter(x=df_master['date'], y=df_master[f'eq_{name}'], 
                                         name=name, line=dict(width=1.5), opacity=0.5), row=1, col=1)
            
            # Area Margine
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Margine_Reale'], 
                                     name='Margine Reale', fill='tozeroy', line=dict(color='orange')), row=2, col=1)
            
            fig.update_layout(height=850, template="plotly_white", hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # --- 6. TABELLA PERFORMANCE ANNUALE ---
            st.write("### 📊 Tabella Performance e ROE")
            df_master['Year'] = df_master['date'].dt.year
            res = df_master.groupby('Year')[pnl_cols].sum().round(0)
            res['PnL Totale'] = res.sum(axis=1)
            
            if capitale_prudenziale > 0:
                res['ROE % (su Prudenziale)'] = (res['PnL Totale'] / capitale_prudenziale * 100).round(2)
            
            st.dataframe(res.style.format("{:,.0f}"), use_container_width=True)
