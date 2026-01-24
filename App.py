import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import requests

st.set_page_config(page_title="Margine Netto Contemporaneo", layout="wide")

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

st.markdown("# 📈 Calcolo Margine Netto Reale (Netting Long/Short)")

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
                    # pnl > 0 (ipotizziamo Long), pnl < 0 (ipotizziamo Short)
                    # Nota: Titan nei file di export indica la direzione del trade
                    data.append({
                        'date': datetime.strptime(parts[0], '%d/%m/%Y'), 
                        'pnl': float(parts[1])
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
        
        st.write("### 🛠️ Strategie in Portafoglio")
        cols = st.columns(min(len(raw_data), 4))
        for i, name in enumerate(sorted(raw_data.keys())):
            ticker = name.split('_')[0].upper().strip()
            ticker_map[name] = ticker
            with cols[i % 4]:
                if st.checkbox(f"{name}", value=True, key=name):
                    selected_names.append(name)

        if selected_names:
            dates_set = sorted(list(set(all_dates)))
            df_master = pd.DataFrame({'date': dates_set})
            
            # Dizionario per tracciare l'esposizione netta per ogni ticker ogni giorno
            # Struttura: { 'DATA': { 'NQ': posizione_netta, 'ES': posizione_netta } }
            daily_net_positions = {d: {} for d in dates_set}

            total_equity = pd.Series(0.0, index=dates_set)

            for name in selected_names:
                ticker = ticker_map[name]
                temp_df = raw_data[name].copy().set_index('date')
                
                for d, row in temp_df.iterrows():
                    if d in daily_net_positions:
                        # Assumiamo 1 contratto per strategia. 
                        # Se PnL > 0 = +1 (Long), se PnL < 0 = -1 (Short)
                        direction = 1 if row['pnl'] > 0 else (-1 if row['pnl'] < 0 else 0)
                        daily_net_positions[d][ticker] = daily_net_positions[d].get(ticker, 0) + direction
                
                # Aggiungiamo all'equity totale
                total_equity = total_equity.add(temp_df['pnl'], fill_value=0)

            # Calcolo del margine giornaliero basato sulla posizione NETTA
            daily_margins = []
            for d in dates_set:
                margin_day = 0
                for ticker, net_pos in daily_net_positions[d].items():
                    # Il margine si paga sul valore assoluto della posizione netta
                    # Se net_pos è 0 (1 Long e 1 Short), il margine è 0
                    margin_day += abs(net_pos) * live_margins.get(ticker, 0)
                daily_margins.append(margin_day)

            df_master['Margine_Netto'] = daily_margins
            df_master['Equity_Cumulata'] = total_equity.cumsum().values
            df_master['DD'] = df_master['Equity_Cumulata'] - df_master['Equity_Cumulata'].cummax()

            # Metriche
            margine_picco = df_master['Margine_Netto'].max()
            max_dd = abs(df_master['DD'].min())
            capitale_req = margine_picco + max_dd

            st.sidebar.header("📊 Analisi Netting")
            st.sidebar.metric("Picco Margine Netto", f"${margine_picco:,.0f}")
            st.sidebar.metric("Max Drawdown", f"${max_dd:,.0f}")
            st.sidebar.success(f"**Capitale Reale: ${capitale_req:,.0f}**")
            st.sidebar.caption("Il calcolo considera 0 margine se le strategie sono contrapposte (Long vs Short) sullo stesso ticker.")

            # Grafico
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                               subplot_titles=("Equity Cumulata", "Margine Netto Impegnato (con Netting)"))
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Equity_Cumulata'], name='Equity', line=dict(color='black')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_master['date'], y=df_master['Margine_Netto'], name='Margine', fill='tozeroy', line=dict(color='blue')), row=2, col=1)
            fig.update_layout(height=800, plot_bgcolor='white')
            st.plotly_chart(fig, use_container_width=True)
