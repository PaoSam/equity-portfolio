import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import requests

st.set_page_config(page_title="Netting Professionale Titan", layout="wide")

# --- FUNZIONE MARGINI IBKR ---
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

st.markdown("# 📈 Analisi Margine Reale con Netting (Dati Titan)")

url_ibkr = "https://www.interactivebrokers.com/en/trading/margin-futures-fops.php"
with st.spinner('Aggiornamento margini IBKR...'):
    live_margins = get_ibkr_margins(url_ibkr)

uploaded_files = st.file_uploader("Carica i file TXT di Titan", type="txt", accept_multiple_files=True)

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
                        'pos': int(float(parts[2]))  # Legge il campo 1, -1 o 0
                    })
            return pd.DataFrame(data).sort_values('date')
        except Exception as e:
            st.error(f"Errore nel file {uploaded_file.name}: {e}")
            return None

    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())

    if raw_data:
        selected_names = []
        ticker_map = {}
        
        st.write("### 🛠️ Strategie Selezionate")
        cols = st.columns(min(len(raw_data), 4))
        for i, name in enumerate(sorted(raw_data.keys())):
            ticker = name.split('_')[0].upper().strip()
            ticker_map[name] = ticker
            with cols[i % 4]:
                if st.checkbox(name, value=True, key=name):
                    selected_names.append(name)

        if selected_names:
            dates_set = sorted(list(set(all_dates)))
            df_master = pd.DataFrame({'date': dates_set})
            
            # Calcolo esposizione netta giornaliera per ogni asset
            net_exposure = {d: {} for d in dates_set}
            total_pnl = pd.Series(0.0, index=dates_set)

            for name in selected_names:
                ticker = ticker_map[name]
                temp_df = raw_data[name].set_index('date')
                
                for d, row in temp_df.iterrows():
                    if d in net_exposure:
                        # Usiamo il valore reale del campo posizione (1, -1, 0)
                        net_exposure[d][ticker] = net_exposure[d].get(ticker, 0) + row['pos']
                
                total_pnl = total_pnl.add(temp_df['pnl'], fill_value=0)

            # Calcolo Margine Reale Applicando il Netting
            m_giornaliero = []
            for d in dates_set:
                day_margin = 0
                for t, pos_netta in net_exposure[d].items():
                    # Il margine si paga sul valore assoluto della posizione netta finale
                    # Se pos_netta è 0 (hedging perfetto), il margine è 0
                    day_margin += abs(pos_netta) * live_margins.get(t, 0)
                m_giornaliero.append(day_margin)

            df_master['Margine_Reale'] = m_giornaliero
            df_master['Equity'] = total_pnl.cumsum().values
            df_master['DD'] = df_master['Equity'] - df_master['Equity'].cummax()

            # --- SIDEBAR METRICHE ---
            max_m = df_master['Margine_Reale'].max()
            max_dd = abs(df_master['DD'].min())
            capitale_necessario = max_m + max_dd

            st.sidebar.header("🛡️ Gestione Rischio")
            st.sidebar.metric("Picco Margine Netto", f"${max_m:,.0f}")
            st.sidebar.metric("Max Drawdown Storico", f"${max_dd:,.0f}")
            st.sidebar.success(f"**Capitale Reale: ${capitale_necessario:,.0f}**")
            st.sidebar.caption("Basato sulla posizione netta reale (Long/Short/Flat) estratta dai file.")

            # --- GRAFICI ---
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                               subplot_titles=("Equity Cumulata", "Margine Reale Impegnato ($)"))
            
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Equity'], name="Equity", line=dict(color="black")), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Margine_Reale'], name="Margine", fill='tozeroy', line=dict(color="orange")), row=2, col=1)
            
            fig.update_layout(height=800, template="plotly_white", showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
            
            # Tabella di verifica
            with st.expander("Vedi log posizioni nette per giorno"):
                check_df = pd.DataFrame([{'Data': d, 'Margine': m} for d, m in zip(dates_set, m_giornaliero)])
                st.dataframe(check_df.sort_values('Margine', ascending=False).head(20))
