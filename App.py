import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date
import requests

# Configurazione Pagina
st.set_page_config(page_title="Equity Portfolio Paolo - Live IBKR", layout="wide")

# --- FUNZIONE PER LEGGERE I MARGINI DAL SITO IBKR ---
@st.cache_data(ttl=3600)
def get_ibkr_margins(url):
    try:
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=header, timeout=15)
        
        # Specifichiamo 'lxml' come parser per evitare ambiguità
        tables = pd.read_html(response.text, flavor='lxml')
        
        margin_dict = {}
        for df in tables:
            # Pulizia nomi colonne (a volte IBKR mette spazi o caratteri speciali)
            df.columns = [str(c).strip() for c in df.columns]
            
            if 'Underlying' in df.columns and 'Overnight Initial' in df.columns:
                for _, row in df.iterrows():
                    ticker = str(row['Underlying']).strip().upper()
                    # Pulizia del valore numerico: togliamo valuta e virgole
                    val_raw = str(row['Overnight Initial']).replace('$', '').replace('€', '').replace(',', '').strip()
                    try:
                        margin_dict[ticker] = float(val_raw)
                    except:
                        continue
        return margin_dict
    except Exception as e:
        # Se fallisce lo scraping, mostriamo l'errore tecnico
        st.error(f"Errore tecnico nella lettura IBKR: {e}")
        return {}

st.markdown("# 📈 Analisi Equity & Margini LIVE")

# Esecuzione scraping
url_ibkr = "https://www.interactivebrokers.com/en/trading/margin-futures-fops.php"
with st.spinner('Connessione a Interactive Brokers in corso...'):
    live_margins = get_ibkr_margins(url_ibkr)

if live_margins:
    st.success(f"✅ Collegamento stabilito: {len(live_margins)} margini aggiornati rilevati.")
else:
    st.error("❌ Impossibile leggere i dati. Verifica il file requirements.txt o la connessione.")

# --- CARICAMENTO E LOGICA APP (Invariata) ---
uploaded_files = st.file_uploader("Carica i file TXT da Titan", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = []
    
    # Funzione interna per caricamento
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
        st.sidebar.header("💰 Analisi Margini Live")
        margine_totale = 0
        
        st.write("### 🛠️ Strategie Caricate")
        selected_names = []
        cols = st.columns(min(len(raw_data), 4))
        
        for i, name in enumerate(sorted(raw_data.keys())):
            m_val = 0
            # Matching ticker: cerchiamo la chiave del margine nel nome del file
            for t in live_margins:
                if t in name.upper():
                    m_val = live_margins[t]
                    break
            
            with cols[i % 4]:
                if st.checkbox(f"{name} (${m_val:,.0f})", value=True, key=name):
                    selected_names.append(name)
                    margine_totale += m_val

        if selected_names:
            st.sidebar.metric("Margine Impegnato", f"${margine_totale:,.2f}")
            
            # --- CREAZIONE DF PORTAFOGLIO ---
            dates_set = sorted(list(set(all_dates)))
            df_port = pd.DataFrame({'date': dates_set})
            for name in selected_names:
                df_port = df_port.merge(raw_data[name][['date', 'pnl']].rename(columns={'pnl': name + '_pnl'}), on='date', how='left')
            df_port.fillna(0, inplace=True)
            
            # Filtro temporale
            start_d = st.sidebar.date_input("Inizio", min(all_dates).date())
            end_d = st.sidebar.date_input("Fine", max(all_dates).date())
            mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
            df_plot = df_port[mask].copy()

            for n in selected_names:
                df_plot[n] = df_plot[n + '_pnl'].cumsum()
            
            df_plot['TOTALE'] = df_plot[selected_names].sum(axis=1)
            df_plot['DD'] = df_plot['TOTALE'] - df_plot['TOTALE'].cummax()

            # Grafico
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['TOTALE'], name='PORTAFOGLIO', line=dict(color='black', width=3)), row=1, col=1)
            for n in selected_names:
                fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[n], name=n, line=dict(width=1), opacity=0.3), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['DD'], name='Drawdown', fill='tozeroy', line=dict(color='red')), row=2, col=1)
            fig.update_layout(plot_bgcolor='white', height=700, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            # Performance Table
            st.write("### 📊 Tabella Rendimenti e ROE")
            df_plot['Year'] = df_plot['date'].dt.year
            res = df_plot.groupby('Year')[[n + '_pnl' for n in selected_names]].sum().round(0)
            res['PnL TOTALE'] = res.sum(axis=1)
            if margine_totale > 0:
                res['ROE %'] = (res['PnL TOTALE'] / margine_totale * 100).round(2)
            
            st.dataframe(res.style.format("{:,.2f}"), use_container_width=True)
