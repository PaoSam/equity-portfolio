import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import requests

# Configurazione Pagina
st.set_page_config(page_title="Equity Portfolio Paolo - Dettaglio Margini", layout="wide")

# --- FUNZIONE PER LEGGERE I MARGINI LIVE DA IBKR ---
@st.cache_data(ttl=3600)
def get_ibkr_margins(url):
    try:
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=header, timeout=15)
        # Utilizziamo lxml per il parsing (assicurati di averlo nel requirements.txt)
        tables = pd.read_html(response.text, flavor='lxml')
        
        margin_dict = {}
        for df in tables:
            df.columns = [str(c).strip() for c in df.columns]
            if 'Underlying' in df.columns and 'Overnight Initial' in df.columns:
                for _, row in df.iterrows():
                    ticker = str(row['Underlying']).strip().upper()
                    val_raw = str(row['Overnight Initial']).replace('$', '').replace('€', '').replace(',', '').strip()
                    try:
                        margin_dict[ticker] = float(val_raw)
                    except:
                        continue
        return margin_dict
    except Exception as e:
        st.error(f"Errore tecnico nella lettura IBKR: {e}")
        return {}

st.markdown("# 📈 Analisi Equity e Dettaglio Margini Strumenti")

# Scraping Live
url_ibkr = "https://www.interactivebrokers.com/en/trading/margin-futures-fops.php"
with st.spinner('Aggiornamento margini da Interactive Brokers...'):
    live_margins = get_ibkr_margins(url_ibkr)

# Caricamento File
uploaded_files = st.file_uploader("Carica i file TXT da Titan", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = []
    
    def load_equity(uploaded_file):
        data = []
        try:
            content = uploaded_file.getvalue().decode("utf-8")
            for line in content.splitlines():
                parts = line.strip().split()
                if len(parts) == 6:
                    try:
                        d = datetime.strptime(parts[0], '%d/%m/%Y')
                        v = float(parts[1])
                        data.append({'date': d, 'pnl': v})
                    except: continue
            df = pd.DataFrame(data)
            return df.groupby('date')['pnl'].sum().reset_index().sort_values('date')
        except: return None

    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())

    if raw_data:
        # --- CALCOLO E DETTAGLIO MARGINI ---
        st.sidebar.header("💰 Analisi Margini Live")
        margine_totale = 0
        dettaglio_strumenti = []

        st.write("### 🛠️ Strategie Selezionate")
        selected_names = []
        cols = st.columns(min(len(raw_data), 4))
        
        for i, name in enumerate(sorted(raw_data.keys())):
            m_val = 0
            ticker_trovato = "N/A"
            # Matching ticker nel nome del file
            for t in live_margins:
                if t in name.upper():
                    m_val = live_margins[t]
                    ticker_trovato = t
                    break
            
            with cols[i % 4]:
                if st.checkbox(f"{name} (${m_val:,.0f})", value=True, key=name):
                    selected_names.append(name)
                    margine_totale += m_val
                    if m_val > 0:
                        dettaglio_strumenti.append({
                            "Strategia": name,
                            "Ticker": ticker_trovato,
                            "Margine Singolo ($)": m_val
                        })

        if selected_names:
            # Mostra Margine Totale
            st.sidebar.metric("Margine Totale Portafoglio", f"${margine_totale:,.2f}")
            
            # Mostra Tabella Dettaglio Singoli Margini
            if dettaglio_strumenti:
                st.sidebar.write("---")
                st.sidebar.subheader("📌 Dettaglio Strumenti")
                df_dettaglio = pd.DataFrame(dettaglio_strumenti)
                st.sidebar.dataframe(
                    df_dettaglio.style.format({"Margine Singolo ($)": "{:,.2f}"}),
                    hide_index=True,
                    use_container_width=True
                )

            # --- ELABORAZIONE GRAFICO ---
            dates_set = sorted(list(set(all_dates)))
            df_port = pd.DataFrame({'date': dates_set})
            for name in selected_names:
                df_port = df_port.merge(raw_data[name][['date', 'pnl']].rename(columns={'pnl': name + '_pnl'}), on='date', how='left')
            df_port.fillna(0, inplace=True)
            
            start_d = st.sidebar.date_input("Inizio", min(all_dates).date())
            end_d = st.sidebar.date_input("Fine", max(all_dates).date())
            mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
            df_plot = df_port[mask].copy()

            for n in selected_names:
                df_plot[n] = df_plot[n + '_pnl'].cumsum()
            
            df_plot['TOTALE'] = df_plot[selected_names].sum(axis=1)
            df_plot['DD'] = df_plot['TOTALE'] - df_plot['TOTALE'].cummax()

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['TOTALE'], name='TOTAL EQUITY', line=dict(color='black', width=3)), row=1, col=1)
            for n in selected_names:
                fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[n], name=n, line=dict(width=1), opacity=0.3), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['DD'], name='Drawdown', fill='tozeroy', line=dict(color='red')), row=2, col=1)
            fig.update_layout(plot_bgcolor='white', height=750, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # Performance Table con ROE
            st.write("### 📊 Risultati Annuali & ROE Live")
            df_plot['Year'] = df_plot['date'].dt.year
            res = df_plot.groupby('Year')[[n + '_pnl' for n in selected_names]].sum().round(0)
            res['PnL TOTALE'] = res.sum(axis=1)
            if margine_totale > 0:
                res['ROE %'] = (res['PnL TOTALE'] / margine_totale * 100).round(2)
            
            st.dataframe(res.style.format("{:,.2f}"), use_container_width=True)
